-- ════════════════════════════════════════════════════════════════════
-- MIGRAZIONE: Paywall / Trial 14 giorni
-- Aggiunge a users il piano e la scadenza del trial.
-- plan: 'trial' (default) | 'active' (pagante) | 'expired'
-- trial_ends_at: data ISO di fine trial (14 giorni dalla registrazione)
-- Esegui una volta nel SQL Editor di Supabase.
-- ════════════════════════════════════════════════════════════════════

ALTER TABLE users ADD COLUMN IF NOT EXISTS plan TEXT DEFAULT 'trial';
ALTER TABLE users ADD COLUMN IF NOT EXISTS trial_ends_at TEXT;

-- Backfill: agli utenti esistenti senza scadenza diamo 14 giorni da ora
UPDATE users
SET trial_ends_at = (CURRENT_TIMESTAMP + INTERVAL '14 days')::text
WHERE trial_ends_at IS NULL OR trial_ends_at = '';

-- ── LICENZA GRATUITA (admin) ────────────────────────────────────────
-- Il TUO account ha accesso illimitato. Sostituisci con la tua email reale
-- (quella con cui ti sei registrato) e togli i due trattini iniziali:
-- UPDATE users SET plan='free', role='admin' WHERE email='simoneserra230@gmail.com';
--
-- Per concedere licenza gratuita ad ALTRI account (uno alla volta):
-- UPDATE users SET plan='free' WHERE email='cliente@esempio.it';
--
-- Nota: puoi anche gestirlo dall'app (pannello admin) o impostando su Render
-- la variabile ADMIN_EMAILS = la tua email (ti rende admin automaticamente).

-- Verifica
SELECT email, plan, role, trial_ends_at FROM users;
