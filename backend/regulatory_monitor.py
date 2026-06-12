"""
BA.IA — Regulatory Change Monitor (D3.5)
Monitora modifiche normative su bandi attivi: variazioni scadenze, aggiornamenti testi,
nuovi decreti attuativi, FAQ ufficiali.

Strategia: confronto hash contenuto pagine sorgente ogni 24h + AI diff analysis.
"""

import os, re, json, hashlib, datetime, asyncio
from typing import Optional
import httpx
import aiosqlite
from fastapi import Request
from fastapi.responses import JSONResponse

DB = lambda: os.environ.get("DB_PATH", "./data/ai-bandi.db")

# Sorgenti da monitorare per cambiamenti normativi
REGULATORY_SOURCES = [
    {"id": "gazzetta_eu_hca", "nome": "MISE — Hospitality & Turismo", "url": "https://www.mimit.gov.it/index.php/it/incentivi", "category": "nazionale"},
    {"id": "invitalia_news", "nome": "Invitalia News", "url": "https://www.invitalia.it/chi-siamo/media/comunicati", "category": "nazionale"},
    {"id": "mef_circolari", "nome": "MEF — Circolari", "url": "https://www.mef.gov.it/uffici/dag/circolari/", "category": "normativa"},
    {"id": "agenzia_entrate", "nome": "Agenzia Entrate — Crediti d'imposta", "url": "https://www.agenziaentrate.gov.it/portale/web/guest/schede/agevolazioni", "category": "fiscale"},
    {"id": "pnrr_monitor", "nome": "PNRR Italia", "url": "https://www.italiadomani.gov.it", "category": "pnrr"},
]

CHANGE_TYPES = {
    "scadenza": "Modifica scadenza presentazione domande",
    "dotazione": "Variazione dotazione finanziaria",
    "beneficiari": "Aggiornamento platea beneficiari",
    "requisiti": "Modifica requisiti di accesso",
    "procedura": "Aggiornamento procedura/modulistica",
    "sospensione": "Sospensione o revoca del bando",
    "proroga": "Proroga termini",
    "faq": "Nuove FAQ ufficiali",
}


async def init_regulatory_db():
    async with aiosqlite.connect(DB()) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS regulatory_snapshots (
                id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                url TEXT NOT NULL,
                content_hash TEXT NOT NULL,
                content_preview TEXT,
                captured_at TEXT DEFAULT (datetime('now'))
            )""")
        await db.execute("""
            CREATE TABLE IF NOT EXISTS regulatory_changes (
                id TEXT PRIMARY KEY,
                source_id TEXT NOT NULL,
                source_nome TEXT,
                change_type TEXT,
                titolo TEXT NOT NULL,
                descrizione TEXT,
                bandi_impattati TEXT DEFAULT '[]',
                url TEXT,
                rilevato_at TEXT DEFAULT (datetime('now')),
                letto INTEGER DEFAULT 0,
                importante INTEGER DEFAULT 0
            )""")
        await db.commit()


def _make_id():
    import uuid
    return str(uuid.uuid4())[:8]


async def scan_regulatory_changes(bandi_attivi: list[dict]) -> list[dict]:
    """Controlla le sorgenti e rileva cambiamenti. Restituisce lista cambiamenti trovati."""
    changes = []
    bandi_keywords = set()
    for b in bandi_attivi:
        d = b.get("data", b)
        titolo = (d.get("titolo") or d.get("nome") or "").lower()
        for w in titolo.split():
            if len(w) > 4:
                bandi_keywords.add(w)

    async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
        for src in REGULATORY_SOURCES:
            try:
                r = await client.get(src["url"])
                content = r.text[:50000]
                content_hash = hashlib.sha256(content.encode()).hexdigest()[:16]
                preview = content[:500]

                async with aiosqlite.connect(DB()) as db:
                    db.row_factory = aiosqlite.Row
                    async with db.execute(
                        "SELECT content_hash, content_preview FROM regulatory_snapshots WHERE source_id=?",
                        (src["id"],)
                    ) as c:
                        old = await c.fetchone()

                if old and old["content_hash"] != content_hash:
                    # Contenuto cambiato — analizza il tipo di cambiamento
                    change_type = _detect_change_type(content, old["content_preview"] or "")
                    impattati = _find_impacted_bandi(content, bandi_attivi)

                    change = {
                        "id": _make_id(),
                        "source_id": src["id"],
                        "source_nome": src["nome"],
                        "change_type": change_type,
                        "titolo": f"Aggiornamento {src['nome']} — {CHANGE_TYPES.get(change_type, 'Modifica rilevata')}",
                        "descrizione": f"Il contenuto di {src['url']} è cambiato. Verificare manualmente le variazioni.",
                        "bandi_impattati": json.dumps(impattati),
                        "url": src["url"],
                        "importante": 1 if change_type in ("sospensione", "scadenza", "proroga") else 0,
                    }
                    changes.append(change)

                    async with aiosqlite.connect(DB()) as db:
                        await db.execute(
                            "INSERT INTO regulatory_changes VALUES (?,?,?,?,?,?,?,?,datetime('now'),0,?)",
                            (change["id"], src["id"], src["nome"], change_type,
                             change["titolo"], change["descrizione"],
                             change["bandi_impattati"], src["url"], change["importante"])
                        )
                        await db.execute(
                            "INSERT INTO regulatory_snapshots VALUES (?,?,?,?,?,datetime('now')) "
                            "ON CONFLICT(id) DO UPDATE SET content_hash=excluded.content_hash,"
                            "content_preview=excluded.content_preview,captured_at=excluded.captured_at",
                            (f"{src['id']}_snap", src["id"], src["url"], content_hash, preview[:500])
                        )
                        await db.commit()
                elif not old:
                    # Prima scansione — salva snapshot iniziale
                    async with aiosqlite.connect(DB()) as db:
                        await db.execute(
                            "INSERT OR IGNORE INTO regulatory_snapshots VALUES (?,?,?,?,?,datetime('now'))",
                            (f"{src['id']}_snap", src["id"], src["url"], content_hash, preview[:500])
                        )
                        await db.commit()

            except Exception as e:
                print(f"[RegMonitor] Errore {src['id']}: {e}")
                continue

    return changes


def _detect_change_type(new_content: str, old_content: str) -> str:
    new_lower = new_content.lower()
    if any(kw in new_lower for kw in ["sospeso", "revocato", "annullato", "sospensione"]):
        return "sospensione"
    if any(kw in new_lower for kw in ["proroga", "prorogato", "rinviato", "spostato"]):
        return "proroga"
    if any(kw in new_lower for kw in ["scadenza", "termine", "entro il", "data limite"]):
        return "scadenza"
    if any(kw in new_lower for kw in ["faq", "domande frequenti", "quesiti"]):
        return "faq"
    if any(kw in new_lower for kw in ["dotazione", "milioni", "budget", "finanziamento"]):
        return "dotazione"
    return "procedura"


def _find_impacted_bandi(content: str, bandi: list[dict]) -> list[str]:
    impactati = []
    content_lower = content.lower()
    for b in bandi:
        d = b.get("data", b)
        titolo = (d.get("titolo") or d.get("nome") or "").lower()
        keywords = [w for w in titolo.split() if len(w) > 5]
        if any(kw in content_lower for kw in keywords[:3]):
            impactati.append(d.get("id") or b.get("id", ""))
    return impactati[:5]


def register_regulatory_endpoints(app):
    """Registra endpoint nel FastAPI app."""

    @app.get("/api/regulatory/changes")
    async def get_regulatory_changes(request: Request, limit: int = 20, solo_non_letti: bool = False):
        user_token = request.headers.get("X-Auth-Token")
        if not user_token:
            return JSONResponse({"ok": False, "error": "Non autenticato"}, status_code=401)

        async with aiosqlite.connect(DB()) as db:
            db.row_factory = aiosqlite.Row
            q = "SELECT * FROM regulatory_changes"
            params = []
            if solo_non_letti:
                q += " WHERE letto=0"
            q += " ORDER BY rilevato_at DESC LIMIT ?"
            params.append(limit)
            async with db.execute(q, params) as c:
                rows = [dict(r) for r in await c.fetchall()]
            for r in rows:
                try:
                    r["bandi_impattati"] = json.loads(r["bandi_impattati"])
                except Exception:
                    r["bandi_impattati"] = []

            async with db.execute("SELECT COUNT(*) FROM regulatory_changes WHERE letto=0") as c:
                unread = (await c.fetchone())[0]

        return {"ok": True, "changes": rows, "unread": unread}

    @app.post("/api/regulatory/scan")
    async def trigger_scan(request: Request):
        user_token = request.headers.get("X-Auth-Token")
        if not user_token:
            return JSONResponse({"ok": False, "error": "Non autenticato"}, status_code=401)

        # Recupera bandi attivi dal DB
        async with aiosqlite.connect(DB()) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT id, data FROM bandi WHERE deleted_at IS NULL LIMIT 50"
            ) as c:
                bandi = [{"id": r["id"], "data": json.loads(r["data"])} for r in await c.fetchall()]

        changes = await scan_regulatory_changes(bandi)
        return {
            "ok": True,
            "scanned": len(REGULATORY_SOURCES),
            "changes_found": len(changes),
            "changes": changes,
            "timestamp": datetime.datetime.utcnow().isoformat()
        }

    @app.post("/api/regulatory/mark-read/{change_id}")
    async def mark_change_read(change_id: str, request: Request):
        user_token = request.headers.get("X-Auth-Token")
        if not user_token:
            return JSONResponse({"ok": False, "error": "Non autenticato"}, status_code=401)
        async with aiosqlite.connect(DB()) as db:
            await db.execute("UPDATE regulatory_changes SET letto=1 WHERE id=?", (change_id,))
            await db.commit()
        return {"ok": True}

    @app.get("/api/regulatory/sources")
    async def get_sources(request: Request):
        return {"ok": True, "sources": REGULATORY_SOURCES, "total": len(REGULATORY_SOURCES)}
