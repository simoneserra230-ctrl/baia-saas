"""
BA.IA — Database abstraction layer
Supporta SQLite (locale) e PostgreSQL/Supabase (cloud) con la stessa API.

In locale: usa aiosqlite con DB_PATH=./data/ai-bandi.db
In cloud:  usa asyncpg con DATABASE_URL=postgresql://...

Detection automatica: se DATABASE_URL è settata, usa PostgreSQL.
"""
import os
import json
import datetime
from contextlib import asynccontextmanager
from typing import Optional, Any, AsyncIterator

# ── Detection mode ────────────────────────────────────────
DATABASE_URL = os.environ.get("DATABASE_URL", "").strip()
USE_POSTGRES = bool(DATABASE_URL) and DATABASE_URL.startswith(("postgres://", "postgresql://"))

# Normalize Heroku-style postgres:// → postgresql://
if USE_POSTGRES and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = "postgresql://" + DATABASE_URL[len("postgres://"):]
    os.environ["DATABASE_URL"] = DATABASE_URL

# Full URL preservata con sslmode — passata direttamente ad asyncpg
_DATABASE_URL_FULL = DATABASE_URL
# Supabase pooler URL fix per asyncpgh
if USE_POSTGRES and "?" in DATABASE_URL:
    DATABASE_URL = DATABASE_URL.split("?")[0]

_pool = None  # asyncpg pool


async def init_pool():
    """Inizializza connection pool PostgreSQL (chiamata 1 volta a startup)."""
    global _pool
    if not USE_POSTGRES:
        return
    if _pool is not None:
        return
    import asyncpg
    _pool = await asyncpg.create_pool(
                _DATABASE_URL_FULL,
        min_size=1,
        max_size=10,
        command_timeout=30,
        statement_cache_size=0,  # richiesto per Supabase pooler PgBouncer
    )
    print(f"[DB] PostgreSQL pool pronto ({DATABASE_URL.split('@')[-1][:40]}...)")


async def close_pool():
    global _pool
    if _pool:
        await _pool.close()
        _pool = None


# ── Conversioni SQLite → PostgreSQL ──────────────────────
def _convert_query(sql: str) -> str:
    """Converte sintassi SQLite in PostgreSQL al volo."""
    if not USE_POSTGRES:
        return sql
    out = sql

    # ? placeholder → $1, $2, ...
    if "?" in out:
        parts = out.split("?")
        new_parts = [parts[0]]
        for i, p in enumerate(parts[1:], start=1):
            new_parts.append(f"${i}{p}")
        out = "".join(new_parts)

    # AUTOINCREMENT → SERIAL/IDENTITY
    out = out.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "SERIAL PRIMARY KEY")
    out = out.replace("AUTOINCREMENT", "")

    # Tipi
    out = out.replace("INTEGER", "INTEGER")  # ok
    # datetime('now') → CURRENT_TIMESTAMP
    out = out.replace("datetime('now')", "CURRENT_TIMESTAMP")
    out = out.replace("DEFAULT (datetime('now'))", "DEFAULT CURRENT_TIMESTAMP")

    # IFNULL → COALESCE (già supportato in Pg)
    # JSON_EXTRACT(col,'$.key') → (col::jsonb->>'key')
    import re
    out = re.sub(
        r"JSON_EXTRACT\(\s*(\w+)\s*,\s*['\"]\$\.(\w+)['\"]\s*\)",
        r"(\1::jsonb->>'\2')",
        out
    )

    # ON CONFLICT(col) → ON CONFLICT (col)
    out = re.sub(r"ON CONFLICT\((\w+)\)", r"ON CONFLICT (\1)", out)

    # excluded.col funziona già in PG
    return out


class Row:
    """Wrapper riga che funziona come dict e tuple."""
    def __init__(self, row):
        if hasattr(row, "keys"):  # asyncpg.Record o sqlite Row
            self._data = dict(row)
        elif isinstance(row, dict):
            self._data = row
        else:
            self._data = {}

    def __getitem__(self, key):
        if isinstance(key, int):
            keys = list(self._data.keys())
            return self._data[keys[key]] if key < len(keys) else None
        return self._data.get(key)

    def __contains__(self, key):
        return key in self._data

    def get(self, key, default=None):
        return self._data.get(key, default)

    def keys(self):
        return self._data.keys()

    def items(self):
        return self._data.items()


class CursorWrapper:
    """Cursore unificato che supporta sia sqlite che asyncpg."""
    def __init__(self, rows):
        self._rows = rows

    async def fetchone(self):
        return Row(self._rows[0]) if self._rows else None

    async def fetchall(self):
        return [Row(r) for r in self._rows]

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


class DBConnection:
    """Connessione unificata SQLite/PostgreSQL."""
    def __init__(self):
        self.row_factory = None
        self._conn = None
        self._tx = None  # transazione PG

    @asynccontextmanager
    async def execute(self, sql: str, params: tuple = ()) -> AsyncIterator[CursorWrapper]:
        """Esegue una query e ritorna un cursore wrapper."""
        if USE_POSTGRES:
            converted = _convert_query(sql)
            # asyncpg non supporta multiple statements in fetch
            try:
                rows = await self._conn.fetch(converted, *params)
            except Exception as e:
                # Se è un INSERT/UPDATE/DELETE senza RETURNING, fetch ritorna vuoto
                msg = str(e)
                if "no results to fetch" in msg.lower() or "does not return" in msg.lower():
                    await self._conn.execute(converted, *params)
                    rows = []
                else:
                    raise
            cur = CursorWrapper(rows)
        else:
            async with self._conn.execute(sql, params) as raw_cur:
                rows = await raw_cur.fetchall()
                cur = CursorWrapper(rows)
        yield cur

    async def execute_simple(self, sql: str, params: tuple = ()):
        """Esegue una query senza ritornare risultati."""
        if USE_POSTGRES:
            converted = _convert_query(sql)
            try:
                await self._conn.execute(converted, *params)
            except Exception:
                raise
        else:
            await self._conn.execute(sql, params)

    async def commit(self):
        if not USE_POSTGRES:
            await self._conn.commit()
        # In PG, autocommit gestito dal pool

    async def close(self):
        if USE_POSTGRES:
            await _pool.release(self._conn)
        else:
            await self._conn.close()


@asynccontextmanager
async def connect(db_path: Optional[str] = None) -> AsyncIterator[DBConnection]:
    """
    Apre una connessione al database.

    Uso:
        async with db.connect() as conn:
            async with conn.execute("SELECT * FROM users") as cur:
                rows = await cur.fetchall()
            await conn.commit()
    """
    conn = DBConnection()
    if USE_POSTGRES:
        if _pool is None:
            await init_pool()
        conn._conn = await _pool.acquire()
        try:
            yield conn
        finally:
            await _pool.release(conn._conn)
    else:
        import aiosqlite
        path = db_path or os.environ.get("DB_PATH", "./data/ai-bandi.db")
        conn._conn = await aiosqlite.connect(path)
        conn._conn.row_factory = aiosqlite.Row
        try:
            yield conn
        finally:
            await conn._conn.close()


# ── Schema initialization (idempotente) ──────────────────
async def init_schema():
    """Crea tutte le tabelle se mancano (compatibile Pg + SQLite)."""
    schemas = []

    if USE_POSTGRES:
        # PostgreSQL schemas
        schemas = [
            """CREATE TABLE IF NOT EXISTS bandi (
                id TEXT PRIMARY KEY,
                data JSONB NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
            """CREATE TABLE IF NOT EXISTS aziende (
                id TEXT PRIMARY KEY,
                data JSONB NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
            """CREATE TABLE IF NOT EXISTS sal (
                id TEXT PRIMARY KEY,
                bando_id TEXT,
                data JSONB NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
            """CREATE TABLE IF NOT EXISTS history (
                id TEXT PRIMARY KEY,
                data JSONB NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
            """CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'consulente',
                invited_by TEXT,
                invite_token TEXT,
                invite_used INTEGER DEFAULT 0,
                company TEXT,
                phone TEXT,
                notes TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
            """CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                expires_at TIMESTAMP NOT NULL
            )""",
            """CREATE TABLE IF NOT EXISTS portal_shares (
                id TEXT PRIMARY KEY,
                consulente_id TEXT NOT NULL,
                cliente_id TEXT NOT NULL,
                resource_type TEXT NOT NULL,
                resource_id TEXT NOT NULL,
                permissions TEXT DEFAULT 'view',
                label TEXT,
                note TEXT,
                visible INTEGER DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
            """CREATE TABLE IF NOT EXISTS portal_messages (
                id TEXT PRIMARY KEY,
                share_id TEXT NOT NULL,
                author_id TEXT NOT NULL,
                author_role TEXT NOT NULL,
                author_name TEXT NOT NULL,
                text TEXT NOT NULL,
                read_by_cliente INTEGER DEFAULT 0,
                read_by_consulente INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
            """CREATE TABLE IF NOT EXISTS portal_docs (
                id TEXT PRIMARY KEY,
                share_id TEXT NOT NULL,
                uploaded_by TEXT NOT NULL,
                filename TEXT NOT NULL,
                size_bytes INTEGER DEFAULT 0,
                description TEXT,
                storage_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
            """CREATE TABLE IF NOT EXISTS rendicontazioni (
                id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                sal_id TEXT,
                bando_id TEXT,
                azienda_id TEXT,
                titolo TEXT NOT NULL,
                importo_approvato REAL DEFAULT 0,
                importo_rendicontato REAL DEFAULT 0,
                data_approvazione TEXT,
                data_scadenza_sal TEXT,
                tipo_sal TEXT DEFAULT 'unico',
                stato TEXT DEFAULT 'aperta',
                ente_erogatore TEXT,
                portale_ente TEXT,
                note TEXT,
                config TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
            """CREATE TABLE IF NOT EXISTS rendicontazione_milestones (
                id TEXT PRIMARY KEY,
                rendicontazione_id TEXT NOT NULL,
                titolo TEXT NOT NULL,
                descrizione TEXT,
                scadenza TEXT,
                ordine INTEGER DEFAULT 0,
                stato TEXT DEFAULT 'pending',
                importo_atteso REAL DEFAULT 0,
                importo_rendicontato REAL DEFAULT 0,
                completata_il TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
            """CREATE TABLE IF NOT EXISTS rendicontazione_documenti (
                id TEXT PRIMARY KEY,
                rendicontazione_id TEXT NOT NULL,
                milestone_id TEXT,
                tipo TEXT NOT NULL,
                titolo TEXT NOT NULL,
                fornitore TEXT,
                numero_documento TEXT,
                data_documento TEXT,
                importo_imponibile REAL DEFAULT 0,
                importo_iva REAL DEFAULT 0,
                importo_totale REAL DEFAULT 0,
                importo_ammissibile REAL DEFAULT 0,
                filename TEXT,
                size_bytes INTEGER DEFAULT 0,
                spesa_categoria TEXT,
                modalita_pagamento TEXT,
                pagato INTEGER DEFAULT 0,
                data_pagamento TEXT,
                note TEXT,
                ai_extracted INTEGER DEFAULT 0,
                ai_confidence TEXT,
                storage_url TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
            """CREATE TABLE IF NOT EXISTS rendicontazione_checklist (
                id TEXT PRIMARY KEY,
                rendicontazione_id TEXT NOT NULL,
                testo TEXT NOT NULL,
                obbligatorio INTEGER DEFAULT 1,
                completato INTEGER DEFAULT 0,
                ordine INTEGER DEFAULT 0,
                note TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
            """CREATE TABLE IF NOT EXISTS scraper_log (
                source_id TEXT PRIMARY KEY,
                last_hash TEXT,
                last_run TIMESTAMP,
                total_new INTEGER DEFAULT 0
            )""",
            "CREATE INDEX IF NOT EXISTS idx_bandi_updated ON bandi(updated_at DESC)",
            "CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id)",
            "CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at)",
            "CREATE INDEX IF NOT EXISTS idx_users_email ON users(email)",
            "CREATE INDEX IF NOT EXISTS idx_users_invited ON users(invited_by)",
            "CREATE INDEX IF NOT EXISTS idx_shares_consulente ON portal_shares(consulente_id)",
            "CREATE INDEX IF NOT EXISTS idx_shares_cliente ON portal_shares(cliente_id)",
            "CREATE INDEX IF NOT EXISTS idx_messages_share ON portal_messages(share_id)",
            "CREATE INDEX IF NOT EXISTS idx_rendicont_user ON rendicontazioni(user_id)",
        ]

    if USE_POSTGRES:
        await init_pool()
        async with _pool.acquire() as conn:
            for sql in schemas:
                try:
                    await conn.execute(sql)
                except Exception as e:
                    print(f"[DB] Schema warning: {e}")
        print("[DB] Schema PostgreSQL pronto")


# ── JSON helpers ──────────────────────────────────────────
def loads_data(value: Any) -> dict:
    """asyncpg ritorna jsonb come dict, sqlite come stringa."""
    if value is None:
        return {}
    if isinstance(value, (dict, list)):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return {}
    return {}


def dumps_data(value: Any) -> str:
    """Serializza per insert SQL."""
    if isinstance(value, str):
        return value
    return json.dumps(value, default=str, ensure_ascii=False)
