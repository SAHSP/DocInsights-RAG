-- ─────────────────────────────────────────────────────────────────────────────
-- RAG Pipeline — PostgreSQL Schema
-- Database: rag_db  |  PostgreSQL 16+
-- Run once to create all tables.
-- ─────────────────────────────────────────────────────────────────────────────

-- Enable UUID generation (built-in from PostgreSQL 13+)
-- gen_random_uuid() is available natively — no extension needed.

-- ─────────────────────────────────────────────────────────────────────────────
-- 1. documents
-- Created when a file is uploaded. Tracks the file through the entire pipeline.
-- Status lifecycle: pending → extracting → chunking → embedding → indexed | failed
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS documents (
    file_id         UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    filename        VARCHAR(512)    NOT NULL,
    file_type       VARCHAR(10)     NOT NULL CHECK (file_type IN ('pdf', 'docx')),
    minio_path      VARCHAR(1024)   NOT NULL,
    status          VARCHAR(20)     NOT NULL DEFAULT 'pending'
                                    CHECK (status IN ('pending', 'extracting', 'chunking', 'embedding', 'indexed', 'failed')),
    error_message   TEXT,
    size_bytes      BIGINT,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- Auto-update updated_at on row change
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_documents_updated_at
    BEFORE UPDATE ON documents
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();

-- ─────────────────────────────────────────────────────────────────────────────
-- 2. parent_chunks
-- Full-context text units. Sent to the LLM during generation.
-- Never indexed in Elasticsearch. Never stores embeddings.
-- chunk_number = sequential position within the document (1, 2, 3...)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS parent_chunks (
    parent_chunk_id UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    file_id         UUID            NOT NULL REFERENCES documents(file_id) ON DELETE CASCADE,
    page_number     INTEGER         NOT NULL,
    chunk_number    INTEGER         NOT NULL,   -- position within document (1-based)
    chunk_text      TEXT            NOT NULL,
    chunk_type      VARCHAR(20)     NOT NULL DEFAULT 'text'
                                    CHECK (chunk_type IN ('text', 'table', 'mixed')),
    metadata        JSONB           NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_parent_chunks_file_id
    ON parent_chunks(file_id);

CREATE INDEX IF NOT EXISTS idx_parent_chunks_file_chunk
    ON parent_chunks(file_id, chunk_number);

-- ─────────────────────────────────────────────────────────────────────────────
-- 3. child_chunks
-- Small, precise text units derived from parent chunks.
-- These are embedded and indexed in Elasticsearch.
-- ANN / BM25 search runs against these.
-- child_number = sequential position within its parent (1, 2 — resets per parent)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS child_chunks (
    child_chunk_id  UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    parent_chunk_id UUID            NOT NULL REFERENCES parent_chunks(parent_chunk_id) ON DELETE CASCADE,
    file_id         UUID            NOT NULL REFERENCES documents(file_id) ON DELETE CASCADE,
    page_number     INTEGER         NOT NULL,
    child_number    INTEGER         NOT NULL,   -- position within parent (1-based, resets per parent)
    chunk_text      TEXT            NOT NULL,
    token_count     INTEGER         NOT NULL,   -- exact token count at creation time
    metadata        JSONB           NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_child_chunks_parent_id
    ON child_chunks(parent_chunk_id);

CREATE INDEX IF NOT EXISTS idx_child_chunks_file_id
    ON child_chunks(file_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- 4. query_history
-- Every user query and its answer is logged here.
-- sources: JSON array of { parent_chunk_id, file_id, page_number, filename }
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS query_history (
    query_id        UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    query_text      TEXT            NOT NULL,
    answer_text     TEXT,
    search_mode     VARCHAR(10)     NOT NULL CHECK (search_mode IN ('keyword', 'semantic')),
    file_id         UUID            REFERENCES documents(file_id) ON DELETE SET NULL,
    sources         JSONB           NOT NULL DEFAULT '[]',
    cached          BOOLEAN         NOT NULL DEFAULT FALSE,
    status          VARCHAR(10)     NOT NULL DEFAULT 'answered'
                                    CHECK (status IN ('answered', 'failed')),
    error_message   TEXT,
    created_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_query_history_created_at
    ON query_history(created_at DESC);

CREATE INDEX IF NOT EXISTS idx_query_history_file_id
    ON query_history(file_id);

-- ─────────────────────────────────────────────────────────────────────────────
-- 5. app_settings (persists LLM and search configuration)
-- Single row, key-value store for runtime settings.
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS app_settings (
    id              INTEGER         PRIMARY KEY DEFAULT 1,
    llm_provider    VARCHAR(50)     NOT NULL DEFAULT 'openrouter',
    llm_model       VARCHAR(100)    NOT NULL DEFAULT 'google/gemini-2.0-flash-exp:free',
    llm_api_key     TEXT,
    llm_base_url    TEXT,
    embedding_model VARCHAR(200)    NOT NULL DEFAULT 'BAAI/bge-large-en-v1.5',
    default_search_mode VARCHAR(10) NOT NULL DEFAULT 'semantic',
    top_k           INTEGER         NOT NULL DEFAULT 20,
    reranker_top_n  INTEGER         NOT NULL DEFAULT 5,
    cache_enabled   BOOLEAN         NOT NULL DEFAULT TRUE,
    cache_ttl       INTEGER         NOT NULL DEFAULT 3600,
    updated_at      TIMESTAMPTZ     NOT NULL DEFAULT NOW(),
    CONSTRAINT single_row CHECK (id = 1)
);

-- Insert default settings row
INSERT INTO app_settings (id) VALUES (1)
ON CONFLICT (id) DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────────────
-- Done.
-- ─────────────────────────────────────────────────────────────────────────────
