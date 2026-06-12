# 🤖 ISTRUZIONI PER CLAUDE IN CHROME

Apri questo file con Claude in Chrome e dagli il seguente prompt:

---

## PROMPT PER CLAUDE IN CHROME

```
Devi aggiornare la mia app BA.IA online su GitHub, Vercel, Render e Supabase.

I file aggiornati sono nello zip BA.IA-v3.1-cloud.zip che ho scaricato.

Procedi in questo ordine e CHIEDIMI CONFERMA prima di ogni step distruttivo:

═══════════════════════════════════════════════════════════
STEP 1 — GITHUB (push del nuovo codice)
═══════════════════════════════════════════════════════════

1. Vai su github.com
2. Apri il mio repository BA.IA (chiedimi il nome esatto se non lo trovi)
3. Verifica il branch principale (main o master)
4. Per ogni file nello zip che ho scaricato (BA.IA-v3.1-cloud.zip):
   - Carica i nuovi file backend/ , frontend/ , deploy/
   - In particolare assicurati che vengano caricati:
     • backend/app_locale.py (versione aggiornata)
     • backend/main.py
     • backend/scraper.py
     • backend/portal.py
     • backend/rendicontazione.py
     • backend/matcher.py
     • backend/db.py
     • backend/sqlite_pg_bridge.py
     • backend/requirements.txt
     • frontend/index.html
     • Dockerfile
     • vercel.json
     • render.yaml
     • deploy/supabase_schema.sql

5. Commit con messaggio: "feat: BA.IA v3.1 - portale clienti, rendicontazione, scraper, multi-AI"
6. Conferma che il commit appaia su GitHub

═══════════════════════════════════════════════════════════
STEP 2 — SUPABASE (aggiorna lo schema DB)
═══════════════════════════════════════════════════════════

1. Vai su supabase.com
2. Apri il progetto BA.IA
3. Vai su SQL Editor
4. Crea una nuova query
5. Copia tutto il contenuto del file deploy/supabase_schema.sql
6. CHIEDIMI CONFERMA prima di eseguire (potrebbe modificare tabelle esistenti)
7. Esegui (Run)
8. Verifica nel Table Editor che le tabelle siano presenti:
   - bandi, aziende, sal, history, users, sessions
   - portal_shares, portal_messages, portal_docs
   - rendicontazioni, rendicontazione_milestones,
     rendicontazione_documenti, rendicontazione_checklist
   - scraper_log

9. Vai su Settings → Database → Connection string
10. Copia la stringa "Connection pooling" (porta 6543)
11. Salvala — serve per Render

═══════════════════════════════════════════════════════════
STEP 3 — RENDER (backend)
═══════════════════════════════════════════════════════════

1. Vai su dashboard.render.com
2. Apri il servizio backend di BA.IA
3. Verifica che il push GitHub abbia triggerato il deploy automatico
4. Se no, clicca "Manual Deploy" → "Deploy latest commit"
5. Vai su Environment e verifica/aggiungi queste variabili:

   DATABASE_URL = [stringa Supabase pooler copiata allo step 2.10]
   GROQ_API_KEY = [mia chiave Groq attuale]
   AI_PROVIDER = groq
   AI_API_KEY = [stessa chiave Groq]
   APP_NAME = BA.IA
   LICENSE_KEY = TEST-MODE
   GROQ_MODEL = meta-llama/llama-4-scout-17b-16e-instruct
   ALLOWED_ORIGINS = [URL Vercel che otterrai allo step 4]

6. Save → Render riavvia automaticamente
7. Attendi il deploy completato (3-5 minuti)
8. Apri l'URL del backend (es. baia-backend.onrender.com)
9. Verifica che ritorni JSON con "status":"ok"

═══════════════════════════════════════════════════════════
STEP 4 — VERCEL (frontend)
═══════════════════════════════════════════════════════════

1. Vai su vercel.com
2. Apri il progetto BA.IA frontend
3. Verifica il deploy automatico da GitHub
4. Vai su Settings → Project → verifica:
   - Framework Preset: Other
   - Root Directory: . (radice)
   - Output Directory: frontend
   - Build Command: (vuoto o "echo skip")
5. Se il deploy non parte, clicca Deployments → Redeploy
6. Attendi il completamento (1-2 minuti)
7. Copia l'URL Vercel finale (es. baia.vercel.app)
8. Torna su Render e aggiorna ALLOWED_ORIGINS con questo URL

═══════════════════════════════════════════════════════════
STEP 5 — VERIFICA FINALE
═══════════════════════════════════════════════════════════

1. Apri l'URL Vercel del frontend in una nuova finestra
2. Dovresti vedere la nuova UI BA.IA v3.1 (sfondo nero, oro, design editoriale)
3. Verifica che siano presenti nel menu:
   - Dashboard
   - Bandi
   - Aziende
   - Matching
   - SAL Tracker
   - Rendicontazione (nuovo!)
   - Scraper Bandi (nuovo!)
   - Portale Clienti (nuovo!)
   - Impostazioni

4. Vai su Impostazioni e verifica i tab:
   - Provider AI (nuovo!)
   - White-label (nuovo!)
   - SMTP Email (nuovo!)
   - Sistema

5. Prova a registrarti come nuovo consulente per testare l'auth
6. Crea un bando di test e verifica che si salvi su Supabase

═══════════════════════════════════════════════════════════
PROBLEMI COMUNI E SOLUZIONI
═══════════════════════════════════════════════════════════

- Se Render non si avvia: controlla logs, di solito DATABASE_URL ha la password sbagliata o usa la porta 5432 invece di 6543

- Se frontend mostra "Backend non raggiungibile": vercel.json deve avere il rewrite /api/* → URL Render corretto

- Se Supabase rifiuta connessioni: assicurati di usare il Pooler (transaction mode, porta 6543), non la connessione diretta

- Se asyncpg dà errore "statement_cache_size": il bridge ha già statement_cache_size=0 per il pooler PgBouncer, dovrebbe funzionare

═══════════════════════════════════════════════════════════
FAI TUTTI GLI STEP NELL'ORDINE INDICATO.
DOPO OGNI STEP DIMMI COSA HAI FATTO E CHE RISULTATO HAI OTTENUTO.
SE QUALCOSA NON FUNZIONA, FERMATI E CHIEDIMI ISTRUZIONI.
═══════════════════════════════════════════════════════════
```

---

## NOTE IMPORTANTI

**Prima di dare il prompt a Claude in Chrome:**

1. **Scarica lo zip** `BA.IA-v3.1-cloud.zip` dalla nostra chat
2. **Estrailo** in una cartella facilmente accessibile (es. Desktop/BA.IA-v3.1)
3. **Apri Claude in Chrome** nella sidebar
4. **Loggati prima** su GitHub, Vercel, Render e Supabase (lascia le tab aperte)
5. **Incolla il prompt** sopra

**Claude in Chrome può:**
- Navigare sui siti
- Cliccare bottoni
- Compilare form
- Caricare file (gli puoi indicare lo zip estratto)
- Copiare valori tra schermate (es. URL Vercel → variabile Render)

**Claude in Chrome NON può:**
- Eseguire git push da terminale
- Per il push GitHub useremo l'interfaccia web (drag&drop dei file)

---

## ALTERNATIVA: Se preferisci farlo tu manualmente

Apri sequenzialmente:
1. https://github.com/[tuoutente]/[repo-baia] — drag&drop dei file aggiornati
2. https://supabase.com/dashboard/projects → SQL Editor → esegui supabase_schema.sql
3. https://dashboard.render.com → verifica deploy automatico + aggiungi DATABASE_URL
4. https://vercel.com/dashboard → verifica deploy automatico

Tempo totale stimato: 10-15 minuti.
