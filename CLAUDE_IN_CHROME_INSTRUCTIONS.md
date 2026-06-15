# 🤖 CLAUDE IN CHROME — Deploy BA.IA (prompt aggiornato 12/6/2026)

Il codice è GIÀ su GitHub (repo `simoneserra230-ctrl/baia-saas`, ultimo commit pushato).
NON serve più caricare zip o fare drag&drop: Render e Vercel leggono direttamente da GitHub.

## PRIMA DI INIZIARE
1. Apri Claude in Chrome (sidebar).
2. Loggati e lascia aperte le tab: github.com, supabase.com, dashboard.render.com, vercel.com, dashboard.stripe.com
3. Tieni a portata (in un password manager, NON in chat): la `DATABASE_URL` di Supabase e la chiave `ANTHROPIC_API_KEY` di BA.IA.
4. Incolla il prompt qui sotto.

---

## PROMPT (copia da qui)

```
Sei il mio assistente di deploy. Dobbiamo mettere online BA.IA, una SaaS di analisi
bandi (FastAPI + frontend statico). Il codice è già su GitHub: simoneserra230-ctrl/baia-saas.
Root del progetto dentro il repo: "BA.IA.SKILLSOLUTIONS.COM/BAIA_SAAS_B2C (OPEX)".

REGOLE:
- Procedi UN passo alla volta. Dopo ogni passo dimmi cosa hai fatto e l'esito.
- Prima di QUALSIASI azione distruttiva (eseguire SQL, sovrascrivere config) CHIEDIMI CONFERMA.
- I segreti (DATABASE_URL, chiavi API) li incollo IO direttamente nei campi del dashboard:
  quando serve un segreto, fermati e chiedimelo — non scriverlo mai nella chat.

═══ STEP 1 — SUPABASE (database) ═══
1. Vai su supabase.com → progetto BA.IA (se non esiste, dimmelo e lo creiamo).
2. SQL Editor → nuova query. Nel repo GitHub, dentro la cartella "deploy/", trova il
   file dello schema (es. supabase_schema.sql). Aprilo, copia il contenuto nella query.
3. FERMATI e chiedimi conferma prima di premere Run (può modificare tabelle esistenti).
4. Dopo Run, in Table Editor verifica che esistano almeno: bandi, aziende, sal, history, users, sessions.
5. Settings → Database → Connection string → modalità "Connection pooling" (porta 6543,
   transaction mode). Dimmi quando ce l'hai: sarà la DATABASE_URL per Render (la incollo io).

═══ STEP 2 — RENDER (backend) ═══
1. dashboard.render.com → New → Web Service → connetti il repo baia-saas.
2. Root Directory: BA.IA.SKILLSOLUTIONS.COM/BAIA_SAAS_B2C (OPEX)
   (Render rileva render.yaml + Dockerfile). Runtime: Docker. Plan: Starter. Region: Frankfurt.
3. Environment → aggiungi queste variabili (i valori segreti li incollo io):
   - DATABASE_URL      = (Supabase pooler, porta 6543)
   - ANTHROPIC_API_KEY = (chiave BA.IA — NON quella del progetto Formazione)
   - ALLOWED_ORIGINS   = * (lo stringiamo all'URL Vercel dopo lo Step 3)
   - APP_URL           = (lo metto dopo, è l'URL Vercel)
   - SMTP_HOST/USER/PASS/FROM = (opzionali, solo se vuoi email)
   Le altre (AI_MODEL=claude-haiku, APP_NAME, PYTHONUTF8) sono già in render.yaml.
4. Crea il servizio e avvia il deploy. Aspetta che finisca (3-5 min).
5. Apri l'URL del backend (tipo https://baia-backend.onrender.com/) e verifica che risponda
   senza errore (è la health "/"). Se fallisce, aprimi i Logs e dimmi l'errore.

═══ STEP 3 — VERCEL (frontend) ═══
1. vercel.com → Add New → Project → importa baia-saas.
2. Root Directory: BA.IA.SKILLSOLUTIONS.COM/BAIA_SAAS_B2C (OPEX)
   (Vercel legge vercel.json: serve la cartella frontend/, riscrive /api/* verso Render).
   Framework Preset: Other. Build: vuoto. Deploy.
3. Apri l'URL Vercel ottenuto (tipo https://baia-xxxx.vercel.app): DEVE mostrare il
   LANDING marketing con i prezzi (Base €29, Pro €79, B2B €1.990), non l'app.
4. Clicca "Inizia gratis": deve portare a /app.html (la schermata di login/registrazione).
5. Dammi l'URL Vercel: torno su Render e aggiorno ALLOWED_ORIGINS e APP_URL con quell'URL,
   poi redeploy del backend.

═══ STEP 4 — STRIPE (pagamenti, MVP) ═══
1. dashboard.stripe.com → Payment Links → crea 3 link ricorrenti:
   Base €29/mese · Pro €79/mese · Pro annuale €699/anno (tutti subscription).
2. Dammi i 3 link: li useremo per la conversione dal trial (il B2B €1.990 va via WhatsApp).

═══ STEP 5 — SMOKE TEST ═══
Sull'URL Vercel: 1) il landing carica e i prezzi sono visibili; 2) "Inizia gratis" apre app.html;
3) registrazione nuovo utente OK (scrive su Supabase); 4) login OK; 5) inserisco un profilo
azienda e il match bandi AI risponde (Claude); 6) export PDF di una scheda. Riportami ogni esito.

Se qualcosa si rompe, FERMATI, mandami l'errore (e i Logs Render se è il backend) e aspetta.
```

---

## PROBLEMI COMUNI
- **Render non parte**: di solito DATABASE_URL ha password errata o usa la porta 5432 invece di 6543 (serve il Pooler).
- **Frontend "Backend non raggiungibile"**: vercel.json deve riscrivere /api/* → URL Render corretto (baia-backend.onrender.com).
- **Supabase rifiuta connessioni**: usa il Pooler in transaction mode (6543), non la connessione diretta.
- **asyncpg "statement_cache_size"**: il bridge SQLite→PG ha già statement_cache_size=0 per PgBouncer, dovrebbe funzionare.
- **Porta**: il Dockerfile ora fa bind su $PORT di Render (fix 12/6) — non fallisce più sulla porta.

## COSA CLAUDE IN CHROME PUÒ / NON PUÒ
Può: navigare, cliccare, compilare form, copiare valori tra schermate (es. URL Vercel → variabile Render).
Non può (e non deve): vedere/scrivere i tuoi segreti in chat — quelli li incolli tu nei campi del dashboard.

Riferimento completo dei passi: `LANCIO_BAIA.md` (stessa cartella).
