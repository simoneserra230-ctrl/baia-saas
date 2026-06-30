"""
BA.IA — AI Features v1.0 (chatbot · blog · business plan · pitch deck · compliance)
Costruito sugli spunti della KB finanza+AI (vedi backend/kb_finanza.py + data/kb_finanza_ai.json).

Principio FISSO (human-in-the-loop): ogni output è una BOZZA da validare. Importi,
percentuali e citazioni normative vanno SEMPRE verificati su fonte ufficiale prima
di consegna/pubblicazione. Ogni risposta porta un disclaimer esplicito.

Il router è creato via factory `make_ai_router(anthropic_call, require_auth, db_path)`
così riusa la chiave/modello/auth già configurati in main.py (zero duplicazioni).
"""

from __future__ import annotations
import json
import re
from typing import Optional, Callable, Awaitable

from fastapi import APIRouter, Depends, Body
from pydantic import BaseModel

import kb_finanza as kb

DISCLAIMER = (
    "⚠️ BOZZA generata da AI — verifica SEMPRE importi, percentuali, scadenze e "
    "riferimenti normativi sulla documentazione ufficiale del bando prima di "
    "consegnare o pubblicare. BA.IA non sostituisce il controllo del consulente."
)


def _parse_json(text: str):
    text = (text or "").strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    try:
        return json.loads(text)
    except Exception:
        m = re.search(r"[\{\[].*[\}\]]", text, re.S)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    return {"raw": text}


def _flag_figures(md: str) -> str:
    """Marca importi/percentuali con un flag DA VERIFICARE (anti-pubblicazione cieca)."""
    def repl(m):
        return m.group(0) + " [DA VERIFICARE]"
    md = re.sub(r"€\s?\d[\d.\,]*", repl, md)
    md = re.sub(r"\b\d{1,3}(?:[.,]\d+)?\s?%", repl, md)
    return md


# ── RAG-lite: retrieval per parole-chiave sui bandi (no embeddings, no dipendenze) ──
def _strip_accents(s: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn")

_RAG_STOP = {
    "che","con","per","dei","del","della","delle","una","uno","sono","come","quale","quali","cosa",
    "gli","sul","sui","nei","nel","nella","dal","dalla","alla","allo","mio","miei","mia","quanto",
    "quando","dove","posso","puo","essere","fare","hai","the","and","ant","non","piu","tra","fra",
}
def _tokenize(q: str):
    raw = re.split(r"[^a-z0-9]+", _strip_accents((q or "").lower()))
    return [t for t in raw if len(t) >= 3 and t not in _RAG_STOP]


# ── Pydantic bodies ─────────────────────────────────────────────────────
class ChatBody(BaseModel):
    message: str
    history: Optional[list] = None      # [{role, content}]
    k: int = 4


class BlogBody(BaseModel):
    seed_title: Optional[str] = None    # se assente usa il prossimo blog_seed libero
    tema: Optional[str] = None
    keyword: Optional[str] = None
    used_titles: Optional[list] = None


class BPBody(BaseModel):
    azienda: dict
    bando: Optional[dict] = None


class PitchBody(BaseModel):
    azienda: dict
    bando: Optional[dict] = None


class ComplianceBody(BaseModel):
    azienda: Optional[dict] = None
    regime: Optional[str] = None              # "de_minimis" | "gber" | None (auto)
    aiuti_ricevuti: Optional[list] = None     # [{anno, importo, fonte}]
    plafond_de_minimis: Optional[float] = None  # default indicativo se assente


class EmailBody(BaseModel):
    azienda: dict                              # {nome, referente, settore, ...}
    bando: Optional[dict] = None               # {name, ente, scadenza, importo, percentuale, settori}
    mittente: Optional[dict] = None            # {nome_consulente, studio, contatto}
    tono: Optional[str] = "professionale"      # professionale | cordiale | diretto
    note: Optional[str] = None                 # istruzioni extra


class RagBody(BaseModel):
    question: str                              # domanda in linguaggio naturale
    k: int = 6                                 # quanti bandi al massimo usare come contesto


AnthropicCall = Callable[..., Awaitable[tuple]]


def make_ai_router(anthropic_call: AnthropicCall, require_auth, db_path: str) -> APIRouter:
    router = APIRouter(prefix="/ai", tags=["BA.IA AI"])

    async def _bandi_context(limit: int = 8) -> str:
        """Best-effort: titoli/ente/scadenza di alcuni bandi dal DB per il chatbot."""
        try:
            import aiosqlite
            async with aiosqlite.connect(db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT data FROM bandi WHERE deleted_at IS NULL "
                    "ORDER BY updated_at DESC LIMIT ?", (limit,)
                ) as c:
                    rows = await c.fetchall()
            items = []
            for r in rows:
                try:
                    b = json.loads(r["data"])
                    items.append(f"- {b.get('name','(senza nome)')} · {b.get('ente','')} · scad. {b.get('scadenza','n/d')}")
                except Exception:
                    continue
            return "\n".join(items)
        except Exception:
            return ""

    # ── 1. CHATBOT Q&A ──────────────────────────────────────────────────
    @router.post("/chat", summary="Chatbot BA.IA (KB finanza+AI + bandi DB come contesto)")
    async def chat(body: ChatBody, _user: dict = Depends(require_auth)):
        built = kb.build_chatbot_messages(body.message, k=body.k)
        bandi_ctx = await _bandi_context()
        system = built["system"]
        if bandi_ctx:
            system += "\n\nBANDI IN PIATTAFORMA (recenti):\n" + bandi_ctx
        # storico opzionale + ultima domanda
        convo = ""
        for m in (body.history or [])[-6:]:
            who = "Utente" if m.get("role") == "user" else "Assistente"
            convo += f"{who}: {m.get('content','')}\n"
        prompt = f"{system}\n\n{convo}Utente: {body.message}\nAssistente:"
        try:
            answer, _ = await anthropic_call(prompt)
        except Exception as e:
            return {"ok": False, "error": f"AI non raggiungibile: {e}"}
        sources = [{"title": a.get("title"), "url": a.get("url")} for a in kb.search_kb(body.message, body.k)]
        return {"ok": True, "answer": answer, "sources": sources, "disclaimer": DISCLAIMER}

    # ── 2. BLOG AUTOMATICO (bozza SEO) ──────────────────────────────────
    @router.post("/blog/generate", summary="Genera bozza articolo blog SEO (con fact-check flag)")
    async def blog_generate(body: BlogBody, _user: dict = Depends(require_auth)):
        seed = None
        if body.seed_title:
            seed = next((s for s in kb.blog_seeds() if s.get("titolo") == body.seed_title), None)
        if not seed:
            seed = kb.next_blog_seed(body.used_titles) or {
                "titolo": body.tema or "Bandi e finanza agevolata: guida pratica",
                "angolo": "educativo", "keyword": body.keyword or "bandi finanza agevolata",
                "cta": "Scopri i bandi adatti a te con BA.IA",
            }
        prompt = (
            "Sei un copywriter esperto di finanza agevolata italiana per il blog di BA.IA. "
            "Scrivi una BOZZA di articolo SEO in italiano, in markdown, originale (no testo "
            "copiato da altri siti). Tono pratico e professionale.\n"
            f"TITOLO/ANGOLO: {seed.get('titolo')} — angolo: {seed.get('angolo')}\n"
            f"KEYWORD principale: {seed.get('keyword')}\n"
            f"CTA finale: {seed.get('cta')}\n\n"
            "Struttura: H1, meta description (max 155 caratteri) tra <!--meta: ...-->, "
            "intro, 3-5 sezioni H2, una sezione FAQ (2-3 Q&A), conclusione con CTA.\n"
            "REGOLE: non inventare importi/percentuali/scadenze precise; se servono numeri, "
            "scrivi '[verifica importo sul bando ufficiale]'. Niente nomi di altri studi/competitor."
        )
        try:
            draft, _ = await anthropic_call(prompt, timeout=120)
        except Exception as e:
            return {"ok": False, "error": f"AI non raggiungibile: {e}"}
        return {"ok": True, "seed": seed, "draft_markdown": _flag_figures(draft),
                "stato": "bozza", "disclaimer": DISCLAIMER}

    # ── 3. BUSINESS PLAN (bozza strutturata) ────────────────────────────
    @router.post("/genera/business-plan", summary="Genera bozza business plan 3 anni")
    async def genera_business_plan(body: BPBody, _user: dict = Depends(require_auth)):
        az = json.dumps(body.azienda, ensure_ascii=False)[:2500]
        bn = json.dumps(body.bando, ensure_ascii=False)[:2000] if body.bando else "nessun bando specifico"
        prompt = (
            "Sei un consulente di finanza agevolata. Genera una BOZZA di business plan per "
            "questa azienda, eventualmente tarata sul bando indicato. Rispondi SOLO con JSON valido "
            "con queste chiavi: executive_summary (stringa), mercato (stringa), modello_ricavi (stringa), "
            "team (stringa), proiezioni_3_anni (array di 3 oggetti {anno, ricavi, costi, ebitda, note}), "
            "richiesta_finanziamento (stringa), allocazione_fondi (array stringhe), rischi (array stringhe), "
            "note_verifica (stringa: cosa va verificato a mano). "
            "Per i numeri usa stime PRUDENZIALI e indica in note_verifica che vanno validati col cliente.\n\n"
            f"AZIENDA:\n{az}\n\nBANDO:\n{bn}"
        )
        try:
            raw, _ = await anthropic_call(prompt, json_mode=True, timeout=150)
        except Exception as e:
            return {"ok": False, "error": f"AI non raggiungibile: {e}"}
        return {"ok": True, "business_plan": _parse_json(raw), "stato": "bozza", "disclaimer": DISCLAIMER}

    # ── 4. PITCH DECK (12 slide) ────────────────────────────────────────
    @router.post("/genera/pitch-deck", summary="Genera struttura pitch deck 12 slide")
    async def genera_pitch_deck(body: PitchBody, _user: dict = Depends(require_auth)):
        az = json.dumps(body.azienda, ensure_ascii=False)[:2500]
        bn = json.dumps(body.bando, ensure_ascii=False)[:2000] if body.bando else "nessun bando specifico"
        prompt = (
            "Sei un esperto di pitch per bandi italiani (Smart&Start, Resto al Sud, ecc.). "
            "Genera una BOZZA di pitch deck di 12 slide per questa azienda/bando. Rispondi SOLO con JSON: "
            "{\"slides\":[{\"n\":1,\"titolo\":\"...\",\"bullet\":[\"...\",\"...\"]}, ...]}. "
            "Struttura consigliata: 1-3 identità/problema/soluzione; 4-5 mercato (TAM/SAM/SOM) e modello ricavi; "
            "6-8 traction/team/competitor; 9-11 roadmap 3 anni, proiezioni, richiesta+allocazione; 12 contatti. "
            "Niente numeri inventati: dove servono dati di mercato/importi scrivi '[da validare]'.\n\n"
            f"AZIENDA:\n{az}\n\nBANDO:\n{bn}"
        )
        try:
            raw, _ = await anthropic_call(prompt, json_mode=True, timeout=120)
        except Exception as e:
            return {"ok": False, "error": f"AI non raggiungibile: {e}"}
        return {"ok": True, "pitch_deck": _parse_json(raw), "stato": "bozza", "disclaimer": DISCLAIMER}

    # ── 5. COMPLIANCE MONITOR (de minimis / GBER / DURC) ────────────────
    @router.post("/compliance/check", summary="Check compliance de minimis / GBER / DURC")
    async def compliance_check(body: ComplianceBody, _user: dict = Depends(require_auth)):
        # parte deterministica: cumulo de minimis (plafond indicativo, DA VERIFICARE)
        PLAFOND_DEFAULT = 300000.0   # Reg. UE 2023/2831 (generale) — indicativo, verificare settore
        plafond = body.plafond_de_minimis or PLAFOND_DEFAULT
        aiuti = body.aiuti_ricevuti or []
        totale = round(sum(float(a.get("importo") or 0) for a in aiuti), 2)
        residuo = round(plafond - totale, 2)
        de_minimis = {
            "plafond_indicativo": plafond,
            "totale_aiuti_dichiarati": totale,
            "residuo_indicativo": residuo,
            "supera_plafond": totale > plafond,
            "nota": "Plafond indicativo Reg. UE 2023/2831 (generale 3 anni). "
                    "VERIFICA il massimale corretto per settore (agricoltura/pesca diversi) "
                    "e il periodo mobile sul Registro Nazionale Aiuti (RNA).",
        }
        # checklist DURC + GBER guidata da AI
        az = json.dumps(body.azienda or {}, ensure_ascii=False)[:1800]
        prompt = (
            "Sei un esperto di aiuti di Stato italiani. Dato il profilo azienda e il regime indicato, "
            "produci una CHECKLIST di compliance. Rispondi SOLO con JSON: "
            "{\"durc\":{\"voci\":[\"...\"],\"rischio\":\"basso|medio|alto\"}, "
            "\"gber\":{\"applicabile\":true/false,\"articoli_possibili\":[\"...\"],\"note\":\"...\"}, "
            "\"de_minimis\":{\"note\":\"...\"}, \"azioni\":[\"...\"], \"avvertenze\":[\"...\"]}. "
            "NON dare per certi importi/soglie: invita a verificare su RNA e Gazzetta Ufficiale.\n\n"
            f"REGIME: {body.regime or 'auto'}\nAZIENDA:\n{az}"
        )
        ai_part = {}
        try:
            raw, _ = await anthropic_call(prompt, json_mode=True, timeout=90)
            ai_part = _parse_json(raw)
        except Exception as e:
            ai_part = {"error": f"AI non raggiungibile: {e}"}
        return {"ok": True, "de_minimis_calcolo": de_minimis, "checklist": ai_part,
                "stato": "bozza", "disclaimer": DISCLAIMER}

    # ── 6. EMAIL OUTREACH (bozza email cliente per un bando) ─────────────
    @router.post("/email/outreach", summary="Genera bozza email di contatto cliente per un bando")
    async def email_outreach(body: EmailBody, _user: dict = Depends(require_auth)):
        az = body.azienda or {}
        ba = body.bando or {}
        mit = body.mittente or {}
        prompt = (
            "Sei un consulente di finanza agevolata italiana. Scrivi una BOZZA di email "
            "professionale in italiano per proporre a un'azienda un'opportunità di "
            "finanziamento (bando). Tono: " + (body.tono or "professionale") + ". "
            "Personalizza sui dati forniti. NON inventare importi/percentuali/scadenze: "
            "se un dato non è fornito usa un segnaposto tipo [verifica sul bando]. "
            "Struttura: Oggetto, saluto al referente, 1-2 paragrafi sul perché il bando è "
            "rilevante per QUESTA azienda, una CTA per fissare una call, firma.\n\n"
            f"AZIENDA: {json.dumps(az, ensure_ascii=False)}\n"
            f"BANDO: {json.dumps(ba, ensure_ascii=False)}\n"
            f"MITTENTE/FIRMA: {json.dumps(mit, ensure_ascii=False)}\n"
            + (f"NOTE: {body.note}\n" if body.note else "")
        )
        try:
            draft, _ = await anthropic_call(prompt, timeout=90)
        except Exception as e:
            return {"ok": False, "error": f"AI non raggiungibile: {e}"}
        return {"ok": True, "email": _flag_figures(draft), "stato": "bozza", "disclaimer": DISCLAIMER}

    # ── 7. RAG — "Chiedi ai tuoi bandi" ─────────────────────────────────
    @router.post("/rag/ask", summary="Chiedi ai tuoi bandi (RAG: risposta basata SOLO sull'archivio)")
    async def rag_ask(body: RagBody, _user: dict = Depends(require_auth)):
        q = (body.question or "").strip()
        if not q:
            return {"ok": False, "error": "Domanda vuota"}
        # 1) carica i bandi e ordina per pertinenza alla domanda (retrieval per parole-chiave)
        bandi = []
        try:
            import aiosqlite
            async with aiosqlite.connect(db_path) as db:
                db.row_factory = aiosqlite.Row
                async with db.execute(
                    "SELECT data FROM bandi WHERE deleted_at IS NULL "
                    "ORDER BY updated_at DESC LIMIT 400"
                ) as c:
                    for r in await c.fetchall():
                        try:
                            bandi.append(json.loads(r["data"]))
                        except Exception:
                            continue
        except Exception as e:
            return {"ok": False, "error": f"Archivio bandi non raggiungibile: {e}"}

        toks = _tokenize(q)
        scored = []
        for b in bandi:
            blob = _strip_accents(json.dumps(b, ensure_ascii=False).lower())
            ne = _strip_accents((str(b.get("name", "")) + " " + str(b.get("ente", ""))).lower())
            score = sum(blob.count(t) + 2 * ne.count(t) for t in toks)   # nome/ente pesano di più
            if score > 0:
                scored.append((score, b))
        scored.sort(key=lambda x: x[0], reverse=True)
        top = [b for _, b in scored[: max(1, min(body.k, 8))]]
        if not top:
            return {"ok": True, "stato": "nessun_match", "bandi_usati": [],
                    "answer": "Non ho trovato bandi pertinenti nel tuo archivio per questa domanda. "
                              "Prova a riformularla o aggiungi altri bandi al tuo archivio.",
                    "disclaimer": DISCLAIMER}

        # 2) contesto bounded dai soli bandi pertinenti
        blocchi = []
        for b in top:
            extra = {k: v for k, v in b.items() if k not in ("html", "raw", "data") and v}
            dett = json.dumps(extra, ensure_ascii=False)[:700]
            blocchi.append(
                f"• BANDO: {b.get('name','(senza nome)')} — Ente: {b.get('ente','n/d')} — "
                f"Scadenza: {b.get('scadenza','n/d')}\n  Dettagli: {dett}"
            )
        contesto = "\n".join(blocchi)[:6000]
        prompt = (
            "Sei l'assistente di BA.IA. Rispondi alla DOMANDA usando ESCLUSIVAMENTE i BANDI forniti "
            "qui sotto (l'archivio dell'utente). Regole tassative:\n"
            "- Usa solo le informazioni presenti nei bandi forniti; NON aggiungere conoscenza esterna.\n"
            "- Cita sempre il/i bando/i da cui prendi la risposta (nome + ente).\n"
            "- Se la risposta NON è nei bandi forniti, scrivi chiaramente 'Non risulta dai tuoi bandi'.\n"
            "- NON inventare importi/percentuali/scadenze: se non sono nel testo scrivi '[verifica sul bando ufficiale]'.\n"
            "- Italiano, conciso e operativo.\n\n"
            f"BANDI (archivio):\n{contesto}\n\nDOMANDA: {q}\nRISPOSTA:"
        )
        try:
            answer, _ = await anthropic_call(prompt, timeout=90)
        except Exception as e:
            return {"ok": False, "error": f"AI non raggiungibile: {e}"}
        citazioni = [{"name": b.get("name"), "ente": b.get("ente"), "scadenza": b.get("scadenza")} for b in top]
        return {"ok": True, "stato": "ok", "answer": _flag_figures(answer),
                "bandi_usati": citazioni, "disclaimer": DISCLAIMER}

    return router
