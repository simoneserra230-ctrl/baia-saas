-- ══════════════════════════════════════════════════════════
-- BA.IA — Schema Supabase PostgreSQL
-- Eseguire una sola volta nel SQL Editor di Supabase
-- ══════════════════════════════════════════════════════════
-- 1. Vai su Supabase → tuo progetto → SQL Editor
-- 2. New query → incolla tutto questo file → Run
-- 3. Verifica creazione tabelle in Table Editor
-- ══════════════════════════════════════════════════════════

-- ── CORE TABLES ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS bandi (
    id TEXT PRIMARY KEY,
    data JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_bandi_updated ON bandi(updated_at DESC);
CREATE INDEX IF NOT EXISTS idx_bandi_data_gin ON bandi USING GIN(data);

CREATE TABLE IF NOT EXISTS aziende (
    id TEXT PRIMARY KEY,
    data JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS sal (
    id TEXT PRIMARY KEY,
    bando_id TEXT,
    data JSONB NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS history (
    id TEXT PRIMARY KEY,
    data JSONB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ── AUTH TABLES ──────────────────────────────────────────
CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT DEFAULT 'consulente',
    invited_by TEXT,
    invite_token TEXT,
    invite_used INTEGER DEFAULT 0,
    company TEXT,
    phone TEXT,
    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);
CREATE INDEX IF NOT EXISTS idx_users_invited ON users(invited_by);

CREATE TABLE IF NOT EXISTS sessions (
    token TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sessions_user ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_expires ON sessions(expires_at);

-- ── PORTAL TABLES ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS portal_shares (
    id TEXT PRIMARY KEY,
    consulente_id TEXT NOT NULL,
    cliente_id TEXT NOT NULL,
    resource_type TEXT NOT NULL,
    resource_id TEXT NOT NULL,
    permissions TEXT DEFAULT 'view',
    label TEXT,
    note TEXT,
    visible INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_shares_consulente ON portal_shares(consulente_id);
CREATE INDEX IF NOT EXISTS idx_shares_cliente ON portal_shares(cliente_id);

CREATE TABLE IF NOT EXISTS portal_messages (
    id TEXT PRIMARY KEY,
    share_id TEXT NOT NULL,
    author_id TEXT NOT NULL,
    author_role TEXT NOT NULL,
    author_name TEXT NOT NULL,
    text TEXT NOT NULL,
    read_by_cliente INTEGER DEFAULT 0,
    read_by_consulente INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_messages_share ON portal_messages(share_id);

CREATE TABLE IF NOT EXISTS portal_docs (
    id TEXT PRIMARY KEY,
    share_id TEXT NOT NULL,
    uploaded_by TEXT NOT NULL,
    filename TEXT NOT NULL,
    size_bytes INTEGER DEFAULT 0,
    description TEXT,
    storage_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ── RENDICONTAZIONE TABLES ───────────────────────────────
CREATE TABLE IF NOT EXISTS rendicontazioni (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    sal_id TEXT,
    bando_id TEXT,
    azienda_id TEXT,
    titolo TEXT NOT NULL,
    importo_approvato REAL DEFAULT 0,
    importo_rendicontato REAL DEFAULT 0,
    data_approvazione TEXT,
    data_scadenza_sal TEXT,
    tipo_sal TEXT DEFAULT 'unico',
    stato TEXT DEFAULT 'aperta',
    ente_erogatore TEXT,
    portale_ente TEXT,
    note TEXT,
    config TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_rendicont_user ON rendicontazioni(user_id);

CREATE TABLE IF NOT EXISTS rendicontazione_milestones (
    id TEXT PRIMARY KEY,
    rendicontazione_id TEXT NOT NULL,
    titolo TEXT NOT NULL,
    descrizione TEXT,
    scadenza TEXT,
    ordine INTEGER DEFAULT 0,
    stato TEXT DEFAULT 'pending',
    importo_atteso REAL DEFAULT 0,
    importo_rendicontato REAL DEFAULT 0,
    completata_il TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS rendicontazione_documenti (
    id TEXT PRIMARY KEY,
    rendicontazione_id TEXT NOT NULL,
    milestone_id TEXT,
    tipo TEXT NOT NULL,
    titolo TEXT NOT NULL,
    fornitore TEXT,
    numero_documento TEXT,
    data_documento TEXT,
    importo_imponibile REAL DEFAULT 0,
    importo_iva REAL DEFAULT 0,
    importo_totale REAL DEFAULT 0,
    importo_ammissibile REAL DEFAULT 0,
    filename TEXT,
    size_bytes INTEGER DEFAULT 0,
    spesa_categoria TEXT,
    modalita_pagamento TEXT,
    pagato INTEGER DEFAULT 0,
    data_pagamento TEXT,
    note TEXT,
    ai_extracted INTEGER DEFAULT 0,
    ai_confidence TEXT,
    storage_url TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS rendicontazione_checklist (
    id TEXT PRIMARY KEY,
    rendicontazione_id TEXT NOT NULL,
    testo TEXT NOT NULL,
    obbligatorio INTEGER DEFAULT 1,
    completato INTEGER DEFAULT 0,
    ordine INTEGER DEFAULT 0,
    note TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ── SCRAPER TABLE ────────────────────────────────────────
CREATE TABLE IF NOT EXISTS scraper_log (
    source_id TEXT PRIMARY KEY,
    last_hash TEXT,
    last_run TIMESTAMP,
    total_new INTEGER DEFAULT 0
);

-- ── ROW LEVEL SECURITY (RLS) ─────────────────────────────
-- IMPORTANTE: Disabilitiamo RLS perché l'auth è gestita dall'app, non da Supabase Auth.
-- Il backend BA.IA fa già la verifica utente/sessione su ogni endpoint.
ALTER TABLE bandi DISABLE ROW LEVEL SECURITY;
ALTER TABLE aziende DISABLE ROW LEVEL SECURITY;
ALTER TABLE sal DISABLE ROW LEVEL SECURITY;
ALTER TABLE history DISABLE ROW LEVEL SECURITY;
ALTER TABLE users DISABLE ROW LEVEL SECURITY;
ALTER TABLE sessions DISABLE ROW LEVEL SECURITY;
ALTER TABLE portal_shares DISABLE ROW LEVEL SECURITY;
ALTER TABLE portal_messages DISABLE ROW LEVEL SECURITY;
ALTER TABLE portal_docs DISABLE ROW LEVEL SECURITY;
ALTER TABLE rendicontazioni DISABLE ROW LEVEL SECURITY;
ALTER TABLE rendicontazione_milestones DISABLE ROW LEVEL SECURITY;
ALTER TABLE rendicontazione_documenti DISABLE ROW LEVEL SECURITY;
ALTER TABLE rendicontazione_checklist DISABLE ROW LEVEL SECURITY;
ALTER TABLE scraper_log DISABLE ROW LEVEL SECURITY;

-- ── VERIFICA SETUP ───────────────────────────────────────
SELECT
    table_name,
    (SELECT COUNT(*) FROM information_schema.columns WHERE table_name = t.table_name) AS columns
FROM information_schema.tables t
WHERE table_schema = 'public'
  AND table_name IN (
    'bandi', 'aziende', 'sal', 'history', 'users', 'sessions',
    'portal_shares', 'portal_messages', 'portal_docs',
    'rendicontazioni', 'rendicontazione_milestones',
    'rendicontazione_documenti', 'rendicontazione_checklist',
    'scraper_log'
  )
ORDER BY table_name;
