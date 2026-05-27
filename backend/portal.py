"""
BA.IA — Client Portal v1.1
Workspace condiviso Consulente ↔ Cliente.

v1.1: sicurezza — bcrypt, path traversal fix, file validation, email validation, size limit.
"""

import os, json, uuid, datetime, secrets
from pathlib import Path
import aiosqlite
from fastapi import Request, UploadFile, File
from fastapi.responses import JSONResponse

from security import (
    hash_password, verify_password, validate_email,
    is_valid_pdf_bytes, sanitize_filename, MAX_UPLOAD_BYTES
)

async def _push_notif(user_id, type_, title, body="", link=""):
    """Wrapper non-bloccante per notifiche in-app."""
    try:
        from notifications import push_notification
        await push_notification(user_id, type_, title, body, link)
    except Exception:
        pass

DB = lambda: os.environ.get("DB_PATH", "./data/ai-bandi.db")

# ── INIT DB ───────────────────────────────────────────────
async def init_portal_db():
    async with aiosqlite.connect(DB()) as db:
        for col in ("role TEXT DEFAULT 'consulente'", "invited_by TEXT",
                    "invite_token TEXT", "invite_used INTEGER DEFAULT 0",
                    "company TEXT", "phone TEXT", "notes TEXT"):
            try:
                await db.execute(f"ALTER TABLE users ADD COLUMN {col}")
            except Exception:
                pass

        await db.execute("""
            CREATE TABLE IF NOT EXISTS portal_shares (
                id TEXT PRIMARY KEY,
                consulente_id TEXT NOT NULL,
                cliente_id TEXT NOT NULL,
                resource_type TEXT NOT NULL,
                resource_id TEXT NOT NULL,
                permissions TEXT DEFAULT 'view',
                label TEXT,
                note TEXT,
                visible INTEGER DEFAULT 1,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now'))
            )""")

        await db.execute("""
            CREATE TABLE IF NOT EXISTS portal_messages (
                id TEXT PRIMARY KEY,
                share_id TEXT NOT NULL,
                author_id TEXT NOT NULL,
                author_role TEXT NOT NULL,
                author_name TEXT NOT NULL,
                text TEXT NOT NULL,
                read_by_cliente INTEGER DEFAULT 0,
                read_by_consulente INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now'))
            )""")

        await db.execute("""
            CREATE TABLE IF NOT EXISTS portal_docs (
                id TEXT PRIMARY KEY,
                share_id TEXT NOT NULL,
                uploaded_by TEXT NOT NULL,
                filename TEXT NOT NULL,
                safe_filename TEXT,
                size_bytes INTEGER DEFAULT 0,
                description TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )""")

        # safe_filename su tabelle esistenti
        try:
            await db.execute("ALTER TABLE portal_docs ADD COLUMN safe_filename TEXT")
        except Exception:
            pass

        await db.commit()
    print("[PORTAL] Tabelle portale clienti pronte")

# ── HELPERS ───────────────────────────────────────────────
def _uid(): return secrets.token_hex(10)
def _now(): return datetime.datetime.utcnow().isoformat()
def _invite_token(): return secrets.token_urlsafe(32)

async def _resolve_token(request: Request) -> dict | None:
    token = request.headers.get("X-Auth-Token") or request.cookies.get("baia_token")
    if not token:
        return None
    async with aiosqlite.connect(DB()) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT u.* FROM users u JOIN sessions s ON s.user_id=u.id "
            "WHERE s.token=? AND s.expires_at>datetime('now')", (token,)
        ) as c:
            row = await c.fetchone()
    return dict(row) if row else None

# ══════════════════════════════════════════════════════════
# ENDPOINT FACTORIES
# ══════════════════════════════════════════════════════════

def register_portal_endpoints(app):

    # ── Invita cliente ─────────────────────────────────────
    @app.post("/portal/invite")
    async def portal_invite(request: Request):
        user = await _resolve_token(request)
        if not user:
            return JSONResponse({"ok": False, "error": "Non autenticato"}, status_code=401)

        body = await request.json()
        name    = (body.get("name") or "").strip()
        email   = (body.get("email") or "").strip().lower()
        company = (body.get("company") or "").strip()
        note    = (body.get("note") or "").strip()

        if not name or not email:
            return JSONResponse({"ok": False, "error": "Nome e email obbligatori"}, status_code=400)
        if not validate_email(email):
            return JSONResponse({"ok": False, "error": "Formato email non valido"}, status_code=400)

        token    = _invite_token()
        client_id = _uid()
        # Password temporanea sicura (12 chars hex)
        tmp_pwd  = secrets.token_hex(6)
        pwd_hash = hash_password(tmp_pwd)

        async with aiosqlite.connect(DB()) as db:
            async with db.execute("SELECT id FROM users WHERE email=?", (email,)) as c:
                if await c.fetchone():
                    return JSONResponse({"ok": False, "error": "Email già registrata"}, status_code=400)

            await db.execute(
                "INSERT INTO users (id,name,email,password_hash,role,invited_by,"
                "invite_token,invite_used,company,notes) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (client_id, name, email, pwd_hash, "cliente",
                 user["id"], token, 0, company, note)
            )
            await db.commit()

        base_url   = str(request.base_url).rstrip("/")
        portal_url = f"{base_url}/portal/activate?token={token}"

        return {
            "ok": True,
            "client_id": client_id,
            "invite_token": token,
            "portal_url": portal_url,
            "tmp_password": tmp_pwd,
            "message": f"Cliente {name} creato. Condividi il link portale."
        }

    # ── Attiva account cliente (primo accesso) ─────────────
    @app.post("/portal/activate")
    async def portal_activate(request: Request):
        body        = await request.json()
        token       = (body.get("token") or "").strip()
        new_password = (body.get("password") or "").strip()

        if not token or not new_password or len(new_password) < 8:
            return JSONResponse({"ok": False, "error": "Token e password (min 8 car) obbligatori"}, status_code=400)

        async with aiosqlite.connect(DB()) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute("SELECT * FROM users WHERE invite_token=?", (token,)) as c:
                row = await c.fetchone()
            if not row:
                return JSONResponse({"ok": False, "error": "Token non valido o già usato"}, status_code=400)
            if row["invite_used"]:
                return JSONResponse({"ok": False, "error": "Account già attivato — effettua il login"}, status_code=400)

            pwd_hash = hash_password(new_password)
            await db.execute(
                "UPDATE users SET password_hash=?,invite_used=1,invite_token=NULL WHERE id=?",
                (pwd_hash, row["id"])
            )
            await db.commit()

        return {"ok": True, "message": "Account attivato. Ora puoi accedere.", "email": row["email"]}

    # ── Lista clienti del consulente ───────────────────────
    @app.get("/portal/clients")
    async def portal_clients(request: Request):
        user = await _resolve_token(request)
        if not user:
            return JSONResponse({"ok": False, "error": "Non autenticato"}, status_code=401)

        async with aiosqlite.connect(DB()) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT id,name,email,company,notes,invite_used,created_at FROM users "
                "WHERE invited_by=? AND role='cliente' ORDER BY created_at DESC",
                (user["id"],)
            ) as c:
                rows = await c.fetchall()

            clients = []
            for r in rows:
                async with db.execute(
                    "SELECT COUNT(*) as n FROM portal_shares WHERE cliente_id=? AND visible=1",
                    (r["id"],)
                ) as c2:
                    share_count = (await c2.fetchone())["n"]
                async with db.execute(
                    "SELECT COUNT(*) as n FROM portal_messages pm "
                    "JOIN portal_shares ps ON pm.share_id=ps.id "
                    "WHERE ps.consulente_id=? AND pm.author_role='cliente' AND pm.read_by_consulente=0",
                    (user["id"],)
                ) as c3:
                    unread = (await c3.fetchone())["n"]
                clients.append({
                    **dict(r),
                    "shares": share_count,
                    "unread_messages": unread,
                    "activated": bool(r["invite_used"]),
                })

        return {"ok": True, "clients": clients}

    # ── Condividi risorsa con cliente ──────────────────────
    @app.post("/portal/share")
    async def portal_share(request: Request):
        user = await _resolve_token(request)
        if not user:
            return JSONResponse({"ok": False, "error": "Non autenticato"}, status_code=401)

        body = await request.json()
        cliente_id    = body.get("cliente_id", "")
        resource_type = body.get("resource_type", "bando")
        resource_id   = body.get("resource_id", "")
        permissions   = body.get("permissions", "view")
        label         = body.get("label", "")
        note          = body.get("note", "")

        if resource_type not in ("bando", "sal", "azienda"):
            return JSONResponse({"ok": False, "error": "Tipo risorsa non valido"}, status_code=400)
        if permissions not in ("view", "upload", "edit"):
            return JSONResponse({"ok": False, "error": "Permesso non valido"}, status_code=400)
        if not cliente_id or not resource_id:
            return JSONResponse({"ok": False, "error": "Dati mancanti"}, status_code=400)

        async with aiosqlite.connect(DB()) as db:
            # Il cliente deve essere invitato da questo consulente
            async with db.execute(
                "SELECT id FROM users WHERE id=? AND invited_by=? AND role='cliente'",
                (cliente_id, user["id"])
            ) as c:
                if not await c.fetchone():
                    return JSONResponse({"ok": False, "error": "Cliente non trovato"}, status_code=404)

            async with db.execute(
                "SELECT id FROM portal_shares WHERE consulente_id=? AND cliente_id=? "
                "AND resource_type=? AND resource_id=?",
                (user["id"], cliente_id, resource_type, resource_id)
            ) as c:
                existing = await c.fetchone()

            if existing:
                await db.execute(
                    "UPDATE portal_shares SET permissions=?,label=?,note=?,visible=1,updated_at=? WHERE id=?",
                    (permissions, label, note, _now(), existing[0])
                )
                share_id = existing[0]
            else:
                share_id = _uid()
                await db.execute(
                    "INSERT INTO portal_shares (id,consulente_id,cliente_id,resource_type,"
                    "resource_id,permissions,label,note) VALUES (?,?,?,?,?,?,?,?)",
                    (share_id, user["id"], cliente_id, resource_type, resource_id,
                     permissions, label, note)
                )
            await db.commit()

        return {"ok": True, "share_id": share_id}

    # ── Rimuovi condivisione ───────────────────────────────
    @app.delete("/portal/share/{share_id}")
    async def portal_unshare(share_id: str, request: Request):
        user = await _resolve_token(request)
        if not user:
            return JSONResponse({"ok": False, "error": "Non autenticato"}, status_code=401)
        async with aiosqlite.connect(DB()) as db:
            await db.execute(
                "UPDATE portal_shares SET visible=0 WHERE id=? AND consulente_id=?",
                (share_id, user["id"])
            )
            await db.commit()
        return {"ok": True}

    # ── Dashboard cliente ──────────────────────────────────
    @app.get("/portal/dashboard")
    async def portal_dashboard(request: Request):
        user = await _resolve_token(request)
        if not user:
            return JSONResponse({"ok": False, "error": "Non autenticato"}, status_code=401)
        if user.get("role") != "cliente":
            return JSONResponse({"ok": False, "error": "Accesso riservato ai clienti"}, status_code=403)

        async with aiosqlite.connect(DB()) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT ps.*, u.name as consulente_name, u.email as consulente_email "
                "FROM portal_shares ps JOIN users u ON u.id=ps.consulente_id "
                "WHERE ps.cliente_id=? AND ps.visible=1 ORDER BY ps.created_at DESC",
                (user["id"],)
            ) as c:
                shares = [dict(r) for r in await c.fetchall()]

        enriched = []
        for s in shares:
            resource = await _load_resource(s["resource_type"], s["resource_id"])
            msg_count, unread = await _get_message_counts(s["id"], user["id"])
            doc_count = await _get_doc_count(s["id"])
            enriched.append({
                **s, "resource": resource,
                "message_count": msg_count,
                "unread_messages": unread,
                "doc_count": doc_count,
            })

        return {
            "ok": True,
            "user": {"id": user["id"], "name": user["name"],
                     "email": user["email"], "role": "cliente"},
            "shares": enriched,
        }

    # ── Dettaglio pratica condivisa ────────────────────────
    @app.get("/portal/share/{share_id}/detail")
    async def portal_share_detail(share_id: str, request: Request):
        user = await _resolve_token(request)
        if not user:
            return JSONResponse({"ok": False, "error": "Non autenticato"}, status_code=401)

        async with aiosqlite.connect(DB()) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM portal_shares WHERE id=? AND visible=1 "
                "AND (consulente_id=? OR cliente_id=?)",
                (share_id, user["id"], user["id"])
            ) as c:
                share = await c.fetchone()
            if not share:
                return JSONResponse({"ok": False, "error": "Pratica non trovata"}, status_code=404)

            share = dict(share)

            async with db.execute(
                "SELECT * FROM portal_messages WHERE share_id=? ORDER BY created_at ASC",
                (share_id,)
            ) as c:
                messages = [dict(r) for r in await c.fetchall()]

            async with db.execute(
                "SELECT id,share_id,uploaded_by,filename,size_bytes,description,created_at "
                "FROM portal_docs WHERE share_id=? ORDER BY created_at DESC",
                (share_id,)
            ) as c:
                docs = [dict(r) for r in await c.fetchall()]

            if user.get("role") == "cliente":
                await db.execute(
                    "UPDATE portal_messages SET read_by_cliente=1 WHERE share_id=?",
                    (share_id,)
                )
            else:
                await db.execute(
                    "UPDATE portal_messages SET read_by_consulente=1 WHERE share_id=?",
                    (share_id,)
                )
            await db.commit()

        resource = await _load_resource(share["resource_type"], share["resource_id"])

        return {
            "ok": True, "share": share,
            "resource": resource, "messages": messages, "docs": docs,
        }

    # ── Invia messaggio ────────────────────────────────────
    @app.post("/portal/message")
    async def portal_send_message(request: Request):
        user = await _resolve_token(request)
        if not user:
            return JSONResponse({"ok": False, "error": "Non autenticato"}, status_code=401)

        body     = await request.json()
        share_id = body.get("share_id", "")
        text     = (body.get("text") or "").strip()
        if not share_id or not text:
            return JSONResponse({"ok": False, "error": "Dati mancanti"}, status_code=400)
        if len(text) > 10_000:
            return JSONResponse({"ok": False, "error": "Messaggio troppo lungo (max 10000 car)"}, status_code=400)

        role = user.get("role", "consulente")

        async with aiosqlite.connect(DB()) as db:
            async with db.execute(
                "SELECT id FROM portal_shares WHERE id=? AND visible=1 "
                "AND (consulente_id=? OR cliente_id=?)",
                (share_id, user["id"], user["id"])
            ) as c:
                if not await c.fetchone():
                    return JSONResponse({"ok": False, "error": "Non autorizzato"}, status_code=403)

            msg_id = _uid()
            await db.execute(
                "INSERT INTO portal_messages (id,share_id,author_id,author_role,author_name,text) "
                "VALUES (?,?,?,?,?,?)",
                (msg_id, share_id, user["id"], role, user["name"], text)
            )
            await db.commit()

        # Notifica in-app al destinatario
        async with aiosqlite.connect(DB()) as db2:
            db2.row_factory = aiosqlite.Row
            async with db2.execute("SELECT consulente_id, cliente_id FROM portal_shares WHERE id=?", (share_id,)) as c2:
                s = await c2.fetchone()
        if s:
            recipient = s["consulente_id"] if user["id"] == s["cliente_id"] else s["cliente_id"]
            await _push_notif(
                recipient, "portal_message",
                f"Nuovo messaggio da {user['name']}",
                text[:100], f"/portal/share/{share_id}"
            )

        return {"ok": True, "message_id": msg_id, "created_at": _now()}

    # ── Upload documento cliente ───────────────────────────
    @app.post("/portal/doc/upload")
    async def portal_doc_upload(request: Request, file: UploadFile = File(...)):
        user = await _resolve_token(request)
        if not user:
            return JSONResponse({"ok": False, "error": "Non autenticato"}, status_code=401)

        share_id    = request.query_params.get("share_id", "")
        description = request.query_params.get("description", "")[:500]

        async with aiosqlite.connect(DB()) as db:
            async with db.execute(
                "SELECT id, permissions FROM portal_shares WHERE id=? AND visible=1 "
                "AND (consulente_id=? OR cliente_id=?)",
                (share_id, user["id"], user["id"])
            ) as c:
                share = await c.fetchone()
            if not share:
                return JSONResponse({"ok": False, "error": "Non autorizzato"}, status_code=403)
            if user.get("role") == "cliente" and share[1] == "view":
                return JSONResponse({"ok": False, "error": "Solo visualizzazione — upload non permesso"}, status_code=403)

        # Leggi e valida file
        content = await file.read()
        size = len(content)

        if size > MAX_UPLOAD_BYTES:
            return JSONResponse({"ok": False, "error": f"File troppo grande (max {MAX_UPLOAD_BYTES // 1024 // 1024} MB)"}, status_code=400)
        if not file.filename.lower().endswith(".pdf"):
            return JSONResponse({"ok": False, "error": "Solo file PDF supportati"}, status_code=400)
        if not is_valid_pdf_bytes(content):
            return JSONResponse({"ok": False, "error": "Il file non è un PDF valido"}, status_code=400)

        # Salva con nome sicuro (no path traversal)
        doc_id    = _uid()
        safe_name = sanitize_filename(file.filename, doc_id)
        doc_dir   = Path(DB()).parent / "portal_docs" / share_id
        doc_dir.mkdir(parents=True, exist_ok=True)
        (doc_dir / safe_name).write_bytes(content)

        async with aiosqlite.connect(DB()) as db:
            await db.execute(
                "INSERT INTO portal_docs (id,share_id,uploaded_by,filename,safe_filename,size_bytes,description) "
                "VALUES (?,?,?,?,?,?,?)",
                (doc_id, share_id, user["id"], file.filename, safe_name, size, description)
            )
            await db.commit()

        return {"ok": True, "doc_id": doc_id, "filename": file.filename, "size": size}

    # ── Lista pratiche per un cliente (vista consulente) ───
    @app.get("/portal/client/{client_id}/shares")
    async def portal_client_shares(client_id: str, request: Request):
        user = await _resolve_token(request)
        if not user:
            return JSONResponse({"ok": False, "error": "Non autenticato"}, status_code=401)

        # Verifica che client_id appartenga al consulente corrente
        async with aiosqlite.connect(DB()) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT id FROM users WHERE id=? AND invited_by=? AND role='cliente'",
                (client_id, user["id"])
            ) as c:
                if not await c.fetchone():
                    return JSONResponse({"ok": False, "error": "Cliente non trovato"}, status_code=404)

            async with db.execute(
                "SELECT * FROM portal_shares WHERE consulente_id=? AND cliente_id=? "
                "ORDER BY created_at DESC",
                (user["id"], client_id)
            ) as c:
                rows = [dict(r) for r in await c.fetchall()]

        enriched = []
        for r in rows:
            res = await _load_resource(r["resource_type"], r["resource_id"])
            msg_c, unread = await _get_message_counts(r["id"], user["id"])
            enriched.append({**r, "resource": res, "message_count": msg_c, "unread": unread})

        return {"ok": True, "shares": enriched}

    # ── Update condivisione ────────────────────────────────
    @app.put("/portal/share/{share_id}")
    async def portal_update_share(share_id: str, request: Request):
        user = await _resolve_token(request)
        if not user:
            return JSONResponse({"ok": False, "error": "Non autenticato"}, status_code=401)
        body = await request.json()
        # Valida permissions se presente
        if "permissions" in body and body["permissions"] not in ("view", "upload", "edit", None):
            return JSONResponse({"ok": False, "error": "Permesso non valido"}, status_code=400)

        async with aiosqlite.connect(DB()) as db:
            await db.execute(
                "UPDATE portal_shares SET label=COALESCE(?,label), note=COALESCE(?,note), "
                "permissions=COALESCE(?,permissions), updated_at=? "
                "WHERE id=? AND consulente_id=?",
                (body.get("label"), body.get("note"), body.get("permissions"),
                 _now(), share_id, user["id"])
            )
            await db.commit()
        return {"ok": True}

    # ── Profilo utente corrente ────────────────────────────
    @app.get("/auth/profile")
    async def auth_profile(request: Request):
        user = await _resolve_token(request)
        if not user:
            return JSONResponse({"ok": False, "error": "Non autenticato"}, status_code=401)
        return {
            "ok": True,
            "user": {
                "id": user["id"], "name": user["name"],
                "email": user["email"],
                "role": user.get("role", "consulente"),
                "company": user.get("company", ""),
            }
        }

    # ── Update profilo ─────────────────────────────────────
    @app.put("/auth/profile")
    async def update_profile(request: Request):
        user = await _resolve_token(request)
        if not user:
            return JSONResponse({"ok": False, "error": "Non autenticato"}, status_code=401)
        body = await request.json()
        name    = (body.get("name") or "").strip()
        company = (body.get("company") or "").strip()
        if not name:
            return JSONResponse({"ok": False, "error": "Nome obbligatorio"}, status_code=400)
        async with aiosqlite.connect(DB()) as db:
            await db.execute(
                "UPDATE users SET name=?,company=COALESCE(?,company) WHERE id=?",
                (name, company or None, user["id"])
            )
            await db.commit()
        return {"ok": True}

# ── HELPER: carica risorsa dal DB principale ──────────────
async def _load_resource(resource_type: str, resource_id: str) -> dict | None:
    if not resource_id:
        return None
    try:
        if resource_type in ("bando", "azienda"):
            table = "bandi" if resource_type == "bando" else "aziende"
            async with aiosqlite.connect(DB()) as db:
                async with db.execute(
                    f"SELECT data FROM {table} WHERE id=? AND deleted_at IS NULL",
                    (resource_id,)
                ) as c:
                    row = await c.fetchone()
            if row:
                d = json.loads(row[0])
                return {
                    "id": d.get("id"), "name": d.get("name"),
                    "ente": d.get("ente"), "scadenza": d.get("scadenza"),
                    "status": d.get("status"),
                    "fields": d.get("fields", []),
                    "pdfs": [{"id": p["id"], "name": p["name"],
                               "analyzed": p.get("analyzed"),
                               "analysis": p.get("analysis", "")[:2000]}
                              for p in d.get("pdfs", [])],
                    "checklist": [item for p in d.get("pdfs", [])
                                  for item in p.get("checklist", [])],
                }
        elif resource_type == "sal":
            return {"id": resource_id, "type": "sal"}
    except Exception:
        pass
    return None

async def _get_message_counts(share_id: str, user_id: str) -> tuple[int, int]:
    async with aiosqlite.connect(DB()) as db:
        async with db.execute(
            "SELECT COUNT(*) as total, "
            "SUM(CASE WHEN author_id!=? AND read_by_consulente=0 THEN 1 ELSE 0 END) as unread "
            "FROM portal_messages WHERE share_id=?",
            (user_id, share_id)
        ) as c:
            row = await c.fetchone()
    return (row[0] or 0, row[1] or 0)

async def _get_doc_count(share_id: str) -> int:
    async with aiosqlite.connect(DB()) as db:
        async with db.execute(
            "SELECT COUNT(*) FROM portal_docs WHERE share_id=?", (share_id,)
        ) as c:
            row = await c.fetchone()
    return row[0] or 0
