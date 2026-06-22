# 🧠 LOGICA E STRUTTURA — Agenti Bandi BA.IA
# Cosa ho imparato dalla cartella esempio reale (DEMO/) — la logica di ragionamento
# che gli agenti della piattaforma devono replicare.
# ⚠️ I dati del cliente reale sono SENSIBILI: mai riportarli in piattaforma né qui.
#     Si conserva solo la LOGICA di ragionamento, non i dati. La cartella DEMO/ con i
#     documenti reali è esclusa da git (.gitignore) e non va mai pubblicata.

---

## COME È ORGANIZZATA UNA CARTELLA BANDO (struttura standard)

```
[ID]_[anno]_[NomeBando]/
├── [ID]_Analisi_Tecnica_[Nome].docx   ← OUTPUT chiave (la "Scheda Progetto", 16 campi)
├── Normativa/                          ← FONTE: decreto, circolare, guide compilazione,
│                                          manuale piattaforma, regolamento UE
├── Allegati/                           ← moduli da compilare, divisi per FASE:
│   ├── Allegati prima fase di valutazione/
│   ├── Allegati seconda fase di valutazione/
│   └── Allegati perfezionamento contratto/
├── Checklist/                          ← cosa serve, per fase (prima/seconda/perfezionamento)
├── Comunicazione/                      ← brochure, template comunicazione, materiale CONFAPI
├── FAQ/                                ← chiarimenti (email/risposte ufficiali)
├── Elenco soggetti ammessi/           ← graduatorie/determine (se pubblicate)
└── [calcolo agevolazioni].xlsx        ← fogli di calcolo del contributo
```

**Flusso logico**: i documenti in `Normativa/` (decreto, circolare, guide) sono la
FONTE da cui si sintetizza l'`Analisi_Tecnica.docx`. Gli `Allegati/` e le `Checklist/`
dicono COSA serve per partecipare, fase per fase.

---

## IL TEMPLATE "ANALISI TECNICA" = SCHEDA PROGETTO (16 campi fissi)

L'analisi tecnica è una TABELLA con questi campi, nell'ordine esatto:

| # | Campo | Cosa contiene |
|---|-------|---------------|
| 1 | **SCHEDA PROGETTO** | intestazione |
| 2 | Redattore/Data/Numero cartella | ⚠️ DA OMETTERE/ANONIMIZZARE nella versione piattaforma (no nomi/loghi azienda) |
| 3 | Iniziativa/Bando | ente erogatore + nome bando |
| 4 | Obiettivo | finalità del bando in 2-4 frasi |
| 5 | Tempistiche | apertura/chiusura domanda, finestre, scadenze |
| 6 | Soggetti beneficiari e requisiti di ammissibilità | CHI può partecipare (forma giuridica, dimensione, sede, ATECO, anzianità) |
| 7 | Spese ammissibili | cosa è finanziabile |
| 8 | Vincoli e Requisiti | soglie, condizioni (es. "min 50% domotica") |
| 9 | Spese NON ammissibili | cosa è escluso |
| 10 | Agevolazioni concedibili | tipo (fondo perduto/finanziamento) + % + importi |
| 11 | Cumulabilità | con altri aiuti (de minimis, GBER) |
| 12 | Erogazione delle agevolazioni | modalità (anticipo/SAL/saldo) |
| 13 | Budget | dotazione complessiva |
| 14 | Modalità di presentazione della Domanda | piattaforma (SIPES, Invitalia...), SPID/firma |
| 15 | Sito di riferimento | URL ufficiale |
| 16 | Note per la rendicontazione | periodo ammissibilità spese, scadenze, regole fatture |

**Regola di stile (richiesta utente)**: l'agente produce QUESTO formato, ma SENZA loghi,
intestazioni o riferimenti all'azienda di consulenza. Solo i contenuti dei 16 campi.

---

## LA LOGICA DEL MATCH AZIENDA ↔ BANDO

Dalla cartella cliente (`Doc. azienda/`): Business Plan + Descrizione Progetto +
**Scheda Scouting Finanza Agevolata** (il documento dove si valuta l'idoneità).

Il match confronta gli ATTRIBUTI dell'azienda con i REQUISITI del bando (campo 6):

| Attributo azienda | Requisito bando da confrontare |
|---|---|
| Forma giuridica | forme ammesse (Srl, coop, ditta individuale, persona fisica...) |
| Anzianità (anni dalla costituzione) | fasce ammesse (es. 0-3 / 3-5 anni per Nuove Imprese) |
| Codice ATECO / settore | settori ammessi (turismo, socio-sanitario, ecc.) |
| Sede operativa (regione/comune) | territorio richiesto (es. Sardegna) |
| Dimensione (PMI/micro) | dimensione richiesta |
| Tipo di progetto/spese previste | spese ammissibili (campo 7) |
| Capacità di cofinanziamento | quota a carico + de minimis residuo |

**Esempio reale appreso**: un'azienda turistica/ricettiva nuova in Sardegna →
matchata a "Nuove Imprese a Tasso Zero" (nuove imprese 0-5 anni) e/o "Alberghi
Diffusi". Una struttura di assistenza residenziale in Sardegna → "IN.DO.M.A.U.S".

**Output del match**: punteggio di compatibilità (alto/medio/basso) + i requisiti
soddisfatti e quelli mancanti/da verificare.

---

## COME UNA CARTELLA CLIENTE È ORGANIZZATA (per la fase operativa)

```
[Cliente]/
├── Doc. azienda/        ← Business Plan, Descrizione Progetto, Scheda Scouting
├── Doc. contabile/      ← bilanci, documenti fiscali
├── Doc. tecnica/        ← documentazione tecnica del progetto
├── Allegati/            ← moduli del bando compilati per il cliente
├── Allegati da firmare/ ← da far firmare
├── Check list/          ← checklist di fase
├── [Ente]/ (es. INVITALIA) ← documenti/output della piattaforma del bando
└── Materiale lavoro/    ← appunti, calcoli
```

Questa struttura è il punto di arrivo: dopo il match, si apre la pratica cliente
e si raccolgono/compilano i documenti seguendo Checklist e Allegati del bando.

---

## I 4 AGENTI DA COSTRUIRE (file in questa cartella)

1. **AGENTE_INGESTION_MONITORAGGIO** — monitora i siti dei bandi, scarica gli allegati,
   organizza la cartella standard. È l'ingresso automatico della documentazione.
2. **AGENTE_ANALISI_TECNICA** — dai documenti `Normativa/` produce la Scheda Progetto
   (16 campi), nello stile del template ma SENZA loghi/riferimenti azienda.
3. **AGENTE_MATCH_AZIENDA_BANDO** — confronta profilo azienda ↔ requisiti bando con la
   logica sopra; produce compatibilità + requisiti soddisfatti/mancanti.
4. **AGENTE_RICONTROLLO_BANDI** — all'inserimento di un NUOVO bando, ri-passa tutte le
   aziende già in piattaforma e segnala i nuovi match.
