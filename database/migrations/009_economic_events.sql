-- Migration 009: Economic Events table for storing detected market events
-- V2.0 Remediation - Priority 1: Economic Event Detection

-- Create urgency enum for events
DO $$ BEGIN
    CREATE TYPE event_urgency AS ENUM ('CRITICAL', 'HIGH', 'MEDIUM', 'LOW');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

-- Create economic_events table
CREATE TABLE IF NOT EXISTS economic_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asin VARCHAR(20) NOT NULL REFERENCES asins(asin) ON DELETE CASCADE,
    event_type VARCHAR(50) NOT NULL,        -- SUPPLY_SHOCK, COMPETITOR_COLLAPSE, QUALITY_DECAY
    event_subtype VARCHAR(50),              -- stockout, seller_churn, rating_drop, etc.
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    confidence REAL NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    urgency event_urgency NOT NULL,
    thesis TEXT,                            -- Investment thesis for this event
    signals JSONB NOT NULL DEFAULT '{}',    -- Raw signals that triggered the event
    event_fingerprint TEXT NOT NULL,        -- sha256(sorted(signals))[:16] for dedup
    run_id UUID REFERENCES pipeline_runs(run_id) ON DELETE SET NULL,

    -- Dedup by fingerprint, not by date (allows variants same day)
    UNIQUE(asin, event_type, event_fingerprint)
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_economic_events_asin ON economic_events(asin);
CREATE INDEX IF NOT EXISTS idx_economic_events_type ON economic_events(event_type);
CREATE INDEX IF NOT EXISTS idx_economic_events_detected_at ON economic_events(detected_at DESC);
CREATE INDEX IF NOT EXISTS idx_economic_events_urgency ON economic_events(urgency);
CREATE INDEX IF NOT EXISTS idx_economic_events_run ON economic_events(run_id);

-- Composite index for shortlist join (recent events by ASIN)
-- Note: Partial index with NOW() not possible (not immutable), use regular composite index
CREATE INDEX IF NOT EXISTS idx_economic_events_asin_recent
ON economic_events(asin, detected_at DESC);

-- Add comment for documentation
COMMENT ON TABLE economic_events IS 'Detected economic events (supply shock, competitor collapse, quality decay) with dedup via fingerprint';
COMMENT ON COLUMN economic_events.event_fingerprint IS 'sha256(sorted(signals_json))[:16] for robust deduplication';
COMMENT ON COLUMN economic_events.urgency IS 'CRITICAL=immediate action, HIGH=act within 48h, MEDIUM=monitor, LOW=informational';
