-- Migration 004: Make asins.title nullable
-- Reason: Keepa sometimes returns dead/delisted ASINs with no title.
-- The pipeline should still store them (for tracking/dedup) rather than crash.
-- The frontend already handles NULL titles gracefully.

ALTER TABLE asins ALTER COLUMN title DROP NOT NULL;

-- Add last_seen_at column for tracking stale/dead ASINs
ALTER TABLE asins ADD COLUMN IF NOT EXISTS last_seen_at TIMESTAMPTZ;

-- Backfill last_seen_at from latest snapshot
UPDATE asins a
SET last_seen_at = (
    SELECT MAX(captured_at) FROM asin_snapshots s WHERE s.asin = a.asin
)
WHERE a.last_seen_at IS NULL;

COMMENT ON COLUMN asins.title IS 'Product title. NULL for dead/delisted ASINs.';
COMMENT ON COLUMN asins.last_seen_at IS 'Last time this ASIN appeared in a Keepa response. NULL = never fetched.';
