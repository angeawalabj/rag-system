-- ─────────────────────────────────────────────────────────────────────────────
-- RAG System — Schéma PostgreSQL initial
-- Exécuté automatiquement par docker-entrypoint-initdb.d au premier démarrage
-- ─────────────────────────────────────────────────────────────────────────────

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";   -- recherche full-text sur filename

-- ─── Enum statuts ─────────────────────────────────────────────────────────────
CREATE TYPE ingestion_status AS ENUM (
    'pending',
    'processing',
    'completed',
    'failed'
);

-- ─── Table documents ──────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS documents (
    id               UUID            PRIMARY KEY DEFAULT uuid_generate_v4(),
    filename         VARCHAR(512)    NOT NULL,
    source_type      VARCHAR(32)     NOT NULL,           -- pdf | md | txt | url
    source_url       TEXT,
    collection       VARCHAR(128)    NOT NULL DEFAULT 'documents',
    status           ingestion_status NOT NULL DEFAULT 'pending',
    chunk_count      INTEGER,
    error_message    TEXT,
    file_size_bytes  BIGINT,
    ingested_at      TIMESTAMPTZ,
    created_at       TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- ─── Index ────────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_documents_status
    ON documents (status);

CREATE INDEX IF NOT EXISTS idx_documents_collection
    ON documents (collection);

CREATE INDEX IF NOT EXISTS idx_documents_created_at
    ON documents (created_at DESC);

-- Recherche full-text sur le nom de fichier
CREATE INDEX IF NOT EXISTS idx_documents_filename_trgm
    ON documents USING GIN (filename gin_trgm_ops);

-- ─── Trigger updated_at ───────────────────────────────────────────────────────
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_documents_updated_at
    BEFORE UPDATE ON documents
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ─── Vue stats rapides ────────────────────────────────────────────────────────
CREATE VIEW v_ingestion_stats AS
SELECT
    collection,
    status,
    COUNT(*)                        AS doc_count,
    SUM(chunk_count)                AS total_chunks,
    SUM(file_size_bytes)            AS total_bytes,
    MAX(ingested_at)                AS last_ingested_at
FROM documents
GROUP BY collection, status;

-- ─── Données de seed (dev uniquement) ────────────────────────────────────────
-- Commenté en prod, décommenté dans docker-compose.override.yml
-- INSERT INTO documents (filename, source_type, collection, status)
-- VALUES ('example.pdf', 'pdf', 'documents', 'pending');
