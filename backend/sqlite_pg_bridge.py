"""
Bridge aiosqlite → PostgreSQL.

Se DATABASE_URL è settata, sostituisce aiosqlite.connect con una versione
che usa asyncpg sotto e traduce SQLite → PostgreSQL al volo.

Questo permette al codice esistente (che usa aiosqlite) di funzionare
trasparentemente con Supabase/PostgreSQL senza modifiche.
"""
import os
import re
import json
import asyncio
from contextlib import asynccontextmanager

DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://"):]

USE_PG = bool(DATABASE_URL) and DATABASE_URL.startswith("postgresql://")

if USE_PG:
    # Strip query params che asyncpg non gestisce
    if "?" in DATABASE_URL:
        DATABASE_URL = DATABASE_URL.split("?")[0]


def _q(sql):
    """Converte query SQLite → PostgreSQL."""
    out = sql
    # ? placeholder → $1, $2, ...
    if "?" in out:
        parts = out.split("?")
        new = [parts[0]]
        for i, p in enumerate(parts[1:], 1):
            new.append(f"${i}{p}")
        out = "".join(new)
    # Tipi
    out = out.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
    out = out.replace("AUTOINCREMENT", "")
    # Date — cast to text so TEXT DEFAULT CURRENT_TIMESTAMP::text is valid in PG
    out = out.replace("datetime('now')", "CURRENT_TIMESTAMP::text")
    # JSON_EXTRACT → ->>
    out = re.sub(
        r"JSON_EXTRACT\(\s*(\w+(?:\.\w+)?)\s*,\s*['\"]\$\.(\w+)['\"]\s*\)",
        r"(\1::jsonb->>'\2')", out
    )
    # ALTER TABLE ADD COLUMN — Pg richiede "IF NOT EXISTS"
    out = re.sub(
        r"ALTER TABLE (\w+) ADD COLUMN (\w+) ",
        r"ALTER TABLE \1 ADD COLUMN IF NOT EXISTS \2 ",
        out
    )
    return out


_pool = None
_pool_lock = asyncio.Lock()


def _parse_pg_url(url: str) -> dict:
    """Parse postgresql:// URL into asyncpg keyword args."""
    import urllib.parse as _up
    p = _up.urlparse(url)
    return dict(
        host=p.hostname or "localhost",
        port=p.port or 5432,
        user=p.username,
        password=_up.unquote(p.password or ""),
        database=(p.path or "/postgres").lstrip("/"),
    )


async def _get_pool():
    global _pool
    if _pool is not None:
        return _pool
    async with _pool_lock:
        if _pool is None:
            import asyncpg
            params = _parse_pg_url(DATABASE_URL)
            _pool = await asyncpg.create_pool(
                **params,
                min_size=1, max_size=10,
                command_timeout=30,
                statement_cache_size=0,
                ssl=True,
            )
            print("[DB] Pool PostgreSQL inizializzato")
    return _pool


class FakeRow(dict):
    """Riga dict-compatibile con accesso per indice."""
    def __init__(self, data):
        super().__init__(data)
        self._keys = list(data.keys())

    def __getitem__(self, key):
        if isinstance(key, int):
            return super().__getitem__(self._keys[key]) if key < len(self._keys) else None
        return super().__getitem__(key)

    def keys(self):
        return self._keys


class _Cursor:
    """Cursore compatibile aiosqlite."""
    def __init__(self, conn, sql, params):
        self.conn = conn
        self.sql = _q(sql)
        self.params = params
        self.lastrowid = None
        self._rows = None

    # Support: await db.execute("CREATE TABLE ...") / await db.execute("INSERT ...")
    def __await__(self):
        return self._run_dml().__await__()

    async def _run_dml(self):
        try:
            await self.conn.execute(self.sql, *self.params)
        except Exception as e:
            # Ignore "already exists" from CREATE TABLE IF NOT EXISTS edge cases
            if "already exists" not in str(e).lower():
                raise
        return self

    async def _fetch(self):
        if self._rows is None:
            try:
                rows = await self.conn.fetch(self.sql, *self.params)
                self._rows = [FakeRow(dict(r)) for r in rows]
            except Exception as e:
                msg = str(e).lower()
                if "no results to fetch" in msg or "does not return" in msg:
                    await self.conn.execute(self.sql, *self.params)
                    self._rows = []
                else:
                    raise

    async def fetchone(self):
        await self._fetch()
        return self._rows[0] if self._rows else None

    async def fetchall(self):
        await self._fetch()
        return self._rows

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class _ConnWrapper:
    """Wrapper che fa sembrare asyncpg come aiosqlite."""
    def __init__(self, conn, pool):
        self._conn = conn
        self._pool = pool
        self.row_factory = None  # ignorato — sempre dict-like

    def execute(self, sql, params=None):
        return _Cursor(self._conn, sql, params or ())

    async def executescript(self, sql):
        # Esegue script multi-statement
        for stmt in sql.split(";"):
            stmt = stmt.strip()
            if stmt:
                try:
                    await self._conn.execute(_q(stmt))
                except Exception as e:
                    print(f"[DB] script warn: {e}")

    async def commit(self):
        pass  # asyncpg autocommit

    async def close(self):
        await self._pool.release(self._conn)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()


@asynccontextmanager
async def _pg_connect(db_path=None):
    """Drop-in replacement per aiosqlite.connect."""
    pool = await _get_pool()
    conn = await pool.acquire()
    wrapper = _ConnWrapper(conn, pool)
    try:
        yield wrapper
    finally:
        await pool.release(conn)


def install():
    """Monkey-patch aiosqlite.connect."""
    if not USE_PG:
        return False

    import aiosqlite
    aiosqlite.connect = _pg_connect

    # Patch Row in modo che dict(row) e row[key] funzionino come ci si aspetta
    class CompatRow(dict):
        def __init__(self, data):
            super().__init__(data if isinstance(data, dict) else {})

    aiosqlite.Row = CompatRow
    print(f"[DB] Bridge aiosqlite → PostgreSQL attivato")
    return True
