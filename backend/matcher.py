"""
BA.IA — Semantic Matcher v1.0
Matching bando × azienda con TF-IDF cosine similarity (locale, zero costo)
+ embedding vettoriale reale se il provider lo supporta.

Architettura:
  1. Ogni bando, quando analizzato, genera un vettore TF-IDF dal testo.
  2. Ogni profilo azienda genera un vettore dallo stesso spazio.
  3. Cosine similarity → score 0-100.
  4. Se disponibile, usa embedding reale (OpenAI/Anthropic) per qualità superiore.

Storage: colonna `embedding` TEXT (JSON array) in tabella `bandi` di SQLite.
"""

import os, re, json, math
from typing import Optional

# ── STOPWORDS ITALIANE ────────────────────────────────────
_STOPWORDS = {
    "il","lo","la","i","gli","le","un","uno","una","e","è","in","di","a","da","con",
    "per","tra","fra","su","non","si","che","se","ma","ed","ad","dei","del","della",
    "delle","degli","nel","nella","nelle","nei","negli","al","ai","alla","alle",
    "agli","dal","dai","dalla","dalle","dagli","sul","sui","sulla","sulle","sugli",
    "col","coi","come","quando","dove","questo","questa","questi","queste","quello",
    "quella","quelli","quelle","anche","sia","poi","però","così","quindi","mentre",
    "sono","ha","ho","avere","essere","fare","the","and","or","of","to","in","for",
    "with","at","by","from","an","on","is","as","it","be","was","this","that","are",
}

def _tokenize(text: str) -> list[str]:
    """Tokenizza testo italiano in termini significativi."""
    text = text.lower()
    text = re.sub(r'[^\w\s]', ' ', text)
    tokens = [t for t in text.split() if len(t) > 2 and t not in _STOPWORDS and not t.isdigit()]
    return tokens

def _tfidf_vector(tokens: list[str], vocab: dict[str, int]) -> list[float]:
    """Calcola TF-IDF vector dato vocab condiviso."""
    if not tokens:
        return [0.0] * len(vocab)
    tf: dict[str, float] = {}
    for t in tokens:
        tf[t] = tf.get(t, 0) + 1
    n = len(tokens)
    vec = [0.0] * len(vocab)
    for term, idx in vocab.items():
        if term in tf:
            vec[idx] = tf[term] / n  # TF semplice normalizzato
    return vec

def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity tra due vettori."""
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)

def _bando_text(bando: dict) -> str:
    """Estrae testo rappresentativo da un bando."""
    parts = [
        bando.get("name", ""),
        bando.get("ente", ""),
    ]
    for f in bando.get("fields", []):
        v = f.get("value") or ""
        if v and str(v).strip():
            parts.append(f"{f.get('label','')} {v}")
    for p in bando.get("pdfs", []):
        if p.get("analysis"):
            parts.append(p["analysis"][:1000])
    return " ".join(str(p) for p in parts if p)

def _azienda_text(azienda: dict) -> str:
    """Estrae testo rappresentativo da un profilo azienda."""
    parts = [
        azienda.get("name", ""),
        azienda.get("ateco", ""),
        azienda.get("forma", ""),
        azienda.get("sede", ""),
        f"dipendenti {azienda.get('dipendenti','')}",
        f"fatturato {azienda.get('fatturato','')}",
    ]
    for c in azienda.get("campi", []):
        if c.get("value"):
            parts.append(str(c["value"]))
    return " ".join(str(p) for p in parts if p)

# ── MATCHING LOCALE (TF-IDF) ──────────────────────────────

def compute_tfidf_scores(azienda: dict, bandi: list[dict]) -> list[dict]:
    """
    Calcola score di compatibilità tra azienda e lista bandi.
    Usa TF-IDF cosine similarity — zero API call, zero costo.
    Ritorna lista [{id, name, score, reason}] ordinata per score desc.
    """
    az_text = _azienda_text(azienda)
    bandi_texts = [(_bando_text(b), b) for b in bandi if b.get("fields") or b.get("pdfs")]

    if not bandi_texts:
        return []

    # Costruisci vocabolario condiviso
    all_tokens: list[list[str]] = [_tokenize(az_text)]
    for bt, _ in bandi_texts:
        all_tokens.append(_tokenize(bt))

    vocab: dict[str, int] = {}
    for tokens in all_tokens:
        for t in tokens:
            if t not in vocab:
                vocab[t] = len(vocab)

    if not vocab:
        return []

    az_vec = _tfidf_vector(all_tokens[0], vocab)
    results = []

    for (bt, bando), btokens in zip(bandi_texts, all_tokens[1:]):
        b_vec = _tfidf_vector(btokens, vocab)
        cos = _cosine(az_vec, b_vec)
        # Boost per corrispondenze esplicite (ATECO, regione, dimensione)
        boost = 0.0
        az_ateco = (azienda.get("ateco") or "").lower().replace(".", "")
        if az_ateco:
            for f in bando.get("fields", []):
                v = str(f.get("value") or "").lower()
                if az_ateco[:4] in v or az_ateco[:2] in v:
                    boost += 0.08
                    break
        # Penalizza bandi scaduti
        scad = bando.get("scadenza", "")
        if scad:
            try:
                import datetime
                d = datetime.date.fromisoformat(scad)
                if d < datetime.date.today():
                    cos *= 0.3
            except Exception:
                pass

        score = min(100, int((cos + boost) * 120))  # scala a 0-100
        if score < 5:
            continue

        # Genera reason breve (campi in comune)
        matching_terms = set(all_tokens[0]) & set(btokens)
        key_terms = [t for t in matching_terms if len(t) > 4][:5]
        reason = f"Termini in comune: {', '.join(key_terms)}" if key_terms else "Compatibilità strutturale"

        results.append({
            "id": bando["id"],
            "name": bando.get("name", ""),
            "ente": bando.get("ente", ""),
            "scadenza": bando.get("scadenza"),
            "score": score,
            "reason_tfidf": reason,
            "method": "tfidf",
        })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results

# ── EMBEDDING REALE (opzionale, se provider supporta) ─────

async def get_embedding(text: str) -> Optional[list[float]]:
    """
    Genera embedding reale tramite API.
    Ritorna None se il provider non supporta embedding.
    """
    import os, httpx
    provider = os.environ.get("AI_PROVIDER", "groq")
    api_key = os.environ.get("AI_API_KEY") or os.environ.get("GROQ_API_KEY", "")

    if not api_key:
        return None

    try:
        if provider == "openai":
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(
                    "https://api.openai.com/v1/embeddings",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={"input": text[:8000], "model": "text-embedding-3-small"}
                )
                r.raise_for_status()
                return r.json()["data"][0]["embedding"]

        elif provider == "anthropic":
            # Anthropic non ha ancora un endpoint pubblico embedding stabile
            # → fallback a TF-IDF
            return None

        elif provider == "mistral":
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(
                    "https://api.mistral.ai/v1/embeddings",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={"input": [text[:8000]], "model": "mistral-embed"}
                )
                r.raise_for_status()
                return r.json()["data"][0]["embedding"]

        elif provider == "gemini":
            model = "text-embedding-004"
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{model}:embedContent?key={api_key}",
                    json={"content": {"parts": [{"text": text[:8000]}]}}
                )
                r.raise_for_status()
                return r.json()["embedding"]["values"]

    except Exception as e:
        print(f"[EMBED] Fallback TF-IDF ({provider}): {e}")
    return None

def cosine_from_embeddings(a: list[float], b: list[float]) -> float:
    return _cosine(a, b)
