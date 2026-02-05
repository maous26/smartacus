-- ============================================================================
-- SMARTACUS - Amazon Economic Probe Database Schema
-- Version: 1.0.0
-- Database: PostgreSQL 15+ with TimescaleDB 2.x
--
-- Optimized for:
--   - 3,000-10,000 ASINs tracking (car phone mounts niche)
--   - 24-48h refresh cycles
--   - Delta detection (snapshot N vs N-1)
--   - Time-series aggregations (7d, 30d, 90d)
--   - Event-driven opportunity detection
-- ============================================================================

-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS timescaledb CASCADE;
CREATE EXTENSION IF NOT EXISTS pg_trgm;        -- For text search optimization
CREATE EXTENSION IF NOT EXISTS btree_gin;      -- For composite GIN indexes

-- ============================================================================
-- ENUMS - Type definitions for data consistency
-- ============================================================================

-- Stock availability states
CREATE TYPE stock_status AS ENUM (
    'in_stock',           -- Available for purchase
    'low_stock',          -- Limited quantity (< 10 units typically)
    'out_of_stock',       -- Not available
    'back_ordered',       -- Available but delayed shipping
    'unknown'             -- Could not determine
);

-- Fulfillment method
CREATE TYPE fulfillment_type AS ENUM (
    'fba',                -- Fulfilled by Amazon
    'fbm',                -- Fulfilled by Merchant
    'amazon',             -- Sold and shipped by Amazon
    'unknown'
);

-- Event severity/importance
CREATE TYPE event_severity AS ENUM (
    'low',                -- Minor change, informational
    'medium',             -- Notable change, worth monitoring
    'high',               -- Significant change, potential opportunity
    'critical'            -- Major event, immediate attention
);

-- Event direction for price/BSR movements
CREATE TYPE movement_direction AS ENUM (
    'up',
    'down',
    'stable'
);

-- Opportunity status workflow
CREATE TYPE opportunity_status AS ENUM (
    'new',                -- Just detected, unreviewed
    'reviewing',          -- Under analysis
    'validated',          -- Confirmed as real opportunity
    'acted',              -- Action taken (order placed, etc.)
    'archived',           -- No longer relevant
    'false_positive'      -- Detected but not a real opportunity
);

-- Opportunity type classification
CREATE TYPE opportunity_type AS ENUM (
    'price_drop',         -- Significant price decrease
    'bsr_surge',          -- Rapid BSR improvement
    'stock_out_competitor', -- Competitor out of stock
    'review_spike',       -- Unusual review activity
    'new_entrant',        -- New product in niche
    'demand_surge',       -- Multiple signals indicating demand
    'arbitrage',          -- Price difference opportunity
    'seasonal'            -- Seasonal pattern detected
);

-- Review sentiment classification
CREATE TYPE sentiment_type AS ENUM (
    'very_negative',
    'negative',
    'neutral',
    'positive',
    'very_positive'
);

-- ============================================================================
-- TABLE: asins
-- Purpose: Master catalog of tracked ASINs with static/semi-static data
-- Update frequency: Weekly or on significant change detection
-- ============================================================================

CREATE TABLE asins (
    -- Primary identifier
    asin VARCHAR(10) PRIMARY KEY,  -- Amazon Standard Identification Number

    -- Product identification
    title TEXT NOT NULL,
    brand VARCHAR(255),
    manufacturer VARCHAR(255),
    model_number VARCHAR(100),

    -- Categorization
    category_id BIGINT,                    -- Amazon browse node ID
    category_path TEXT[],                  -- Full category breadcrumb
    subcategory VARCHAR(255),

    -- Product characteristics
    color VARCHAR(100),
    size VARCHAR(100),
    material VARCHAR(100),
    weight_grams INTEGER,
    dimensions_cm JSONB,                   -- {"length": x, "width": y, "height": z}

    -- Listing details
    main_image_url TEXT,
    bullet_points TEXT[],                  -- Feature bullets (up to 5)
    description TEXT,

    -- Seller information
    current_seller_id VARCHAR(50),
    current_seller_name VARCHAR(255),
    is_amazon_choice BOOLEAN DEFAULT FALSE,
    is_best_seller BOOLEAN DEFAULT FALSE,

    -- Tracking metadata
    first_seen_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    is_active BOOLEAN DEFAULT TRUE,        -- Still being tracked
    tracking_priority INTEGER DEFAULT 5,   -- 1-10, higher = more frequent refresh

    -- Data quality
    data_quality_score DECIMAL(3,2),       -- 0.00-1.00 completeness score
    last_full_scrape_at TIMESTAMPTZ,

    -- Soft delete support
    deleted_at TIMESTAMPTZ
);

-- Indexes for asins table
CREATE INDEX idx_asins_brand ON asins(brand) WHERE deleted_at IS NULL;
CREATE INDEX idx_asins_category ON asins(category_id) WHERE deleted_at IS NULL;
CREATE INDEX idx_asins_active ON asins(is_active) WHERE deleted_at IS NULL;
CREATE INDEX idx_asins_priority ON asins(tracking_priority DESC) WHERE is_active = TRUE;
CREATE INDEX idx_asins_title_trgm ON asins USING gin(title gin_trgm_ops);
CREATE INDEX idx_asins_updated ON asins(last_updated_at);

-- ============================================================================
-- TABLE: asin_snapshots (TimescaleDB Hypertable)
-- Purpose: Time-series data for price, BSR, stock, ratings
-- Update frequency: Every 24-48 hours per ASIN
-- Retention: 90 days detailed, then compressed to daily aggregates
-- ============================================================================

CREATE TABLE asin_snapshots (
    -- Composite primary key for hypertable
    snapshot_id BIGSERIAL,
    asin VARCHAR(10) NOT NULL,
    captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Pricing data
    price_current DECIMAL(10,2),           -- Current listing price
    price_original DECIMAL(10,2),          -- Original/list price (for discount calc)
    price_lowest_new DECIMAL(10,2),        -- Lowest new price from other sellers
    price_lowest_used DECIMAL(10,2),       -- Lowest used price
    price_currency VARCHAR(3) DEFAULT 'USD',
    coupon_discount_percent DECIMAL(5,2),  -- Active coupon if any
    coupon_discount_amount DECIMAL(10,2),
    deal_type VARCHAR(50),                 -- Lightning Deal, Deal of the Day, etc.

    -- Sales rank (BSR)
    bsr_primary INTEGER,                   -- Main category BSR
    bsr_category_name VARCHAR(255),        -- Category name for BSR
    bsr_subcategory INTEGER,               -- Subcategory BSR
    bsr_subcategory_name VARCHAR(255),

    -- Availability
    stock_status stock_status NOT NULL DEFAULT 'unknown',
    stock_quantity INTEGER,                -- Estimated if available
    fulfillment fulfillment_type DEFAULT 'unknown',
    seller_count INTEGER,                  -- Number of sellers

    -- Ratings and reviews (current totals)
    rating_average DECIMAL(2,1),           -- 1.0-5.0
    rating_count INTEGER,                  -- Total ratings
    review_count INTEGER,                  -- Total reviews (subset of ratings)

    -- Rating distribution (optional detailed capture)
    rating_5_star_percent DECIMAL(5,2),
    rating_4_star_percent DECIMAL(5,2),
    rating_3_star_percent DECIMAL(5,2),
    rating_2_star_percent DECIMAL(5,2),
    rating_1_star_percent DECIMAL(5,2),

    -- Computed deltas (vs previous snapshot)
    price_delta DECIMAL(10,2),             -- Price change
    price_delta_percent DECIMAL(5,2),      -- Price change %
    bsr_delta INTEGER,                     -- BSR change
    bsr_delta_percent DECIMAL(5,2),        -- BSR change %
    review_count_delta INTEGER,            -- New reviews since last

    -- Scraping metadata
    scrape_session_id UUID,
    scrape_duration_ms INTEGER,
    data_source VARCHAR(50),               -- 'keepa', 'direct', 'sp-api', etc.

    -- Constraints
    CONSTRAINT pk_asin_snapshots PRIMARY KEY (asin, captured_at)
);

-- Convert to TimescaleDB hypertable
-- Chunk interval: 1 day (optimized for 24-48h refresh of 10k ASINs = ~10k rows/day)
SELECT create_hypertable(
    'asin_snapshots',
    'captured_at',
    chunk_time_interval => INTERVAL '1 day',
    if_not_exists => TRUE
);

-- Indexes optimized for common query patterns
-- 1. Get latest snapshot for an ASIN
CREATE INDEX idx_snapshots_asin_time ON asin_snapshots(asin, captured_at DESC);

-- 2. Find significant price changes
CREATE INDEX idx_snapshots_price_delta ON asin_snapshots(price_delta_percent)
    WHERE price_delta_percent IS NOT NULL AND ABS(price_delta_percent) > 5;

-- 3. Find BSR movers
CREATE INDEX idx_snapshots_bsr_delta ON asin_snapshots(bsr_delta_percent)
    WHERE bsr_delta_percent IS NOT NULL AND ABS(bsr_delta_percent) > 10;

-- 4. Stock status queries
CREATE INDEX idx_snapshots_stock ON asin_snapshots(stock_status, captured_at DESC);

-- 5. Time-based aggregations
CREATE INDEX idx_snapshots_time ON asin_snapshots(captured_at DESC);

-- ============================================================================
-- TABLE: price_events
-- Purpose: Captured significant price changes (>5% threshold)
-- Populated by: Trigger or ETL process comparing snapshots
-- ============================================================================

CREATE TABLE price_events (
    event_id BIGSERIAL PRIMARY KEY,
    asin VARCHAR(10) NOT NULL REFERENCES asins(asin),
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Price change details
    price_before DECIMAL(10,2) NOT NULL,
    price_after DECIMAL(10,2) NOT NULL,
    price_change DECIMAL(10,2) NOT NULL,
    price_change_percent DECIMAL(5,2) NOT NULL,
    direction movement_direction NOT NULL,

    -- Context
    is_deal BOOLEAN DEFAULT FALSE,         -- Part of a deal/promotion
    deal_type VARCHAR(50),
    is_coupon BOOLEAN DEFAULT FALSE,

    -- Classification
    severity event_severity NOT NULL DEFAULT 'medium',

    -- Reference to snapshots
    snapshot_before_id BIGINT,
    snapshot_after_id BIGINT,
    snapshot_before_at TIMESTAMPTZ,
    snapshot_after_at TIMESTAMPTZ,

    -- Processing status
    processed_at TIMESTAMPTZ,
    opportunity_generated BOOLEAN DEFAULT FALSE,

    -- Metadata
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for price_events
CREATE INDEX idx_price_events_asin ON price_events(asin, detected_at DESC);
CREATE INDEX idx_price_events_time ON price_events(detected_at DESC);
CREATE INDEX idx_price_events_severity ON price_events(severity) WHERE severity IN ('high', 'critical');
CREATE INDEX idx_price_events_unprocessed ON price_events(detected_at) WHERE processed_at IS NULL;
CREATE INDEX idx_price_events_direction ON price_events(direction, price_change_percent);

-- ============================================================================
-- TABLE: bsr_events
-- Purpose: Captured significant BSR movements
-- Threshold: >20% change or absolute change > 10,000 positions
-- ============================================================================

CREATE TABLE bsr_events (
    event_id BIGSERIAL PRIMARY KEY,
    asin VARCHAR(10) NOT NULL REFERENCES asins(asin),
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- BSR change details
    bsr_before INTEGER NOT NULL,
    bsr_after INTEGER NOT NULL,
    bsr_change INTEGER NOT NULL,           -- Positive = worsening, Negative = improving
    bsr_change_percent DECIMAL(5,2) NOT NULL,
    direction movement_direction NOT NULL, -- 'up' = improving (lower BSR), 'down' = worsening
    category_name VARCHAR(255),

    -- Velocity metrics
    change_velocity DECIMAL(10,2),         -- Positions per hour
    is_sustained BOOLEAN,                  -- Change held for multiple snapshots

    -- Classification
    severity event_severity NOT NULL DEFAULT 'medium',

    -- Potential causes (populated by analysis)
    likely_cause VARCHAR(100),             -- 'price_drop', 'promotion', 'seasonal', 'viral', etc.

    -- Reference snapshots
    snapshot_before_at TIMESTAMPTZ,
    snapshot_after_at TIMESTAMPTZ,

    -- Processing
    processed_at TIMESTAMPTZ,
    opportunity_generated BOOLEAN DEFAULT FALSE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for bsr_events
CREATE INDEX idx_bsr_events_asin ON bsr_events(asin, detected_at DESC);
CREATE INDEX idx_bsr_events_time ON bsr_events(detected_at DESC);
CREATE INDEX idx_bsr_events_severity ON bsr_events(severity) WHERE severity IN ('high', 'critical');
CREATE INDEX idx_bsr_events_improving ON bsr_events(direction, bsr_change_percent) WHERE direction = 'up';

-- ============================================================================
-- TABLE: stock_events
-- Purpose: Stock status transitions (in->out, out->in, etc.)
-- Critical for competitor monitoring and demand signals
-- ============================================================================

CREATE TABLE stock_events (
    event_id BIGSERIAL PRIMARY KEY,
    asin VARCHAR(10) NOT NULL REFERENCES asins(asin),
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Stock transition
    status_before stock_status NOT NULL,
    status_after stock_status NOT NULL,
    quantity_before INTEGER,
    quantity_after INTEGER,

    -- Classification
    event_type VARCHAR(50) NOT NULL,       -- 'stockout', 'restock', 'low_stock_alert'
    severity event_severity NOT NULL DEFAULT 'medium',

    -- Duration tracking (for stockouts)
    stockout_started_at TIMESTAMPTZ,       -- When stockout began (if applicable)
    stockout_duration_hours INTEGER,       -- How long it was out

    -- Context
    seller_id VARCHAR(50),
    seller_name VARCHAR(255),
    is_primary_seller BOOLEAN DEFAULT TRUE,

    -- Reference
    snapshot_before_at TIMESTAMPTZ,
    snapshot_after_at TIMESTAMPTZ,

    -- Processing
    processed_at TIMESTAMPTZ,
    opportunity_generated BOOLEAN DEFAULT FALSE,

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for stock_events
CREATE INDEX idx_stock_events_asin ON stock_events(asin, detected_at DESC);
CREATE INDEX idx_stock_events_type ON stock_events(event_type, detected_at DESC);
CREATE INDEX idx_stock_events_stockouts ON stock_events(detected_at DESC)
    WHERE event_type = 'stockout';

-- ============================================================================
-- TABLE: reviews
-- Purpose: Individual review storage for NLP analysis
-- Update frequency: Incremental capture of new reviews
-- ============================================================================

CREATE TABLE reviews (
    review_id VARCHAR(50) PRIMARY KEY,     -- Amazon's review ID (R...)
    asin VARCHAR(10) NOT NULL REFERENCES asins(asin),

    -- Review content
    title TEXT,
    body TEXT,
    rating DECIMAL(2,1) NOT NULL,          -- 1.0-5.0

    -- Author info
    author_id VARCHAR(50),
    author_name VARCHAR(255),
    author_is_vine BOOLEAN DEFAULT FALSE,  -- Vine Voice reviewer

    -- Metadata
    review_date DATE,
    is_verified_purchase BOOLEAN DEFAULT FALSE,
    helpful_votes INTEGER DEFAULT 0,
    total_votes INTEGER DEFAULT 0,

    -- Media
    has_images BOOLEAN DEFAULT FALSE,
    has_video BOOLEAN DEFAULT FALSE,
    image_count INTEGER DEFAULT 0,

    -- Variant info
    variant_attributes JSONB,              -- {"color": "black", "size": "large"}

    -- Processing status
    captured_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    analyzed_at TIMESTAMPTZ,               -- When NLP analysis completed

    -- Deduplication
    content_hash VARCHAR(64),              -- SHA256 of title+body for dedup

    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for reviews
CREATE INDEX idx_reviews_asin ON reviews(asin, review_date DESC);
CREATE INDEX idx_reviews_rating ON reviews(asin, rating);
CREATE INDEX idx_reviews_verified ON reviews(asin, is_verified_purchase) WHERE is_verified_purchase = TRUE;
CREATE INDEX idx_reviews_unanalyzed ON reviews(captured_at) WHERE analyzed_at IS NULL;
CREATE INDEX idx_reviews_date ON reviews(review_date DESC);
CREATE INDEX idx_reviews_helpful ON reviews(helpful_votes DESC) WHERE helpful_votes > 0;
CREATE INDEX idx_reviews_content_trgm ON reviews USING gin(body gin_trgm_ops);

-- ============================================================================
-- TABLE: review_analysis
-- Purpose: NLP analysis results for reviews
-- Populated by: Python NLP pipeline (sentiment, keywords, topics)
-- ============================================================================

CREATE TABLE review_analysis (
    analysis_id BIGSERIAL PRIMARY KEY,
    review_id VARCHAR(50) NOT NULL REFERENCES reviews(review_id),
    asin VARCHAR(10) NOT NULL,             -- Denormalized for efficient queries

    -- Sentiment analysis
    sentiment sentiment_type NOT NULL,
    sentiment_score DECIMAL(4,3),          -- -1.000 to +1.000
    sentiment_confidence DECIMAL(3,2),     -- 0.00-1.00

    -- Emotion detection
    emotions JSONB,                        -- {"joy": 0.8, "anger": 0.1, ...}
    primary_emotion VARCHAR(50),

    -- Keyword extraction
    keywords TEXT[],                       -- Extracted significant terms
    key_phrases TEXT[],                    -- Multi-word phrases

    -- Topic/aspect classification
    topics TEXT[],                         -- Detected topics
    aspects JSONB,                         -- {"durability": "positive", "price": "negative"}

    -- Problem/complaint detection
    is_complaint BOOLEAN DEFAULT FALSE,
    complaint_categories TEXT[],           -- ['quality', 'shipping', 'fit', etc.]
    complaint_severity event_severity,

    -- Feature mentions
    mentioned_features TEXT[],
    feature_sentiments JSONB,              -- {"magnetic mount": "positive", "suction": "negative"}

    -- Competitor mentions
    mentions_competitor BOOLEAN DEFAULT FALSE,
    competitor_asins TEXT[],
    competitor_comparison_sentiment sentiment_type,

    -- Summary generation
    summary TEXT,                          -- AI-generated one-line summary

    -- Model metadata
    model_version VARCHAR(50),             -- NLP model version used
    analyzed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processing_time_ms INTEGER,

    CONSTRAINT unique_review_analysis UNIQUE (review_id)
);

-- Indexes for review_analysis
CREATE INDEX idx_review_analysis_asin ON review_analysis(asin);
CREATE INDEX idx_review_analysis_sentiment ON review_analysis(asin, sentiment);
CREATE INDEX idx_review_analysis_complaints ON review_analysis(asin) WHERE is_complaint = TRUE;
CREATE INDEX idx_review_analysis_keywords ON review_analysis USING gin(keywords);
CREATE INDEX idx_review_analysis_topics ON review_analysis USING gin(topics);

-- ============================================================================
-- TABLE: opportunities
-- Purpose: Scored opportunities detected by the analysis engine
-- Workflow: new -> reviewing -> validated -> acted -> archived
-- ============================================================================

CREATE TABLE opportunities (
    opportunity_id BIGSERIAL PRIMARY KEY,

    -- Identification
    asin VARCHAR(10) NOT NULL REFERENCES asins(asin),
    opportunity_type opportunity_type NOT NULL,

    -- Timing
    detected_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ,                -- When opportunity likely expires

    -- Scoring
    score_total DECIMAL(5,2) NOT NULL,     -- 0-100 overall score
    score_breakdown JSONB NOT NULL,        -- Detailed scoring factors
    /* Example score_breakdown:
    {
        "price_attractiveness": 25,
        "bsr_momentum": 20,
        "market_gap": 15,
        "review_sentiment": 10,
        "competition_weakness": 20,
        "confidence": 0.85
    }
    */
    confidence DECIMAL(3,2),               -- 0.00-1.00 confidence level

    -- Context data
    trigger_event_type VARCHAR(50),        -- What triggered detection
    trigger_event_id BIGINT,               -- Reference to specific event
    supporting_data JSONB,                 -- Additional context
    /* Example supporting_data:
    {
        "price_before": 29.99,
        "price_after": 19.99,
        "bsr_trend_7d": -15.2,
        "competitor_stockouts": 2,
        "review_velocity": 3.5
    }
    */

    -- Analysis
    ai_summary TEXT,                       -- AI-generated opportunity summary
    risk_factors TEXT[],                   -- Identified risks
    action_recommendations TEXT[],         -- Suggested actions

    -- Workflow status
    status opportunity_status NOT NULL DEFAULT 'new',
    status_changed_at TIMESTAMPTZ DEFAULT NOW(),
    reviewed_by VARCHAR(100),
    review_notes TEXT,

    -- Action tracking
    action_taken TEXT,
    action_taken_at TIMESTAMPTZ,
    action_result TEXT,
    roi_actual DECIMAL(10,2),              -- Actual ROI if tracked

    -- Related opportunities
    related_opportunity_ids BIGINT[],
    superseded_by_id BIGINT,               -- If replaced by newer opportunity

    -- Metadata
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Indexes for opportunities
CREATE INDEX idx_opportunities_asin ON opportunities(asin, detected_at DESC);
CREATE INDEX idx_opportunities_status ON opportunities(status, score_total DESC);
CREATE INDEX idx_opportunities_type ON opportunities(opportunity_type, detected_at DESC);
CREATE INDEX idx_opportunities_score ON opportunities(score_total DESC) WHERE status = 'new';
CREATE INDEX idx_opportunities_active ON opportunities(detected_at DESC)
    WHERE status IN ('new', 'reviewing', 'validated');
CREATE INDEX idx_opportunities_expiring ON opportunities(expires_at)
    WHERE expires_at IS NOT NULL AND status = 'new';

-- ============================================================================
-- MATERIALIZED VIEWS - Pre-computed aggregations
-- ============================================================================

-- Latest snapshot for each ASIN (critical for dashboard and joins)
CREATE MATERIALIZED VIEW mv_latest_snapshots AS
SELECT DISTINCT ON (asin)
    asin,
    captured_at,
    price_current,
    price_original,
    bsr_primary,
    bsr_category_name,
    stock_status,
    rating_average,
    review_count,
    price_delta_percent,
    bsr_delta_percent
FROM asin_snapshots
ORDER BY asin, captured_at DESC;

CREATE UNIQUE INDEX idx_mv_latest_snapshots_asin ON mv_latest_snapshots(asin);
CREATE INDEX idx_mv_latest_snapshots_bsr ON mv_latest_snapshots(bsr_primary);
CREATE INDEX idx_mv_latest_snapshots_price ON mv_latest_snapshots(price_current);

-- 7-day aggregations per ASIN
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
    -- Price volatility
    (MAX(price_current) - MIN(price_current)) / NULLIF(AVG(price_current), 0) * 100 as price_volatility_pct,
    -- BSR trend (simple linear regression slope)
    REGR_SLOPE(bsr_primary, EXTRACT(EPOCH FROM captured_at)) as bsr_trend,
    SUM(CASE WHEN stock_status = 'out_of_stock' THEN 1 ELSE 0 END) as stockout_count,
    MAX(captured_at) as last_snapshot_at
FROM asin_snapshots
WHERE captured_at >= NOW() - INTERVAL '30 days'
GROUP BY asin;

CREATE UNIQUE INDEX idx_mv_stats_30d_asin ON mv_asin_stats_30d(asin);

-- Review sentiment aggregation by ASIN
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
-- FUNCTIONS - Delta detection and event generation
-- ============================================================================

-- Function to calculate deltas when inserting a new snapshot
CREATE OR REPLACE FUNCTION calculate_snapshot_deltas()
RETURNS TRIGGER AS $$
DECLARE
    prev_snapshot RECORD;
BEGIN
    -- Get the most recent previous snapshot for this ASIN
    SELECT price_current, bsr_primary, review_count
    INTO prev_snapshot
    FROM asin_snapshots
    WHERE asin = NEW.asin
      AND captured_at < NEW.captured_at
    ORDER BY captured_at DESC
    LIMIT 1;

    -- Calculate deltas if previous snapshot exists
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

-- Function to auto-generate price events on significant changes
CREATE OR REPLACE FUNCTION generate_price_events()
RETURNS TRIGGER AS $$
DECLARE
    prev_snapshot RECORD;
    v_severity event_severity;
    v_direction movement_direction;
BEGIN
    -- Only process if we have a significant price delta
    IF NEW.price_delta_percent IS NULL OR ABS(NEW.price_delta_percent) < 5 THEN
        RETURN NEW;
    END IF;

    -- Get previous snapshot for reference
    SELECT captured_at, price_current
    INTO prev_snapshot
    FROM asin_snapshots
    WHERE asin = NEW.asin
      AND captured_at < NEW.captured_at
    ORDER BY captured_at DESC
    LIMIT 1;

    -- Determine severity
    IF ABS(NEW.price_delta_percent) >= 25 THEN
        v_severity := 'critical';
    ELSIF ABS(NEW.price_delta_percent) >= 15 THEN
        v_severity := 'high';
    ELSIF ABS(NEW.price_delta_percent) >= 10 THEN
        v_severity := 'medium';
    ELSE
        v_severity := 'low';
    END IF;

    -- Determine direction
    IF NEW.price_delta < 0 THEN
        v_direction := 'down';
    ELSIF NEW.price_delta > 0 THEN
        v_direction := 'up';
    ELSE
        v_direction := 'stable';
    END IF;

    -- Insert price event
    INSERT INTO price_events (
        asin,
        price_before,
        price_after,
        price_change,
        price_change_percent,
        direction,
        severity,
        snapshot_before_at,
        snapshot_after_at
    ) VALUES (
        NEW.asin,
        prev_snapshot.price_current,
        NEW.price_current,
        NEW.price_delta,
        NEW.price_delta_percent,
        v_direction,
        v_severity,
        prev_snapshot.captured_at,
        NEW.captured_at
    );

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_generate_price_events
    AFTER INSERT ON asin_snapshots
    FOR EACH ROW
    EXECUTE FUNCTION generate_price_events();

-- Similar function for BSR events
CREATE OR REPLACE FUNCTION generate_bsr_events()
RETURNS TRIGGER AS $$
DECLARE
    prev_snapshot RECORD;
    v_severity event_severity;
    v_direction movement_direction;
BEGIN
    -- Only process significant BSR changes (>20% or >10000 positions)
    IF NEW.bsr_delta IS NULL OR
       (ABS(NEW.bsr_delta_percent) < 20 AND ABS(NEW.bsr_delta) < 10000) THEN
        RETURN NEW;
    END IF;

    -- Get previous snapshot
    SELECT captured_at, bsr_primary
    INTO prev_snapshot
    FROM asin_snapshots
    WHERE asin = NEW.asin
      AND captured_at < NEW.captured_at
    ORDER BY captured_at DESC
    LIMIT 1;

    -- Determine severity (BSR improving is more interesting)
    IF NEW.bsr_delta < 0 THEN  -- BSR improved (lower is better)
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
        v_severity := 'low';  -- BSR worsening is less critical
    END IF;

    INSERT INTO bsr_events (
        asin,
        bsr_before,
        bsr_after,
        bsr_change,
        bsr_change_percent,
        direction,
        category_name,
        severity,
        snapshot_before_at,
        snapshot_after_at
    ) VALUES (
        NEW.asin,
        prev_snapshot.bsr_primary,
        NEW.bsr_primary,
        NEW.bsr_delta,
        NEW.bsr_delta_percent,
        v_direction,
        NEW.bsr_category_name,
        v_severity,
        prev_snapshot.captured_at,
        NEW.captured_at
    );

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_generate_bsr_events
    AFTER INSERT ON asin_snapshots
    FOR EACH ROW
    EXECUTE FUNCTION generate_bsr_events();

-- Function to generate stock events
CREATE OR REPLACE FUNCTION generate_stock_events()
RETURNS TRIGGER AS $$
DECLARE
    prev_snapshot RECORD;
    v_event_type VARCHAR(50);
    v_severity event_severity;
BEGIN
    -- Get previous snapshot
    SELECT captured_at, stock_status, stock_quantity
    INTO prev_snapshot
    FROM asin_snapshots
    WHERE asin = NEW.asin
      AND captured_at < NEW.captured_at
    ORDER BY captured_at DESC
    LIMIT 1;

    -- No previous snapshot, skip
    IF NOT FOUND THEN
        RETURN NEW;
    END IF;

    -- No status change, skip
    IF prev_snapshot.stock_status = NEW.stock_status THEN
        RETURN NEW;
    END IF;

    -- Determine event type and severity
    IF prev_snapshot.stock_status IN ('in_stock', 'low_stock') AND NEW.stock_status = 'out_of_stock' THEN
        v_event_type := 'stockout';
        v_severity := 'high';
    ELSIF prev_snapshot.stock_status = 'out_of_stock' AND NEW.stock_status IN ('in_stock', 'low_stock') THEN
        v_event_type := 'restock';
        v_severity := 'medium';
    ELSIF NEW.stock_status = 'low_stock' THEN
        v_event_type := 'low_stock_alert';
        v_severity := 'low';
    ELSE
        v_event_type := 'status_change';
        v_severity := 'low';
    END IF;

    INSERT INTO stock_events (
        asin,
        status_before,
        status_after,
        quantity_before,
        quantity_after,
        event_type,
        severity,
        snapshot_before_at,
        snapshot_after_at
    ) VALUES (
        NEW.asin,
        prev_snapshot.stock_status,
        NEW.stock_status,
        prev_snapshot.stock_quantity,
        NEW.stock_quantity,
        v_event_type,
        v_severity,
        prev_snapshot.captured_at,
        NEW.captured_at
    );

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_generate_stock_events
    AFTER INSERT ON asin_snapshots
    FOR EACH ROW
    EXECUTE FUNCTION generate_stock_events();

-- ============================================================================
-- CONTINUOUS AGGREGATES (TimescaleDB feature)
-- Real-time materialized views that auto-update
-- ============================================================================

-- Daily price statistics (auto-refreshes)
CREATE MATERIALIZED VIEW cagg_daily_price_stats
WITH (timescaledb.continuous) AS
SELECT
    asin,
    time_bucket('1 day', captured_at) AS day,
    MIN(price_current) as price_min,
    MAX(price_current) as price_max,
    AVG(price_current) as price_avg,
    FIRST(price_current, captured_at) as price_open,
    LAST(price_current, captured_at) as price_close,
    COUNT(*) as snapshot_count
FROM asin_snapshots
GROUP BY asin, time_bucket('1 day', captured_at)
WITH NO DATA;

-- Refresh policy: every hour, refresh last 3 days
SELECT add_continuous_aggregate_policy('cagg_daily_price_stats',
    start_offset => INTERVAL '3 days',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour'
);

-- Daily BSR statistics
CREATE MATERIALIZED VIEW cagg_daily_bsr_stats
WITH (timescaledb.continuous) AS
SELECT
    asin,
    time_bucket('1 day', captured_at) AS day,
    MIN(bsr_primary) as bsr_best,
    MAX(bsr_primary) as bsr_worst,
    AVG(bsr_primary) as bsr_avg,
    FIRST(bsr_primary, captured_at) as bsr_open,
    LAST(bsr_primary, captured_at) as bsr_close
FROM asin_snapshots
GROUP BY asin, time_bucket('1 day', captured_at)
WITH NO DATA;

SELECT add_continuous_aggregate_policy('cagg_daily_bsr_stats',
    start_offset => INTERVAL '3 days',
    end_offset => INTERVAL '1 hour',
    schedule_interval => INTERVAL '1 hour'
);

-- ============================================================================
-- DATA RETENTION POLICIES (TimescaleDB)
-- ============================================================================

-- Drop raw chunks older than 90 days (keep aggregates)
SELECT add_retention_policy('asin_snapshots', INTERVAL '90 days');

-- Enable compression for chunks older than 7 days
ALTER TABLE asin_snapshots SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'asin',
    timescaledb.compress_orderby = 'captured_at DESC'
);

SELECT add_compression_policy('asin_snapshots', INTERVAL '7 days');

-- ============================================================================
-- HELPER VIEWS - Commonly used queries
-- ============================================================================

-- Active opportunities dashboard view
CREATE VIEW v_active_opportunities AS
SELECT
    o.*,
    a.title as product_title,
    a.brand,
    ls.price_current,
    ls.bsr_primary,
    ls.stock_status
FROM opportunities o
JOIN asins a ON o.asin = a.asin
LEFT JOIN mv_latest_snapshots ls ON o.asin = ls.asin
WHERE o.status IN ('new', 'reviewing', 'validated')
ORDER BY o.score_total DESC;

-- ASIN dashboard view with all metrics
CREATE VIEW v_asin_dashboard AS
SELECT
    a.asin,
    a.title,
    a.brand,
    a.is_amazon_choice,
    a.is_best_seller,
    ls.price_current,
    ls.price_original,
    ls.bsr_primary,
    ls.stock_status,
    ls.rating_average,
    ls.review_count,
    s7.price_min as price_7d_min,
    s7.price_max as price_7d_max,
    s7.bsr_best as bsr_7d_best,
    s7.stockout_count as stockouts_7d,
    s30.price_volatility_pct as volatility_30d,
    s30.bsr_trend as bsr_trend_30d,
    rs.avg_sentiment,
    rs.positive_ratio as review_positive_pct,
    rs.complaint_count as complaints_90d
FROM asins a
LEFT JOIN mv_latest_snapshots ls ON a.asin = ls.asin
LEFT JOIN mv_asin_stats_7d s7 ON a.asin = s7.asin
LEFT JOIN mv_asin_stats_30d s30 ON a.asin = s30.asin
LEFT JOIN mv_review_sentiment rs ON a.asin = rs.asin
WHERE a.is_active = TRUE AND a.deleted_at IS NULL;

-- Recent events summary
CREATE VIEW v_recent_events AS
SELECT
    'price' as event_type,
    asin,
    detected_at,
    severity::TEXT,
    CONCAT(direction::TEXT, ' ', ABS(price_change_percent)::TEXT, '%') as description
FROM price_events
WHERE detected_at >= NOW() - INTERVAL '7 days'
UNION ALL
SELECT
    'bsr' as event_type,
    asin,
    detected_at,
    severity::TEXT,
    CONCAT(direction::TEXT, ' ', ABS(bsr_change_percent)::TEXT, '%') as description
FROM bsr_events
WHERE detected_at >= NOW() - INTERVAL '7 days'
UNION ALL
SELECT
    'stock' as event_type,
    asin,
    detected_at,
    severity::TEXT,
    event_type as description
FROM stock_events
WHERE detected_at >= NOW() - INTERVAL '7 days'
ORDER BY detected_at DESC;

-- ============================================================================
-- PERMISSIONS (adjust as needed for your setup)
-- ============================================================================

-- Create application role
-- CREATE ROLE smartacus_app LOGIN PASSWORD 'your_secure_password';
-- GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO smartacus_app;
-- GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO smartacus_app;
-- GRANT SELECT ON ALL TABLES IN SCHEMA timescaledb_information TO smartacus_app;

-- Create read-only analytics role
-- CREATE ROLE smartacus_readonly LOGIN PASSWORD 'your_secure_password';
-- GRANT SELECT ON ALL TABLES IN SCHEMA public TO smartacus_readonly;

-- ============================================================================
-- INITIAL DATA LOAD OPTIMIZATION
-- For bulk loading, temporarily disable triggers
-- ============================================================================

-- To disable triggers for bulk load:
-- ALTER TABLE asin_snapshots DISABLE TRIGGER trg_calculate_deltas;
-- ALTER TABLE asin_snapshots DISABLE TRIGGER trg_generate_price_events;
-- ALTER TABLE asin_snapshots DISABLE TRIGGER trg_generate_bsr_events;
-- ALTER TABLE asin_snapshots DISABLE TRIGGER trg_generate_stock_events;

-- After bulk load, re-enable:
-- ALTER TABLE asin_snapshots ENABLE TRIGGER trg_calculate_deltas;
-- ALTER TABLE asin_snapshots ENABLE TRIGGER trg_generate_price_events;
-- ALTER TABLE asin_snapshots ENABLE TRIGGER trg_generate_bsr_events;
-- ALTER TABLE asin_snapshots ENABLE TRIGGER trg_generate_stock_events;

-- ============================================================================
-- MAINTENANCE PROCEDURES
-- ============================================================================

-- Procedure to refresh all materialized views
CREATE OR REPLACE PROCEDURE refresh_all_materialized_views()
LANGUAGE plpgsql AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_latest_snapshots;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_asin_stats_7d;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_asin_stats_30d;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mv_review_sentiment;
END;
$$;

-- Schedule: CALL refresh_all_materialized_views(); via pg_cron or external scheduler

-- Procedure to clean up old events (beyond retention)
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
-- COMMENTS FOR DOCUMENTATION
-- ============================================================================

COMMENT ON TABLE asins IS 'Master catalog of tracked Amazon ASINs with static/semi-static product data';
COMMENT ON TABLE asin_snapshots IS 'Time-series snapshots of ASIN metrics (price, BSR, stock, ratings) - TimescaleDB hypertable';
COMMENT ON TABLE price_events IS 'Significant price change events (>5% threshold) for opportunity detection';
COMMENT ON TABLE bsr_events IS 'Significant BSR movement events for demand signal detection';
COMMENT ON TABLE stock_events IS 'Stock availability transitions for competitor monitoring';
COMMENT ON TABLE reviews IS 'Individual Amazon reviews for NLP analysis';
COMMENT ON TABLE review_analysis IS 'NLP analysis results (sentiment, keywords, complaints) for reviews';
COMMENT ON TABLE opportunities IS 'Scored opportunities detected by the analysis engine';

COMMENT ON MATERIALIZED VIEW mv_latest_snapshots IS 'Latest snapshot per ASIN - refresh hourly';
COMMENT ON MATERIALIZED VIEW mv_asin_stats_7d IS '7-day aggregated stats per ASIN - refresh hourly';
COMMENT ON MATERIALIZED VIEW mv_asin_stats_30d IS '30-day aggregated stats per ASIN - refresh daily';
COMMENT ON MATERIALIZED VIEW mv_review_sentiment IS '90-day review sentiment aggregation - refresh daily';
