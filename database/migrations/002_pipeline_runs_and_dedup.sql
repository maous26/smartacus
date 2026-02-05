-- ============================================================================
-- SMARTACUS - Migration 002: Pipeline Runs + Event Deduplication
-- Target: Railway PostgreSQL 17
-- ============================================================================

-- ============================================================================
-- A) TABLE: pipeline_runs — "Black box recorder"
-- ============================================================================

CREATE TYPE pipeline_run_status AS ENUM (
    'running', 'completed', 'failed', 'cancelled'
);

CREATE TABLE pipeline_runs (
    run_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    status pipeline_run_status NOT NULL DEFAULT 'running',

    -- Timing
    started_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    ended_at TIMESTAMPTZ,

    -- ASIN counts
    asins_total INTEGER DEFAULT 0,
    asins_ok INTEGER DEFAULT 0,
    asins_failed INTEGER DEFAULT 0,
    asins_skipped INTEGER DEFAULT 0,          -- skipped (freshness threshold)

    -- Phase durations (ms)
    duration_ingestion_ms INTEGER,
    duration_events_ms INTEGER,
    duration_scoring_ms INTEGER,
    duration_refresh_ms INTEGER,
    duration_total_ms INTEGER,

    -- Outputs
    opportunities_generated INTEGER DEFAULT 0,
    events_generated INTEGER DEFAULT 0,
    shortlist_size INTEGER DEFAULT 0,

    -- Resource tracking
    keepa_tokens_used INTEGER DEFAULT 0,
    db_size_mb DECIMAL(10,2),

    -- Error tracking
    error_message TEXT,
    error_details JSONB,
    failed_asins TEXT[],

    -- Config snapshot (what params were used)
    config_snapshot JSONB,

    -- Metadata
    triggered_by VARCHAR(50) DEFAULT 'manual',  -- manual, cron, api
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_pipeline_runs_status ON pipeline_runs(status, started_at DESC);
CREATE INDEX idx_pipeline_runs_time ON pipeline_runs(started_at DESC);

COMMENT ON TABLE pipeline_runs IS 'Pipeline execution history — tracks every run with timing, counts, and errors';

-- ============================================================================
-- B) Event deduplication constraints
-- Prevent duplicate events if a pipeline run is replayed
-- ============================================================================

-- Price events: same ASIN + same before/after timestamps = duplicate
CREATE UNIQUE INDEX IF NOT EXISTS idx_price_events_dedup
    ON price_events(asin, snapshot_before_at, snapshot_after_at)
    WHERE snapshot_before_at IS NOT NULL AND snapshot_after_at IS NOT NULL;

-- BSR events: same ASIN + same before/after timestamps = duplicate
CREATE UNIQUE INDEX IF NOT EXISTS idx_bsr_events_dedup
    ON bsr_events(asin, snapshot_before_at, snapshot_after_at)
    WHERE snapshot_before_at IS NOT NULL AND snapshot_after_at IS NOT NULL;

-- Stock events: same ASIN + same before/after timestamps = duplicate
CREATE UNIQUE INDEX IF NOT EXISTS idx_stock_events_dedup
    ON stock_events(asin, snapshot_before_at, snapshot_after_at)
    WHERE snapshot_before_at IS NOT NULL AND snapshot_after_at IS NOT NULL;

-- ============================================================================
-- C) Make triggers re-run safe (ON CONFLICT DO NOTHING)
-- ============================================================================

-- Replace price event trigger to be idempotent
CREATE OR REPLACE FUNCTION generate_price_events()
RETURNS TRIGGER AS $$
DECLARE
    prev_snapshot RECORD;
    v_severity event_severity;
    v_direction movement_direction;
BEGIN
    IF NEW.price_delta_percent IS NULL OR ABS(NEW.price_delta_percent) < 5 THEN
        RETURN NEW;
    END IF;

    SELECT captured_at, price_current
    INTO prev_snapshot
    FROM asin_snapshots
    WHERE asin = NEW.asin
      AND captured_at < NEW.captured_at
    ORDER BY captured_at DESC
    LIMIT 1;

    IF NOT FOUND THEN RETURN NEW; END IF;

    IF ABS(NEW.price_delta_percent) >= 25 THEN v_severity := 'critical';
    ELSIF ABS(NEW.price_delta_percent) >= 15 THEN v_severity := 'high';
    ELSIF ABS(NEW.price_delta_percent) >= 10 THEN v_severity := 'medium';
    ELSE v_severity := 'low';
    END IF;

    IF NEW.price_delta < 0 THEN v_direction := 'down';
    ELSIF NEW.price_delta > 0 THEN v_direction := 'up';
    ELSE v_direction := 'stable';
    END IF;

    INSERT INTO price_events (
        asin, price_before, price_after, price_change,
        price_change_percent, direction, severity,
        snapshot_before_at, snapshot_after_at
    ) VALUES (
        NEW.asin, prev_snapshot.price_current, NEW.price_current,
        NEW.price_delta, NEW.price_delta_percent, v_direction, v_severity,
        prev_snapshot.captured_at, NEW.captured_at
    ) ON CONFLICT (asin, snapshot_before_at, snapshot_after_at)
      WHERE snapshot_before_at IS NOT NULL AND snapshot_after_at IS NOT NULL
      DO NOTHING;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Replace BSR event trigger to be idempotent
CREATE OR REPLACE FUNCTION generate_bsr_events()
RETURNS TRIGGER AS $$
DECLARE
    prev_snapshot RECORD;
    v_severity event_severity;
    v_direction movement_direction;
BEGIN
    IF NEW.bsr_delta IS NULL OR
       (ABS(NEW.bsr_delta_percent) < 20 AND ABS(NEW.bsr_delta) < 10000) THEN
        RETURN NEW;
    END IF;

    SELECT captured_at, bsr_primary
    INTO prev_snapshot
    FROM asin_snapshots
    WHERE asin = NEW.asin
      AND captured_at < NEW.captured_at
    ORDER BY captured_at DESC
    LIMIT 1;

    IF NOT FOUND THEN RETURN NEW; END IF;

    IF NEW.bsr_delta < 0 THEN
        v_direction := 'up';
        IF ABS(NEW.bsr_delta_percent) >= 50 OR ABS(NEW.bsr_delta) >= 50000 THEN v_severity := 'critical';
        ELSIF ABS(NEW.bsr_delta_percent) >= 30 THEN v_severity := 'high';
        ELSE v_severity := 'medium';
        END IF;
    ELSE
        v_direction := 'down';
        v_severity := 'low';
    END IF;

    INSERT INTO bsr_events (
        asin, bsr_before, bsr_after, bsr_change,
        bsr_change_percent, direction, category_name, severity,
        snapshot_before_at, snapshot_after_at
    ) VALUES (
        NEW.asin, prev_snapshot.bsr_primary, NEW.bsr_primary,
        NEW.bsr_delta, NEW.bsr_delta_percent, v_direction,
        NEW.bsr_category_name, v_severity,
        prev_snapshot.captured_at, NEW.captured_at
    ) ON CONFLICT (asin, snapshot_before_at, snapshot_after_at)
      WHERE snapshot_before_at IS NOT NULL AND snapshot_after_at IS NOT NULL
      DO NOTHING;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Replace stock event trigger to be idempotent
CREATE OR REPLACE FUNCTION generate_stock_events()
RETURNS TRIGGER AS $$
DECLARE
    prev_snapshot RECORD;
    v_event_type VARCHAR(50);
    v_severity event_severity;
BEGIN
    SELECT captured_at, stock_status, stock_quantity
    INTO prev_snapshot
    FROM asin_snapshots
    WHERE asin = NEW.asin
      AND captured_at < NEW.captured_at
    ORDER BY captured_at DESC
    LIMIT 1;

    IF NOT FOUND THEN RETURN NEW; END IF;
    IF prev_snapshot.stock_status = NEW.stock_status THEN RETURN NEW; END IF;

    IF prev_snapshot.stock_status IN ('in_stock', 'low_stock') AND NEW.stock_status = 'out_of_stock' THEN
        v_event_type := 'stockout'; v_severity := 'high';
    ELSIF prev_snapshot.stock_status = 'out_of_stock' AND NEW.stock_status IN ('in_stock', 'low_stock') THEN
        v_event_type := 'restock'; v_severity := 'medium';
    ELSIF NEW.stock_status = 'low_stock' THEN
        v_event_type := 'low_stock_alert'; v_severity := 'low';
    ELSE
        v_event_type := 'status_change'; v_severity := 'low';
    END IF;

    INSERT INTO stock_events (
        asin, status_before, status_after, quantity_before, quantity_after,
        event_type, severity, snapshot_before_at, snapshot_after_at
    ) VALUES (
        NEW.asin, prev_snapshot.stock_status, NEW.stock_status,
        prev_snapshot.stock_quantity, NEW.stock_quantity,
        v_event_type, v_severity, prev_snapshot.captured_at, NEW.captured_at
    ) ON CONFLICT (asin, snapshot_before_at, snapshot_after_at)
      WHERE snapshot_before_at IS NOT NULL AND snapshot_after_at IS NOT NULL
      DO NOTHING;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;
