"""
BA.IA — Audit Log GDPR v1.0
Registra ogni accesso/modifica ai dati personali e sensibili.
Obbligatorio per compliance GDPR Art. 30 (registro trattamenti).
"""

import os, json, datetime
import aiosqlite
from fastapi import Request

DB = lambda: os.environ.get("DB_PATH", "./data/ai-bandi.db")

# ── INIT ─────────────────────────────────────────────────
async def init_audit_db():
    async with aiosqlite.connect(DB()) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts TEXT NOT NULL DEFAULT (datetime('now')),
                user_id TEXT,
                user_email TEXT,
                action TEXT NOT NULL,
                resource_type TEXT,
                resource_id TEXT,
                ip TEXT,
                details TEXT
            )""")
        await db.execute("CREATE INDEX IF NOT EXISTS ix_audit_ts ON audit_log(ts)")
        await db.execute("CREATE INDEX IF NOT EXISTS ix_audit_user ON audit_log(user_id)")
        await db.commit()
    print("[AUDIT] Tabella audit_log pronta")

# ── LOG ───────────────────────────────────────────────────
async def log_action(
    action: str,
    user_id: str = None,
    user_email: str = None,
    resource_type: str = None,
    resource_id: str = None,
    ip: str = None,
    details: dict = None,
):
    """Scrive un record nel registro audit. Non-blocking — gli errori vengono ignorati."""
    try:
        async with aiosqlite.connect(DB()) as db:
            await db.execute(
                "INSERT INTO audit_log (ts,user_id,user_email,action,resource_type,resource_id,ip,details) "
                "VALUES (datetime('now'),?,?,?,?,?,?,?)",
                (
                    user_id, user_email, action, resource_type, resource_id, ip,
                    json.dumps(details) if details else None,
                )
            )
            await db.commit()
    except Exception as e:
        print(f"[AUDIT] Errore scrittura log: {e}")

def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"

# ── ENDPOINT LETTURA LOG (solo admin) ────────────────────
def register_audit_endpoints(app):
    from fastapi import Depends, HTTPException
    from main import require_auth

    @app.get("/admin/audit-log")
    async def get_audit_log(
        limit: int = 100,
        offset: int = 0,
        action: str = None,
        user_id: str = None,
        current_user: dict = Depends(require_auth),
    ):
        """Legge il registro audit. Solo consulenti/admin."""
        # In futuro: check role == 'consulente' o 'admin'
        async with aiosqlite.connect(DB()) as db:
            db.row_factory = aiosqlite.Row
            where = "WHERE 1=1"
            params = []
            if action:
                where += " AND action=?"; params.append(action)
            if user_id:
                where += " AND user_id=?"; params.append(user_id)
            params += [min(limit, 500), offset]
            async with db.execute(
                f"SELECT * FROM audit_log {where} ORDER BY ts DESC LIMIT ? OFFSET ?",
                params
            ) as c:
                rows = await c.fetchall()
            async with db.execute(f"SELECT COUNT(*) FROM audit_log {where}", params[:-2]) as c:
                total = (await c.fetchone())[0]
        return {
            "total": total, "limit": limit, "offset": offset,
            "logs": [dict(r) for r in rows]
        }
