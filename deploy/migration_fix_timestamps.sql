-- ════════════════════════════════════════════════════════════════════
-- MIGRAZIONE: colonne TIMESTAMP → TEXT
-- Il backend BA.IA scrive stringhe ISO nei timestamp (es. _expires()).
-- SQLite le accetta; PostgreSQL (asyncpg) no → errore 500 in registrazione.
-- Questa migrazione converte TUTTE le colonne timestamp dello schema public
-- in TEXT, coerente con il resto del codice (che usa già TEXT per i timestamp).
-- Sicura: converte i valori esistenti con ::text, non perde dati.
-- Esegui una volta nel SQL Editor di Supabase.
-- ════════════════════════════════════════════════════════════════════

DO $$
DECLARE r RECORD;
BEGIN
  FOR r IN
    SELECT table_name, column_name
    FROM information_schema.columns
    WHERE table_schema = 'public'
      AND data_type IN ('timestamp without time zone', 'timestamp with time zone')
  LOOP
    -- 1. rimuovi eventuale DEFAULT (CURRENT_TIMESTAMP non è valido per TEXT)
    EXECUTE format('ALTER TABLE public.%I ALTER COLUMN %I DROP DEFAULT',
                   r.table_name, r.column_name);
    -- 2. cambia il tipo a TEXT convertendo i valori esistenti
    EXECUTE format('ALTER TABLE public.%I ALTER COLUMN %I TYPE TEXT USING %I::text',
                   r.table_name, r.column_name, r.column_name);
    -- 3. rimetti un default testuale (per created_at/updated_at che lo usavano)
    EXECUTE format('ALTER TABLE public.%I ALTER COLUMN %I SET DEFAULT (CURRENT_TIMESTAMP::text)',
                   r.table_name, r.column_name);
    RAISE NOTICE 'Convertita: %.% → TEXT', r.table_name, r.column_name;
  END LOOP;
END $$;

-- Verifica: nessuna colonna timestamp dovrebbe rimanere
SELECT table_name, column_name, data_type
FROM information_schema.columns
WHERE table_schema='public' AND data_type LIKE 'timestamp%';
