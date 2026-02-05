-- ============================================================================
-- SMARTACUS - Railway PostgreSQL Schema (No TimescaleDB / No pgvector)
-- Adapted from 001_init_schema.sql + 002_performance_indexes.sql + 003_rag
-- Target: PostgreSQL 17 on Railway (extensions: pg_trgm, btree_gin)
-- ============================================================================

-- Enable available extensions
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS btree_gin;

-- ============================================================================
-- ENUMS
-- ============================================================================

CREATE TYPE stock_status AS ENUM (
    'in_stock', 'low_stock', 'out_of_stock', 'back_ordered', 'unknown'
);

CREATE TYPE fulfillment_type AS ENUM (
    'fba', 'fbm', 'amazon', 'unknown'
);

CREATE TYPE event_severity AS ENUM (
    'low', 'medium', 'high', 'critical'
);

CREATE TYPE movement_direction AS ENUM (
    'up', 'down', 'stable'
);

CREATE TYPE opportunity_status AS ENUM (
    'new', 'reviewing', 'validated', 'acted', 'archived', 'false_positive'
);

CREATE TYPE opportunity_type AS ENUM (
    'price_drop', 'bsr_surge', 'stock_out_competitor', 'review_spike',
    'new_entrant', 'demand_surge', 'arbitrage', 'seasonal'
);

CREATE TYPE sentiment_type AS ENUM (
    'very_negative', 'negative', 'neutral', 'positive', 'very_positive'
);

-- ============================================================================
-- TABLE: asins
-- ============================================================================

CREATE TABLE asins (
    asin VARCHAR(10) PRIMARY KEY,
    title TEXT NOT NULL,
    brand VARCHAR(255),
    manufacturer VARCHAR(255),
    model_number VARCHAR(100),
    category_id BIGINT,
    category_path TEXT[],
    subcategory VARCHAR(255),
    color VARCHAR(100),
    size VARCHAR(100),
    material VARCHAR(100),
    weight_grams INTEGER,
    dimensions_cm JSONB,
    main_image_url TEXT,
    bullet_points TEXT[],
    description TEXT,
    current_seller_id VARCHAR(50),
    current_seller_name VARCHAR(255),
    is_amazon_choice BOOLEAN DEFAULT FALSE,
    is_best_seller BOOLEAN DEFAULT FALSE,
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE,
    tracking_priority INTEGER DEFAULT 5,
    data_quality_score DECIMAL(3,2),
    last_full_scrape_at TIMESTAMPTZ,
    deleted_at TIMESTAMPTZ
);

CREATE INDEX idx_asins_brand ON asins(brand) WHERE deleted_at IS NULL;
CREATE INDEX idx_asins_category ON asins(category_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_asins_active ON asins(is_active) WHERE deleted_at IS NULL;
CREATE INDEX idx_asins_priority ON asins(tracking_priority DESC) WHERE is_active = TRUE;
CREATE INDEX idx_asins_title_trgm ON asins USING gin(title gin_trgm_ops);
CREATE INDEX idx_asins_updated ON asins(last_updated_at);

-- ============================================================================
-- TABLE: asin_snapshots (regular table, NOT hypertable)
-- ============================================================================

CREATE TABLE asin_snapshots (
    snapshot_id BIGSERIAL,
    asin VARCHAR(10) NOT NULL,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    price_current DECIMAL(10,2),
    price_original DECIMAL(10,2),
    price_lowest_new DECIMAL(10,2),
    price_lowest_used DECIMAL(10,2),
    price_currency VARCHAR(3) DEFAULT 'USD',
    coupon_discount_percent DECIMAL(5,2),
    coupon_discount_amount DECIMAL(10,2),
    deal_type VARCHAR(50),
    bsr_primary INTEGER,
    bsr_category_name VARCHAR(255),
    bsr_subcategory INTEGER,
    bsr_subcategory_name VARCHAR(255),
    stock_status stock_status NOT NULL DEFAULT 'unknown',
    stock_quantity INTEGER,
    fulfillment fulfillment_type DEFAULT 'unknown',
    seller_count INTEGER,
    rating_average DECIMAL(2,1),
    rating_count INTEGER,
    review_count INTEGER,
    rating_5_star_percent DECIMAL(5,2),
    rating_4_star_percent DECIMAL(5,2),
    rating_3_star_percent DECIMAL(5,2),
    rating_2_star_percent DECIMAL(5,2),
    rating_1_star_percent DECIMAL(5,2),
    price_delta DECIMAL(10,2),
    price_delta_percent DECIMAL(5,2),
    bsr_delta INTEGER,
    bsr_delta_percent DECIMAL(5,2),
    review_count_delta INTEGER,
    scrape_session_id UUID,
    scrape_duration_ms INTEGER,
    data_source VARCHAR(50),
    CONSTRAINT pk_asin_snapshots PRIMARY KEY (asin, captured_at)
);

-- Indexes for asin_snapshots
CREATE INDEX idx_snapshots_asin_time ON asin_snapshots(asin, captured_at DESC);
CREATE INDEX idx_snapshots_price_delta ON asin_snapshots(price_delta_percent)
    WHERE price_delta_percent IS NOT NULL AND ABS(price_delta_percent) > 5;
CREATE INDEX idx_snapshots_bsr_delta ON asin_snapshots(bsr_delta_percent)
    WHERE bsr_delta_percent IS NOT NULL AND ABS(bsr_delta_percent) > 10;
CREATE INDEX idx_snapshots_stock ON asin_snapshots(stock_status, captured_at DESC);
CREATE INDEX idx_snapshots_time ON asin_snapshots(captured_at DESC);

-- ============================================================================
-- TABLE: price_events
-- ============================================================================

CREATE TABLE price_events (
    event_id BIGSERIAL PRIMARY KEY,
    asin VARCHAR(10) NOT NULL REFERENCES asins(asin),
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    price_before DECIMAL(10,2) NOT NULL,
    price_after DECIMAL(10,2) NOT NULL,
    price_change DECIMAL(10,2) NOT NULL,
    price_change_percent DECIMAL(5,2) NOT NULL,
    direction movement_direction NOT NULL,
    is_deal BOOLEAN DEFAULT FALSE,
    deal_type VARCHAR(50),
    is_coupon BOOLEAN DEFAULT FALSE,
    severity event_severity NOT NULL DEFAULT 'medium',
    snapshot_before_id BIGINT,
    snapshot_after_id BIGINT,
    snapshot_before_at TIMESTAMPTZ,
    snapshot_after_at TIMESTAMPTZ,
    processed_at TIMESTAMPTZ,
    opportunity_generated BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_price_events_asin ON price_events(asin, detected_at DESC);
CREATE INDEX idx_price_events_time ON price_events(detected_at DESC);
CREATE INDEX idx_price_events_severity ON price_events(severity) WHERE severity IN ('high', 'critical');
CREATE INDEX idx_price_events_unprocessed ON price_events(detected_at) WHERE processed_at IS NULL;
CREATE INDEX idx_price_events_direction ON price_events(direction, price_change_percent);

-- ============================================================================
-- TABLE: bsr_events
-- ============================================================================

CREATE TABLE bsr_events (
    event_id BIGSERIAL PRIMARY KEY,
    asin VARCHAR(10) NOT NULL REFERENCES asins(asin),
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    bsr_before INTEGER NOT NULL,
    bsr_after INTEGER NOT NULL,
    bsr_change INTEGER NOT NULL,
    bsr_change_percent DECIMAL(5,2) NOT NULL,
    direction movement_direction NOT NULL,
    category_name VARCHAR(255),
    change_velocity DECIMAL(10,2),
    is_sustained BOOLEAN,
    severity event_severity NOT NULL DEFAULT 'medium',
    likely_cause VARCHAR(100),
    snapshot_before_at TIMESTAMPTZ,
    snapshot_after_at TIMESTAMPTZ,
    processed_at TIMESTAMPTZ,
    opportunity_generated BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_bsr_events_asin ON bsr_events(asin, detected_at DESC);
CREATE INDEX idx_bsr_events_time ON bsr_events(detected_at DESC);
CREATE INDEX idx_bsr_events_severity ON bsr_events(severity) WHERE severity IN ('high', 'critical');
CREATE INDEX idx_bsr_events_improving ON bsr_events(direction, bsr_change_percent) WHERE direction = 'up';

-- ============================================================================
-- TABLE: stock_events
-- ============================================================================

CREATE TABLE stock_events (
    event_id BIGSERIAL PRIMARY KEY,
    asin VARCHAR(10) NOT NULL REFERENCES asins(asin),
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    status_before stock_status NOT NULL,
    status_after stock_status NOT NULL,
    quantity_before INTEGER,
    quantity_after INTEGER,
    event_type VARCHAR(50) NOT NULL,
    severity event_severity NOT NULL DEFAULT 'medium',
    stockout_started_at TIMESTAMPTZ,
    stockout_duration_hours INTEGER,
    seller_id VARCHAR(50),
    seller_name VARCHAR(255),
    is_primary_seller BOOLEAN DEFAULT TRUE,
    snapshot_before_at TIMESTAMPTZ,
    snapshot_after_at TIMESTAMPTZ,
    processed_at TIMESTAMPTZ,
    opportunity_generated BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_stock_events_asin ON stock_events(asin, detected_at DESC);
CREATE INDEX idx_stock_events_type ON stock_events(event_type, detected_at DESC);
CREATE INDEX idx_stock_events_stockouts ON stock_events(detected_at DESC)
    WHERE event_type = 'stockout';

-- ============================================================================
-- TABLE: reviews
-- ============================================================================

CREATE TABLE reviews (
    review_id VARCHAR(50) PRIMARY KEY,
    asin VARCHAR(10) NOT NULL REFERENCES asins(asin),
    title TEXT,
    body TEXT,
    rating DECIMAL(2,1) NOT NULL,
    author_id VARCHAR(50),
    author_name VARCHAR(255),
    author_is_vine BOOLEAN DEFAULT FALSE,
    review_date DATE,
    is_verified_purchase BOOLEAN DEFAULT FALSE,
    helpful_votes INTEGER DEFAULT 0,
    total_votes INTEGER DEFAULT 0,
    has_images BOOLEAN DEFAULT FALSE,
    has_video BOOLEAN DEFAULT FALSE,
    image_count INTEGER DEFAULT 0,
    variant_attributes JSONB,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    analyzed_at TIMESTAMPTZ,
    content_hash VARCHAR(64),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_reviews_asin ON reviews(asin, review_date DESC);
CREATE INDEX idx_reviews_rating ON reviews(asin, rating);
CREATE INDEX idx_reviews_verified ON reviews(asin, is_verified_purchase) WHERE is_verified_purchase = TRUE;
CREATE INDEX idx_reviews_unanalyzed ON reviews(captured_at) WHERE analyzed_at IS NULL;
CREATE INDEX idx_reviews_date ON reviews(review_date DESC);
CREATE INDEX idx_reviews_helpful ON reviews(helpful_votes DESC) WHERE helpful_votes > 0;
CREATE INDEX idx_reviews_content_trgm ON reviews USING gin(body gin_trgm_ops);

-- ============================================================================
-- TABLE: review_analysis
-- ============================================================================

CREATE TABLE review_analysis (
    analysis_id BIGSERIAL PRIMARY KEY,
    review_id VARCHAR(50) NOT NULL REFERENCES reviews(review_id),
    asin VARCHAR(10) NOT NULL,
    sentiment sentiment_type NOT NULL,
    sentiment_score DECIMAL(4,3),
    sentiment_confidence DECIMAL(3,2),
    emotions JSONB,
    primary_emotion VARCHAR(50),
    keywords TEXT[],
    key_phrases TEXT[],
    topics TEXT[],
    aspects JSONB,
    is_complaint BOOLEAN DEFAULT FALSE,
    complaint_categories TEXT[],
    complaint_severity event_severity,
    mentioned_features TEXT[],
    feature_sentiments JSONB,
    mentions_competitor BOOLEAN DEFAULT FALSE,
    competitor_asins TEXT[],
    competitor_comparison_sentiment sentiment_type,
    summary TEXT,
    model_version VARCHAR(50),
    analyzed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processing_time_ms INTEGER,
    CONSTRAINT unique_review_analysis UNIQUE (review_id)
);

CREATE INDEX idx_review_analysis_asin ON review_analysis(asin);
CREATE INDEX idx_review_analysis_sentiment ON review_analysis(asin, sentiment);
CREATE INDEX idx_review_analysis_complaints ON review_analysis(asin) WHERE is_complaint = TRUE;
CREATE INDEX idx_review_analysis_keywords ON review_analysis USING gin(keywords);
CREATE INDEX idx_review_analysis_topics ON review_analysis USING gin(topics);

-- ============================================================================
-- TABLE: opportunities
-- ============================================================================

CREATE TABLE opportunities (
    opportunity_id BIGSERIAL PRIMARY KEY,
    asin VARCHAR(10) NOT NULL REFERENCES asins(asin),
    opportunity_type opportunity_type NOT NULL,
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ,
    score_total DECIMAL(5,2) NOT NULL,
    score_breakdown JSONB NOT NULL,
    confidence DECIMAL(3,2),
    trigger_event_type VARCHAR(50),
    trigger_event_id BIGINT,
    supporting_data JSONB,
    ai_summary TEXT,
    risk_factors TEXT[],
    action_recommendations TEXT[],
    status opportunity_status NOT NULL DEFAULT 'new',
    status_changed_at TIMESTAMPTZ DEFAULT NOW(),
    reviewed_by VARCHAR(100),
    review_notes TEXT,
    action_taken TEXT,
    action_taken_at TIMESTAMPTZ,
    action_result TEXT,
    roi_actual DECIMAL(10,2),
    related_opportunity_ids BIGINT[],
    superseded_by_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_opportunities_asin ON opportunities(asin, detected_at DESC);
CREATE INDEX idx_opportunities_status ON opportunities(status, score_total DESC);
CREATE INDEX idx_opportunities_type ON opportunities(opportunity_type, detected_at DESC);
CREATE INDEX idx_opportunities_score ON opportunities(score_total DESC) WHERE status = 'new';
CREATE INDEX idx_opportunities_active ON opportunities(detected_at DESC)
    WHERE status IN ('new', 'reviewing', 'validated');
CREATE INDEX idx_opportunities_expiring ON opportunities(expires_at)
    WHERE expires_at IS NOT NULL AND status = 'new';

-- ============================================================================
-- MATERIALIZED VIEWS
-- ============================================================================

-- Latest snapshot per ASIN
CREATE MATERIALIZED VIEW mv_latest_snapshots AS
SELECT DISTINCT ON (asin)
    asin, captured_at, price_current, price_original,
    bsr_primary, bsr_category_name, stock_status,
    rating_average, review_count, price_delta_percent, bsr_delta_percent
FROM asin_snapshots
ORDER BY asin, captured_at DESC;

CREATE UNIQUE INDEX idx_mv_latest_snapshots_asin ON mv_latest_snapshots(asin);
CREATE INDEX idx_mv_latest_snapshots_bsr ON mv_latest_snapshots(bsr_primary);
CREATE INDEX idx_mv_latest_snapshots_price ON mv_latest_snapshots(price_current);

-- 7-day aggregations
CREATE MATERIALIZED VIEW mv_asin_stats_7d AS
SELECT
    asin,
    COUNT(*) as snapshot_count,
    MIN(price_current) as price_min,
    MAX(price_current) as price_max,
    AVG(price_current) as price_avg,
    MIN(bsr_primary) as bsr_best,
    MAX(bsr_primary) as bsr_worst,
    AVG(bsr_primary) as bsr_avg,
    SUM(CASE WHEN stock_status = 'out_of_stock' THEN 1 ELSE 0 END) as stockout_count,
    MAX(captured_at) as last_snapshot_at
FROM asin_snapshots
WHERE captured_at >= NOW() - INTERVAL '7 days'
GROUP BY asin;

CREATE UNIQUE INDEX idx_mv_stats_7d_asin ON mv_asin_stats_7d(asin);

-- 30-day aggregations
CREATE MATERIALIZED VIEW mv_asin_stats_30d AS
SELECT
    asin,
    COUNT(*) as snapshot_count,
    MIN(price_current) as price_min,
    MAX(price_current) as price_max,
    AVG(price_current) as price_avg,
    STDDEV(price_current) as price_stddev,
    MIN(bsr_primary) as bsr_best,
    MAX(bsr_primary) as bsr_worst,
    AVG(bsr_primary) as bsr_avg,
    (MAX(price_current) - MIN(price_current)) / NULLIF(AVG(price_current), 0) * 100 as price_volatility_pct,
    REGR_SLOPE(bsr_primary, EXTRACT(EPOCH FROM captured_at)) as bsr_trend,
    SUM(CASE WHEN stock_status = 'out_of_stock' THEN 1 ELSE 0 END) as stockout_count,
    MAX(captured_at) as last_snapshot_at
FROM asin_snapshots
WHERE captured_at >= NOW() - INTERVAL '30 days'
GROUP BY asin;

CREATE UNIQUE INDEX idx_mv_stats_30d_asin ON mv_asin_stats_30d(asin);

-- Review sentiment aggregation
CREATE MATERIALIZED VIEW mv_review_sentiment AS
SELECT
    ra.asin,
    COUNT(*) as analyzed_count,
    AVG(ra.sentiment_score) as avg_sentiment,
    SUM(CASE WHEN ra.sentiment IN ('positive', 'very_positive') THEN 1 ELSE 0 END)::DECIMAL / COUNT(*) as positive_ratio,
    SUM(CASE WHEN ra.is_complaint THEN 1 ELSE 0 END) as complaint_count,
    array_agg(DISTINCT unnest) FILTER (WHERE unnest IS NOT NULL) as all_keywords,
    array_agg(DISTINCT unnest2) FILTER (WHERE unnest2 IS NOT NULL) as all_complaint_categories
FROM review_analysis ra
LEFT JOIN LATERAL unnest(ra.keywords) ON TRUE
LEFT JOIN LATERAL unnest(ra.complaint_categories) unnest2 ON TRUE
WHERE ra.analyzed_at >= NOW() - INTERVAL '90 days'
GROUP BY ra.asin;

CREATE UNIQUE INDEX idx_mv_sentiment_asin ON mv_review_sentiment(asin);

-- ============================================================================
-- TRIGGER FUNCTIONS
-- ============================================================================

-- Calculate deltas on snapshot insert
CREATE OR REPLACE FUNCTION calculate_snapshot_deltas()
RETURNS TRIGGER AS $$
DECLARE
    prev_snapshot RECORD;
BEGIN
    SELECT price_current, bsr_primary, review_count
    INTO prev_snapshot
    FROM asin_snapshots
    WHERE asin = NEW.asin
      AND captured_at < NEW.captured_at
    ORDER BY captured_at DESC
    LIMIT 1;

    IF FOUND THEN
        NEW.price_delta := NEW.price_current - prev_snapshot.price_current;
        IF prev_snapshot.price_current > 0 THEN
            NEW.price_delta_percent := ((NEW.price_current - prev_snapshot.price_current) / prev_snapshot.price_current) * 100;
        END IF;
        NEW.bsr_delta := NEW.bsr_primary - prev_snapshot.bsr_primary;
        IF prev_snapshot.bsr_primary > 0 THEN
            NEW.bsr_delta_percent := ((NEW.bsr_primary - prev_snapshot.bsr_primary)::DECIMAL / prev_snapshot.bsr_primary) * 100;
        END IF;
        NEW.review_count_delta := NEW.review_count - prev_snapshot.review_count;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_calculate_deltas
    BEFORE INSERT ON asin_snapshots
    FOR EACH ROW
    EXECUTE FUNCTION calculate_snapshot_deltas();

-- Auto-generate price events
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

    IF ABS(NEW.price_delta_percent) >= 25 THEN
        v_severity := 'critical';
    ELSIF ABS(NEW.price_delta_percent) >= 15 THEN
        v_severity := 'high';
    ELSIF ABS(NEW.price_delta_percent) >= 10 THEN
        v_severity := 'medium';
    ELSE
        v_severity := 'low';
    END IF;

    IF NEW.price_delta < 0 THEN
        v_direction := 'down';
    ELSIF NEW.price_delta > 0 THEN
        v_direction := 'up';
    ELSE
        v_direction := 'stable';
    END IF;

    INSERT INTO price_events (
        asin, price_before, price_after, price_change,
        price_change_percent, direction, severity,
        snapshot_before_at, snapshot_after_at
    ) VALUES (
        NEW.asin, prev_snapshot.price_current, NEW.price_current,
        NEW.price_delta, NEW.price_delta_percent, v_direction, v_severity,
        prev_snapshot.captured_at, NEW.captured_at
    );

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_generate_price_events
    AFTER INSERT ON asin_snapshots
    FOR EACH ROW
    EXECUTE FUNCTION generate_price_events();

-- Auto-generate BSR events
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

    IF NEW.bsr_delta < 0 THEN
        v_direction := 'up';
        IF ABS(NEW.bsr_delta_percent) >= 50 OR ABS(NEW.bsr_delta) >= 50000 THEN
            v_severity := 'critical';
        ELSIF ABS(NEW.bsr_delta_percent) >= 30 THEN
            v_severity := 'high';
        ELSE
            v_severity := 'medium';
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
    );

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_generate_bsr_events
    AFTER INSERT ON asin_snapshots
    FOR EACH ROW
    EXECUTE FUNCTION generate_bsr_events();

-- Auto-generate stock events
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
    );

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_generate_stock_events
    AFTER INSERT ON asin_snapshots
    FOR EACH ROW
    EXECUTE FUNCTION generate_stock_events();

-- ============================================================================
-- VIEWS
-- ============================================================================

CREATE VIEW v_active_opportunities AS
SELECT
    o.*, a.title as product_title, a.brand,
    ls.price_current, ls.bsr_primary, ls.stock_status
FROM opportunities o
JOIN asins a ON o.asin = a.asin
LEFT JOIN mv_latest_snapshots ls ON o.asin = ls.asin
WHERE o.status IN ('new', 'reviewing', 'validated')
ORDER BY o.score_total DESC;

CREATE VIEW v_asin_dashboard AS
SELECT
    a.asin, a.title, a.brand, a.is_amazon_choice, a.is_best_seller,
    ls.price_current, ls.price_original, ls.bsr_primary, ls.stock_status,
    ls.rating_average, ls.review_count,
    s7.price_min as price_7d_min, s7.price_max as price_7d_max,
    s7.bsr_best as bsr_7d_best, s7.stockout_count as stockouts_7d,
    s30.price_volatility_pct as volatility_30d,
    s30.bsr_trend as bsr_trend_30d,
    rs.avg_sentiment, rs.positive_ratio as review_positive_pct,
    rs.complaint_count as complaints_90d
FROM asins a
LEFT JOIN mv_latest_snapshots ls ON a.asin = ls.asin
LEFT JOIN mv_asin_stats_7d s7 ON a.asin = s7.asin
LEFT JOIN mv_asin_stats_30d s30 ON a.asin = s30.asin
LEFT JOIN mv_review_sentiment rs ON a.asin = rs.asin
WHERE a.is_active = TRUE AND a.deleted_at IS NULL;

CREATE VIEW v_recent_events AS
SELECT 'price' as event_type, asin, detected_at, severity::TEXT,
       CONCAT(direction::TEXT, ' ', ABS(price_change_percent)::TEXT, '%') as description
FROM price_events WHERE detected_at >= NOW() - INTERVAL '7 days'
UNION ALL
SELECT 'bsr', asin, detected_at, severity::TEXT,
       CONCAT(direction::TEXT, ' ', ABS(bsr_change_percent)::TEXT, '%')
FROM bsr_events WHERE detected_at >= NOW() - INTERVAL '7 days'
UNION ALL
SELECT 'stock', asin, detected_at, severity::TEXT, event_type
FROM stock_events WHERE detected_at >= NOW() - INTERVAL '7 days'
ORDER BY detected_at DESC;

-- ============================================================================
-- PROCEDURES
-- ============================================================================

CREATE OR REPLACE PROCEDURE refresh_all_materialized_views()
LANGUAGE plpgsql AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_latest_snapshots;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_asin_stats_7d;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_asin_stats_30d;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_review_sentiment;
END;
$$;

CREATE OR REPLACE PROCEDURE cleanup_old_events(retention_days INTEGER DEFAULT 180)
LANGUAGE plpgsql AS $$
BEGIN
    DELETE FROM price_events WHERE detected_at < NOW() - (retention_days || ' days')::INTERVAL;
    DELETE FROM bsr_events WHERE detected_at < NOW() - (retention_days || ' days')::INTERVAL;
    DELETE FROM stock_events WHERE detected_at < NOW() - (retention_days || ' days')::INTERVAL;
    DELETE FROM opportunities WHERE status = 'archived' AND updated_at < NOW() - (retention_days || ' days')::INTERVAL;
END;
$$;

-- ============================================================================
-- ADDITIONAL PERFORMANCE INDEXES (from migration 002)
-- ============================================================================

CREATE INDEX IF NOT EXISTS idx_asins_scrape_priority
    ON asins(tracking_priority DESC, last_updated_at ASC)
    WHERE is_active = TRUE AND deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_asins_brand_analysis
    ON asins(brand, asin) WHERE is_active = TRUE AND deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_price_events_actionable
    ON price_events(detected_at DESC, asin)
    WHERE severity IN ('high', 'critical') AND processed_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_bsr_events_actionable
    ON bsr_events(detected_at DESC, asin)
    WHERE severity IN ('high', 'critical') AND processed_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_snapshots_dashboard_cover
    ON asin_snapshots(asin, captured_at DESC)
    INCLUDE (price_current, bsr_primary, stock_status, rating_average, review_count);

CREATE INDEX IF NOT EXISTS idx_opportunities_listing_cover
    ON opportunities(status, score_total DESC)
    INCLUDE (asin, opportunity_type, detected_at, expires_at)
    WHERE status IN ('new', 'reviewing', 'validated');

CREATE INDEX IF NOT EXISTS idx_price_events_brin
    ON price_events USING BRIN(detected_at) WITH (pages_per_range = 32);

CREATE INDEX IF NOT EXISTS idx_bsr_events_brin
    ON bsr_events USING BRIN(detected_at) WITH (pages_per_range = 32);

CREATE INDEX IF NOT EXISTS idx_stock_events_brin
    ON stock_events USING BRIN(detected_at) WITH (pages_per_range = 32);

CREATE INDEX IF NOT EXISTS idx_asins_bullets_gin ON asins USING GIN(bullet_points);
CREATE INDEX IF NOT EXISTS idx_asins_category_path_gin ON asins USING GIN(category_path);
CREATE INDEX IF NOT EXISTS idx_opportunities_supporting_gin ON opportunities USING GIN(supporting_data jsonb_path_ops);
CREATE INDEX IF NOT EXISTS idx_review_analysis_aspects_gin ON review_analysis USING GIN(aspects jsonb_path_ops);
CREATE INDEX IF NOT EXISTS idx_review_analysis_emotions_gin ON review_analysis USING GIN(emotions jsonb_path_ops);

CREATE INDEX IF NOT EXISTS idx_asins_brand_lower ON asins(LOWER(brand));

-- FK indexes
CREATE INDEX IF NOT EXISTS idx_price_events_fk_asin ON price_events(asin);
CREATE INDEX IF NOT EXISTS idx_bsr_events_fk_asin ON bsr_events(asin);
CREATE INDEX IF NOT EXISTS idx_stock_events_fk_asin ON stock_events(asin);
CREATE INDEX IF NOT EXISTS idx_reviews_fk_asin ON reviews(asin);
CREATE INDEX IF NOT EXISTS idx_review_analysis_fk_review ON review_analysis(review_id);
CREATE INDEX IF NOT EXISTS idx_opportunities_fk_asin ON opportunities(asin);

-- Constraints
ALTER TABLE asin_snapshots
    ADD CONSTRAINT chk_price_positive CHECK (price_current >= 0),
    ADD CONSTRAINT chk_bsr_positive CHECK (bsr_primary >= 1),
    ADD CONSTRAINT chk_rating_range CHECK (rating_average >= 1.0 AND rating_average <= 5.0);

ALTER TABLE reviews
    ADD CONSTRAINT chk_review_rating_range CHECK (rating >= 1.0 AND rating <= 5.0);

ALTER TABLE opportunities
    ADD CONSTRAINT chk_score_range CHECK (score_total >= 0 AND score_total <= 100),
    ADD CONSTRAINT chk_confidence_range CHECK (confidence >= 0 AND confidence <= 1);

-- Parallel workers
ALTER TABLE asin_snapshots SET (parallel_workers = 4);
ALTER TABLE reviews SET (parallel_workers = 4);
ALTER TABLE review_analysis SET (parallel_workers = 4);

-- ============================================================================
-- RAG TABLES (without pgvector - embedding stored as JSONB for now)
-- ============================================================================

CREATE TABLE IF NOT EXISTS rag_documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    doc_type VARCHAR(20) NOT NULL CHECK (doc_type IN ('rules', 'ops', 'templates', 'memory')),
    domain VARCHAR(50) NOT NULL,
    title VARCHAR(500) NOT NULL,
    description TEXT,
    source VARCHAR(500),
    source_type VARCHAR(50) DEFAULT 'manual',
    marketplace VARCHAR(10) DEFAULT 'US',
    category VARCHAR(100),
    language VARCHAR(5) DEFAULT 'en',
    effective_date DATE DEFAULT CURRENT_DATE,
    expiry_date DATE,
    confidence DECIMAL(3,2) DEFAULT 1.0 CHECK (confidence >= 0 AND confidence <= 1),
    run_id VARCHAR(50),
    asin VARCHAR(20),
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE
);

CREATE TABLE IF NOT EXISTS rag_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL REFERENCES rag_documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    content_hash VARCHAR(64) NOT NULL,
    context_header TEXT,
    -- Embedding stored as JSONB array (pgvector not available)
    -- Migrate to vector(1536) when pgvector becomes available
    embedding JSONB,
    token_count INTEGER,
    doc_type VARCHAR(20) NOT NULL,
    domain VARCHAR(50) NOT NULL,
    marketplace VARCHAR(10) DEFAULT 'US',
    category VARCHAR(100),
    language VARCHAR(5) DEFAULT 'en',
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (document_id, chunk_index),
    UNIQUE (content_hash)
);

CREATE TABLE IF NOT EXISTS rag_citations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    session_id VARCHAR(50) NOT NULL,
    agent_type VARCHAR(20) NOT NULL,
    query_text TEXT NOT NULL,
    chunk_ids UUID[] NOT NULL,
    similarity_scores DECIMAL(4,3)[],
    extracted_rules TEXT[],
    recommended_template_id UUID,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rag_chunks_doc_type ON rag_chunks(doc_type);
CREATE INDEX IF NOT EXISTS idx_rag_chunks_domain ON rag_chunks(domain);
CREATE INDEX IF NOT EXISTS idx_rag_chunks_marketplace ON rag_chunks(marketplace);
CREATE INDEX IF NOT EXISTS idx_rag_chunks_filters ON rag_chunks(doc_type, domain, marketplace, language);
CREATE INDEX IF NOT EXISTS idx_rag_documents_doc_type ON rag_documents(doc_type);
CREATE INDEX IF NOT EXISTS idx_rag_documents_domain ON rag_documents(domain);
CREATE INDEX IF NOT EXISTS idx_rag_documents_active ON rag_documents(is_active) WHERE is_active = TRUE;
CREATE INDEX IF NOT EXISTS idx_rag_documents_asin ON rag_documents(asin) WHERE asin IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_rag_citations_session ON rag_citations(session_id);
CREATE INDEX IF NOT EXISTS idx_rag_citations_agent ON rag_citations(agent_type);

-- RAG document timestamp trigger
CREATE OR REPLACE FUNCTION update_rag_document_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trigger_rag_documents_updated
    BEFORE UPDATE ON rag_documents
    FOR EACH ROW
    EXECUTE FUNCTION update_rag_document_timestamp();

-- ============================================================================
-- COMMENTS
-- ============================================================================

COMMENT ON TABLE asins IS 'Master catalog of tracked Amazon ASINs';
COMMENT ON TABLE asin_snapshots IS 'Time-series snapshots of ASIN metrics (price, BSR, stock, ratings)';
COMMENT ON TABLE price_events IS 'Significant price change events (>5% threshold)';
COMMENT ON TABLE bsr_events IS 'Significant BSR movement events';
COMMENT ON TABLE stock_events IS 'Stock availability transitions';
COMMENT ON TABLE reviews IS 'Individual Amazon reviews for NLP analysis';
COMMENT ON TABLE review_analysis IS 'NLP analysis results for reviews';
COMMENT ON TABLE opportunities IS 'Scored opportunities detected by the analysis engine';
COMMENT ON TABLE rag_documents IS 'RAG knowledge base documents';
COMMENT ON TABLE rag_chunks IS 'RAG chunks for semantic search (embedding as JSONB until pgvector available)';
COMMENT ON TABLE rag_citations IS 'Tracks chunk usage in agent responses';
