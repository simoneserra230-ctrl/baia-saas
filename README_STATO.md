# BA.IA SaaS B2C — Stato e Percorso al Lancio
# Aggiornato: 12 giugno 2026 | Ruolo strategico: IL CUNEO (primo prodotto da lanciare)

## Cos'è
Piattaforma AI per identificazione e analisi bandi di finanziamento HoReCa.
FastAPI + frontend JS + Anthropic API. Auth X-Auth-Token. Chiave API propria (finanziata).

## Stato attuale — COMPLETO AL ~80%
✅ Backend funzionante in locale (LANCIA.BAT / lancia.sh)
✅ Landing page (BAIA_landing_page.html) + area riservata + demo
✅ Moduli recenti: ai_advisor, regulatory_monitor, report_generator, rendicontazione
✅ Docker + docker-compose + render.yaml + vercel.json pronti
✅ Repo GitHub: simoneserra230-ctrl/baia-saas
✅ Skill Claude in .claude/
⬜ Deploy produzione MAI eseguito (Render + Vercel)
⬜ Prezzo e pagamenti (Stripe) non configurati
⬜ Zero clienti

## Percorso al "livello finale" (lancio)
➡️ **Runbook completo passo-passo: `LANCIO_BAIA.md`** (deploy Render+Vercel+Stripe, smoke test).

Stato 12/6/2026 — deploy-ready:
- ✅ Bug porta Dockerfile risolto (bind su $PORT di Render)
- ✅ Funnel: `frontend/index.html` = landing marketing con prezzi; `frontend/app.html` = app
- ✅ Pricing definito: Base €29 · Pro €79 · B2B €1.990 (già nel landing)
- ✅ CTA collegate (Inizia gratis → app; demo/team → WhatsApp)
- ⬜ Restano i passi sugli account (Supabase, Render, Vercel, Stripe) → vedi LANCIO_BAIA.md
- ⬜ Primi 10 clienti: suite AGENTI_FINANZA come servizio, content marketing scadenze bandi

## Collegamenti ecosistema
- AGENTI_FINANZA/AGENTE_PRATICA_BANDO.md = il servizio premium sopra il SaaS
- BAD360 modulo bandi = futuro white-label di questo motore

## Sicurezza
- .env e .env.render ESCLUSI dal repo (mai committare)
- File "BA.IA - SS KEY.txt" nella cartella padre: DA SPOSTARE in password manager
