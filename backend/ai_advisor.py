"""
BA.IA — AI Advisor v1.0
Matching semantico avanzato bando × azienda con Claude.
Sostituisce / affianca il matcher TF-IDF con analisi profonda multi-step.
"""

import json
import httpx
from typing import AsyncGenerator

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"

# ── HELPERS ──────────────────────────────────────────────────────

def _fmt_bando(b: dict) -> str:
    parts = [f"BANDO: {b.get('name','N/D')}", f"Ente: {b.get('ente','N/D')}"]
    scad = b.get("scadenza")
    if scad:
        parts.append(f"Scadenza: {scad}")
    for f in b.get("fields", []):
        v = str(f.get("value") or "").strip()
        if v and v not in ("null","None",""):
            parts.append(f"{f.get('label','')}: {v}")
    for p in b.get("pdfs", []):
        if p.get("analysis"):
            parts.append(f"Testo bando (estratto): {p['analysis'][:1500]}")
            break
    return "\n".join(parts)[:3500]


def _fmt_azienda(a: dict) -> str:
    parts = [
        f"AZIENDA: {a.get('name','N/D')}",
        f"ATECO: {a.get('ateco','N/D')}",
        f"Forma giuridica: {a.get('forma','N/D')}",
        f"Sede / Regione: {a.get('sede','')} {a.get('regione','')}".strip(),
        f"Dipendenti: {a.get('dipendenti','N/D')}",
        f"Fatturato: {a.get('fatturato','N/D')} €",
    ]
    for c in a.get("campi", []):
        v = c.get("value","")
        if v:
            parts.append(f"{c.get('label','')}: {v}")
    return "\n".join(str(p) for p in parts if p)[:2500]


# ── PROMPT TEMPLATES ─────────────────────────────────────────────

_COMPAT_SYSTEM = (
    "Sei un esperto senior di finanza agevolata italiana con 20 anni di esperienza. "
    "Rispondi SEMPRE e SOLO con JSON valido. Nessun testo, nessun backtick."
)

_COMPAT_PROMPT = """\
Analizza la compatibilità tra questa azienda e questo bando di finanziamento.

{azienda}

{bando}

Valuta profondamente e rispondi con questo JSON esatto:
{{
  "score": <intero 0-100>,
  "rationale": "<2-3 frasi in italiano — livello di compatibilità e perché>",
  "requisiti_soddisfatti": ["<req 1>", "<req 2>"],
  "requisiti_mancanti": ["<req mancante 1>"],
  "probabilita_successo": "<alta|media|bassa>",
  "azioni_consigliate": ["<azione concreta 1>", "<azione 2>", "<azione 3>"],
  "urgenza": "<urgente|normale|non_prioritario>",
  "importo_stimato": "<importo max ottenibile o null>",
  "note_normative": "<vincoli GBER, de minimis, aiuti di Stato rilevanti — o null>"
}}

CRITERI SCORE:
85-100 = Perfettamente compatibile, forte probabilità di approvazione
65-84  = Buon match, piccoli requisiti da verificare
45-64  = Match parziale, lavoro di adeguamento necessario
25-44  = Match basso, ostacoli significativi
0-24   = Non compatibile
"""

_BATCH_SYSTEM = (
    "Sei un esperto di finanza agevolata italiana. "
    "Rispondi SEMPRE con un array JSON valido. Nessun testo aggiuntivo."
)

_BATCH_PROMPT = """\
Profilo azienda:
{azienda}

Valuta RAPIDAMENTE questi {n} bandi per questa azienda.
Per ognuno: score 0-100, max 1 frase rationale, urgenza.

BANDI:
{bandi}

Rispondi con array JSON:
[{{"id":"<id>","score":<0-100>,"rationale":"<1 frase>","urgenza":"<urgente|normale|non_prioritario>"}}]
"""

_ADVISOR_SYSTEM = (
    "Sei un consulente strategico di finanza agevolata italiana. "
    "Rispondi SEMPRE con JSON valido. Nessun testo aggiuntivo."
)

_ADVISOR_PROMPT = """\
Profilo azienda:
{azienda}

Genera un report strategico di finanziabilità per questa azienda.
Identifica le opportunità più adatte al suo profilo anche oltre i bandi attuali.

Rispondi con questo JSON:
{{
  "sommario": "<2-3 frasi sul profilo di finanziabilità>",
  "profilo_finanziabilita": "<eccellente|buono|discreto|basso>",
  "opportunita_principali": [
    {{"titolo":"<nome>","descrizione":"<1-2 frasi>","importo":"<stima>","urgenza":"<alta|media|bassa>","fonte":"<ente o normativa>"}}
  ],
  "azioni_immediate": ["<cosa fare questa settimana 1>", "<azione 2>"],
  "azioni_medio_termine": ["<entro 3 mesi>", "<azione 2>"],
  "punti_di_forza": ["<punto 1>", "<punto 2>"],
  "punti_di_debolezza": ["<punto 1>"],
  "note_normative": "<de minimis, GBER, aiuti di Stato: saldo disponibile da verificare>"
}}
"""

# ── API HELPERS ───────────────────────────────────────────────────

def _headers(api_key: str) -> dict:
    return {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }


def _clean_json(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        parts = text.split("```")
        text = parts[1] if len(parts) > 1 else text
        if text.startswith("json"):
            text = text[4:]
    return text.strip()


# ── FUNZIONI PUBBLICHE ────────────────────────────────────────────

async def ai_analyze_compatibility(
    azienda: dict,
    bando: dict,
    api_key: str,
    model: str,
) -> dict:
    """
    Analisi AI profonda di compatibilità bando × azienda.
    Torna dict con score, rationale, requisiti, azioni consigliate.
    """
    prompt = _COMPAT_PROMPT.format(
        azienda=_fmt_azienda(azienda),
        bando=_fmt_bando(bando),
    )
    body = {
        "model": model,
        "max_tokens": 1200,
        "system": _COMPAT_SYSTEM,
        "messages": [{"role": "user", "content": prompt}],
    }
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(ANTHROPIC_URL, headers=_headers(api_key), json=body)
        r.raise_for_status()
    result = json.loads(_clean_json(r.json()["content"][0]["text"]))
    result["method"]     = "claude-ai"
    result["bando_id"]   = bando.get("id", "")
    result["bando_name"] = bando.get("name", "")
    return result


async def ai_rank_bandi(
    azienda: dict,
    bandi: list[dict],
    api_key: str,
    model: str,
    top_n: int = 10,
) -> list[dict]:
    """
    Pre-filtra con TF-IDF, poi fa Claude batch-ranking sui top candidati.
    Efficiente: massimo 2 chiamate Claude indipendentemente dal numero di bandi.
    """
    from matcher import compute_tfidf_scores

    # Step 1 — TF-IDF pre-filter: top-20 candidati a costo zero
    tfidf = compute_tfidf_scores(azienda, bandi)
    candidates = tfidf[:20]
    cand_ids   = {c["id"] for c in candidates}
    cand_bandi = [b for b in bandi if b.get("id") in cand_ids]

    if not cand_bandi:
        return []

    # Step 2 — Claude batch ranking sui candidati (max 15 per context)
    batch = cand_bandi[:15]
    bandi_text = "\n\n---\n".join(
        f"ID: {b.get('id','')}\nTitolo: {b.get('name','')}\nEnte: {b.get('ente','')}\n"
        + "\n".join(
            f"{f.get('label','')}: {f.get('value','')}"
            for f in b.get("fields", [])
            if f.get("value") and str(f["value"]).strip()
        )[:600]
        for b in batch
    )
    prompt = _BATCH_PROMPT.format(
        azienda=_fmt_azienda(azienda),
        n=len(batch),
        bandi=bandi_text,
    )
    body = {
        "model": model,
        "max_tokens": 2048,
        "system": _BATCH_SYSTEM,
        "messages": [{"role": "user", "content": prompt}],
    }
    try:
        async with httpx.AsyncClient(timeout=90) as client:
            r = await client.post(ANTHROPIC_URL, headers=_headers(api_key), json=body)
            r.raise_for_status()
        ai_scores: list[dict] = json.loads(_clean_json(r.json()["content"][0]["text"]))
    except Exception as e:
        print(f"[AI RANK] Fallback TF-IDF ({e})")
        ai_scores = [
            {"id": c["id"], "score": c["score"], "rationale": c.get("reason_tfidf",""), "urgenza": "normale"}
            for c in candidates
        ]

    ai_map   = {item.get("id"): item for item in ai_scores}
    tfidf_map = {c["id"]: c for c in candidates}

    results = []
    for b in cand_bandi:
        bid  = b.get("id","")
        ai   = ai_map.get(bid, {})
        tf   = tfidf_map.get(bid, {})
        results.append({
            "id":          bid,
            "name":        b.get("name",""),
            "ente":        b.get("ente",""),
            "scadenza":    b.get("scadenza"),
            "score_ai":    ai.get("score",   tf.get("score", 0)),
            "score_tfidf": tf.get("score",   0),
            "rationale":   ai.get("rationale", tf.get("reason_tfidf","")),
            "urgenza":     ai.get("urgenza",   "normale"),
            "method":      "claude-ai",
        })

    results.sort(key=lambda x: x["score_ai"], reverse=True)
    return results[:top_n]


async def ai_advisor_report(
    azienda: dict,
    api_key: str,
    model: str,
) -> dict:
    """
    Report strategico proattivo per un'azienda.
    Identifica opportunità e suggerisce azioni concrete.
    """
    body = {
        "model": model,
        "max_tokens": 1500,
        "system": _ADVISOR_SYSTEM,
        "messages": [{"role": "user", "content": _ADVISOR_PROMPT.format(azienda=_fmt_azienda(azienda))}],
    }
    async with httpx.AsyncClient(timeout=90) as client:
        r = await client.post(ANTHROPIC_URL, headers=_headers(api_key), json=body)
        r.raise_for_status()
    return json.loads(_clean_json(r.json()["content"][0]["text"]))


async def stream_analysis(
    text: str,
    api_key: str,
    model: str,
    chunk_size: int = 80000,
) -> AsyncGenerator[str, None]:
    """
    Analisi bando in streaming via Anthropic SSE.
    Yield di chunk di testo man mano che Claude li produce.
    """
    prompt = (
        "Sei un esperto di finanza agevolata italiana. "
        "Analizza questo bando e fornisci:\n"
        "**Obiettivo principale**\n"
        "**Beneficiari ammessi**\n"
        "**Requisiti chiave**\n"
        "**Scadenze importanti**\n"
        "**Opportunità strategiche**\n"
        "**Punti di attenzione**\n\n"
        f"Testo bando:\n{text[:chunk_size]}"
    )
    body = {
        "model": model,
        "max_tokens": 4096,
        "stream": True,
        "messages": [{"role": "user", "content": prompt}],
    }
    async with httpx.AsyncClient(timeout=180) as client:
        async with client.stream("POST", ANTHROPIC_URL, headers=_headers(api_key), json=body) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line.startswith("data: "):
                    continue
                try:
                    data = json.loads(line[6:])
                    if data.get("type") == "content_block_delta":
                        t = data.get("delta", {}).get("text", "")
                        if t:
                            yield t
                except json.JSONDecodeError:
                    continue
