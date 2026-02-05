-- Migration 007: Product Spec Generator (V1.8)
-- ==============================================
-- Cache for generated OEM specs, QC checklists, and RFQ messages.
-- Additive — does not modify existing tables.

-- ============================================================================
-- TABLE: product_spec_bundles
-- ============================================================================

CREATE TABLE IF NOT EXISTS product_spec_bundles (
    bundle_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asin VARCHAR(10) NOT NULL REFERENCES asins(asin),
    run_id UUID REFERENCES pipeline_runs(run_id),
    version TEXT NOT NULL DEFAULT '1.8',
    oem_spec_text TEXT NOT NULL DEFAULT '',
    qc_checklist_text TEXT NOT NULL DEFAULT '',
    rfq_message_text TEXT NOT NULL DEFAULT '',
    bundle_json JSONB NOT NULL DEFAULT '{}',
    improvement_score DECIMAL(4,3) NOT NULL DEFAULT 0.000,
    reviews_analyzed INTEGER NOT NULL DEFAULT 0,
    total_requirements INTEGER NOT NULL DEFAULT 0,
    total_qc_tests INTEGER NOT NULL DEFAULT 0,
    generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (asin, run_id)
);

-- ============================================================================
-- INDEXES
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_spec_bundles_asin
    ON product_spec_bundles(asin);

CREATE INDEX IF NOT EXISTS idx_spec_bundles_generated
    ON product_spec_bundles(generated_at DESC);

CREATE INDEX IF NOT EXISTS idx_spec_bundles_score
    ON product_spec_bundles(improvement_score DESC);

-- ============================================================================
-- VERIFY
-- ============================================================================

DO $$
DECLARE
    tbl_exists BOOLEAN;
    idx_count INTEGER;
BEGIN
    SELECT EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_name = 'product_spec_bundles'
    ) INTO tbl_exists;

    SELECT COUNT(*) INTO idx_count
    FROM pg_indexes
    WHERE indexname LIKE 'idx_spec_bundles_%';

    RAISE NOTICE 'Migration 007: product_spec_bundles exists = %, % indexes',
        tbl_exists, idx_count;
END$$;
