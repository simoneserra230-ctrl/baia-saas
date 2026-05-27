"""
AI Analisi Bandi — License Server v1.0
Micro-servizio FastAPI per la verifica delle licenze software.
Deploy su VPS Hetzner (5€/mese) o qualsiasi server con Docker.

Avvio rapido:
  pip install fastapi uvicorn
  uvicorn main:app --host 0.0.0.0 --port 3001
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from datetime import datetime
from typing import Optional
import json, os, hashlib, hmac

app = FastAPI(title="License Server", docs_url=None, redoc_url=None)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ──────────────────────────────────────────────────
# DATABASE LICENZE (in produzione: usa PostgreSQL/Redis)
# Formato: LIC-ANNO-CLIENTEID
# ──────────────────────────────────────────────────
LICENZE: dict = {
    # ── PIANO BASE (1 utente, 1 installazione) ────
    "LIC-2025-BASE001": {
        "cliente":        "Demo Cliente Srl",
        "email":          "demo@example.com",
        "piano":          "base",
        "scadenza":       "2026-12-31",
        "installazioni":  1,
        "note":           "Licenza demo - non commerciale",
        "attiva":         True,
    },

    # ── PIANO PROFESSIONAL ────────────────────────
    "LIC-2025-PRO001": {
        "cliente":        "Studio Commerciale Rossi Srl",
        "email":          "admin@studiorossi.it",
        "piano":          "professional",
        "scadenza":       "2026-12-31",
        "installazioni":  3,
        "note":           "Onboarding effettuato il 2025-03-15",
        "attiva":         True,
    },

    # ── PIANO ENTERPRISE ──────────────────────────
    "LIC-2025-ENT001": {
        "cliente":        "Confartigianato Bergamo",
        "email":          "it@confartigianato-bg.it",
        "piano":          "enterprise",
        "scadenza":       "2027-06-30",
        "installazioni":  10,
        "note":           "Integrazione white-label con logo personalizzato",
        "attiva":         True,
    },
}

# ──────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────
def _get_license(key: str) -> Optional[dict]:
    return LICENZE.get(key.strip().upper())

def _is_expired(scadenza: str) -> bool:
    try:
        exp = datetime.strptime(scadenza, "%Y-%m-%d")
        return datetime.now() > exp
    except ValueError:
        return True

def _days_left(scadenza: str) -> int:
    try:
        exp = datetime.strptime(scadenza, "%Y-%m-%d")
        delta = exp - datetime.now()
        return max(0, delta.days)
    except ValueError:
        return 0

# ──────────────────────────────────────────────────
# ENDPOINTS
# ──────────────────────────────────────────────────

@app.get("/")
def health():
    return {"status": "ok", "service": "AI Bandi License Server", "version": "1.0"}

@app.get("/verify")
async def verify(key: str, request: Request):
    """
    Endpoint chiamato da install.sh e dal backend all'avvio.
    Ritorna: "ok" | "expired" | "invalid" | "disabled"
    """
    client_ip = request.client.host
    print(f"[VERIFY] key={key[:12]}... | ip={client_ip} | ts={datetime.now().isoformat()}")

    lic = _get_license(key)
    if not lic:
        return "invalid"

    if not lic.get("attiva", True):
        return "disabled"

    if _is_expired(lic["scadenza"]):
        return "expired"

    return "ok"

@app.get("/info")
async def info(key: str):
    """
    Ritorna i dettagli della licenza (usato dal pannello admin).
    """
    lic = _get_license(key)
    if not lic:
        return {"error": "Licenza non trovata"}

    return {
        "cliente":        lic["cliente"],
        "piano":          lic["piano"],
        "scadenza":       lic["scadenza"],
        "giorni_rimasti": _days_left(lic["scadenza"]),
        "scaduta":        _is_expired(lic["scadenza"]),
        "installazioni":  lic.get("installazioni", 1),
        "attiva":         lic.get("attiva", True),
    }

# ──────────────────────────────────────────────────
# ENDPOINT ADMIN (protetto da secret header)
# ──────────────────────────────────────────────────
ADMIN_SECRET = os.environ.get("ADMIN_SECRET", "cambia-questa-password-in-produzione")

@app.get("/admin/list")
async def list_licenses(request: Request):
    """Lista tutte le licenze — solo per uso interno."""
    if request.headers.get("X-Admin-Secret") != ADMIN_SECRET:
        return {"error": "Non autorizzato"}

    result = []
    for key, lic in LICENZE.items():
        result.append({
            "key":            key,
            "cliente":        lic["cliente"],
            "piano":          lic["piano"],
            "scadenza":       lic["scadenza"],
            "giorni_rimasti": _days_left(lic["scadenza"]),
            "attiva":         lic.get("attiva", True),
        })
    return {"licenze": result, "totale": len(result)}

@app.post("/admin/revoke")
async def revoke_license(key: str, request: Request):
    """Revoca una licenza immediatamente."""
    if request.headers.get("X-Admin-Secret") != ADMIN_SECRET:
        return {"error": "Non autorizzato"}

    if key in LICENZE:
        LICENZE[key]["attiva"] = False
        return {"ok": True, "key": key}
    return {"error": "Licenza non trovata"}
