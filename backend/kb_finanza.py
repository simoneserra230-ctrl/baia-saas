"""
BA.IA — Knowledge Base Finanza Agevolata & AI (loader)
Carica data/kb_finanza_ai.json e fornisce helper per:
  - chatbot:  kb_context_for_chatbot(query) -> contesto compatto con fonti
  - blog:     blog_seeds() / next_blog_seed(used_ids)
  - ricerca:  search_kb(query)

Contenuto trasformativo/originale (no testo verbatim). Zero dipendenze esterne.
Le citazioni di importi/norme vanno SEMPRE verificate su fonte ufficiale prima
della pubblicazione (vedi license_note nel JSON).
"""

from __future__ import annotations
import json
import os
import re
from functools import lru_cache
from typing import Optional

# La KB vive in backend/kb_data/ (versionata → arriva in prod). Fallback: data/ (gitignored, solo locale).
_KB_CANDIDATES = [
    os.path.join(os.path.dirname(__file__), "kb_data", "kb_finanza_ai.json"),
    os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "kb_finanza_ai.json"),
]
_KB_PATH = next((p for p in _KB_CANDIDATES if os.path.exists(p)), _KB_CANDIDATES[0])

_STOP = {"di", "a", "da", "in", "con", "su", "per", "tra", "fra", "il", "lo", "la",
         "i", "gli", "le", "un", "una", "e", "che", "come", "cosa", "del", "dei",
         "della", "delle", "the", "of", "and", "to", "for"}


@lru_cache(maxsize=1)
def load_kb() -> dict:
    """Carica (e cachea) la knowledge base. Torna {} se il file manca."""
    if not os.path.exists(_KB_PATH):
        return {}
    with open(_KB_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _tokens(text: str) -> set:
    return {t for t in re.findall(r"[a-zàèéìòù0-9]+", (text or "").lower()) if t not in _STOP and len(t) > 2}


def _entry_blob(a: dict) -> str:
    parts = [a.get("title", ""), a.get("summary", ""), a.get("theme", "")]
    parts += a.get("takeaways", []) or []
    parts += a.get("baia_implications", []) or []
    return " ".join(parts)


def search_kb(query: str, k: int = 4) -> list[dict]:
    """Ricerca per keyword sugli articoli. Torna i k entry più pertinenti."""
    kb = load_kb()
    arts = kb.get("articles", [])
    q = _tokens(query)
    if not q:
        return arts[:k]
    scored = []
    for a in arts:
        overlap = len(q & _tokens(_entry_blob(a)))
        if overlap:
            scored.append((overlap, a))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [a for _, a in scored[:k]] or arts[:k]


def kb_context_for_chatbot(query: str, k: int = 4, max_chars: int = 2600) -> str:
    """
    Contesto compatto da iniettare nel system prompt del chatbot.
    Include sintesi + spunti BA.IA + URL fonte (per attribuzione/verifica).
    """
    hits = search_kb(query, k)
    blocks = []
    for a in hits:
        tk = " · ".join((a.get("takeaways") or [])[:3])
        blocks.append(
            f"[{a.get('title','')}] ({a.get('date','')})\n"
            f"Sintesi: {a.get('summary','')}\n"
            f"Punti: {tk}\n"
            f"Fonte: {a.get('url','')}"
        )
    ctx = "\n\n".join(blocks)
    return ctx[:max_chars]


def blog_seeds() -> list[dict]:
    """Idee-blog originali pronte (titolo, angolo, keyword, cta)."""
    return load_kb().get("blog_seeds", [])


def next_blog_seed(used_titles: Optional[list[str]] = None) -> Optional[dict]:
    """Prossima idea-blog non ancora usata (per il blog automatico)."""
    used = set(used_titles or [])
    for s in blog_seeds():
        if s.get("titolo") not in used:
            return s
    return None


def chatbot_seed_faq() -> list[dict]:
    return load_kb().get("chatbot_seed_faq", [])


def baia_feature_signals() -> dict:
    """Segnali di roadmap: cosa BA.IA ha già e cosa conviene costruire."""
    return load_kb().get("baia_roadmap_signals", {})


CHATBOT_SYSTEM = (
    "Sei l'assistente di BA.IA, piattaforma di finanza agevolata con AI. "
    "Rispondi in italiano, in modo chiaro e pratico, su bandi, agevolazioni, "
    "requisiti, regimi di aiuto (de minimis/GBER) e su come BA.IA aiuta. "
    "Usa SOLO il contesto fornito e la conoscenza generale prudente. "
    "Per importi, percentuali e scadenze precise invita SEMPRE a verificare sul "
    "bando ufficiale in piattaforma: non inventare cifre. Cita la fonte quando utile."
)


def build_chatbot_messages(user_query: str, k: int = 4) -> dict:
    """Pronto-per-Anthropic: system + contesto KB + domanda utente."""
    ctx = kb_context_for_chatbot(user_query, k)
    system = CHATBOT_SYSTEM + ("\n\nCONTESTO (knowledge base BA.IA):\n" + ctx if ctx else "")
    return {"system": system, "messages": [{"role": "user", "content": user_query}]}
