# 🚀 LANCIO BA.IA — Runbook Deploy & Go-Live
# Tutto ciò che serve per mettere BA.IA online. Aggiornato: 12 giugno 2026.
# Stato codice: deploy-ready. Restano solo i passi sugli account (sotto).

---

## 0. ARCHITETTURA DEL DEPLOY (com'è fatto)

```
  Visitatore
      │
      ▼
  VERCEL (frontend statico, gratis)
   ├── /            → frontend/index.html   (LANDING marketing + prezzi)
   ├── /app.html    → l'applicazione (login/registrazione, dashboard)
   └── /api/*  ──────────────► riscritto a ────► RENDER
                                                   │
                              RENDER (backend Docker, piano starter)
                              FastAPI · backend/app_locale:app
                                                   │
                                                   ▼
                              SUPABASE (PostgreSQL) + ANTHROPIC (Claude)
```

Il frontend rileva l'ambiente da solo (`BACKEND_URL` in index/app): su `*.vercel.app`
usa `/api` (riscritto da `vercel.json` verso Render). Su dominio custom: vedi §6.

---

## 1. PRIMA DI TUTTO — Segreti e account (15 min)

- [ ] **Sposta le chiavi** `recovery-codes.txt` e `BA.IA - SS KEY.txt` dal Desktop a un
      password manager. Non servono nel repo.
- [ ] **Supabase**: progetto attivo → copia la **connection string** (Pooler, modalità
      `psycopg`/`asyncpg`, con `sslmode=require`). Sarà la `DATABASE_URL`.
      → Esegui lo schema del DB se non già fatto (tabelle bandi/aziende/utenti).
- [ ] **Anthropic**: chiave API di BA.IA (finanziata, NON quella del progetto Formazione).
      Console → verifica credito disponibile.

---

## 2. DEPLOY BACKEND — Render (10 min)

1. [ ] dashboard.render.com → **New → Web Service** → connetti GitHub `baia-saas`
2. [ ] Root Directory: **VUOTO** (il repo `baia-saas` ha già `Dockerfile`/`render.yaml`
       nella sua radice — NON mettere sottocartelle). Render rileva il `Dockerfile`.
3. [ ] Runtime: **Docker** · Plan: **Starter** (evita il cold start del free) · Region: **Frankfurt**
4. [ ] **Environment Variables** (le `sync:false` vanno inserite qui):
       | Chiave | Valore |
       |---|---|
       | `DATABASE_URL` | (Supabase pooler, da §1) |
       | `ANTHROPIC_API_KEY` | (chiave BA.IA) |
       | `ALLOWED_ORIGINS` | (URL Vercel — lo sai dopo §3; metti `*` ora, stringi dopo) |
       | `APP_URL` | (URL Vercel) |
       | `SMTP_HOST/USER/PASS/FROM` | (opzionale — per email alert/reset) |
       Le altre (`AI_MODEL`, `APP_NAME`, `PYTHONUTF8`…) sono già nel `render.yaml`.
5. [ ] Deploy. Verifica: l'URL `https://baia-backend.onrender.com/` risponde (health `/`).
       ⚠️ Il `Dockerfile` ora bind su `$PORT` di Render (fix 12/6) — il deploy non fallisce più sulla porta.

---

## 3. DEPLOY FRONTEND — Vercel (5 min)

1. [ ] vercel.com → **Add New → Project** → importa `baia-saas`
2. [ ] Root Directory: **VUOTO** (il repo `baia-saas` ha `vercel.json` nella radice).
       Vercel legge `vercel.json`: serve `frontend/`, riscrive `/api/*` → Render.
3. [ ] Nessun build necessario (sito statico). Deploy.
4. [ ] Ottieni l'URL `https://<progetto>.vercel.app`. Aprilo: deve mostrare il **landing**.
5. [ ] Torna su Render → aggiorna `ALLOWED_ORIGINS` e `APP_URL` con l'URL Vercel reale → redeploy.

---

## 4. PAGAMENTI — Stripe (MVP, 15 min)

Per partire NON serve integrare Stripe nel codice: usa **Payment Links** (zero codice).

1. [ ] dashboard.stripe.com → **Payment Links** → crea 3 link ricorrenti:
       | Piano | Prezzo | Tipo |
       |---|---|---|
       | Base | €29 / mese | subscription |
       | Pro | €79 / mese | subscription |
       | (Pro annuale) | €699 / anno | subscription |
       Il B2B (€1.990 una tantum) → contatto WhatsApp (già collegato).
2. [ ] Il funnel attuale è **trial-first**: le CTA "Inizia gratis" → `app.html` (registrazione,
       14 giorni, no carta). Alla conversione invii il Payment Link giusto.
       → Quando vorrai automatizzare: integra **Stripe Checkout** + webhook su `app_locale.py`.

---

## 5. SMOKE TEST (prima di promuovere — 10 min)

- [ ] Landing carica su Vercel, prezzi visibili, CTA "Inizia gratis" → app.html
- [ ] Registrazione nuovo utente funziona (scrive su Supabase)
- [ ] Login funziona, token salvato
- [ ] Inserimento profilo azienda → match bandi AI restituisce risultati (Claude risponde)
- [ ] Export PDF scheda bando
- [ ] Alert email (se SMTP configurato)
- [ ] Da mobile: landing responsive, app usabile

---

## 6. NOTE & TODO COSMETICI (non bloccanti)

- **Dominio custom** (es. `baia.skillsolutions.com`): il rewrite `/api` di Vercel funziona
  su qualsiasi dominio, ma la logica `BACKEND_URL` usa `/api` solo su `*.vercel.app`.
  Su dominio custom imposta in `app.html`/`index.html`: `window.BAIA_BACKEND_URL='/api'`
  (oppure lancia prima su `*.vercel.app`).
- **Link footer del landing** ancora `href="#"` (Blog, Changelog, Chi siamo…): cosmetici,
  da collegare quando esistono le pagine. `Privacy` → `privacy.html` (già presente).
- **README_STATO.md**: stato passa da 80% → deploy-ready dopo questo runbook.

---

## RIEPILOGO PRICING (già nel landing)

| Piano | Prezzo | Per chi |
|---|---|---|
| **Base** | €29/mese | singolo locale, 1 profilo, top 3 match/giorno |
| **Pro** ⭐ | €79/mese | 3 profili, DB completo, realtime, PDF, API |
| **B2B PRO LAN/NAS** | €1.990 una tantum | studi consulenza, on-premise, white-label |

Razionale: un singolo bando vinto vale migliaia di €. €29-79/mese è un "sì" facile.
Il B2B una tantum monetizza i consulenti (che sono anche un canale di rivendita).
