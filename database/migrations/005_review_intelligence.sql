-- Migration 005: Review Intelligence Engine tables
-- Purpose: Store deterministic defect extraction and LLM feature requests
-- These tables are additive — they don't modify existing pipeline tables.

-- ============================================================================
-- TABLE: review_defects (deterministic extraction, no LLM)
-- ============================================================================

CREATE TABLE IF NOT EXISTS review_defects (
    defect_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asin VARCHAR(10) NOT NULL REFERENCES asins(asin),
    run_id UUID REFERENCES pipeline_runs(run_id),
    defect_type TEXT NOT NULL,           -- e.g. 'mechanical_failure', 'poor_grip'
    frequency INTEGER NOT NULL DEFAULT 0,
    severity_score DECIMAL(3,2) NOT NULL DEFAULT 0.00, -- 0.00 to 1.00
    example_quotes TEXT[],               -- max 3 verbatim quotes
    total_reviews_scanned INTEGER NOT NULL DEFAULT 0,
    negative_reviews_scanned INTEGER NOT NULL DEFAULT 0,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_review_defects_asin ON review_defects(asin);
CREATE INDEX idx_review_defects_type ON review_defects(defect_type);
CREATE INDEX idx_review_defects_severity ON review_defects(severity_score DESC);

-- ============================================================================
-- TABLE: review_feature_requests (LLM batch extraction, phase 2)
-- ============================================================================

CREATE TABLE IF NOT EXISTS review_feature_requests (
    request_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asin VARCHAR(10) NOT NULL REFERENCES asins(asin),
    run_id UUID REFERENCES pipeline_runs(run_id),
    feature TEXT NOT NULL,               -- e.g. 'stronger suction cup'
    mentions INTEGER NOT NULL DEFAULT 0,
    confidence DECIMAL(3,2) NOT NULL DEFAULT 0.00, -- 0.00 to 1.00
    source_quotes TEXT[],                -- evidence
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_review_feature_requests_asin ON review_feature_requests(asin);
CREATE INDEX idx_review_feature_requests_mentions ON review_feature_requests(mentions DESC);

-- ============================================================================
-- TABLE: review_improvement_profiles (aggregated per ASIN)
-- ============================================================================

CREATE TABLE IF NOT EXISTS review_improvement_profiles (
    profile_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asin VARCHAR(10) NOT NULL REFERENCES asins(asin),
    run_id UUID REFERENCES pipeline_runs(run_id),
    top_defects JSONB NOT NULL DEFAULT '[]',       -- [{type, freq, severity}]
    missing_features JSONB NOT NULL DEFAULT '[]',  -- [{feature, mentions, confidence}]
    dominant_pain TEXT,                             -- single most impactful defect
    improvement_score DECIMAL(4,3) NOT NULL DEFAULT 0.000, -- 0.000 to 1.000
    reviews_analyzed INTEGER NOT NULL DEFAULT 0,
    negative_reviews_analyzed INTEGER NOT NULL DEFAULT 0,
    reviews_ready BOOLEAN NOT NULL DEFAULT FALSE,
    computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (asin, run_id)
);

CREATE INDEX idx_review_profiles_asin ON review_improvement_profiles(asin);
CREATE INDEX idx_review_profiles_score ON review_improvement_profiles(improvement_score DESC);
