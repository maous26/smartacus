-- Migration 011: Opportunity Theses table for auto-generated investment theses
-- V2.0 Remediation - Priority 4: Automatic Thesis Generation

-- Create opportunity_theses table
CREATE TABLE IF NOT EXISTS opportunity_theses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asin VARCHAR(20) NOT NULL REFERENCES asins(asin) ON DELETE CASCADE,
    run_id UUID REFERENCES pipeline_runs(run_id) ON DELETE SET NULL,

    -- Thesis content
    headline VARCHAR(255),                      -- Short headline: "Supply shock + quality decay = 90j window"
    thesis TEXT NOT NULL,                       -- Full investment thesis
    confidence REAL CHECK (confidence >= 0 AND confidence <= 1),  -- Confidence score [0-1]

    -- Recommendation
    action_recommendation TEXT,                 -- Specific action: "Contact supplier X, MOQ 500"
    urgency VARCHAR(20),                        -- CRITICAL, HIGH, MEDIUM, LOW

    -- Economic estimates (snapshot at generation time)
    economic_estimates JSONB DEFAULT '{}',      -- {monthly_profit, annual_value, risk_adjusted, cogs, etc.}

    -- Source data (what was used to generate thesis)
    source_events JSONB DEFAULT '[]',           -- Economic events that triggered thesis
    source_profile JSONB DEFAULT '{}',          -- Review intelligence profile snapshot

    -- Metadata
    generated_at TIMESTAMPTZ DEFAULT NOW(),
    generator_version VARCHAR(20) DEFAULT '2.0', -- Track thesis generator version

    -- Unique: one thesis per ASIN per run (can have multiple across runs)
    UNIQUE(asin, run_id)
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_opportunity_theses_asin ON opportunity_theses(asin);
CREATE INDEX IF NOT EXISTS idx_opportunity_theses_generated ON opportunity_theses(generated_at DESC);
CREATE INDEX IF NOT EXISTS idx_opportunity_theses_run ON opportunity_theses(run_id);
CREATE INDEX IF NOT EXISTS idx_opportunity_theses_confidence ON opportunity_theses(confidence DESC);

-- Index for cache lookup (recent theses for an ASIN)
CREATE INDEX IF NOT EXISTS idx_opportunity_theses_asin_recent
ON opportunity_theses(asin, generated_at DESC);

-- Add comments
COMMENT ON TABLE opportunity_theses IS 'Auto-generated investment theses for scored opportunities';
COMMENT ON COLUMN opportunity_theses.headline IS 'Short summary for display in lists';
COMMENT ON COLUMN opportunity_theses.thesis IS 'Full investment thesis with reasoning';
COMMENT ON COLUMN opportunity_theses.economic_estimates IS 'Snapshot of economic calculations at thesis generation time';
COMMENT ON COLUMN opportunity_theses.source_events IS 'Economic events that contributed to this thesis';
