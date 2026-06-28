# 🔁 BA.IA — Guida al REDEPLOY (prod già esistente)

> BA.IA è già online (Render backend Docker + Vercel frontend). Questa guida serve a
> **rilasciare le modifiche recenti** in sicurezza. Niente viene pubblicato in automatico
> da qui: il deploy parte quando fai `git push` (Render/Vercel ribuildano da soli).

## Architettura (invariata)
- **Backend**: Render, servizio `baia-backend`, **Docker** (`Dockerfile`), region frankfurt.
  DB: PostgreSQL (Neon/Supabase) via `DATABASE_URL` (in locale SQLite). AI via httpx → Anthropic.
- **Frontend**: Vercel (statico, cartella `frontend/`). `vercel.json` riscrive
  `/api/(.*)` → `https://baia-backend.onrender.com/$1`. L'app usa `location.origin + '/api'`
  su *.vercel.app, quindi le chiamate (incluso il nuovo AI Studio) passano dal proxy.

## Cosa è cambiato (da rilasciare)
- **AI Studio** in `frontend/app.html` + `backend/baia_ai.py`: chat KB, blog, business-plan,
  pitch-deck, compliance, e il **nuovo tab "Email" → `/ai/email/outreach`** (generatore email
  outreach cliente per bando, importato da DAPC2). Usa l'infra esistente (`anthropic_call`,
  `require_auth`) → **nessuna nuova dipendenza**.
- **KB finanza+AI** versionata in `backend/kb_data/` → arriva in prod col codice (niente upload manuale).

## Passi di redeploy
1. **Commit + push** del repo `baia-saas` (branch di prod). Render builda il Docker, Vercel il frontend.
2. **Verifica le env su Render** (Dashboard → baia-backend → Environment), in particolare:
   - `ANTHROPIC_API_KEY` ✅ (necessaria per TUTTO l'AI Studio, incluso il tab Email)
   - `AI_MODEL` (oggi `claude-haiku-4-5-20251001`) — valuta `claude-sonnet-4-6` per qualità superiore
   - `DATABASE_URL`, `ALLOWED_ORIGINS` (l'URL Vercel), `APP_URL`, SMTP_* (se usi invio email/inviti)
3. **DB**: nessuna migrazione manuale — `db.init_schema()` è **idempotente** (crea le tabelle se mancano).
4. **Vercel**: se il dominio/URL backend cambia, aggiorna la `destination` in `vercel.json`.

## Verifica post-deploy
- `https://<backend>/api/docs` risponde (FastAPI docs).
- Login nell'app → apri **AI Studio (✨)** → tab **Email** → genera una bozza (deve tornare testo + disclaimer).
- Le cifre nelle bozze AI sono marcate `[DA VERIFICARE]` (human-in-the-loop) — atteso.

## Note
- Mai `ANTHROPIC_API_KEY` nel frontend: sta solo nelle env di Render.
- Se l'AI Studio dà "AI non raggiungibile": manca/è errata `ANTHROPIC_API_KEY` su Render.
