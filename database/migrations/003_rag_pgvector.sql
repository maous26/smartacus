-- =============================================================================
-- Smartacus RAG Schema with pgvector
-- Migration 003: RAG Knowledge Base
-- =============================================================================

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- =============================================================================
-- RAG DOCUMENTS TABLE
-- =============================================================================
-- Stores document metadata (not the content itself)
-- Documents are logical containers for chunks

CREATE TABLE IF NOT EXISTS rag_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Classification (4 corpus)
    doc_type VARCHAR(20) NOT NULL CHECK (doc_type IN ('rules', 'ops', 'templates', 'memory')),
    domain VARCHAR(50) NOT NULL,  -- e.g., 'sourcing', 'negotiation', 'compliance', 'analysis'

    -- Metadata
    title VARCHAR(500) NOT NULL,
    description TEXT,
    source VARCHAR(500),  -- URL, file path, or reference
    source_type VARCHAR(50) DEFAULT 'manual',  -- manual, auto, import, run

    -- Filtering attributes
    marketplace VARCHAR(10) DEFAULT 'US',  -- US, UK, DE, FR, etc.
    category VARCHAR(100),  -- Product category if applicable
    language VARCHAR(5) DEFAULT 'en',

    -- Lifecycle
    effective_date DATE DEFAULT CURRENT_DATE,
    expiry_date DATE,  -- TTL: NULL = no expiry
    confidence DECIMAL(3,2) DEFAULT 1.0 CHECK (confidence >= 0 AND confidence <= 1),

    -- Linking
    run_id VARCHAR(50),  -- If from a pipeline run
    asin VARCHAR(20),  -- If product-specific

    -- Metadata JSON for flexibility
    metadata JSONB DEFAULT '{}',

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Soft delete
    is_active BOOLEAN DEFAULT TRUE
);

-- =============================================================================
-- RAG CHUNKS TABLE
-- =============================================================================
-- Stores chunked content with embeddings
-- OpenAI text-embedding-3-small produces 1536-dim vectors

CREATE TABLE IF NOT EXISTS rag_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES rag_documents(id) ON DELETE CASCADE,

    -- Chunk positioning
    chunk_index INTEGER NOT NULL,

    -- Content
    content TEXT NOT NULL,
    content_hash VARCHAR(64) NOT NULL,  -- SHA256 for deduplication

    -- Context preservation (anti-orphan)
    context_header TEXT,  -- Title + parent headers

    -- Embedding (1536 dimensions for text-embedding-3-small)
    embedding vector(1536),

    -- Token info
    token_count INTEGER,

    -- Inherited filters (denormalized for fast filtering)
    doc_type VARCHAR(20) NOT NULL,
    domain VARCHAR(50) NOT NULL,
    marketplace VARCHAR(10) DEFAULT 'US',
    category VARCHAR(100),
    language VARCHAR(5) DEFAULT 'en',

    -- Metadata
    metadata JSONB DEFAULT '{}',

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- Constraints
    UNIQUE (document_id, chunk_index),
    UNIQUE (content_hash)  -- Prevent duplicate chunks
);

-- =============================================================================
-- INDEXES FOR RAG PERFORMANCE
-- =============================================================================

-- Vector similarity search index (HNSW for better performance)
-- HNSW: better query performance, slightly slower inserts
CREATE INDEX IF NOT EXISTS idx_rag_chunks_embedding_hnsw
ON rag_chunks
USING hnsw (embedding vector_cosine_ops)
WITH (m = 16, ef_construction = 64);

-- Alternative: IVFFlat (faster inserts, good for larger datasets)
-- CREATE INDEX IF NOT EXISTS idx_rag_chunks_embedding_ivfflat
-- ON rag_chunks
-- USING ivfflat (embedding vector_cosine_ops)
-- WITH (lists = 100);

-- Filtering indexes (for 2-stage retrieval)
CREATE INDEX IF NOT EXISTS idx_rag_chunks_doc_type ON rag_chunks(doc_type);
CREATE INDEX IF NOT EXISTS idx_rag_chunks_domain ON rag_chunks(domain);
CREATE INDEX IF NOT EXISTS idx_rag_chunks_marketplace ON rag_chunks(marketplace);
CREATE INDEX IF NOT EXISTS idx_rag_chunks_category ON rag_chunks(category);
CREATE INDEX IF NOT EXISTS idx_rag_chunks_language ON rag_chunks(language);

-- Composite index for common filter patterns
CREATE INDEX IF NOT EXISTS idx_rag_chunks_filters
ON rag_chunks(doc_type, domain, marketplace, language);

-- Document indexes
CREATE INDEX IF NOT EXISTS idx_rag_documents_doc_type ON rag_documents(doc_type);
CREATE INDEX IF NOT EXISTS idx_rag_documents_domain ON rag_documents(domain);
CREATE INDEX IF NOT EXISTS idx_rag_documents_active ON rag_documents(is_active) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_rag_documents_asin ON rag_documents(asin) WHERE asin IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_rag_documents_run_id ON rag_documents(run_id) WHERE run_id IS NOT NULL;

-- =============================================================================
-- RAG CITATIONS TABLE
-- =============================================================================
-- Tracks which chunks were used in agent responses (traceability)

CREATE TABLE IF NOT EXISTS rag_citations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Context
    session_id VARCHAR(50) NOT NULL,
    agent_type VARCHAR(20) NOT NULL,
    query_text TEXT NOT NULL,

    -- Citations
    chunk_ids UUID[] NOT NULL,
    similarity_scores DECIMAL(4,3)[],

    -- Extracted info
    extracted_rules TEXT[],
    recommended_template_id UUID,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rag_citations_session ON rag_citations(session_id);
CREATE INDEX IF NOT EXISTS idx_rag_citations_agent ON rag_citations(agent_type);

-- =============================================================================
-- HELPER FUNCTIONS
-- =============================================================================

-- Function to search chunks with metadata filtering + vector similarity
CREATE OR REPLACE FUNCTION rag_search(
    query_embedding vector(1536),
    p_doc_types TEXT[] DEFAULT NULL,
    p_domains TEXT[] DEFAULT NULL,
    p_marketplace TEXT DEFAULT NULL,
    p_category TEXT DEFAULT NULL,
    p_language TEXT DEFAULT 'en',
    p_limit INTEGER DEFAULT 5
)
RETURNS TABLE (
    chunk_id UUID,
    document_id UUID,
    content TEXT,
    context_header TEXT,
    doc_type VARCHAR(20),
    domain VARCHAR(50),
    similarity DECIMAL(4,3),
    metadata JSONB
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        c.id AS chunk_id,
        c.document_id,
        c.content,
        c.context_header,
        c.doc_type,
        c.domain,
        (1 - (c.embedding <=> query_embedding))::DECIMAL(4,3) AS similarity,
        c.metadata
    FROM rag_chunks c
    JOIN rag_documents d ON c.document_id = d.id
    WHERE
        d.is_active = TRUE
        AND (d.expiry_date IS NULL OR d.expiry_date > CURRENT_DATE)
        AND (p_doc_types IS NULL OR c.doc_type = ANY(p_doc_types))
        AND (p_domains IS NULL OR c.domain = ANY(p_domains))
        AND (p_marketplace IS NULL OR c.marketplace = p_marketplace)
        AND (p_category IS NULL OR c.category = p_category)
        AND c.language = p_language
    ORDER BY c.embedding <=> query_embedding
    LIMIT p_limit;
END;
$$ LANGUAGE plpgsql;

-- Function to get document with all its chunks
CREATE OR REPLACE FUNCTION get_document_with_chunks(p_document_id UUID)
RETURNS TABLE (
    document_id UUID,
    title VARCHAR(500),
    doc_type VARCHAR(20),
    domain VARCHAR(50),
    chunk_index INTEGER,
    content TEXT,
    context_header TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        d.id AS document_id,
        d.title,
        d.doc_type,
        d.domain,
        c.chunk_index,
        c.content,
        c.context_header
    FROM rag_documents d
    JOIN rag_chunks c ON c.document_id = d.id
    WHERE d.id = p_document_id
    ORDER BY c.chunk_index;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- TRIGGERS
-- =============================================================================

-- Auto-update updated_at on documents
CREATE OR REPLACE FUNCTION update_rag_document_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_rag_documents_updated
    BEFORE UPDATE ON rag_documents
    FOR EACH ROW
    EXECUTE FUNCTION update_rag_document_timestamp();

-- =============================================================================
-- COMMENTS
-- =============================================================================

COMMENT ON TABLE rag_documents IS 'RAG knowledge base documents - logical containers for chunks';
COMMENT ON TABLE rag_chunks IS 'RAG chunks with embeddings for semantic search';
COMMENT ON TABLE rag_citations IS 'Tracks chunk usage in agent responses for traceability';
COMMENT ON COLUMN rag_chunks.embedding IS 'OpenAI text-embedding-3-small (1536 dimensions)';
COMMENT ON COLUMN rag_chunks.content_hash IS 'SHA256 hash for deduplication';
COMMENT ON COLUMN rag_chunks.context_header IS 'Preserved headers to prevent orphan chunks';
COMMENT ON FUNCTION rag_search IS '2-stage retrieval: metadata filter + vector similarity';
