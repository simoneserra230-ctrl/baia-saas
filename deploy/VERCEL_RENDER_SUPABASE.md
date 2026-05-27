# BA.IA — Deploy su Vercel + Render + Supabase

Setup ottimale per produzione: frontend statico veloce, backend scalabile,
database PostgreSQL gestito. **Tempo totale: ~15 minuti.**

---

## Architettura

```
   Utente browser
        ↓
   ┌────────────┐
   │   Vercel   │   ← Frontend statico (HTML/JS/CSS)
   │ baia.ver…  │     URL: tuoprogetto.vercel.app
   └─────┬──────┘
         │ /api/* riscritto a →
         ↓
   ┌────────────┐
   │   Render   │   ← Backend Python FastAPI
   │ baia.onr…  │     URL: baia-backend.onrender.com
   └─────┬──────┘
         │ Connessione PostgreSQL via pooler →
         ↓
   ┌────────────┐
   │  Supabase  │   ← Database PostgreSQL gestito
   │ db.supab…  │     Storage opzionale per documenti
   └────────────┘
```

---

## STEP 1 — Setup Supabase (3 minuti)

1. Accedi su [supabase.com](https://supabase.com)
2. **New project**:
   - Name: `baia-production`
   - Database Password: genera password forte e **annotala**
   - Region: **Frankfurt** (più vicina all'Italia)
   - Plan: **Free** va bene per iniziare
3. Attendi creazione (1-2 min)
4. **Settings** → **Database** → **Connection string** → tab **URI**
   - Copia la stringa che inizia con `postgresql://`
   - Sostituisci `[YOUR-PASSWORD]` con la password reale
   - Usa la **Connection Pooler** (Transaction mode, porta 6543)
   - Formato finale:
     ```
     postgresql://postgres.xxxxxx:PASSWORD@aws-0-eu-central-1.pooler.supabase.com:6543/postgres
     ```
5. **SQL Editor** → **New query**:
   - Apri il file `deploy/supabase_schema.sql`
   - Copia tutto il contenuto e incolla nell'editor SQL
   - **Run**
   - Dovresti vedere 14 tabelle create

**Annotati la `DATABASE_URL` — serve allo step successivo.**

---

## STEP 2 — Backend su Render (5 minuti)

### Opzione A: Da GitHub (consigliato)

1. Crea un repository GitHub con i file BA.IA
2. Su [render.com](https://dashboard.render.com) → **New** → **Blueprint**
3. Connetti il repo GitHub
4. Render rileva `render.yaml` e configura il servizio
5. Inserisci le **Environment Variables**:

| Variabile | Valore |
|-----------|--------|
| `DATABASE_URL` | la stringa Supabase del passo 1 |
| `GROQ_API_KEY` | la tua chiave Groq (gratis su console.groq.com) |
| `AI_API_KEY` | stessa chiave Groq |
| `ALLOWED_ORIGINS` | `https://tuoprogetto.vercel.app` (riempi dopo step 3) |

6. **Apply** → attendi build (~3 min)
7. Render genera un URL tipo `https://baia-backend.onrender.com`
8. **Annota questo URL** — serve allo step successivo

### Opzione B: Manuale

1. **New** → **Web Service**
2. Public Git repository → incolla URL del repo
3. Configurazione:
   - Name: `baia-backend`
   - Region: **Frankfurt**
   - Branch: `main`
   - Runtime: **Docker**
   - Plan: **Starter** ($7/mese) o **Free** (va in sleep dopo 15min)
4. Environment variables come sopra
5. **Create Web Service**

**Verifica funzionamento**: apri `https://baia-backend.onrender.com/` — dovresti vedere JSON con `"status":"ok"`.

---

## STEP 3 — Frontend su Vercel (3 minuti)

1. **Modifica `vercel.json`** sostituendo l'URL del backend:
   ```json
   "destination": "https://baia-backend.onrender.com/$1"
   ```
   con l'URL Render reale ottenuto allo step 2.

2. Su [vercel.com](https://vercel.com) → **Add New** → **Project**
3. Importa lo stesso repository GitHub
4. Configurazione:
   - Framework Preset: **Other**
   - Root Directory: `.` (radice)
   - Build Command: lascia vuoto o `echo skip`
   - Output Directory: `frontend`
5. **Deploy**
6. Vercel genera un URL `https://tuoprogetto.vercel.app`

**Torna su Render** → Environment → aggiorna `ALLOWED_ORIGINS` con l'URL Vercel finale → **Save** (riavvio automatico).

---

## STEP 4 — Custom domain (opzionale, 3 minuti)

### Per Vercel (frontend)
1. Vercel project → **Settings** → **Domains**
2. **Add** → inserisci `baia.tuodominio.it`
3. Vercel mostra i record DNS da configurare
4. Vai sul tuo registrar (Aruba, Register.it, ecc.) → DNS Manager
5. Aggiungi il record CNAME suggerito
6. Attendi propagazione (5-30 min) — HTTPS automatico via Vercel

### Per Render (backend)
Non serve dominio custom — il frontend lo chiama via `/api/*` interno.

---

## STEP 5 — Verifica e test (2 minuti)

1. Apri `https://baia.tuodominio.it` (o l'URL Vercel)
2. Schermata di registrazione BA.IA
3. **Registrati** come consulente
4. Crea un bando di prova
5. Controlla Supabase → **Table Editor** → `bandi` — dovresti vedere il record

---

## Costi mensili stimati

| Servizio | Free tier | Production |
|----------|-----------|------------|
| **Vercel** | 100GB bandwidth/mese | Free fino a 1TB |
| **Render Backend** | Sleep dopo 15min | $7/mese (Starter, always-on) |
| **Supabase** | 500MB DB + 1GB storage | $25/mese (Pro, 8GB + 100GB) |
| **Groq AI** | 14.400 req/giorno | Free anche in prod |
| **Dominio** | — | ~€12/anno |

**Setup professionale realistico**: ~$32/mese (€30) — sostenibile da 1-2 clienti.

---

## File storage per documenti

Render e Vercel non hanno filesystem persistente. Per upload di documenti (PDF, allegati portale, giustificativi rendicontazione) usa **Supabase Storage**:

1. Su Supabase → **Storage** → **Create bucket**
2. Nome: `baia-docs`
3. **Public bucket**: NO (privato)
4. Genera service role key in Settings → API
5. Aggiungi a Render env:
   - `SUPABASE_URL=https://xxxx.supabase.co`
   - `SUPABASE_SERVICE_KEY=eyJh...`

Il codice rileva queste variabili automaticamente e usa Supabase Storage invece del filesystem locale.

---

## Sicurezza produzione

### Cose critiche

- ✅ `DATABASE_URL` mai in repository (solo env Render)
- ✅ `GROQ_API_KEY` mai esposta al frontend
- ✅ `ALLOWED_ORIGINS` configurato solo con dominio Vercel reale
- ✅ HTTPS forzato (Vercel + Render default)
- ✅ Sessioni hash-based (già implementato)
- ❌ NON committare mai `.env` con chiavi reali

### Backup automatici

Supabase Free fa backup giornalieri automatici per 7 giorni. Per più sicurezza:

```bash
# Schedula backup settimanale via GitHub Actions
# .github/workflows/backup.yml — esempio
```

---

## Troubleshooting

**"500 Internal Server Error" su Render**
→ Controlla i logs Render → di solito `DATABASE_URL` malformata o Groq key mancante

**Frontend Vercel vede "Backend non raggiungibile"**
→ Verifica `vercel.json` → `destination` punta al backend Render giusto
→ Controlla `ALLOWED_ORIGINS` su Render include il dominio Vercel

**"Connection refused" Supabase**
→ Usa la connection string del **Pooler** (porta 6543), non quella diretta (5432)
→ Verifica `?pgbouncer=true` viene rimosso automaticamente dal codice

**Render va in sleep su piano free**
→ Upgrade a Starter ($7/mese) per always-on
→ Oppure usa cron-job.org per ping ogni 14 min (workaround sgradevole)

---

## Scaling oltre

Quando supererai i ~50 utenti attivi giornalieri:

1. **Render** Starter → Standard ($25/mese, più RAM)
2. **Supabase** Free → Pro ($25/mese, DB più grosso, backup, support)
3. **CDN per frontend**: già incluso in Vercel
4. **Queue per scraper**: integra Upstash Redis per separare job lunghi

---

*Per il setup multi-tenant (un'istanza, più studi): vedi note tecniche in DEPLOY.md.*
