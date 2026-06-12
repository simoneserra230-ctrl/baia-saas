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
1. Deploy backend su Render (render.yaml pronto; env da .env.render — NON è nel repo)
2. Deploy frontend/landing su Vercel (vercel.json pronto)
3. Smoke test produzione: registrazione → ricerca bando → report
4. Listino (proposta: €29-49/mese B2C) + Stripe Payment Link come MVP pagamenti
5. Primi 10 clienti via: suite AGENTI_FINANZA come servizio (pratica bando completa),
   content marketing scadenze bandi, network HoReCa Sardegna

## Collegamenti ecosistema
- AGENTI_FINANZA/AGENTE_PRATICA_BANDO.md = il servizio premium sopra il SaaS
- BAD360 modulo bandi = futuro white-label di questo motore

## Sicurezza
- .env e .env.render ESCLUSI dal repo (mai committare)
- File "BA.IA - SS KEY.txt" nella cartella padre: DA SPOSTARE in password manager
