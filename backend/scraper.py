"""
BA.IA — Scraper Bandi Italiani v1.0
Monitora automaticamente le principali fonti italiane di finanza agevolata.

Fonti monitorate:
  - Invitalia (incentivi imprese)
  - MIMIT (Ministero Imprese)
  - SIMEST (internazionalizzazione)
  - CDP (Cassa Depositi e Prestiti)
  - Unioncamere
  - Regione Sardegna (pilota)
  - Regione Lombardia
  - Regione Lazio
  - Regione Campania
  - Regione Sicilia
  - Regione Veneto
  - Regione Toscana
  - Regione Emilia-Romagna
  - Fondazione per il Sud
  - PNRR Monitor (centrostudifinanza.it)

Ogni run: GET pagina → hash → se nuovo → estrai PDF/link → analizza AI → salva DB.
Schedule: ogni 24h alle 03:00 CET + trigger manuale via API.
"""

import os, re, json, hashlib, asyncio, datetime, tempfile
from pathlib import Path
from typing import Optional
import httpx
from bs4 import BeautifulSoup

# ── FONTI ─────────────────────────────────────────────────
SOURCES = [
    # Fonti nazionali
    {
        "id": "invitalia",
        "nome": "Invitalia",
        "url": "https://www.invitalia.it/cosa-facciamo/rafforziamo-le-imprese",
        "tipo": "html",
        "regioni": [],
        "pdf_selector": "a[href$='.pdf']",
        "link_selector": ".news-item a, .incentivo-card a, article a",
    },
    {
        "id": "mimit",
        "nome": "MIMIT — Incentivi",
        "url": "https://www.mimit.gov.it/index.php/it/incentivi",
        "tipo": "html",
        "regioni": [],
        "pdf_selector": "a[href$='.pdf']",
        "link_selector": ".incentivi-list a, .news-link",
    },
    {
        "id": "simest",
        "nome": "SIMEST",
        "url": "https://www.simest.it/finanziamenti-e-cofinanziamenti",
        "tipo": "html",
        "regioni": [],
        "pdf_selector": "a[href$='.pdf']",
        "link_selector": "a.btn, .card a, article a",
    },
    {
        "id": "cdp",
        "nome": "CDP — Imprese",
        "url": "https://www.cdp.it/clienti/imprese/finanziamenti",
        "tipo": "html",
        "regioni": [],
        "pdf_selector": "a[href$='.pdf']",
        "link_selector": ".product-card a, .incentivo a",
    },
    {
        "id": "unioncamere",
        "nome": "Unioncamere — Bandi",
        "url": "https://www.unioncamere.gov.it/P42A3498C160S123/bandi.htm",
        "tipo": "html",
        "regioni": [],
        "pdf_selector": "a[href$='.pdf']",
        "link_selector": ".lista-bandi a, table a",
    },
    # Fonti regionali
    {
        "id": "sardegna",
        "nome": "Regione Sardegna",
        "url": "https://www.regione.sardegna.it/j/v/2537?s=1&v=9&c=1031&t=1",
        "tipo": "html",
        "regioni": ["sardegna"],
        "pdf_selector": "a[href$='.pdf']",
        "link_selector": ".news a, .bando a, .documento a",
    },
    {
        "id": "lombardia",
        "nome": "Regione Lombardia",
        "url": "https://www.regione.lombardia.it/wps/portal/istituzionale/HP/DettaglioServizi/servizi-e-informazioni/Imprese/Agevolazioni-e-contributi",
        "tipo": "html",
        "regioni": ["lombardia"],
        "pdf_selector": "a[href$='.pdf']",
        "link_selector": ".news-teaser a, .card a",
    },
    {
        "id": "lazio",
        "nome": "Lazio Innova",
        "url": "https://www.lazioinnova.it/bandi/",
        "tipo": "html",
        "regioni": ["lazio"],
        "pdf_selector": "a[href$='.pdf']",
        "link_selector": ".bando-card a, article a",
    },
    {
        "id": "campania",
        "nome": "Regione Campania — FESR",
        "url": "https://www.regione.campania.it/regione/it/tematiche/fondi-europei",
        "tipo": "html",
        "regioni": ["campania"],
        "pdf_selector": "a[href$='.pdf']",
        "link_selector": ".news a, .bando a",
    },
    {
        "id": "toscana",
        "nome": "Sviluppo Toscana",
        "url": "https://www.sviluppo.toscana.it/bandi",
        "tipo": "html",
        "regioni": ["toscana"],
        "pdf_selector": "a[href$='.pdf']",
        "link_selector": ".bandi-list a, .card-bando a",
    },
    {
        "id": "emiliaromagna",
        "nome": "Regione Emilia-Romagna",
        "url": "https://www.regione.emilia-romagna.it/bandi-finanziamenti",
        "tipo": "html",
        "regioni": ["emilia-romagna"],
        "pdf_selector": "a[href$='.pdf']",
        "link_selector": ".news-item a, article a",
    },
    {
        "id": "veneto",
        "nome": "Regione Veneto — Bandi",
        "url": "https://bandi.regione.veneto.it/Public/Iniziative/RicercaAvanzata",
        "tipo": "html",
        "regioni": ["veneto"],
        "pdf_selector": "a[href$='.pdf']",
        "link_selector": ".bando-link a, table a",
    },
]

# ── FONTI ESTESE (da "monitoraggio siti bandi/siti da monitorare.xlsx") ──
# Generate in backend/scraper_sources.json. Si fondono con le fonti curate
# sopra (che hanno selettori ottimizzati); le nuove usano selettori generici.
def _load_extra_sources() -> list:
    path = os.path.join(os.path.dirname(__file__), "scraper_sources.json")
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"[SCRAPER] scraper_sources.json non caricato: {e}")
        return []

def _merge_sources(curated: list, extra: list) -> list:
    from urllib.parse import urlparse
    def _key(u):
        try:
            p = urlparse(u)
            return (p.netloc.lower().lstrip("www."), p.path.rstrip("/").lower())
        except Exception:
            return (u, "")
    seen = {_key(s["url"]) for s in curated}
    merged = list(curated)
    for s in extra:
        u = s.get("url", "")
        k = _key(u)
        if not u or k in seen:
            continue
        seen.add(k)
        s.setdefault("tipo", "html")
        s.setdefault("regioni", [])
        s.setdefault("pdf_selector", "a[href$='.pdf']")
        s.setdefault("link_selector", "a")   # generico: i link sono filtrati per keyword
        merged.append(s)
    return merged

SOURCES = _merge_sources(SOURCES, _load_extra_sources())
print(f"[SCRAPER] {len(SOURCES)} fonti monitorate")

# Limite di nuovi bandi analizzati per run (controllo costi AI; override via env).
MAX_NEW_PER_RUN = int(os.getenv("SCRAPER_MAX_NEW_PER_RUN", "60") or 60)

# User-Agent browser realistico: molti siti PA bloccano gli UA "bot".
BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")
# Parole-chiave che identificano un link/pagina di bando.
BANDO_KW = ["bando", "contribut", "agevolaz", "incentiv", "finanziament", "avviso",
            "misura", "fondo", "grant", "voucher", "bonus", "sovvenzion", "credito",
            "aiuti", "dote", "sostegno", "sportello", "callforproposal", "call-for"]

# ── SCRAPER STATE ─────────────────────────────────────────
_state = {
    "running": False,
    "last_run": None,
    "last_run_results": [],
    "total_scraped": 0,
    "total_new": 0,
    "errors": [],
}

def get_status() -> dict:
    return {
        "running": _state["running"],
        "last_run": _state["last_run"],
        "total_scraped": _state["total_scraped"],
        "total_new": _state["total_new"],
        "recent_results": _state["last_run_results"][-20:],
        "sources": len(SOURCES),
        "errors": _state["errors"][-5:],
        "schedule": "Ogni 24h alle 03:00 CET + trigger manuale",
    }

# ── HELPERS ───────────────────────────────────────────────
def _hash(text: str) -> str:
    return hashlib.md5(text.encode("utf-8", errors="ignore")).hexdigest()

def _uid() -> str:
    import secrets, time
    return datetime.datetime.utcnow().strftime("%Y%m%d") + secrets.token_hex(5)

async def _fetch(url: str, timeout: int = 20) -> Optional[str]:
    """Fetch HTML con retry e user-agent realistico."""
    headers = {
        "User-Agent": BROWSER_UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "it-IT,it;q=0.9,en;q=0.5",
    }
    for attempt in range(3):
        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=True,
                headers=headers,
                verify=False,  # alcuni siti PA hanno certificati problematici
            ) as client:
                r = await client.get(url)
                if r.status_code == 200:
                    return r.text
                if r.status_code == 429:
                    await asyncio.sleep(30 * (attempt + 1))
        except Exception as e:
            if attempt < 2:
                await asyncio.sleep(5 * (attempt + 1))
            else:
                raise
    return None

async def _fetch_pdf_bytes(url: str, timeout: int = 30) -> Optional[bytes]:
    headers = {"User-Agent": BROWSER_UA}
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True,
                                     headers=headers, verify=False) as client:
            r = await client.get(url)
            if r.status_code == 200 and "pdf" in r.headers.get("content-type", "").lower():
                return r.content
    except Exception:
        pass
    return None

def _extract_pdf_text(pdf_bytes: bytes) -> str:
    try:
        from pypdf import PdfReader
        import io
        reader = PdfReader(io.BytesIO(pdf_bytes))
        return "".join(p.extract_text() or "" for p in reader.pages[:30])
    except Exception:
        return ""

def _make_absolute(url: str, base: str) -> str:
    if url.startswith("http"):
        return url
    from urllib.parse import urljoin
    return urljoin(base, url)

def _html_to_text(html: str) -> str:
    """Testo visibile di una pagina HTML (per analizzare i bandi pubblicati come pagina)."""
    try:
        soup = BeautifulSoup(html, "lxml")
        for t in soup(["script", "style", "nav", "header", "footer", "noscript", "svg"]):
            t.extract()
        return re.sub(r"\n{3,}", "\n\n", soup.get_text("\n", strip=True))
    except Exception:
        return ""

def _extract_links_and_pdfs(html: str, source: dict) -> tuple[list[str], list[str]]:
    """Estrae link a PDF e link a pagine-bando. Matching su testo del link E href."""
    from urllib.parse import urlparse
    soup = BeautifulSoup(html, "lxml")
    base = source["url"]
    base_dom = urlparse(base).netloc.lower().lstrip("www.")
    pdf_links, page_links = [], []
    for a in soup.find_all("a", href=True):
        href = (a.get("href") or "").strip()
        if not href or href.startswith(("javascript", "#", "mailto", "tel")):
            continue
        low = href.lower()
        absu = _make_absolute(href, base)
        if ".pdf" in low:
            pdf_links.append(absu)
            continue
        text = a.get_text(strip=True).lower()
        if (len(text) > 8 and any(k in text for k in BANDO_KW)) or any(k in low for k in BANDO_KW):
            dom = urlparse(absu).netloc.lower().lstrip("www.")
            if dom in (base_dom, ""):   # solo pagine dello stesso dominio
                page_links.append(absu)
    return list(dict.fromkeys(pdf_links))[:10], list(dict.fromkeys(page_links))[:12]

async def _analyze_text(text: str, source_name: str, title_hint: str = "") -> Optional[dict]:
    """Analizza testo bando con AI e ritorna struttura."""
    if len(text) < 200:
        return None
    try:
        from app_locale import ai_call_multi
    except Exception as _e:
        print(f"[SCRAPER] ai_call_multi non disponibile: {_e}")
        return None

    prompt = (
        f"Sei un esperto di finanza agevolata italiana. Dal seguente testo estratto "
        f"da '{source_name}', estrai le informazioni del bando come JSON. "
        f"Rispondi SOLO con JSON valido, zero testo aggiuntivo:\n"
        '{"nome":"","ente":"","scadenza":"YYYY-MM-DD o null","dotazione":"","contributo_max":"",'
        '"percentuale":"","beneficiari":"","ateco_ammessi":"","regioni":[],'
        '"spese_ammissibili":"","regime_aiuti":"","link_ufficiale":"","descrizione":""}\n\n'
        f"TESTO ({len(text)} car):\n{text[:6000]}"
    )
    try:
        result, _ = await ai_call_multi(prompt, json_mode=True, timeout=90)
        clean = result.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        data = json.loads(clean)
        # Usa title_hint se il nome estratto è vuoto
        if not data.get("nome") and title_hint:
            data["nome"] = title_hint
        return data
    except Exception as e:
        print(f"[SCRAPER] AI parse error: {e}")
        return None

# ── CORE SCRAPE FUNCTION ──────────────────────────────────

async def _save_bando(ai_data: dict, source: dict, source_url: str,
                      content_hash: str, text_len: int, db_path: str) -> bool:
    """Costruisce e salva un bando nel DB. Ritorna True se salvato."""
    import aiosqlite
    nome = (ai_data.get("nome") or "").strip() or f"Bando {source['nome']} {datetime.date.today()}"
    is_pdf = ".pdf" in source_url.lower()
    bando_obj = {
        "id": _uid(), "name": nome,
        "ente": ai_data.get("ente") or source["nome"],
        "scadenza": ai_data.get("scadenza"),
        "regioni": ai_data.get("regioni") or source.get("regioni", []),
        "source_url": source_url, "source_id": source["id"], "source_hash": content_hash,
        "scraped": True,
        "pdfs": [{
            "id": _uid(),
            "name": (source_url.split("/")[-1] or "bando.pdf") if is_pdf else "pagina-web",
            "uploadedAt": datetime.datetime.utcnow().isoformat(),
            "analyzed": True, "textLength": text_len,
            "analysis": f"Bando: {nome}\nEnte: {ai_data.get('ente','')}\n"
                        f"Scadenza: {ai_data.get('scadenza','n/d')}\n"
                        f"Contributo max: {ai_data.get('contributo_max','n/d')}\n"
                        f"Beneficiari: {ai_data.get('beneficiari','n/d')}\n"
                        f"Descrizione: {ai_data.get('descrizione','n/d')}",
            "checklist": [],
        }],
        "fields": _ai_data_to_fields(ai_data),
        "note": f"Importato automaticamente dallo scraper il {datetime.date.today()} — fonte: {source_url}",
        "status": "active",
        "createdAt": datetime.datetime.utcnow().isoformat(),
        "updatedAt": datetime.datetime.utcnow().isoformat(),
    }
    now_str = datetime.datetime.utcnow().isoformat()
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO bandi (id,data,created_at,updated_at) VALUES (?,?,?,?)",
            (bando_obj["id"], json.dumps(bando_obj), now_str, now_str))
        await db.commit()
    return True

async def scrape_source(source: dict, db_path: str) -> dict:
    """Scrapa una singola fonte. Ritorna report."""
    result = {
        "source_id": source["id"],
        "nome": source["nome"],
        "new": 0, "updated": 0, "skipped": 0, "errors": 0,
        "ts": datetime.datetime.utcnow().isoformat(),
    }
    try:
        html = await _fetch(source["url"], timeout=25)
        if not html:
            result["errors"] += 1
            result["error_msg"] = "Nessuna risposta HTTP"
            return result

        page_hash = _hash(html)
        # Controlla se la pagina è cambiata
        import aiosqlite
        async with aiosqlite.connect(db_path) as db:
            await db.execute("""CREATE TABLE IF NOT EXISTS scraper_log (
                source_id TEXT PRIMARY KEY, last_hash TEXT, last_run TEXT, total_new INT DEFAULT 0)""")
            await db.commit()
            async with db.execute(
                "SELECT last_hash FROM scraper_log WHERE source_id=?", (source["id"],)
            ) as cur:
                row = await cur.fetchone()

        if row and row[0] == page_hash:
            result["skipped"] = 1
            return result  # Pagina invariata

        pdf_links, page_links = _extract_links_and_pdfs(html, source)
        print(f"[SCRAPER] {source['nome']}: {len(pdf_links)} PDF, {len(page_links)} link pagine")

        import aiosqlite
        async def _process(text: str, source_url: str) -> bool:
            """Dedup + AI + salvataggio. Ritorna True se nuovo bando salvato."""
            if not text or len(text) < 350:
                return False
            content_hash = _hash(text)
            async with aiosqlite.connect(db_path) as db:
                async with db.execute(
                    "SELECT id FROM bandi WHERE JSON_EXTRACT(data,'$.source_hash')=?",
                    (content_hash,)) as cur:
                    if await cur.fetchone():
                        return False
            ai_data = await _analyze_text(text, source["nome"])
            if not ai_data or not (ai_data.get("nome") or "").strip():
                return False
            await _save_bando(ai_data, source, source_url, content_hash, len(text), db_path)
            result["new"] += 1
            _state["total_new"] += 1
            _state["run_new"] = _state.get("run_new", 0) + 1
            print(f"[SCRAPER] ✅ Nuovo bando: {ai_data.get('nome')}")
            await asyncio.sleep(2)
            return True

        # 1) PDF diretti sulla pagina fonte
        for pdf_url in pdf_links[:5]:
            if _state.get("run_new", 0) >= MAX_NEW_PER_RUN:
                break
            try:
                pdf_bytes = await _fetch_pdf_bytes(pdf_url)
                if pdf_bytes:
                    await _process(_extract_pdf_text(pdf_bytes), pdf_url)
            except Exception as e:
                print(f"[SCRAPER] Errore PDF {pdf_url[:60]}: {e}")
                result["errors"] += 1

        # 2) Pagine-bando HTML (molti bandi non sono PDF ma pagine web)
        for page_url in page_links[:6]:
            if _state.get("run_new", 0) >= MAX_NEW_PER_RUN:
                break
            try:
                sub_html = await _fetch(page_url, timeout=20)
                if not sub_html:
                    continue
                sub_pdfs, _ = _extract_links_and_pdfs(sub_html, {"url": page_url})
                done = False
                if sub_pdfs:
                    pb = await _fetch_pdf_bytes(sub_pdfs[0])
                    if pb:
                        done = await _process(_extract_pdf_text(pb), sub_pdfs[0])
                if not done:
                    await _process(_html_to_text(sub_html), page_url)
            except Exception as e:
                print(f"[SCRAPER] Errore pagina {page_url[:60]}: {e}")
                result["errors"] += 1

        # Aggiorna log
        async with aiosqlite.connect(db_path) as db:
            await db.execute(
                "INSERT INTO scraper_log (source_id,last_hash,last_run,total_new) VALUES (?,?,?,?) "
                "ON CONFLICT(source_id) DO UPDATE SET last_hash=excluded.last_hash,"
                "last_run=excluded.last_run,total_new=total_new+excluded.total_new",
                (source["id"], page_hash, datetime.datetime.utcnow().isoformat(), result["new"])
            )
            await db.commit()
        _state["total_scraped"] += 1

    except Exception as e:
        result["errors"] += 1
        result["error_msg"] = str(e)[:200]
        print(f"[SCRAPER] Errore fonte {source['nome']}: {e}")

    return result

def _ai_data_to_fields(ai_data: dict) -> list[dict]:
    """Converte output AI in lista campi strutturati."""
    mapping = [
        ("nome", "Titolo bando", "Identificazione"),
        ("ente", "Ente erogatore", "Identificazione"),
        ("scadenza", "Scadenza", "Scadenze"),
        ("dotazione", "Dotazione finanziaria", "Importi"),
        ("contributo_max", "Contributo massimo", "Importi"),
        ("percentuale", "Percentuale contributo", "Importi"),
        ("beneficiari", "Beneficiari", "Ammissibilità"),
        ("ateco_ammessi", "Codici ATECO ammessi", "Ammissibilità"),
        ("spese_ammissibili", "Spese ammissibili", "Requisiti"),
        ("regime_aiuti", "Regime aiuti di stato", "Requisiti"),
        ("descrizione", "Descrizione", "Identificazione"),
    ]
    fields = []
    for key, label, section in mapping:
        val = ai_data.get(key)
        if val and str(val).strip() and str(val) != "null":
            fields.append({"section": section, "label": label, "value": str(val),
                           "source": "scraper", "confidenza": "media"})
    return fields

# ── SCHEDULER ─────────────────────────────────────────────

_scheduler = None

def get_scheduler():
    global _scheduler
    if _scheduler is None:
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger
        _scheduler = AsyncIOScheduler(timezone="Europe/Rome")
    return _scheduler

async def run_all_sources(db_path: str, max_sources: int = None) -> list[dict]:
    """Scrapa tutte le fonti. Chiamato dallo scheduler o manualmente."""
    if _state["running"]:
        return [{"error": "Scraper già in esecuzione"}]

    _state["running"] = True
    _state["last_run"] = datetime.datetime.utcnow().isoformat()
    _state["run_new"] = 0
    sources = SOURCES if max_sources is None else SOURCES[:max_sources]
    results = []

    print(f"[SCRAPER] Avvio — {len(sources)} fonti")
    for source in sources:
        if _state.get("run_new", 0) >= MAX_NEW_PER_RUN:
            print(f"[SCRAPER] Cap {MAX_NEW_PER_RUN} nuovi bandi/run raggiunto — stop")
            break
        result = await scrape_source(source, db_path)
        results.append(result)
        _state["last_run_results"].append(result)
        # Pausa tra fonti per non sovraccaricare
        await asyncio.sleep(5)

    _state["running"] = False
    total_new = sum(r.get("new", 0) for r in results)
    print(f"[SCRAPER] Completato — {total_new} nuovi bandi trovati")
    return results

def start_scheduler(db_path: str):
    """Avvia lo scheduler APScheduler per il run automatico ogni 24h."""
    sched = get_scheduler()
    if sched.running:
        return
    from apscheduler.triggers.cron import CronTrigger
    sched.add_job(
        lambda: asyncio.ensure_future(run_all_sources(db_path)),
        trigger=CronTrigger(hour=3, minute=0, timezone="Europe/Rome"),
        id="scrape_all",
        replace_existing=True,
        misfire_grace_time=3600,
    )
    # Job cleanup bandi scaduti (ogni 6h)
    sched.add_job(
        lambda: asyncio.ensure_future(_cleanup_expired(db_path)),
        trigger=CronTrigger(hour="*/6", timezone="Europe/Rome"),
        id="cleanup_expired",
        replace_existing=True,
    )
    sched.start()
    print("[SCRAPER] Scheduler avviato — run automatico alle 03:00 CET")

async def _cleanup_expired(db_path: str):
    """Marca come non attivi i bandi con scadenza passata."""
    import aiosqlite
    today = datetime.date.today().isoformat()
    try:
        async with aiosqlite.connect(db_path) as db:
            async with db.execute("SELECT id, data FROM bandi") as cur:
                rows = await cur.fetchall()
            updated = 0
            for row_id, data_str in rows:
                try:
                    d = json.loads(data_str)
                    scad = d.get("scadenza", "")
                    if scad and scad < today and d.get("status") == "active":
                        d["status"] = "expired"
                        await db.execute(
                            "UPDATE bandi SET data=? WHERE id=?",
                            (json.dumps(d), row_id)
                        )
                        updated += 1
                except Exception:
                    pass
            await db.commit()
        if updated:
            print(f"[SCRAPER] {updated} bandi marcati come scaduti")
    except Exception as e:
        print(f"[SCRAPER] Cleanup error: {e}")
