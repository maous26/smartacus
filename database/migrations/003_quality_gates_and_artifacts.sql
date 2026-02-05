-- ============================================================================
-- SMARTACUS - Migration 003: Quality Gates, Artifacts, Observability
-- Covers checklist items: #2 (error budget), #3 (hystérésis), #7 (data quality),
--                         #8 (artefacts immuables), #10 (freeze mode)
-- ============================================================================

-- ============================================================================
-- A) Add DEGRADED status to pipeline_run_status enum
-- ============================================================================

ALTER TYPE pipeline_run_status ADD VALUE IF NOT EXISTS 'degraded' AFTER 'completed';

-- ============================================================================
-- B) Add quality gate columns to pipeline_runs
-- ============================================================================

ALTER TABLE pipeline_runs
    ADD COLUMN IF NOT EXISTS error_rate DECIMAL(5,4),               -- asins_failed / asins_total
    ADD COLUMN IF NOT EXISTS error_budget_threshold DECIMAL(5,4) DEFAULT 0.10,  -- 10% default
    ADD COLUMN IF NOT EXISTS error_budget_breached BOOLEAN DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS shortlist_frozen BOOLEAN DEFAULT FALSE, -- freeze mode: don't overwrite
    ADD COLUMN IF NOT EXISTS dq_price_missing_pct DECIMAL(5,2),     -- data quality: % missing prices
    ADD COLUMN IF NOT EXISTS dq_bsr_missing_pct DECIMAL(5,2),       -- data quality: % missing BSR
    ADD COLUMN IF NOT EXISTS dq_review_missing_pct DECIMAL(5,2),    -- data quality: % missing reviews
    ADD COLUMN IF NOT EXISTS dq_passed BOOLEAN DEFAULT TRUE,        -- all DQ gates passed?
    ADD COLUMN IF NOT EXISTS dq_threshold DECIMAL(5,2) DEFAULT 20.0; -- max % missing before DEGRADED

-- ============================================================================
-- C) TABLE: opportunity_artifacts — Immutable scoring snapshots
-- ============================================================================

CREATE TABLE IF NOT EXISTS opportunity_artifacts (
    artifact_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Link to pipeline run
    run_id UUID REFERENCES pipeline_runs(run_id),

    -- Opportunity identity
    asin VARCHAR(10) NOT NULL,
    rank INTEGER NOT NULL,

    -- Complete scoring snapshot (immutable)
    final_score INTEGER NOT NULL,
    base_score DECIMAL(5,4) NOT NULL,
    time_multiplier DECIMAL(4,3) NOT NULL,

    -- Score breakdown (full detail)
    component_scores JSONB NOT NULL,
    /*
    {
        "margin": {"score": 25, "max": 30, "pct": 83.3},
        "velocity": {"score": 18, "max": 25, "pct": 72.0},
        "competition": {"score": 15, "max": 20, "pct": 75.0},
        "gap": {"score": 10, "max": 15, "pct": 66.7}
    }
    */

    -- Time pressure factors
    time_pressure_factors JSONB NOT NULL,
    /*
    {
        "stockout_factor": 1.2,
        "churn_factor": 1.1,
        "volatility_factor": 1.0,
        "bsr_factor": 1.3,
        "geometric_mean": 1.15
    }
    */

    -- Economic thesis
    thesis TEXT NOT NULL,
    action_recommendation TEXT NOT NULL,

    -- Economic values at time of scoring
    estimated_monthly_profit DECIMAL(12,2) NOT NULL,
    estimated_annual_value DECIMAL(12,2) NOT NULL,
    risk_adjusted_value DECIMAL(12,2) NOT NULL,

    -- Window
    window_days INTEGER NOT NULL,
    urgency_level VARCHAR(20) NOT NULL,

    -- Signals pour/contre
    signals_for JSONB DEFAULT '[]',    -- ["3 stockouts in 30d", "BSR improving 15%"]
    signals_against JSONB DEFAULT '[]', -- ["High competition (12 sellers)", "Low margin"]

    -- Economic events active at time of scoring
    economic_events JSONB DEFAULT '[]',

    -- Input data snapshot (what was fed to scorer)
    input_data JSONB NOT NULL,

    -- Product context at time of scoring
    amazon_price DECIMAL(10,2),
    review_count INTEGER,
    rating DECIMAL(2,1),
    bsr_primary INTEGER,

    -- Timestamps
    scored_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_artifacts_run ON opportunity_artifacts(run_id);
CREATE INDEX idx_artifacts_asin ON opportunity_artifacts(asin, scored_at DESC);
CREATE INDEX idx_artifacts_score ON opportunity_artifacts(final_score DESC);
CREATE INDEX idx_artifacts_time ON opportunity_artifacts(scored_at DESC);

COMMENT ON TABLE opportunity_artifacts IS 'Immutable scoring snapshots — one per opportunity per run. Future training dataset.';

-- ============================================================================
-- D) TABLE: shortlist_snapshots — Hystérésis support
-- ============================================================================

CREATE TABLE IF NOT EXISTS shortlist_snapshots (
    snapshot_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id UUID REFERENCES pipeline_runs(run_id),

    -- Shortlist content (immutable)
    asins TEXT[] NOT NULL,                    -- ordered list of ASINs in shortlist
    scores INTEGER[] NOT NULL,               -- parallel array of scores
    total_value DECIMAL(12,2) NOT NULL,

    -- Stability tracking
    asins_added TEXT[] DEFAULT '{}',          -- new vs previous shortlist
    asins_removed TEXT[] DEFAULT '{}',        -- dropped vs previous shortlist
    stability_score DECIMAL(3,2),            -- 0.0 (total churn) to 1.0 (identical)

    -- Metadata
    frozen BOOLEAN DEFAULT FALSE,             -- was this shortlist frozen (not overwritten)?
    active BOOLEAN DEFAULT TRUE,              -- is this the current shortlist?
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_shortlist_snapshots_active ON shortlist_snapshots(active, created_at DESC);
CREATE INDEX idx_shortlist_snapshots_run ON shortlist_snapshots(run_id);

COMMENT ON TABLE shortlist_snapshots IS 'Shortlist history for hystérésis and stability tracking';

-- ============================================================================
-- E) TABLE: system_metrics — Observability log
-- ============================================================================

CREATE TABLE IF NOT EXISTS system_metrics (
    id BIGSERIAL PRIMARY KEY,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- DB metrics
    db_size_mb DECIMAL(10,2),
    table_sizes JSONB,                       -- {"asin_snapshots": 45.2, "reviews": 12.1, ...}

    -- Row counts
    asin_count INTEGER,
    snapshot_count INTEGER,
    event_count INTEGER,                     -- total across all event tables
    opportunity_count INTEGER,

    -- Mat view refresh
    mv_refresh_duration_ms INTEGER,

    -- Run reference
    run_id UUID REFERENCES pipeline_runs(run_id),

    -- Alerts
    alerts JSONB DEFAULT '[]'                -- [{"type": "db_size_high", "value": 450}]
);

CREATE INDEX idx_system_metrics_time ON system_metrics(recorded_at DESC);

COMMENT ON TABLE system_metrics IS 'System observability metrics — logged per run or on schedule';

-- ============================================================================
-- F) Helper function: compute DB size metrics
-- ============================================================================

CREATE OR REPLACE FUNCTION get_db_metrics()
RETURNS JSONB AS $$
DECLARE
    result JSONB;
BEGIN
    SELECT jsonb_build_object(
        'db_size_mb', round(pg_database_size(current_database()) / 1024.0 / 1024.0, 2),
        'tables', (
            SELECT jsonb_object_agg(
                relname,
                round(pg_total_relation_size(c.oid) / 1024.0 / 1024.0, 2)
            )
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE n.nspname = 'public' AND c.relkind = 'r'
        ),
        'row_counts', jsonb_build_object(
            'asins', (SELECT count(*) FROM asins WHERE deleted_at IS NULL),
            'snapshots', (SELECT count(*) FROM asin_snapshots),
            'price_events', (SELECT count(*) FROM price_events),
            'bsr_events', (SELECT count(*) FROM bsr_events),
            'stock_events', (SELECT count(*) FROM stock_events),
            'opportunities', (SELECT count(*) FROM opportunities),
            'reviews', (SELECT count(*) FROM reviews),
            'pipeline_runs', (SELECT count(*) FROM pipeline_runs)
        )
    ) INTO result;

    RETURN result;
END;
$$ LANGUAGE plpgsql;

COMMENT ON FUNCTION get_db_metrics IS 'Returns DB size, table sizes, and row counts as JSONB';
