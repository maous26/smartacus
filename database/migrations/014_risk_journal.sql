-- Migration 014: Risk Journal (User Override Tracking)
-- V3.1 - UX/UI Honest Framing
--
-- Philosophy: "Les gens prendront des risques. Le rôle du système n'est pas
-- de les infantiliser, mais de rendre le risque conscient et traçable."

-- =============================================================================
-- RISK OVERRIDES: Track when users proceed despite incomplete analysis
-- =============================================================================
CREATE TABLE IF NOT EXISTS risk_overrides (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asin VARCHAR(20) NOT NULL,  -- No FK to asins since we may override for ASINs not yet tracked
    run_id UUID,                 -- No FK to pipeline_runs for flexibility

    -- User identification (for multi-user future)
    user_id VARCHAR(100) DEFAULT 'default',

    -- Confidence state at override time
    confidence_level VARCHAR(20) NOT NULL,  -- eclaire, incomplet, fragile
    confidence_score REAL,                   -- 0-1 if computed

    -- User's explicit hypothesis
    hypothesis TEXT NOT NULL,
    hypothesis_reason VARCHAR(50) NOT NULL,  -- product_improvement, marketing_advantage, etc.

    -- What was missing at the time
    missing_info JSONB DEFAULT '[]',        -- Array of strings

    -- Outcome tracking (filled later)
    outcome VARCHAR(20),                     -- success, partial, failure, abandoned
    outcome_notes TEXT,
    outcome_recorded_at TIMESTAMPTZ,

    -- Audit
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_risk_overrides_asin ON risk_overrides(asin);
CREATE INDEX idx_risk_overrides_user ON risk_overrides(user_id);
CREATE INDEX idx_risk_overrides_created ON risk_overrides(created_at DESC);
CREATE INDEX idx_risk_overrides_confidence ON risk_overrides(confidence_level);

-- =============================================================================
-- COMMENTS
-- =============================================================================
COMMENT ON TABLE risk_overrides IS 'Audit trail for user decisions to proceed despite incomplete analysis';
COMMENT ON COLUMN risk_overrides.hypothesis IS 'User-stated reason for proceeding (logged, not judged)';
COMMENT ON COLUMN risk_overrides.hypothesis_reason IS 'Categorized reason: product_improvement, marketing_advantage, low_volume_test, market_knowledge, other';
COMMENT ON COLUMN risk_overrides.missing_info IS 'JSON array of what was missing at decision time';
COMMENT ON COLUMN risk_overrides.outcome IS 'Post-mortem: success, partial, failure, abandoned (filled by user later)';
