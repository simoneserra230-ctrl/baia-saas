"""
BA.IA — Notifiche in-app v1.0
Sistema di notifiche per eventi interni: scadenze, messaggi portale, aggiornamenti bandi.
"""

import os, json, datetime
import aiosqlite
from fastapi import Request
from fastapi.responses import JSONResponse

DB = lambda: os.environ.get("DB_PATH", "./data/ai-bandi.db")


# ── INIT ─────────────────────────────────────────────────
async def init_notifications_db():
    async with aiosqlite.connect(DB()) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS notifications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                type TEXT NOT NULL,
                title TEXT NOT NULL,
                body TEXT,
                link TEXT,
                read INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            )""")
        await db.execute("CREATE INDEX IF NOT EXISTS ix_notif_user ON notifications(user_id, read)")
        await db.commit()
    print("[NOTIF] Tabella notifiche pronta")


# ── HELPER: crea notifica ────────────────────────────────
async def push_notification(
    user_id: str,
    type: str,
    title: str,
    body: str = "",
    link: str = "",
):
    """Inserisce una notifica per un utente. Non-blocking."""
    try:
        async with aiosqlite.connect(DB()) as db:
            await db.execute(
                "INSERT INTO notifications (user_id,type,title,body,link) VALUES (?,?,?,?,?)",
                (user_id, type, title, body, link)
            )
            await db.commit()
    except Exception as e:
        print(f"[NOTIF] Errore push: {e}")


# ── PULIZIA AUTOMATICA: elimina notifiche > 90 giorni ────
async def cleanup_old_notifications():
    try:
        async with aiosqlite.connect(DB()) as db:
            await db.execute(
                "DELETE FROM notifications WHERE created_at < datetime('now','-90 days')"
            )
            await db.commit()
    except Exception:
        pass


# ── SCHEDULER: controlla scadenze bandi ogni mattina ─────
async def check_bandi_scadenze():
    """
    Crea notifiche per i bandi in scadenza nei prossimi 7/30 giorni.
    Chiamato dallo scheduler APScheduler al boot.
    """
    try:
        today = datetime.date.today()
        async with aiosqlite.connect(DB()) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT DISTINCT b.id, b.data, s.user_id FROM bandi b "
                "JOIN sessions s ON 1=1 "
                "WHERE b.deleted_at IS NULL LIMIT 200"
            ) as c:
                rows = await c.fetchall()

        for row in rows:
            try:
                data = json.loads(row["data"])
                scad_str = data.get("scadenza")
                if not scad_str:
                    continue
                scad = datetime.date.fromisoformat(scad_str)
                giorni = (scad - today).days

                if giorni in (30, 7, 3, 1):
                    # Ottieni utenti autenticati (tutti, semplificato)
                    async with aiosqlite.connect(DB()) as db2:
                        db2.row_factory = aiosqlite.Row
                        async with db2.execute(
                            "SELECT DISTINCT user_id FROM sessions WHERE expires_at > datetime('now')"
                        ) as c2:
                            users = await c2.fetchall()

                    for u in users:
                        urgency = "🔴" if giorni <= 3 else "🟡" if giorni <= 7 else "🔵"
                        await push_notification(
                            user_id=u["user_id"],
                            type="scadenza_bando",
                            title=f"{urgency} Scadenza bando tra {giorni} giorni",
                            body=data.get("name", "Bando senza nome"),
                            link=f"/bando/{row['id']}",
                        )
            except Exception:
                pass
    except Exception as e:
        print(f"[NOTIF] Errore check scadenze: {e}")


# ── ENDPOINTS ────────────────────────────────────────────
def register_notification_endpoints(app):
    from main import require_auth
    from fastapi import Depends

    @app.get("/notifications")
    async def get_notifications(
        unread_only: bool = False,
        limit: int = 50,
        current_user: dict = Depends(require_auth),
    ):
        """Legge le notifiche dell'utente corrente."""
        async with aiosqlite.connect(DB()) as db:
            db.row_factory = aiosqlite.Row
            where = "WHERE user_id=?"
            params = [current_user["id"]]
            if unread_only:
                where += " AND read=0"
            async with db.execute(
                f"SELECT * FROM notifications {where} ORDER BY created_at DESC LIMIT ?",
                params + [min(limit, 200)]
            ) as c:
                rows = [dict(r) for r in await c.fetchall()]
            async with db.execute(
                "SELECT COUNT(*) FROM notifications WHERE user_id=? AND read=0",
                (current_user["id"],)
            ) as c:
                unread_count = (await c.fetchone())[0]

        return {"ok": True, "notifications": rows, "unread": unread_count}

    @app.post("/notifications/read")
    async def mark_notifications_read(
        request: Request,
        current_user: dict = Depends(require_auth),
    ):
        """Marca notifiche come lette. Body: {"ids": [1,2,3]} oppure {} per tutte."""
        body = await request.json()
        ids  = body.get("ids")
        async with aiosqlite.connect(DB()) as db:
            if ids:
                placeholders = ",".join("?" * len(ids))
                await db.execute(
                    f"UPDATE notifications SET read=1 WHERE user_id=? AND id IN ({placeholders})",
                    [current_user["id"]] + ids
                )
            else:
                await db.execute(
                    "UPDATE notifications SET read=1 WHERE user_id=?",
                    (current_user["id"],)
                )
            await db.commit()
        return {"ok": True}

    @app.delete("/notifications/{notif_id}")
    async def delete_notification(notif_id: int, current_user: dict = Depends(require_auth)):
        async with aiosqlite.connect(DB()) as db:
            await db.execute(
                "DELETE FROM notifications WHERE id=? AND user_id=?",
                (notif_id, current_user["id"])
            )
            await db.commit()
        return {"ok": True}
