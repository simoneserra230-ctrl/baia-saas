"""
AI Analisi Bandi — Backend v1.2
FastAPI + Anthropic Claude API
v1.2: sicurezza — auth su /db/*, CORS whitelist, file validation, email validation.
"""

from fastapi import FastAPI, UploadFile, File, Body, Request, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
import httpx, tempfile, os, asyncio, re, json, datetime, io, smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pypdf import PdfReader
import aiosqlite
from fpdf import FPDF
from typing import Optional

from security import validate_email, is_valid_pdf_bytes, MAX_UPLOAD_BYTES

# ─── CONFIG ───────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("AI_API_KEY", "")
ANTHROPIC_URL     = "https://api.anthropic.com/v1/messages"
MODEL             = os.environ.get("AI_MODEL", "claude-haiku-4-5-20251001")
CHUNK_SIZE        = int(os.environ.get("CHUNK_SIZE", "30000"))
SIMPLE_LIMIT      = int(os.environ.get("SIMPLE_LIMIT", "80000"))
LICENSE_KEY    = os.environ.get("LICENSE_KEY", "")
LICENSE_SERVER = os.environ.get("LICENSE_SERVER", "https://licenses.tuodominio.it")
APP_NAME       = os.environ.get("APP_NAME", "AI Analisi Bandi")
APP_VERSION    = "1.2.0"

DB_PATH   = os.environ.get("DB_PATH", "/data/ai-bandi.db")
SMTP_HOST = os.environ.get("SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")
SMTP_FROM = os.environ.get("SMTP_FROM", "noreply@ai-bandi.it")

# CORS: lista origini ammesse. Usa "*" solo in sviluppo locale.
_raw_origins = os.environ.get("ALLOWED_ORIGINS", "")
ALLOWED_ORIGINS: list[str] = (
    [o.strip() for o in _raw_origins.split(",") if o.strip()]
    if _raw_origins else ["*"]
)

# ─── DATABASE INIT ────────────────────────────────────────
async def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bandi (
                id TEXT PRIMARY KEY, data TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now')),
                deleted_at TEXT)""")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS aziende (
                id TEXT PRIMARY KEY, data TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now')),
                updated_at TEXT DEFAULT (datetime('now')),
                deleted_at TEXT)""")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS sal_trackers (
                id TEXT PRIMARY KEY, data TEXT NOT NULL,
                updated_at TEXT DEFAULT (datetime('now')))""")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS match_history (
                id TEXT PRIMARY KEY, data TEXT NOT NULL,
                created_at TEXT DEFAULT (datetime('now')))""")
        # Aggiungi deleted_at se tabella esiste già senza di essa
        for tbl in ("bandi", "aziende"):
            try:
                await db.execute(f"ALTER TABLE {tbl} ADD COLUMN deleted_at TEXT")
            except Exception:
                pass
        await db.commit()
    print(f"[DB] SQLite pronto: {DB_PATH}")

# ─── LICENZA ──────────────────────────────────────────────
_license_ok = False

async def verify_license_on_startup():
    global _license_ok
    if not LICENSE_KEY or LICENSE_KEY == "TEST-MODE":
        print(f"[LICENSE] TEST MODE — licenza bypassata ({APP_NAME} v{APP_VERSION})")
        _license_ok = True
        return
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{LICENSE_SERVER}/verify", params={"key": LICENSE_KEY})
            status = r.text.strip().strip('"')
            if status == "ok":
                print(f"[LICENSE] Valida — {APP_NAME} v{APP_VERSION}"); _license_ok = True
            elif status == "expired":
                print("[LICENSE] Scaduta"); _license_ok = False
            else:
                print("[LICENSE] Non valida"); _license_ok = False
    except Exception as e:
        print(f"[LICENSE] Grace period ({e})"); _license_ok = True

# ─── APP ──────────────────────────────────────────────────
app = FastAPI(title=APP_NAME, version=APP_VERSION, docs_url="/api/docs", redoc_url=None)

@app.on_event("startup")
async def startup():
    await init_db()
    await verify_license_on_startup()

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# ─── AUTH DEPENDENCY ──────────────────────────────────────

async def require_auth(request: Request) -> dict:
    """
    Dependency FastAPI: richiede token valido in X-Auth-Token.
    Se la tabella sessions non esiste ancora (avvio standalone), nega l'accesso.
    """
    token = request.headers.get("X-Auth-Token") or request.cookies.get("baia_token")
    if not token:
        raise HTTPException(status_code=401, detail="Autenticazione richiesta")
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT u.id, u.name, u.email FROM users u "
                "JOIN sessions s ON s.user_id = u.id "
                "WHERE s.token=? AND s.expires_at > datetime('now')",
                (token,)
            ) as c:
                row = await c.fetchone()
        if row:
            return {"id": row["id"], "name": row["name"], "email": row["email"]}
    except Exception:
        pass
    raise HTTPException(status_code=401, detail="Token non valido o scaduto")

# ─── HELPERS ──────────────────────────────────────────────
def extract_text(pdf_path: str) -> str:
    reader = PdfReader(pdf_path)
    return "".join(page.extract_text() or "" for page in reader.pages)

async def anthropic_call(prompt: str, json_mode: bool = False, timeout: int = 120) -> tuple[str, float]:
    if not ANTHROPIC_API_KEY:
        raise RuntimeError("ANTHROPIC_API_KEY non configurata")
    headers = {
        "x-api-key": ANTHROPIC_API_KEY,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    body: dict = {
        "model": MODEL,
        "max_tokens": 4096,
        "messages": [{"role": "user", "content": prompt}],
    }
    if json_mode:
        body["system"] = "Rispondi SEMPRE con JSON valido e nient'altro. Nessun backtick, nessun testo aggiuntivo."
    print(f"[ANTHROPIC] {len(prompt)} char | json={json_mode}", end=" → ", flush=True)
    async with httpx.AsyncClient(timeout=timeout) as client:
        r = await client.post(ANTHROPIC_URL, headers=headers, json=body)
        if r.status_code != 200:
            raise RuntimeError(f"Anthropic {r.status_code}: {r.text[:200]}")
        result = r.json()["content"][0]["text"]
        print(f"{len(result)} char OK")
        return result, 0.0

async def analyze_simple(text: str) -> str:
    result, _ = await anthropic_call(
        "Sei un esperto di finanza agevolata italiana. Analizza questo bando e restituisci:\n"
        "- Obiettivo principale\n- Beneficiari ammessi\n- Requisiti chiave\n"
        "- Scadenze importanti\n- Opportunità strategiche\n\n"
        f"Testo:\n{text[:SIMPLE_LIMIT]}")
    return result

async def analyze_in_chunks(text: str) -> str:
    chunks = [text[i:i+CHUNK_SIZE] for i in range(0, len(text), CHUNK_SIZE)]
    parts = []
    for i, chunk in enumerate(chunks):
        result, _ = await anthropic_call(
            f"Parte {i+1}/{len(chunks)} di un bando. "
            f"Estrai Obiettivo, Beneficiari, Requisiti, Scadenze, Opportunità.\n\n{chunk}")
        parts.append(result)
        if i < len(chunks) - 1: await asyncio.sleep(3)
    result, _ = await anthropic_call(
        "Crea un'analisi finale completa da questi estratti:\n\n" +
        "".join(f"--- Parte {i+1} ---\n{r}\n" for i, r in enumerate(parts)), timeout=180)
    return result

async def analyze_auto(text: str) -> str:
    if len(text) <= SIMPLE_LIMIT:
        print(f"[INFO] Testo breve ({len(text)} car) → analisi diretta")
        return await analyze_simple(text)
    print(f"[INFO] Testo lungo ({len(text)} car) → chunking")
    return await analyze_in_chunks(text)

# ─── BA.IA AI FEATURES (chatbot · blog · business plan · pitch · compliance) ──
from baia_ai import make_ai_router
app.include_router(make_ai_router(anthropic_call, require_auth, DB_PATH))

# ─── ENDPOINTS CORE ───────────────────────────────────────

@app.get("/")
def home(request: Request = None):
    is_test = LICENSE_KEY in ("TEST-MODE", "")
    if request:
        accept = request.headers.get("accept", "")
        if "text/html" in accept and "json" not in request.headers.get("content-type", ""):
            from fastapi.responses import FileResponse
            from pathlib import Path
            frontend = Path(__file__).parent.parent / "frontend" / "index.html"
            if frontend.exists():
                return FileResponse(str(frontend))
    return {"status": "ok", "app": APP_NAME, "version": APP_VERSION,
            "provider": "anthropic", "model": MODEL, "licensed": _license_ok,
            "mode": "test" if is_test else "production"}

@app.get("/model")
def get_model(): return {"model": MODEL, "app": APP_NAME}

@app.post("/analyze")
async def analyze(file: UploadFile = File(...), _user: dict = Depends(require_auth)):
    if not file.filename.lower().endswith(".pdf"):
        return {"error": "Solo file PDF supportati"}
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        return {"error": f"File troppo grande (max {MAX_UPLOAD_BYTES // 1024 // 1024} MB)"}
    if not is_valid_pdf_bytes(data):
        return {"error": "Il file non è un PDF valido"}
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(data); tmp_path = tmp.name
        text = extract_text(tmp_path)
        return {"result": await analyze_auto(text), "chars": len(text)}
    except Exception as e: return {"error": "Errore elaborazione PDF"}
    finally:
        if tmp_path and os.path.exists(tmp_path): os.unlink(tmp_path)

# ─── ANALISI TECNICA — Scheda Progetto a 16 campi (Agente AI) ─────────
SCHEDA_TECNICA_SYSTEM = (
    "Sei un analista di finanza agevolata italiana. Dal testo di un bando produci la "
    "SCHEDA PROGETTO. Rispondi SOLO con JSON valido (nessun backtick, nessun testo extra). "
    "Il JSON deve avere queste 14 chiavi di tipo stringa: iniziativa_bando, obiettivo, "
    "tempistiche, soggetti_beneficiari, spese_ammissibili, vincoli_requisiti, "
    "spese_non_ammissibili, agevolazioni, cumulabilita, erogazione, budget, "
    "modalita_presentazione, sito, note_rendicontazione. "
    "PIU' una chiave 'indicatori' di tipo OGGETTO con esattamente questi campi: "
    "accessibilita_pmi (intero 1-10: quanto è accessibile a micro/piccole imprese), "
    "indice_complessita (intero 1-10: complessità documentale e procedurale), "
    "rischio_operativo (una tra 'basso','medio','alto'), "
    "rigidita_normativa (intero 1-10), "
    "dimensione_impresa_ammessa (stringa, es. 'micro, piccola, media' oppure 'tutte'), "
    "ambito_territoriale (stringa, es. 'Sardegna' oppure 'nazionale'), "
    "percentuale_contributo (stringa con %, es. 'fino al 90%'; '' se non previsto), "
    "massimale_contributo (stringa con importo €; '' se non previsto), "
    "investimento_minimo (stringa con importo €; '' se non previsto), "
    "investimento_massimo (stringa con importo €; '' se non previsto), "
    "de_minimis (stringa, es. 'sì - Reg. UE 2023/2831' oppure '' se non pertinente). "
    "I 4 campi numerici/enumerati (accessibilita_pmi, indice_complessita, rischio_operativo, "
    "rigidita_normativa) sono una TUA valutazione di sintesi da esperto, coerente col bando. "
    "Regole: contenuti concreti dal testo (date, %, €), riferimenti normativi per esteso, "
    "MAI inventare dati fattuali; se un campo testuale non è ricavabile scrivi "
    "'[Non specificato nella documentazione]'. NESSUN logo, nome o riferimento ad aziende di consulenza."
)
SCHEDA_LIMIT = 45000

def _parse_scheda(result: str) -> dict:
    import json as _json, re as _re
    try:
        return _json.loads(result)
    except Exception:
        m = _re.search(r"\{.*\}", result, _re.S)
        if m:
            try: return _json.loads(m.group(0))
            except Exception: pass
    return {"raw": result}

@app.post("/bando/analisi-tecnica")
async def bando_analisi_tecnica(file: UploadFile = File(...), _user: dict = Depends(require_auth)):
    """Genera la Scheda Progetto a 16 campi da un PDF di bando."""
    if not file.filename.lower().endswith(".pdf"):
        return {"error": "Solo file PDF supportati"}
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        return {"error": f"File troppo grande (max {MAX_UPLOAD_BYTES // 1024 // 1024} MB)"}
    if not is_valid_pdf_bytes(data):
        return {"error": "Il file non è un PDF valido"}
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(data); tmp_path = tmp.name
        text = extract_text(tmp_path)
        result, _ = await anthropic_call(
            SCHEDA_TECNICA_SYSTEM + "\n\nTESTO DEL BANDO:\n" + text[:SCHEDA_LIMIT],
            json_mode=True, timeout=150)
        return {"ok": True, "scheda": _parse_scheda(result), "chars": len(text)}
    except Exception as e:
        print(f"[ANALISI-TECNICA] errore: {e}")
        return {"error": "Errore generazione scheda tecnica"}
    finally:
        if tmp_path and os.path.exists(tmp_path): os.unlink(tmp_path)

class _SchedaTextReq(BaseModel):
    text: str

@app.post("/bando/analisi-tecnica-text")
async def bando_analisi_tecnica_text(req: _SchedaTextReq, _user: dict = Depends(require_auth)):
    """Genera la Scheda Progetto da testo già estratto."""
    if not (req.text or "").strip():
        return {"error": "Testo mancante"}
    result, _ = await anthropic_call(
        SCHEDA_TECNICA_SYSTEM + "\n\nTESTO DEL BANDO:\n" + req.text[:SCHEDA_LIMIT],
        json_mode=True, timeout=150)
    return {"ok": True, "scheda": _parse_scheda(result)}

@app.post("/extract-text")
async def extract_text_endpoint(file: UploadFile = File(...), _user: dict = Depends(require_auth)):
    if not file.filename.lower().endswith(".pdf"):
        return {"error": "Solo file PDF supportati", "text": ""}
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        return {"error": f"File troppo grande (max {MAX_UPLOAD_BYTES // 1024 // 1024} MB)", "text": ""}
    if not is_valid_pdf_bytes(data):
        return {"error": "Il file non è un PDF valido", "text": ""}
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(data); tmp_path = tmp.name
        text = extract_text(tmp_path)
        return {"text": text, "length": len(text)}
    except Exception as e: return {"error": "Errore elaborazione PDF", "text": ""}
    finally:
        if tmp_path and os.path.exists(tmp_path): os.unlink(tmp_path)

class EnrichRequest(BaseModel):
    bando_title: str
    bando_context: str
    fields: list[dict]

@app.post("/enrich")
async def enrich_fields_endpoint(req: EnrichRequest, _user: dict = Depends(require_auth)):
    if not req.fields: return {"campi": []}
    fields_text = "\n".join(f'  - "{f.get("label","?")}"  (sezione: {f.get("section","?")})' for f in req.fields)
    prompt = (
        "Sei un esperto senior di finanza agevolata e normativa italiana. "
        "Per il bando indicato, i seguenti campi NON sono stati estratti dal testo PDF. "
        "Devi ricercarli usando le tue conoscenze approfondite su:\n"
        "  • Gazzetta Ufficiale (GU), Ministeri (MIMIT, MEF, MUR, MIPAAF), Invitalia, CDP, Regioni\n"
        "  • Normative UE: GBER (Reg. 651/2014), de minimis (Reg. 1407/2013), PSC, PNRR\n"
        "  • Prassi consolidate per bandi simili\n\n"
        f'BANDO: "{req.bando_title}"\n'
        f"CONTESTO DISPONIBILE: {req.bando_context[:900]}\n\n"
        f"CAMPI DA RICERCARE:\n{fields_text}\n\n"
        "ISTRUZIONI:\n  1. Per ogni campo fornisci il valore più accurato possibile.\n"
        "  2. Se non puoi determinarlo con sicurezza, metti null come valore.\n"
        "  3. Indica sempre la fonte ufficiale (nome e URL se disponibile).\n"
        "  4. Confidenza: 'alta'=fonte certa/verificabile, 'media'=dedotto da prassi, 'bassa'=stima.\n"
        "  5. Non inventare — preferisci null a dati non verificabili.\n\n"
        "RISPOSTA: JSON valido ESCLUSIVAMENTE, zero testo aggiuntivo, zero backtick:\n"
        '{"campi":[{"label":"nome esatto campo","valore":"valore o null",'
        '"fonte_nome":"es. GU n.123/2024 – MIMIT","fonte_url":"https://...",'
        '"confidenza":"alta|media|bassa","nota":"breve nota metodologica"}]}'
    )
    try:
        result, _ = await anthropic_call(prompt, json_mode=True, timeout=150)
        if isinstance(result, str):
            clean = result.strip()
            if clean.startswith("```"):
                clean = clean.split("```")[1]
                if clean.startswith("json"): clean = clean[4:]
            parsed = json.loads(clean.strip())
        else: parsed = result
        return parsed
    except Exception: return {"error": "Errore elaborazione AI", "campi": []}

class PromptRequest(BaseModel):
    prompt: str

@app.post("/prompt")
async def prompt_endpoint(req: PromptRequest, _user: dict = Depends(require_auth)):
    try:
        is_chat = "Rispondi in italiano" in req.prompt and "Cita dati precisi" in req.prompt
        json_mode = (not is_chat) and "{" in req.prompt and (
            "sezione" in req.prompt.lower() or
            "compila ESATTAMENTE" in req.prompt or
            "schema JSON" in req.prompt)
        result, wait_secs = await anthropic_call(req.prompt, json_mode=json_mode)
        response = {"result": result}
        if wait_secs > 0: response["waitSecs"] = round(wait_secs, 1)
        return response
    except Exception as e: return {"error": "Errore elaborazione AI"}

# ─── PERSISTENZA SQLite (richiede autenticazione) ─────────

@app.get("/db/bandi")
async def db_get_bandi(
    limit: int = 200, offset: int = 0,
    _user: dict = Depends(require_auth)
):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, data, created_at, updated_at FROM bandi "
            "WHERE deleted_at IS NULL ORDER BY updated_at DESC LIMIT ? OFFSET ?",
            (limit, offset)
        ) as c:
            rows = await c.fetchall()
        async with db.execute("SELECT COUNT(*) FROM bandi WHERE deleted_at IS NULL") as c:
            total = (await c.fetchone())[0]
    return {
        "bandi": [{"id": r["id"], "data": json.loads(r["data"]),
                   "created_at": r["created_at"], "updated_at": r["updated_at"]} for r in rows],
        "total": total, "limit": limit, "offset": offset
    }

@app.put("/db/bandi/{bando_id}")
async def db_upsert_bando(bando_id: str, payload: dict = Body(...), _user: dict = Depends(require_auth)):
    now = datetime.datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO bandi (id,data,created_at,updated_at) VALUES (?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
            (bando_id, json.dumps(payload), now, now))
        await db.commit()
    return {"ok": True, "id": bando_id}

@app.delete("/db/bandi/{bando_id}")
async def db_delete_bando(bando_id: str, _user: dict = Depends(require_auth)):
    now = datetime.datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE bandi SET deleted_at=? WHERE id=?", (now, bando_id))
        await db.commit()
    return {"ok": True}

@app.get("/db/aziende")
async def db_get_aziende(
    limit: int = 200, offset: int = 0,
    _user: dict = Depends(require_auth)
):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id, data, created_at, updated_at FROM aziende "
            "WHERE deleted_at IS NULL ORDER BY updated_at DESC LIMIT ? OFFSET ?",
            (limit, offset)
        ) as c:
            rows = await c.fetchall()
        async with db.execute("SELECT COUNT(*) FROM aziende WHERE deleted_at IS NULL") as c:
            total = (await c.fetchone())[0]
    return {
        "aziende": [{"id": r["id"], "data": json.loads(r["data"]),
                     "created_at": r["created_at"], "updated_at": r["updated_at"]} for r in rows],
        "total": total, "limit": limit, "offset": offset
    }

@app.put("/db/aziende/{azienda_id}")
async def db_upsert_azienda(azienda_id: str, payload: dict = Body(...), _user: dict = Depends(require_auth)):
    now = datetime.datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO aziende (id,data,created_at,updated_at) VALUES (?,?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
            (azienda_id, json.dumps(payload), now, now))
        await db.commit()
    return {"ok": True, "id": azienda_id}

@app.delete("/db/aziende/{azienda_id}")
async def db_delete_azienda(azienda_id: str, _user: dict = Depends(require_auth)):
    now = datetime.datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE aziende SET deleted_at=? WHERE id=?", (now, azienda_id))
        await db.commit()
    return {"ok": True}

@app.get("/db/sal")
async def db_get_sal(_user: dict = Depends(require_auth)):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT id, data FROM sal_trackers") as c:
            rows = await c.fetchall()
    return {"sal": {r["id"]: json.loads(r["data"]) for r in rows}}

@app.put("/db/sal/{sal_id}")
async def db_upsert_sal(sal_id: str, payload: dict = Body(...), _user: dict = Depends(require_auth)):
    now = datetime.datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO sal_trackers (id,data,updated_at) VALUES (?,?,?) "
            "ON CONFLICT(id) DO UPDATE SET data=excluded.data, updated_at=excluded.updated_at",
            (sal_id, json.dumps(payload), now))
        await db.commit()
    return {"ok": True}

@app.get("/db/history")
async def db_get_history(
    limit: int = 100, offset: int = 0,
    _user: dict = Depends(require_auth)
):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT id,data,created_at FROM match_history ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (min(limit, 500), offset)
        ) as c:
            rows = await c.fetchall()
    return {"history": [{"id": r["id"], "data": json.loads(r["data"]), "created_at": r["created_at"]} for r in rows]}

@app.put("/db/history/{entry_id}")
async def db_upsert_history(entry_id: str, payload: dict = Body(...), _user: dict = Depends(require_auth)):
    now = datetime.datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO match_history (id,data,created_at) VALUES (?,?,?) ON CONFLICT(id) DO NOTHING",
            (entry_id, json.dumps(payload), now))
        await db.commit()
    return {"ok": True}

class SyncPayload(BaseModel):
    bandi: list[dict] = []
    aziende: list[dict] = []
    salTrackers: dict = {}
    matchHistory: list[dict] = []

@app.post("/db/sync")
async def db_sync(payload: SyncPayload, _user: dict = Depends(require_auth)):
    """Importa lo stato completo del browser (localStorage) nel DB server."""
    now = datetime.datetime.utcnow().isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        for b in payload.bandi:
            if bid := b.get("id"):
                await db.execute(
                    "INSERT INTO bandi (id,data,created_at,updated_at) VALUES (?,?,?,?) "
                    "ON CONFLICT(id) DO UPDATE SET data=excluded.data,updated_at=excluded.updated_at",
                    (bid, json.dumps(b), now, now))
        for a in payload.aziende:
            if aid := a.get("id"):
                await db.execute(
                    "INSERT INTO aziende (id,data,created_at,updated_at) VALUES (?,?,?,?) "
                    "ON CONFLICT(id) DO UPDATE SET data=excluded.data,updated_at=excluded.updated_at",
                    (aid, json.dumps(a), now, now))
        for sid, sdata in payload.salTrackers.items():
            await db.execute(
                "INSERT INTO sal_trackers (id,data,updated_at) VALUES (?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET data=excluded.data,updated_at=excluded.updated_at",
                (sid, json.dumps(sdata), now))
        for h in payload.matchHistory:
            if hid := h.get("id"):
                await db.execute(
                    "INSERT INTO match_history (id,data,created_at) VALUES (?,?,?) ON CONFLICT(id) DO NOTHING",
                    (hid, json.dumps(h), now))
        await db.commit()
    return {"ok": True, "synced": {
        "bandi": len(payload.bandi), "aziende": len(payload.aziende),
        "sal": len(payload.salTrackers), "history": len(payload.matchHistory)}}

# ─── EXPORT PDF ───────────────────────────────────────────

class PdfExportRequest(BaseModel):
    bando_name: str
    app_name: str = "AI Analisi Bandi"
    sections: list[dict] = []
    note: str = ""

@app.post("/export-pdf")
async def export_pdf(req: PdfExportRequest, _user: dict = Depends(require_auth)):
    try:
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()

        pdf.set_fill_color(15, 15, 26)
        pdf.rect(0, 0, 210, 28, "F")
        pdf.set_text_color(212, 175, 55)
        pdf.set_font("Helvetica", "B", 14)
        pdf.set_xy(10, 8)
        pdf.cell(0, 8, req.app_name, ln=True)
        pdf.set_font("Helvetica", "", 9)
        pdf.set_text_color(180, 180, 200)
        pdf.set_x(10)
        pdf.cell(0, 5, "Report Analisi Bando", ln=True)
        pdf.set_y(32)

        pdf.set_text_color(15, 15, 26)
        pdf.set_font("Helvetica", "B", 13)
        pdf.multi_cell(0, 7, req.bando_name, ln=True)
        pdf.set_font("Helvetica", "", 8)
        pdf.set_text_color(120, 120, 140)
        pdf.cell(0, 5, f"Generato il {datetime.datetime.now().strftime('%d/%m/%Y %H:%M')}  —  {req.app_name} v{APP_VERSION}", ln=True)
        pdf.ln(4)

        for sec in req.sections:
            fields = sec.get("fields", [])
            if not any(f.get("value") for f in fields): continue
            pdf.set_fill_color(240, 240, 248)
            pdf.set_text_color(40, 40, 80)
            pdf.set_font("Helvetica", "B", 9)
            pdf.cell(0, 6, f"  {sec.get('title','')}", ln=True, fill=True)
            pdf.ln(1)
            for field in fields:
                value = str(field.get("value") or "").strip()
                if not value or value in ("null", "None", "undefined", ""): continue
                pdf.set_text_color(80, 80, 100)
                pdf.set_font("Helvetica", "B", 8)
                pdf.set_x(12)
                pdf.cell(50, 5, (field.get("label","") + ":")[:40], ln=False)
                pdf.set_text_color(20, 20, 40)
                pdf.set_font("Helvetica", "", 8)
                if len(value) > 300: value = value[:297] + "…"
                pdf.multi_cell(0, 5, value, ln=True)
            pdf.ln(3)

        if req.note:
            pdf.ln(2)
            pdf.set_fill_color(255, 248, 220)
            pdf.set_text_color(100, 80, 0)
            pdf.set_font("Helvetica", "B", 8)
            pdf.cell(0, 6, "  Note", ln=True, fill=True)
            pdf.set_font("Helvetica", "", 8)
            pdf.set_x(12)
            pdf.multi_cell(0, 5, req.note, ln=True)

        pdf.set_y(-18)
        pdf.set_text_color(160, 160, 180)
        pdf.set_font("Helvetica", "", 7)
        pdf.cell(0, 5,
            f"{req.app_name}  |  Report AI  |  Verificare sempre i dati sul sito ufficiale dell'ente erogatore",
            align="C")

        buf = io.BytesIO(pdf.output())
        filename = re.sub(r"[^a-zA-Z0-9_\-]", "_", req.bando_name[:60]) + ".pdf"
        return StreamingResponse(buf, media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'})
    except Exception:
        return JSONResponse({"error": "Errore generazione PDF"}, status_code=500)

# ─── NOTIFICHE EMAIL ──────────────────────────────────────

class EmailNotifyRequest(BaseModel):
    to: str
    subject: str
    bandi_in_scadenza: list[dict]

@app.post("/notify-email")
async def notify_email(req: EmailNotifyRequest, _user: dict = Depends(require_auth)):
    if not SMTP_HOST:
        return {"ok": False, "error": "SMTP non configurato. Aggiungi SMTP_HOST nel .env"}
    if not validate_email(req.to):
        return {"ok": False, "error": "Indirizzo email destinatario non valido"}
    righe = ""
    for b in req.bandi_in_scadenza:
        giorni = b.get("giorni", 0)
        colore = "#dc2626" if giorni <= 7 else "#d97706" if giorni <= 30 else "#16a34a"
        # Escaping per prevenire HTML injection
        name = str(b.get("name", "—")).replace("<", "&lt;").replace(">", "&gt;")
        scad = str(b.get("scadenza", "—")).replace("<", "&lt;").replace(">", "&gt;")
        righe += (
            f"<tr><td style='padding:8px 12px;border-bottom:1px solid #eee;'>{name}</td>"
            f"<td style='padding:8px 12px;border-bottom:1px solid #eee;'>{scad}</td>"
            f"<td style='padding:8px 12px;border-bottom:1px solid #eee;color:{colore};font-weight:700;'>{int(giorni)} giorni</td></tr>")
    html_body = f"""<html><body style="font-family:sans-serif;color:#1a1a2e;max-width:600px;margin:auto;">
      <div style="background:#0f0f1a;padding:20px 24px;border-radius:8px 8px 0 0;">
        <h2 style="color:#d4af37;margin:0;">{APP_NAME}</h2>
        <p style="color:#aaa;margin:4px 0 0;">Notifica Scadenze</p></div>
      <div style="border:1px solid #eee;border-top:none;padding:20px 24px;border-radius:0 0 8px 8px;">
        <p>I seguenti bandi sono in scadenza:</p>
        <table style="width:100%;border-collapse:collapse;font-size:14px;">
          <thead><tr style="background:#f5f5f8;">
            <th style="padding:8px 12px;text-align:left;">Bando</th>
            <th style="padding:8px 12px;text-align:left;">Scadenza</th>
            <th style="padding:8px 12px;text-align:left;">Tempo rimasto</th>
          </tr></thead><tbody>{righe}</tbody></table>
        <p style="margin-top:20px;font-size:12px;color:#888;">Messaggio automatico da {APP_NAME}. Verificare sempre sul sito ufficiale.</p>
      </div></body></html>"""
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = req.subject; msg["From"] = SMTP_FROM; msg["To"] = req.to
        msg.attach(MIMEText(html_body, "html"))
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=15) as smtp:
            smtp.ehlo(); smtp.starttls()
            if SMTP_USER and SMTP_PASS: smtp.login(SMTP_USER, SMTP_PASS)
            smtp.sendmail(SMTP_FROM, req.to, msg.as_string())
        return {"ok": True, "sent_to": req.to}
    except Exception:
        return {"ok": False, "error": "Errore invio email"}

@app.get("/notify-email/test")
async def test_smtp():
    if not SMTP_HOST:
        return {"configured": False, "message": "SMTP_HOST non impostato nel .env"}
    return {"configured": True, "host": SMTP_HOST, "port": SMTP_PORT,
            "user": SMTP_USER or "(nessuno)", "from": SMTP_FROM}

# ─── AI ADVISOR — MATCHING SEMANTICO CON CLAUDE ───────────────────
#
# Questi endpoint usano ai_advisor.py per sostituire / affiancare
# il matching TF-IDF con analisi Claude profonda.
#
# POST /match-ai          — compatibilità profonda bando × azienda
# POST /match-ai/rank     — ranking batch di tutti i bandi per un'azienda
# POST /advisor           — report strategico proattivo per un'azienda
# POST /analyze/stream    — analisi PDF in streaming (SSE)
#
# Tutti richiedono ANTHROPIC_API_KEY nel .env.
# ──────────────────────────────────────────────────────────────────

try:
    from ai_advisor import (
        ai_analyze_compatibility,
        ai_rank_bandi,
        ai_match_companies_to_bando,
        ai_advisor_report,
        stream_analysis,
    )
    _AI_ADVISOR_OK = True
except ImportError as _e:
    print(f"[AI ADVISOR] Import non disponibile: {_e}")
    _AI_ADVISOR_OK = False


class MatchAIRequest(BaseModel):
    azienda: dict
    bando: dict


class RankAIRequest(BaseModel):
    azienda: dict
    bandi: list[dict]
    top_n: int = 10


class AdvisorRequest(BaseModel):
    azienda: dict


@app.post("/match-ai")
async def match_ai_endpoint(req: MatchAIRequest, _user: dict = Depends(require_auth)):
    """
    Analisi AI profonda compatibilità singolo bando × azienda.
    Ritorna score 0-100, rationale, requisiti soddisfatti/mancanti, azioni.
    """
    if not _AI_ADVISOR_OK:
        return JSONResponse({"error": "Modulo AI Advisor non disponibile"}, status_code=503)
    if not ANTHROPIC_API_KEY:
        return JSONResponse({"error": "ANTHROPIC_API_KEY non configurata nel .env"}, status_code=400)
    try:
        result = await ai_analyze_compatibility(
            req.azienda, req.bando, ANTHROPIC_API_KEY, MODEL
        )
        return result
    except Exception as e:
        return JSONResponse({"error": f"Errore analisi AI: {e}"}, status_code=500)


@app.post("/match-ai/rank")
async def rank_ai_endpoint(req: RankAIRequest, _user: dict = Depends(require_auth)):
    """
    Ranking AI batch: pre-filtra con TF-IDF, poi Claude analizza i top candidati.
    Efficiente: max 2 chiamate Claude indipendentemente dal numero di bandi.
    """
    if not _AI_ADVISOR_OK:
        return JSONResponse({"error": "Modulo AI Advisor non disponibile"}, status_code=503)
    if not ANTHROPIC_API_KEY:
        return JSONResponse({"error": "ANTHROPIC_API_KEY non configurata nel .env"}, status_code=400)
    if not req.bandi:
        return {"results": [], "total": 0}
    try:
        results = await ai_rank_bandi(
            req.azienda, req.bandi, ANTHROPIC_API_KEY, MODEL, req.top_n
        )
        return {"results": results, "total": len(results)}
    except Exception as e:
        return JSONResponse({"error": f"Errore ranking AI: {e}"}, status_code=500)


class RicontrolloRequest(BaseModel):
    bando: dict
    aziende: list[dict]
    top_n: int = 20


@app.post("/bando/ricontrollo")
async def bando_ricontrollo(req: RicontrolloRequest, _user: dict = Depends(require_auth)):
    """RICONTROLLO: un nuovo bando → ripassa tutte le aziende, ritorna le compatibili."""
    if not _AI_ADVISOR_OK:
        return JSONResponse({"error": "Modulo AI Advisor non disponibile"}, status_code=503)
    if not ANTHROPIC_API_KEY:
        return JSONResponse({"error": "ANTHROPIC_API_KEY non configurata"}, status_code=400)
    if not req.aziende:
        return {"matches": [], "total": 0}
    try:
        matches = await ai_match_companies_to_bando(
            req.bando, req.aziende, ANTHROPIC_API_KEY, MODEL, req.top_n
        )
        return {"matches": matches, "total": len(matches)}
    except Exception as e:
        return JSONResponse({"error": f"Errore ricontrollo: {e}"}, status_code=500)


@app.post("/advisor")
async def advisor_endpoint(req: AdvisorRequest, _user: dict = Depends(require_auth)):
    """
    Report strategico proattivo: analizza il profilo dell'azienda e
    suggerisce opportunità, azioni immediate e piano a medio termine.
    """
    if not _AI_ADVISOR_OK:
        return JSONResponse({"error": "Modulo AI Advisor non disponibile"}, status_code=503)
    if not ANTHROPIC_API_KEY:
        return JSONResponse({"error": "ANTHROPIC_API_KEY non configurata nel .env"}, status_code=400)
    try:
        result = await ai_advisor_report(req.azienda, ANTHROPIC_API_KEY, MODEL)
        return result
    except Exception as e:
        return JSONResponse({"error": f"Errore advisor AI: {e}"}, status_code=500)


@app.post("/analyze/stream")
async def analyze_stream_endpoint(
    file: UploadFile = File(...),
    _user: dict = Depends(require_auth),
):
    """
    Versione streaming di /analyze.
    Ritorna Server-Sent Events: ogni chunk è {"delta":"..."}, il finale è {"done":true}.
    """
    if not file.filename.lower().endswith(".pdf"):
        return JSONResponse({"error": "Solo file PDF"}, status_code=400)
    data = await file.read()
    if len(data) > MAX_UPLOAD_BYTES:
        return JSONResponse({"error": "File troppo grande"}, status_code=400)
    if not is_valid_pdf_bytes(data):
        return JSONResponse({"error": "File PDF non valido"}, status_code=400)
    if not ANTHROPIC_API_KEY:
        return JSONResponse({"error": "ANTHROPIC_API_KEY non configurata"}, status_code=400)
    if not _AI_ADVISOR_OK:
        return JSONResponse({"error": "Modulo streaming non disponibile"}, status_code=503)

    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            tmp.write(data); tmp_path = tmp.name
        text = extract_text(tmp_path)
    except Exception:
        return JSONResponse({"error": "Errore lettura PDF"}, status_code=500)
    finally:
        if tmp_path and os.path.exists(tmp_path): os.unlink(tmp_path)

    chars = len(text)

    async def generate():
        try:
            async for chunk in stream_analysis(text, ANTHROPIC_API_KEY, MODEL, SIMPLE_LIMIT):
                yield f"data: {json.dumps({'delta': chunk})}\n\n"
            yield f"data: {json.dumps({'done': True, 'chars': chars})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
