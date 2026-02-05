-- Migration 008: Spec Versioning
-- ================================
-- Adds mapping_version and inputs_hash columns to product_spec_bundles
-- for reproducibility and drift detection.
-- Additive — does not modify existing data.

ALTER TABLE product_spec_bundles
    ADD COLUMN IF NOT EXISTS mapping_version TEXT NOT NULL DEFAULT '1.8.0',
    ADD COLUMN IF NOT EXISTS inputs_hash TEXT NOT NULL DEFAULT '';

-- Verify
DO $$
DECLARE
    col_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO col_count
    FROM information_schema.columns
    WHERE table_name = 'product_spec_bundles'
      AND column_name IN ('mapping_version', 'inputs_hash');

    RAISE NOTICE 'Migration 008: % versioning columns added', col_count;
END$$;
