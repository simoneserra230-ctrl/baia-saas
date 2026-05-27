# BA.IA — Piattaforma AI per Finanza Agevolata Italiana

Software professionale on-premise per consulenti che si occupano di bandi
di finanza agevolata, dalla ricerca alla rendicontazione finale.

---

## Avvio

**Windows** — doppio click su `LANCIA.BAT`
**Mac / Linux** — doppio click su `lancia.sh`

Al primo avvio l'app installa tutte le dipendenze (1-2 minuti) e apre il
browser con un wizard guidato per configurare la chiave AI.

---

## Funzionalità

**Analisi bandi AI** — Carica PDF di bandi, estrazione automatica di tutti
i campi rilevanti (scadenze, beneficiari, importi, requisiti, regimi di aiuto)
con checklist adempimenti generata in automatico.

**Multi-AI provider** — Groq (default, gratuito), Claude, OpenAI, Gemini,
Mistral. Chiave API personalizzata per il professionista.

**Scraper automatico** — Monitoraggio quotidiano di 12 fonti italiane:
Invitalia, MIMIT, SIMEST, CDP, Unioncamere, Regioni Sardegna, Lombardia,
Lazio, Campania, Toscana, Emilia-Romagna, Veneto. Run automatico alle
03:00 CET, trigger manuale disponibile.

**Profili azienda** — Inserimento manuale, da CSV, o estrazione AI da
bilancio, visura camerale, business plan.

**Matching semantico** — TF-IDF cosine similarity locale (zero costo, zero
chiamate API) + embedding reali se il provider lo supporta. Matrice N
aziende × M bandi.

**SAL Tracker** — Kanban drag & drop a 5 colonne: Identificato → In
lavorazione → Presentato → Approvato → Erogato. Collegamento bando/azienda,
importo, scadenza, storia dei movimenti.

**Rendicontazione** — Gestione post-approvazione completa: milestone SAL
configurabili (unico/doppio/triplo), upload giustificativi con estrazione
AI automatica (fattura/bonifico/contratto), checklist conformità con 12
controlli standard per la finanza agevolata italiana, calcolo importi
rendicontati vs ammessi, report Word professionale per l'ente.

**Portale Clienti** — Workspace condiviso consulente ↔ cliente. Invita
clienti via email, condividi bandi/SAL con permessi configurabili, thread
messaggi per ogni pratica, upload documenti dal cliente.

**White-label completo** — Nome studio, logo, colore primario, tagline,
footer report personalizzabili.

**Export** — PDF e Word professionali con dati strutturati, checklist,
tabelle giustificativi.

**Multi-utente** — Sistema autenticazione con ruoli Consulente / Cliente,
sessioni separate, login Google.

---

## Requisiti

- Python 3.10 o superiore — [python.org](https://python.org)
- Connessione internet (per AI e scraper)
- Chrome, Firefox, Safari o Edge moderni

---

## Privacy & Dati

Tutti i documenti caricati vengono elaborati e archiviati esclusivamente
sul tuo computer. Le uniche comunicazioni esterne sono:

- Le chiamate API verso il provider AI scelto (solo per analisi testo)
- Lo scraper, che fa richieste GET pubbliche alle fonti istituzionali

Nessun dato viene mai inviato a server BA.IA. Il database SQLite resta
nella cartella `data/`.

---

## Configurazione AI

Al primo avvio, ottieni una chiave gratuita su:

- **Groq** — [console.groq.com](https://console.groq.com) (raccomandato, gratis)
- **Claude** — [console.anthropic.com](https://console.anthropic.com) (qualità massima)
- **OpenAI** — [platform.openai.com](https://platform.openai.com)
- **Gemini** — [makersuite.google.com](https://makersuite.google.com)
- **Mistral** — [console.mistral.ai](https://console.mistral.ai) (privacy UE)

Cambiabile in qualsiasi momento da Impostazioni → Provider AI.

---

## Struttura del pacchetto

```
BA.IA/
├── LANCIA.BAT / lancia.sh    Launcher universale (Windows / Mac-Linux)
├── .env.example              Template variabili d'ambiente
├── docker-compose.yml        Avvio via Docker (backend + nginx)
├── render.yaml               Deploy cloud su Render.com
├── vercel.json               Deploy frontend su Vercel
├── backend/
│   ├── app_locale.py         Entry point principale — auth, white-label, export Word
│   ├── main.py               Endpoint CRUD core (bandi, aziende, SAL, matching)
│   ├── db.py                 Livello database SQLite / PostgreSQL
│   ├── matcher.py            Matching semantico TF-IDF
│   ├── scraper.py            Scraper automatico fonti italiane
│   ├── portal.py             Portale clienti
│   ├── rendicontazione.py    Gestione SAL e giustificativi
│   ├── sqlite_pg_bridge.py   Bridge automatico SQLite → PostgreSQL
│   ├── requirements.txt      Dipendenze Python
│   └── Dockerfile            Immagine Docker per il backend
├── frontend/
│   └── index.html            SPA completa (HTML + CSS + JS, zero build)
├── nginx/
│   └── default.conf          Config Nginx per il frontend containerizzato
└── data/                     Database SQLite (creato al primo avvio)
```

---

## API e documentazione

Il backend espone una REST API completa. Con il server avviato:

- **App web** → `http://localhost:8000/app`
- **Swagger UI** → `http://localhost:8000/api/docs`
- **Health check** → `http://localhost:8000/` (JSON con stato, versione, provider)

L'autenticazione usa il header `X-Auth-Token: <token>` restituito da
`POST /auth/register` o `POST /auth/login`.

---

## Avvio avanzato (Docker)

In alternativa al launcher, è possibile avviare tutto con Docker Compose:

```bash
cp .env.example .env   # compila GROQ_API_KEY e LICENSE_KEY
docker compose up
```

- Backend disponibile su `http://localhost:8000`
- Frontend (Nginx) su `http://localhost:8080`

---

*BA.IA v3.0 — Finanza agevolata, semplificata.*
# Agent Instructions

You're working inside the **WAT framework** (Workflows, Agents, Tools). This architecture separates concerns so that probabilistic AI handles reasoning while deterministic code handles execution. That separation is what makes this system reliable.

## The WAT Architecture

**Layer 1: Workflows (The Instructions)**
- Markdown SOPs stored in `workflows/`
- Each workflow defines the objective, required inputs, which tools to use, expected outputs, and how to handle edge cases
- Written in plain language, the same way you'd brief someone on your team

**Layer 2: Agents (The Decision-Maker)**
- This is your role. You're responsible for intelligent coordination.
- Read the relevant workflow, run tools in the correct sequence, handle failures gracefully, and ask clarifying questions when needed
- You connect intent to execution without trying to do everything yourself
- Example: If you need to pull data from a website, don't attempt it directly. Read `workflows/scrape_website.md`, figure out the required inputs, then execute `tools/scrape_single_site.py`

**Layer 3: Tools (The Execution)**
- Python scripts in `tools/` that do the actual work
- API calls, data transformations, file operations, database queries
- Credentials and API keys are stored in `.env`
- These scripts are consistent, testable, and fast

**Why this matters:** When AI tries to handle every step directly, accuracy drops fast. If each step is 90% accurate, you're down to 59% success after just five steps. By offloading execution to deterministic scripts, you stay focused on orchestration and decision-making where you excel.

## How to Operate

**1. Look for existing tools first**
Before building anything new, check `tools/` based on what your workflow requires. Only create new scripts when nothing exists for that task.

**2. Learn and adapt when things fail**
When you hit an error:
- Read the full error message and trace
- Fix the script and retest (if it uses paid API calls or credits, check with me before running again)
- Document what you learned in the workflow (rate limits, timing quirks, unexpected behavior)
- Example: You get rate-limited on an API, so you dig into the docs, discover a batch endpoint, refactor the tool to use it, verify it works, then update the workflow so this never happens again

**3. Keep workflows current**
Workflows should evolve as you learn. When you find better methods, discover constraints, or encounter recurring issues, update the workflow. That said, don't create or overwrite workflows without asking unless I explicitly tell you to. These are your instructions and need to be preserved and refined, not tossed after one use.

## The Self-Improvement Loop

Every failure is a chance to make the system stronger:
1. Identify what broke
2. Fix the tool
3. Verify the fix works
4. Update the workflow with the new approach
5. Move on with a more robust system

## File Structure

**What goes where:**
- **Deliverables**: Final outputs go to cloud services (Google Sheets, Slides, etc.) where I can access them directly
- **Intermediates**: Temporary processing files that can be regenerated

**Directory layout:**
```
.tmp/              # Temporary files (scraped data, intermediate exports). Regenerated as needed.
tools/             # Python scripts for deterministic execution
workflows/         # Markdown SOPs defining what to do and how
.env               # API keys and environment variables (NEVER store secrets anywhere else)
credentials.json, token.json  # Google OAuth (gitignored)
```

**Core principle:** Local files are just for processing. Anything I need to see or use lives in cloud services. Everything in `.tmp/` is disposable.

## Bottom Line

You sit between what I want (workflows) and what actually gets done (tools). Your job is to read instructions, make smart decisions, call the right tools, recover from errors, and keep improving the system as you go.

Stay pragmatic. Stay reliable. Keep learning.
