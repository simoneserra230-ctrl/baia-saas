---
name: run-baia-saas
description: Run, start, build, launch, test, screenshot, smoke-test the BA.IA SaaS B2C web app (FastAPI backend + vanilla JS frontend). Use this skill to start the server, verify API endpoints, or drive the app for review.
---

# BA.IA SaaS B2C — Run Skill

BA.IA is a FastAPI + vanilla-JS SPA for Italian grant-matching (finanza agevolata). The backend serves both the API and the frontend on port 8000. This skill drives the app via `smoke.ps1`, a PowerShell script that starts the server, runs HTTP smoke tests, and stops cleanly.

All paths below are relative to the project root (`BAIA_SAAS_B2C (OPEX)/`).

---

## Prerequisites (one-time setup)

Python 3.10+ must be installed. Then from the project root:

```powershell
# Create virtualenv
python -m venv .venv

# Install dependencies
.venv\Scripts\pip install -r backend\requirements.txt

# Create .env (copy from template, set test-safe values)
Copy-Item .env.example .env
# Edit .env: set LICENSE_KEY=TEST-MODE and GROQ_API_KEY=dummy-key-for-testing
```

**Critical gotcha:** Windows uses cp1252 encoding by default. The app prints emoji on startup, which crashes uvicorn unless you set `PYTHONUTF8=1` (the driver and SKILL.md commands below all set this).

---

## Run (agent path) — smoke.ps1 driver

The driver starts the server, runs all smoke checks, prints results, and stops cleanly.

```powershell
powershell -File .claude\skills\run-baia-saas\smoke.ps1
```

Expected output (all green = pass):
```
[1] Clearing port 8000...
[2] Starting BA.IA backend...
[3] Waiting for server...
  Server up (PID 12345)
[4] Running smoke tests...
  OK  GET /
  OK  GET /model
  OK  POST /auth/register or /auth/login
  OK  GET /auth/me
  OK  GET /db/bandi
  OK  GET /db/aziende
  OK  GET /scraper/status

All smoke tests PASSED
  Frontend available at: http://127.0.0.1:8000/app
  API docs at:           http://127.0.0.1:8000/api/docs
  Token for manual use:  <token>
  Header to use:         X-Auth-Token: <token>
[5] Stopping server (PID 12345)...
  Done.
```

### Manual API testing while server is running

Start the server in one step (stays running), test in another:

```powershell
# Terminal 1 — start server
$env:PYTHONUTF8="1"; $env:PYTHONIOENCODING="utf-8"; $env:LICENSE_KEY="TEST-MODE"; $env:GROQ_API_KEY="dummy"
.venv\Scripts\uvicorn backend.app_locale:app --host 127.0.0.1 --port 8000 --log-level warning

# Terminal 2 — register and get token
$r = Invoke-WebRequest -Uri "http://127.0.0.1:8000/auth/register" -Method POST `
  -Body '{"email":"test@test.local","password":"TestPass123!","name":"Test"}' `
  -ContentType "application/json" -UseBasicParsing
$TOKEN = ($r.Content | ConvertFrom-Json).token

# Use token with X-Auth-Token header (NOT Authorization: Bearer)
$H = @{ "X-Auth-Token" = $TOKEN }
Invoke-WebRequest -Uri "http://127.0.0.1:8000/auth/me" -Headers $H -UseBasicParsing
Invoke-WebRequest -Uri "http://127.0.0.1:8000/db/bandi" -Headers $H -UseBasicParsing
```

---

## Run (human path)

Double-click `LANCIA.BAT` on Windows or run `./lancia.sh` on Mac/Linux. The launcher installs deps, starts the server, and opens `http://localhost:8000` in the default browser. Not useful headless.

---

## Key endpoints

| Method | Path | Auth? | Description |
|--------|------|-------|-------------|
| GET | `/` | no | Health check — returns JSON with status, version, mode |
| GET | `/model` | no | Active AI provider and model |
| POST | `/auth/register` | no | Register new user → `{ok, token, user}` |
| POST | `/auth/login` | no | Login → `{ok, token, user}` |
| GET | `/auth/me` | yes | Current user info |
| GET | `/db/bandi` | yes | List all grant calls |
| GET | `/db/aziende` | yes | List all companies |
| GET | `/db/sal` | yes | SAL tracker entries |
| GET | `/scraper/status` | yes | Scraper state (running, last_run, sources count) |
| GET | `/api/docs` | no | Swagger UI |

**Auth header:** `X-Auth-Token: <token>` — NOT `Authorization: Bearer`.

---

## Gotchas

- **Windows cp1252 crash on startup** — The app prints emoji (`🧪`) to stdout. Without `PYTHONUTF8=1`, uvicorn exits immediately with `UnicodeEncodeError: 'charmap' codec can't encode character`. Always set `$env:PYTHONUTF8="1"` before launching.

- **`Authorization: Bearer` does not work** — The app reads `request.headers.get("X-Auth-Token")`, not `Authorization`. Using `Bearer` gives `{"ok":false,"error":"Non autenticato"}` even with a valid token.

- **Token invalidated on server restart** — Sessions are persisted in SQLite (`./data/ai-bandi.db`), but tokens expire after 7 days. A restart with a fresh DB invalidates all tokens; re-register or re-login.

- **`GROQ_API_KEY=dummy` is fine for UI/auth testing** — The app starts and all CRUD/auth endpoints work. AI calls (`/analyze`, `/match/*`, `/prompt`) will return errors from Groq, but everything else is functional.

- **`LICENSE_KEY=TEST-MODE` bypasses all license checks** — Required for local testing. In production it's a `LIC-XXXX-XXXXXXXX` key verified against a license server.

- **PowerShell 5.1 `-Environment` parameter does not exist** — Use `$env:VAR = "value"` before `Start-Process`, not `-Environment @{...}`. The driver does this correctly.

---

## Troubleshooting

| Symptom | Fix |
|---------|-----|
| `UnicodeEncodeError: 'charmap'` on startup | Set `$env:PYTHONUTF8="1"` before launching uvicorn |
| `{"ok":false,"error":"Non autenticato"}` from `/auth/me` | Use `X-Auth-Token` header, not `Authorization: Bearer` |
| `Impossibile effettuare la connessione` (connection refused) | Server hasn't started yet; poll or wait 6s |
| Server exits immediately with no output | Check stderr file; likely missing `.env` or import error |
| `ModuleNotFoundError` | Run from project root (not from `backend/`); uvicorn needs `backend.app_locale:app` |
| Port already in use | `Stop-Process -Name "uvicorn" -Force` then retry |
