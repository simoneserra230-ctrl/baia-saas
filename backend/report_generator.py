"""
BA.IA — Natural Language Report Generator (D1.2)
Genera report testuali in linguaggio naturale: portfolio bandi, stato SAL,
compliance check, forecast scadenze.

Endpoint: POST /api/report/generate
Output: testo strutturato + sezioni JSON + PDF export
"""

import os, json, datetime
from typing import Optional
import aiosqlite
from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel
import httpx

DB = lambda: os.environ.get("DB_PATH", "./data/ai-bandi.db")
ANTHROPIC_API_KEY = lambda: os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("AI_API_KEY", "")
MODEL = lambda: os.environ.get("AI_MODEL", "claude-haiku-4-5-20251001")


class ReportRequest(BaseModel):
    tipo: str = "portfolio"          # portfolio | compliance | sal | forecast | executive
    periodo: Optional[str] = None    # "2026-Q1", "2026", "ultimi-30"
    azienda_nome: Optional[str] = None
    include_grafici: bool = False
    lingua: str = "it"


async def _get_report_context(tipo: str) -> dict:
    """Raccoglie dati rilevanti dal DB in base al tipo di report."""
    ctx: dict = {"tipo": tipo, "generato_il": datetime.datetime.utcnow().isoformat()}

    async with aiosqlite.connect(DB()) as db:
        db.row_factory = aiosqlite.Row

        # Bandi
        async with db.execute(
            "SELECT id, data, created_at FROM bandi WHERE deleted_at IS NULL ORDER BY updated_at DESC LIMIT 30"
        ) as c:
            bandi_rows = [{"id": r["id"], **json.loads(r["data"])} for r in await c.fetchall()]
        ctx["bandi"] = bandi_rows
        ctx["totale_bandi"] = len(bandi_rows)

        # Aziende
        async with db.execute(
            "SELECT id, data FROM aziende WHERE deleted_at IS NULL ORDER BY updated_at DESC LIMIT 10"
        ) as c:
            ctx["aziende"] = [{"id": r["id"], **json.loads(r["data"])} for r in await c.fetchall()]

        # Match history
        async with db.execute(
            "SELECT id, data, created_at FROM match_history ORDER BY created_at DESC LIMIT 20"
        ) as c:
            ctx["match_history"] = [{"id": r["id"], **json.loads(r["data"])} for r in await c.fetchall()]

        # SAL / rendicontazioni
        try:
            async with db.execute(
                "SELECT * FROM rendicontazioni ORDER BY created_at DESC LIMIT 10"
            ) as c:
                ctx["rendicontazioni"] = [dict(r) for r in await c.fetchall()]
        except Exception:
            ctx["rendicontazioni"] = []

    return ctx


def _build_local_report(ctx: dict, tipo: str) -> str:
    """Genera report locale senza AI (fallback)."""
    bandi = ctx.get("bandi", [])
    aziende = ctx.get("aziende", [])
    match_hist = ctx.get("match_history", [])
    sal = ctx.get("rendicontazioni", [])
    now = ctx.get("generato_il", datetime.datetime.utcnow().isoformat())

    if tipo == "portfolio":
        stati = {}
        for b in bandi:
            s = b.get("stato", "non definito")
            stati[s] = stati.get(s, 0) + 1

        scaduti = [b for b in bandi if b.get("scadenza") and b["scadenza"] < now[:10]]
        imminenti = [b for b in bandi if b.get("scadenza") and now[:10] <= b["scadenza"] <= (datetime.datetime.utcnow() + datetime.timedelta(days=30)).strftime("%Y-%m-%d")]

        lines = [
            f"REPORT PORTFOLIO BANDI — {now[:10]}",
            f"{'='*50}",
            f"\nRIEPILOGO",
            f"Totale bandi in portafoglio: {len(bandi)}",
            f"Aziende profilate: {len(aziende)}",
            f"Match storici: {len(match_hist)}",
            f"\nDISTRIBUZIONE PER STATO",
        ]
        for s, n in stati.items():
            lines.append(f"  • {s.title()}: {n} bandi")

        if imminenti:
            lines.append(f"\nSCADENZE IMMINENTI (30 giorni)")
            for b in imminenti[:5]:
                lines.append(f"  ⚠ {b.get('titolo','—')} — scade il {b['scadenza']}")

        if scaduti:
            lines.append(f"\nBandi scaduti recentemente: {len(scaduti)}")

        if aziende:
            lines.append(f"\nAZIENDE IN PORTAFOGLIO")
            for a in aziende[:5]:
                lines.append(f"  • {a.get('nome') or a.get('ragione_sociale','Azienda senza nome')}")

        lines.append(f"\n{'='*50}")
        lines.append("Report generato da BA.IA — Finanza Agevolata AI")
        return "\n".join(lines)

    elif tipo == "sal":
        lines = [
            f"REPORT STATO SAL — {now[:10]}",
            f"{'='*50}",
            f"\nRendicontazioni attive: {len(sal)}",
        ]
        for r in sal[:10]:
            pct = 0
            if r.get("importo_approvato") and r["importo_approvato"] > 0:
                pct = round((r.get("importo_rendicontato", 0) / r["importo_approvato"]) * 100, 1)
            lines.append(f"\n  📋 {r.get('titolo','—')}")
            lines.append(f"     Stato: {r.get('stato','—')} | Avanzamento: {pct}%")
            lines.append(f"     Importo approvato: € {r.get('importo_approvato',0):,.2f}")
            if r.get("data_scadenza_sal"):
                lines.append(f"     Scadenza SAL: {r['data_scadenza_sal']}")
        lines.append(f"\n{'='*50}")
        lines.append("Report generato da BA.IA — Finanza Agevolata AI")
        return "\n".join(lines)

    elif tipo == "forecast":
        lines = [
            f"FORECAST SCADENZE — {now[:10]}",
            f"{'='*50}",
            "\nProssimi 90 giorni:",
        ]
        oggi = datetime.date.today()
        for b in sorted(bandi, key=lambda x: x.get("scadenza") or "9999"):
            scad = b.get("scadenza")
            if not scad: continue
            try:
                d = datetime.date.fromisoformat(scad)
                delta = (d - oggi).days
                if 0 <= delta <= 90:
                    urg = "🔴" if delta < 14 else "🟡" if delta < 30 else "🟢"
                    lines.append(f"  {urg} {b.get('titolo','—')[:50]} — {scad} ({delta}gg)")
            except Exception:
                pass
        if len(lines) <= 4:
            lines.append("  Nessuna scadenza nei prossimi 90 giorni.")
        lines.append(f"\n{'='*50}")
        lines.append("Report generato da BA.IA — Finanza Agevolata AI")
        return "\n".join(lines)

    else:  # executive
        importo_tot = sum(float(b.get("importo_max") or b.get("budget") or 0) for b in bandi)
        lines = [
            f"EXECUTIVE SUMMARY — {now[:10]}",
            f"{'='*50}",
            f"\nPortafoglio totale: {len(bandi)} bandi | {len(aziende)} aziende",
            f"Valore opportunità: € {importo_tot:,.0f}",
            f"Match effettuati: {len(match_hist)}",
            f"Pratiche SAL: {len(sal)}",
            f"\nDimensionamento: il portafoglio BA.IA è operativo e monitorato.",
            f"\n{'='*50}",
            "Report generato da BA.IA — Finanza Agevolata AI",
        ]
        return "\n".join(lines)


async def _ai_report(ctx: dict, tipo: str, azienda_nome: str, lingua: str) -> str:
    """Genera report con AI Anthropic."""
    bandi_summary = "\n".join(
        f"- {b.get('titolo','?')[:60]} | Stato: {b.get('stato','?')} | Scadenza: {b.get('scadenza','N/A')} | Importo max: {b.get('importo_max','?')}"
        for b in ctx["bandi"][:15]
    )
    sal_summary = "\n".join(
        f"- {r.get('titolo','?')[:50]} | Stato: {r.get('stato','?')} | Approvato: € {r.get('importo_approvato',0):,.0f} | Rendicontato: € {r.get('importo_rendicontato',0):,.0f}"
        for r in ctx["rendicontazioni"][:5]
    )

    tipo_map = {
        "portfolio": "analisi completa del portfolio bandi",
        "sal": "stato avanzamento lavori e rendicontazioni",
        "forecast": "forecast scadenze e priorità dei prossimi 90 giorni",
        "compliance": "compliance check rispetto ai requisiti dei bandi",
        "executive": "executive summary per la direzione aziendale",
    }

    prompt = (
        f"Sei un consulente esperto di finanza agevolata italiana. "
        f"Genera un report professionale di {tipo_map.get(tipo, tipo)} "
        f"per {azienda_nome or 'azienda cliente'} in lingua {'italiana' if lingua == 'it' else 'inglese'}.\n\n"
        f"DATI PORTAFOGLIO BANDI:\n{bandi_summary or 'Nessun bando in portafoglio.'}\n\n"
        f"PRATICHE SAL:\n{sal_summary or 'Nessuna pratica SAL attiva.'}\n\n"
        f"Struttura il report con: Riepilogo Esecutivo, Analisi Dettagliata, Priorità d'Azione, Raccomandazioni. "
        f"Usa dati concreti. Lunghezza: 400-600 parole."
    )

    api_key = ANTHROPIC_API_KEY()
    if not api_key:
        return _build_local_report(ctx, tipo)

    try:
        async with httpx.AsyncClient(timeout=60) as client:
            r = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
                json={"model": MODEL(), "max_tokens": 2048, "messages": [{"role": "user", "content": prompt}]}
            )
        if r.status_code == 200:
            return r.json()["content"][0]["text"]
        return _build_local_report(ctx, tipo)
    except Exception:
        return _build_local_report(ctx, tipo)


def register_report_endpoints(app):

    @app.post("/api/report/generate")
    async def generate_report(req: ReportRequest, request: Request):
        token = request.headers.get("X-Auth-Token")
        if not token:
            return JSONResponse({"ok": False, "error": "Non autenticato"}, status_code=401)

        ctx = await _get_report_context(req.tipo)
        testo = await _ai_report(ctx, req.tipo, req.azienda_nome or "", req.lingua)

        return {
            "ok": True,
            "tipo": req.tipo,
            "periodo": req.periodo,
            "generato_il": ctx["generato_il"],
            "stats": {
                "bandi": ctx["totale_bandi"],
                "aziende": len(ctx["aziende"]),
                "match": len(ctx["match_history"]),
                "sal": len(ctx["rendicontazioni"]),
            },
            "report_text": testo,
        }

    @app.get("/api/report/tipi")
    async def get_report_types():
        return {"ok": True, "tipi": [
            {"id": "portfolio", "label": "Portfolio Bandi", "descrizione": "Analisi completa del portafoglio bandi attivi"},
            {"id": "sal", "label": "Stato SAL", "descrizione": "Avanzamento pratiche di rendicontazione"},
            {"id": "forecast", "label": "Forecast Scadenze", "descrizione": "Prossime scadenze e priorità azione"},
            {"id": "compliance", "label": "Compliance Check", "descrizione": "Verifica conformità requisiti bandi"},
            {"id": "executive", "label": "Executive Summary", "descrizione": "Riepilogo per direzione aziendale"},
        ]}

    # SOP Generator (B2.8) — integrato qui per completezza
    @app.post("/api/bando/sop-guida")
    async def genera_sop_bando(request: Request):
        token = request.headers.get("X-Auth-Token")
        if not token:
            return JSONResponse({"ok": False, "error": "Non autenticato"}, status_code=401)

        body = await request.json()
        bando_titolo = body.get("bando_titolo", "")
        bando_id = body.get("bando_id")
        settore = body.get("settore", "Hospitality / F&B")
        tipo_azienda = body.get("tipo_azienda", "PMI")
        importo_max = body.get("importo_max", "non specificato")
        scadenza = body.get("scadenza", "non specificata")
        ente = body.get("ente", "ente erogatore")

        # Recupera testo bando dal DB se bando_id fornito
        bando_testo = ""
        if bando_id:
            async with aiosqlite.connect(DB()) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute("SELECT data FROM bandi WHERE id=?", (bando_id,)) as c:
                    row = await c.fetchone()
                if row:
                    d = json.loads(row["data"])
                    bando_testo = d.get("analisi") or d.get("testo") or json.dumps(d)[:1500]

        # Template SOP locale (fallback)
        def _local_sop():
            return {
                "titolo": f"Guida Presentazione Domanda — {bando_titolo or 'Bando'}",
                "ente": ente,
                "scadenza": scadenza,
                "importo_max": importo_max,
                "settore": settore,
                "fasi": [
                    {"n": 1, "fase": "Verifica requisiti di ammissibilità", "durata": "1-2 giorni",
                     "attivita": ["Controllare codici ATECO ammessi", "Verificare dimensione aziendale (PMI/grande impresa)", "Controllare requisiti di regolarità contributiva (DURC)", "Verificare assenza procedura concorsuale"],
                     "documenti": ["Visura camerale aggiornata", "Statuto aziendale", "Ultimo bilancio depositato"]},
                    {"n": 2, "fase": "Raccolta documentazione", "durata": "3-5 giorni",
                     "attivita": ["Preparare piano investimenti dettagliato", "Raccogliere preventivi fornitori (min. 3 preventivi per importi > 5.000€)", "Predisporre relazione tecnica progetto", "Ottenere DURC in corso di validità"],
                     "documenti": ["Piano investimenti con dettaglio voci di spesa", "Preventivi fornitori", "Relazione tecnica/business plan", "DURC valido (< 90 giorni)", "Dichiarazioni antimafia se richieste"]},
                    {"n": 3, "fase": "Compilazione domanda", "durata": "1-2 giorni",
                     "attivita": [f"Accedere al portale {ente}", "Compilare tutti i campi obbligatori", "Caricare i documenti in formato PDF/A", "Verificare firma digitale CRS/CNS", "Salvare bozza e verificare completezza"],
                     "documenti": ["Domanda compilata sul portale", "Documenti allegati verificati", "Firma digitale attiva"]},
                    {"n": 4, "fase": "Invio e protocollazione", "durata": "1 giorno",
                     "attivita": ["Verificare apertura sportello", "Inviare domanda entro le 17:00 del giorno di scadenza", "Salvare ricevuta di protocollo", "Annotare numero pratica assegnato"],
                     "documenti": ["Ricevuta protocollazione", "PEC di conferma ricezione"]},
                    {"n": 5, "fase": "Post-presentazione e istruttoria", "durata": "variabile",
                     "attivita": ["Monitorare portale per richieste integrazione", "Rispondere a eventuali richieste dell'ente entro i termini", "Conservare tutta la documentazione originale", "Attendere comunicazione esito (di solito 60-120 giorni)"],
                     "documenti": ["Fascicolo completo documentazione inviata", "Comunicazioni dell'ente"]},
                ],
                "note_critiche": [
                    f"Scadenza presentazione: {scadenza} — non sono ammesse proroghe individuali",
                    "Le spese devono essere sostenute DOPO la data di presentazione della domanda",
                    "Conservare tutta la documentazione per eventuali controlli per 5 anni",
                    "In caso di aggiudicazione, verificare le condizioni di erogazione (anticipo, SAL, saldo)",
                ],
                "errori_comuni": [
                    "DURC scaduto al momento della presentazione",
                    "Preventivi non comparabili o di fornitori correlati",
                    "Mancata firma digitale sulla domanda",
                    "Codice ATECO non incluso tra i beneficiari",
                    "Superamento massimali de minimis",
                ],
                "metodo": "template_locale",
            }

        api_key = ANTHROPIC_API_KEY()
        if not api_key:
            return {"ok": True, "sop": _local_sop()}

        prompt = (
            f"Sei un consulente esperto di finanza agevolata italiana. "
            f"Genera una guida SOP passo-passo per presentare la domanda per questo bando.\n\n"
            f"BANDO: {bando_titolo}\n"
            f"ENTE: {ente}\n"
            f"SETTORE: {settore}\n"
            f"TIPO AZIENDA: {tipo_azienda}\n"
            f"IMPORTO MAX: {importo_max}\n"
            f"SCADENZA: {scadenza}\n"
            f"{'TESTO BANDO: ' + bando_testo[:2000] if bando_testo else ''}\n\n"
            f"Restituisci JSON con: titolo, fasi (array con: n, fase, durata, attivita[], documenti[]), "
            f"note_critiche[], errori_comuni[]. JSON valido e nient'altro."
        )

        try:
            async with httpx.AsyncClient(timeout=60) as client:
                r = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={"x-api-key": api_key, "anthropic-version": "2023-06-01", "Content-Type": "application/json"},
                    json={"model": MODEL(), "max_tokens": 2048,
                          "system": "Rispondi SEMPRE con JSON valido e nient'altro.",
                          "messages": [{"role": "user", "content": prompt}]}
                )
            if r.status_code == 200:
                ai_text = r.json()["content"][0]["text"]
                sop = json.loads(ai_text)
                sop["metodo"] = "ai"
                sop.setdefault("ente", ente)
                sop.setdefault("scadenza", scadenza)
                sop.setdefault("importo_max", importo_max)
                return {"ok": True, "sop": sop}
        except Exception:
            pass

        return {"ok": True, "sop": _local_sop()}
