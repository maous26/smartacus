-- ============================================================================
-- SMARTACUS - Performance Optimization Indexes
-- Additional indexes for specific query patterns
-- Run AFTER initial data load for optimal performance
-- ============================================================================

-- ============================================================================
-- COMPOSITE INDEXES FOR COMMON JOIN PATTERNS
-- ============================================================================

-- Fast lookup: Active ASIN with priority for scraping scheduler
CREATE INDEX IF NOT EXISTS idx_asins_scrape_priority
    ON asins(tracking_priority DESC, last_updated_at ASC)
    WHERE is_active = TRUE AND deleted_at IS NULL;

-- Brand + BSR for brand performance analysis
CREATE INDEX IF NOT EXISTS idx_asins_brand_analysis
    ON asins(brand, asin)
    WHERE is_active = TRUE AND deleted_at IS NULL;

-- ============================================================================
-- PARTIAL INDEXES FOR HOT DATA
-- ============================================================================

-- Recent snapshots (last 7 days) - most frequently queried
CREATE INDEX IF NOT EXISTS idx_snapshots_recent_7d
    ON asin_snapshots(asin, captured_at DESC)
    WHERE captured_at >= NOW() - INTERVAL '7 days';

-- High-value events only
CREATE INDEX IF NOT EXISTS idx_price_events_actionable
    ON price_events(detected_at DESC, asin)
    WHERE severity IN ('high', 'critical') AND processed_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_bsr_events_actionable
    ON bsr_events(detected_at DESC, asin)
    WHERE severity IN ('high', 'critical') AND processed_at IS NULL;

-- ============================================================================
-- COVERING INDEXES (Index-Only Scans)
-- ============================================================================

-- For dashboard quick view (no table access needed)
CREATE INDEX IF NOT EXISTS idx_snapshots_dashboard_cover
    ON asin_snapshots(asin, captured_at DESC)
    INCLUDE (price_current, bsr_primary, stock_status, rating_average, review_count);

-- For opportunity listing
CREATE INDEX IF NOT EXISTS idx_opportunities_listing_cover
    ON opportunities(status, score_total DESC)
    INCLUDE (asin, opportunity_type, detected_at, expires_at)
    WHERE status IN ('new', 'reviewing', 'validated');

-- ============================================================================
-- BRIN INDEXES FOR LARGE TIME-SERIES DATA
-- More efficient than B-tree for sorted insert patterns
-- ============================================================================

-- Note: TimescaleDB handles this internally for hypertables,
-- but useful for event tables
CREATE INDEX IF NOT EXISTS idx_price_events_brin
    ON price_events USING BRIN(detected_at) WITH (pages_per_range = 32);

CREATE INDEX IF NOT EXISTS idx_bsr_events_brin
    ON bsr_events USING BRIN(detected_at) WITH (pages_per_range = 32);

CREATE INDEX IF NOT EXISTS idx_stock_events_brin
    ON stock_events USING BRIN(detected_at) WITH (pages_per_range = 32);

-- ============================================================================
-- GIN INDEXES FOR ARRAY/JSONB QUERIES
-- ============================================================================

-- Search within bullet points
CREATE INDEX IF NOT EXISTS idx_asins_bullets_gin
    ON asins USING GIN(bullet_points);

-- Search within category path
CREATE INDEX IF NOT EXISTS idx_asins_category_path_gin
    ON asins USING GIN(category_path);

-- JSONB queries on opportunity supporting data
CREATE INDEX IF NOT EXISTS idx_opportunities_supporting_gin
    ON opportunities USING GIN(supporting_data jsonb_path_ops);

-- JSONB queries on review analysis aspects
CREATE INDEX IF NOT EXISTS idx_review_analysis_aspects_gin
    ON review_analysis USING GIN(aspects jsonb_path_ops);

CREATE INDEX IF NOT EXISTS idx_review_analysis_emotions_gin
    ON review_analysis USING GIN(emotions jsonb_path_ops);

-- ============================================================================
-- EXPRESSION INDEXES
-- ============================================================================

-- Discount percentage calculation (frequently computed)
CREATE INDEX IF NOT EXISTS idx_snapshots_discount
    ON asin_snapshots(
        (ROUND((1 - price_current / NULLIF(price_original, 0)) * 100, 1))
    )
    WHERE price_original > 0 AND price_current < price_original;

-- Lowercase brand for case-insensitive search
CREATE INDEX IF NOT EXISTS idx_asins_brand_lower
    ON asins(LOWER(brand));

-- ============================================================================
-- STATISTICS TARGETS
-- Increase statistics for frequently filtered columns
-- ============================================================================

ALTER TABLE asin_snapshots ALTER COLUMN asin SET STATISTICS 1000;
ALTER TABLE asin_snapshots ALTER COLUMN stock_status SET STATISTICS 500;
ALTER TABLE asin_snapshots ALTER COLUMN bsr_primary SET STATISTICS 500;

ALTER TABLE opportunities ALTER COLUMN status SET STATISTICS 500;
ALTER TABLE opportunities ALTER COLUMN opportunity_type SET STATISTICS 500;

ALTER TABLE review_analysis ALTER COLUMN sentiment SET STATISTICS 500;

-- ============================================================================
-- TABLESPACE CONSIDERATIONS
-- Uncomment and adjust if using multiple storage tiers
-- ============================================================================

-- Fast SSD for hot/recent data
-- CREATE TABLESPACE fast_storage LOCATION '/ssd/postgres/data';
-- ALTER INDEX idx_snapshots_recent_7d SET TABLESPACE fast_storage;
-- ALTER INDEX idx_opportunities_listing_cover SET TABLESPACE fast_storage;

-- Slower HDD for archive/cold data
-- CREATE TABLESPACE archive_storage LOCATION '/hdd/postgres/archive';

-- ============================================================================
-- CLUSTER TABLES
-- Physically reorder table data to match index for optimal read performance
-- Run periodically during low-traffic periods
-- ============================================================================

-- Note: These are expensive operations, run only during maintenance windows

-- Cluster asins by ASIN (already primary key, likely already ordered)
-- CLUSTER asins USING asins_pkey;

-- Cluster opportunities by status and score for dashboard
-- CLUSTER opportunities USING idx_opportunities_listing_cover;

-- Cluster reviews by ASIN and date for sequential reading
-- CLUSTER reviews USING idx_reviews_asin;

-- ============================================================================
-- VACUUM AND ANALYZE RECOMMENDATIONS
-- ============================================================================

-- After initial bulk load:
-- VACUUM (VERBOSE, ANALYZE) asins;
-- VACUUM (VERBOSE, ANALYZE) asin_snapshots;
-- VACUUM (VERBOSE, ANALYZE) reviews;
-- VACUUM (VERBOSE, ANALYZE) review_analysis;
-- VACUUM (VERBOSE, ANALYZE) opportunities;

-- For routine maintenance, use autovacuum with tuned settings:
-- ALTER TABLE asin_snapshots SET (
--     autovacuum_vacuum_scale_factor = 0.05,  -- Vacuum more frequently
--     autovacuum_analyze_scale_factor = 0.02
-- );

-- ============================================================================
-- PARALLEL QUERY HINTS
-- ============================================================================

-- These tables benefit from parallel queries
ALTER TABLE asin_snapshots SET (parallel_workers = 4);
ALTER TABLE reviews SET (parallel_workers = 4);
ALTER TABLE review_analysis SET (parallel_workers = 4);

-- ============================================================================
-- CONSTRAINT VALIDATION
-- Add check constraints for data integrity
-- ============================================================================

ALTER TABLE asin_snapshots
    ADD CONSTRAINT chk_price_positive CHECK (price_current >= 0),
    ADD CONSTRAINT chk_bsr_positive CHECK (bsr_primary >= 1),
    ADD CONSTRAINT chk_rating_range CHECK (rating_average >= 1.0 AND rating_average <= 5.0);

ALTER TABLE reviews
    ADD CONSTRAINT chk_review_rating_range CHECK (rating >= 1.0 AND rating <= 5.0);

ALTER TABLE opportunities
    ADD CONSTRAINT chk_score_range CHECK (score_total >= 0 AND score_total <= 100),
    ADD CONSTRAINT chk_confidence_range CHECK (confidence >= 0 AND confidence <= 1);

-- ============================================================================
-- FOREIGN KEY INDEXES
-- PostgreSQL doesn't auto-create indexes on FK columns
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_price_events_fk_asin
    ON price_events(asin);

CREATE INDEX IF NOT EXISTS idx_bsr_events_fk_asin
    ON bsr_events(asin);

CREATE INDEX IF NOT EXISTS idx_stock_events_fk_asin
    ON stock_events(asin);

CREATE INDEX IF NOT EXISTS idx_reviews_fk_asin
    ON reviews(asin);

CREATE INDEX IF NOT EXISTS idx_review_analysis_fk_review
    ON review_analysis(review_id);

CREATE INDEX IF NOT EXISTS idx_opportunities_fk_asin
    ON opportunities(asin);
