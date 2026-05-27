"""
BA.IA — Security utilities v1.0
Condiviso tra main.py e app_locale.py.
"""

import os, re, time, hashlib, hmac, secrets, uuid
from collections import defaultdict
from typing import Optional

# ── PASSWORD HASHING ─────────────────────────────────────
try:
    import bcrypt as _bcrypt
    _HAVE_BCRYPT = True
except ImportError:
    _HAVE_BCRYPT = False
    print("[SECURITY] bcrypt non trovato — uso PBKDF2. Installa: pip install bcrypt")

def hash_password(password: str) -> str:
    """Hash password con bcrypt (preferito) o PBKDF2-SHA256."""
    if _HAVE_BCRYPT:
        return _bcrypt.hashpw(password.encode("utf-8"), _bcrypt.gensalt(12)).decode("utf-8")
    salt = secrets.token_bytes(32)
    key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 260_000)
    return f"pbkdf2:{salt.hex()}:{key.hex()}"

def verify_password(password: str, stored: str) -> bool:
    """Verifica password contro hash salvato. Supporta bcrypt, PBKDF2 e legacy SHA-256."""
    try:
        if _HAVE_BCRYPT and stored.startswith("$2"):
            return _bcrypt.checkpw(password.encode("utf-8"), stored.encode("utf-8"))

        if stored.startswith("pbkdf2:"):
            _, salt_hex, key_hex = stored.split(":", 2)
            key = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), 260_000)
            return hmac.compare_digest(key.hex(), key_hex)

        if ":" in stored:
            # Legacy SHA-256: salt:hash (vecchio formato app_locale.py)
            salt, stored_hash = stored.split(":", 1)
            test = hashlib.sha256(f"{salt}{password}{salt[::-1]}".encode()).hexdigest()
            return hmac.compare_digest(test, stored_hash)
    except Exception:
        pass
    return False

# ── EMAIL VALIDATION ──────────────────────────────────────
_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$")

def validate_email(email: str) -> bool:
    """Valida formato email e previene header injection."""
    if not email:
        return False
    if "\n" in email or "\r" in email or "\x00" in email:
        return False
    return bool(_EMAIL_RE.match(email.strip()))

# ── RATE LIMITER ──────────────────────────────────────────
class RateLimiter:
    """Rate limiter in-memory per endpoint sensibili."""

    def __init__(self, max_calls: int, window_seconds: int):
        self._max = max_calls
        self._window = window_seconds
        self._calls: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, key: str) -> bool:
        now = time.monotonic()
        cutoff = now - self._window
        self._calls[key] = [t for t in self._calls[key] if t > cutoff]
        if len(self._calls[key]) >= self._max:
            return False
        self._calls[key].append(now)
        return True

    def retry_after(self, key: str) -> int:
        """Secondi rimanenti prima che il rate limit si azzeri."""
        if not self._calls.get(key):
            return 0
        oldest = min(self._calls[key])
        return max(0, int(self._window - (time.monotonic() - oldest)))

# Istanze condivise (importate dove servono)
login_limiter    = RateLimiter(max_calls=5,  window_seconds=300)    # 5 tentativi / 5 min
register_limiter = RateLimiter(max_calls=3,  window_seconds=3600)   # 3 registrazioni / ora
api_limiter      = RateLimiter(max_calls=30, window_seconds=60)     # 30 chiamate AI / min

# ── FILE VALIDATION ───────────────────────────────────────
MAX_UPLOAD_MB    = int(os.environ.get("MAX_UPLOAD_MB", "50"))
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024

_PDF_MAGIC = b"%PDF"

def is_valid_pdf_bytes(data: bytes) -> bool:
    """Verifica magic bytes PDF."""
    return len(data) > 4 and data[:4] == _PDF_MAGIC

def sanitize_filename(original_name: str, doc_id: str) -> str:
    """Genera filename sicuro per upload documenti (previene path traversal)."""
    ext = ".pdf" if original_name.lower().endswith(".pdf") else ".bin"
    return f"{doc_id}_{uuid.uuid4().hex}{ext}"

# ── TOKEN HELPER ─────────────────────────────────────────
def make_token() -> str:
    return secrets.token_hex(32)
