-- Migration 006: Review Intelligence — Enum + Indexes
-- ==================================================
-- 1. Create defect_type Postgres enum to prevent string drift
-- 2. Migrate existing text column to use enum
-- 3. Ensure proper indexes for review intelligence queries

-- ============================================================================
-- 1. DEFECT TYPE ENUM
-- ============================================================================

-- Create enum matching Python DefectType
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'defect_type_enum') THEN
        CREATE TYPE defect_type_enum AS ENUM (
            'mechanical_failure',
            'poor_grip',
            'installation_issue',
            'compatibility_issue',
            'material_quality',
            'vibration_noise',
            'heat_issue',
            'size_fit',
            'durability'
        );
    END IF;
END$$;

-- Migrate review_defects.defect_type from TEXT to enum
-- (safe: only runs if column is still TEXT)
DO $$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'review_defects'
          AND column_name = 'defect_type'
          AND data_type = 'text'
    ) THEN
        ALTER TABLE review_defects
            ALTER COLUMN defect_type TYPE defect_type_enum
            USING defect_type::defect_type_enum;
    END IF;
END$$;

-- ============================================================================
-- 2. INDEXES FOR REVIEW QUERIES
-- ============================================================================

-- reviews: already has idx_reviews_asin (asin, review_date DESC) from migration 001
-- reviews: already has idx_reviews_rating (asin, rating) from migration 001
-- reviews: already has idx_reviews_content_trgm from migration 001

-- review_defects: fast lookup by ASIN + type
CREATE INDEX IF NOT EXISTS idx_review_defects_asin
    ON review_defects(asin, defect_type);

CREATE INDEX IF NOT EXISTS idx_review_defects_severity
    ON review_defects(severity_score DESC);

-- review_feature_requests: fast lookup by ASIN
CREATE INDEX IF NOT EXISTS idx_review_features_asin
    ON review_feature_requests(asin);

CREATE INDEX IF NOT EXISTS idx_review_features_mentions
    ON review_feature_requests(mentions DESC);

-- review_improvement_profiles: fast lookup by ASIN + score
CREATE INDEX IF NOT EXISTS idx_review_profiles_asin
    ON review_improvement_profiles(asin);

CREATE INDEX IF NOT EXISTS idx_review_profiles_score
    ON review_improvement_profiles(improvement_score DESC);

-- ============================================================================
-- 3. VERIFY
-- ============================================================================

-- Quick verification
DO $$
DECLARE
    enum_count INTEGER;
    idx_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO enum_count
    FROM pg_enum WHERE enumtypid = 'defect_type_enum'::regtype;

    SELECT COUNT(*) INTO idx_count
    FROM pg_indexes
    WHERE indexname LIKE 'idx_review_%';

    RAISE NOTICE 'Migration 006: defect_type_enum has % values, % review indexes exist',
        enum_count, idx_count;
END$$;
