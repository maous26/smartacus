-- Migration 012: Category Intelligence for Auto-Discovery
-- V2.1 - Smart Scheduler with Category Auto-Selection

-- =============================================================================
-- CATEGORY REGISTRY: Track all discovered categories
-- =============================================================================
CREATE TABLE IF NOT EXISTS category_registry (
    category_id BIGINT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    path TEXT[],                              -- Breadcrumb: ['Electronics', 'Cell Phones', ...]
    parent_id BIGINT REFERENCES category_registry(category_id),

    -- Discovery metadata
    discovered_at TIMESTAMPTZ DEFAULT NOW(),
    discovered_via VARCHAR(50),               -- 'manual', 'crawl', 'keepa_suggestion'
    amazon_domain VARCHAR(10) DEFAULT 'com',  -- com, fr, de, uk, etc.

    -- Category stats (updated periodically)
    estimated_product_count INTEGER,
    avg_price REAL,
    avg_reviews INTEGER,
    avg_rating REAL,

    -- Tracking config
    is_active BOOLEAN DEFAULT false,          -- Currently being tracked?
    priority INTEGER DEFAULT 5,               -- 1=highest, 10=lowest
    last_scanned_at TIMESTAMPTZ,
    scan_frequency_hours INTEGER DEFAULT 168, -- Default: weekly

    -- Performance metrics (computed from historical runs)
    total_runs INTEGER DEFAULT 0,
    total_opportunities_found INTEGER DEFAULT 0,
    avg_opportunity_score REAL,
    best_opportunity_score INTEGER,
    conversion_rate REAL,                     -- opportunities_found / asins_scanned

    UNIQUE(category_id, amazon_domain)
);

CREATE INDEX idx_category_registry_active ON category_registry(is_active) WHERE is_active = true;
CREATE INDEX idx_category_registry_priority ON category_registry(priority, last_scanned_at);
CREATE INDEX idx_category_registry_domain ON category_registry(amazon_domain);

-- =============================================================================
-- CATEGORY PERFORMANCE: Historical tracking per run
-- =============================================================================
CREATE TABLE IF NOT EXISTS category_performance (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    category_id BIGINT NOT NULL REFERENCES category_registry(category_id),
    run_id UUID REFERENCES pipeline_runs(run_id),

    -- Run metrics
    scanned_at TIMESTAMPTZ DEFAULT NOW(),
    asins_discovered INTEGER DEFAULT 0,
    asins_scored INTEGER DEFAULT 0,
    opportunities_found INTEGER DEFAULT 0,    -- score >= 40
    high_value_opps INTEGER DEFAULT 0,        -- score >= 60

    -- Token consumption
    tokens_used INTEGER DEFAULT 0,
    tokens_per_opportunity REAL,              -- efficiency metric

    -- Value metrics
    total_potential_value REAL DEFAULT 0,     -- sum of risk_adjusted_value
    avg_score REAL,
    max_score INTEGER,

    -- Timing
    duration_seconds REAL,

    -- Errors
    error_count INTEGER DEFAULT 0,
    error_rate REAL
);

CREATE INDEX idx_category_performance_category ON category_performance(category_id, scanned_at DESC);
CREATE INDEX idx_category_performance_run ON category_performance(run_id);

-- =============================================================================
-- TOKEN BUDGET: Track monthly consumption
-- =============================================================================
CREATE TABLE IF NOT EXISTS token_budget (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    month_year VARCHAR(7) NOT NULL,           -- '2026-02'

    -- Budget
    monthly_limit INTEGER NOT NULL,           -- Total tokens available
    tokens_used INTEGER DEFAULT 0,
    tokens_remaining INTEGER GENERATED ALWAYS AS (monthly_limit - tokens_used) STORED,

    -- Allocation
    discovery_allocation_pct INTEGER DEFAULT 20,  -- % for discovering new categories
    scanning_allocation_pct INTEGER DEFAULT 80,   -- % for scanning known categories

    -- Stats
    runs_completed INTEGER DEFAULT 0,
    categories_scanned INTEGER DEFAULT 0,
    opportunities_found INTEGER DEFAULT 0,

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    UNIQUE(month_year)
);

CREATE INDEX idx_token_budget_month ON token_budget(month_year);

-- =============================================================================
-- SCHEDULER CONFIG: Global scheduler settings
-- =============================================================================
CREATE TABLE IF NOT EXISTS scheduler_config (
    key VARCHAR(100) PRIMARY KEY,
    value JSONB NOT NULL,
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    updated_by VARCHAR(100)
);

-- Insert default config
INSERT INTO scheduler_config (key, value) VALUES
    ('enabled', 'true'),
    ('run_interval_hours', '24'),
    ('min_tokens_per_run', '50'),
    ('max_categories_per_run', '5'),
    ('discovery_enabled', 'true'),
    ('discovery_depth', '2'),                 -- How deep to crawl subcategories
    ('priority_weights', '{"recency": 0.3, "performance": 0.4, "potential": 0.3}'),
    ('target_domains', '["com", "fr"]'),
    ('min_category_products', '100'),
    ('max_category_products', '50000')
ON CONFLICT (key) DO NOTHING;

-- =============================================================================
-- SEED CATEGORIES: Initial high-potential categories to explore
-- =============================================================================
INSERT INTO category_registry (category_id, name, path, amazon_domain, discovered_via, priority, is_active) VALUES
    -- Current category
    (7072562011, 'Cell Phone Automobile Cradles', ARRAY['Electronics', 'Cell Phones & Accessories', 'Accessories', 'Car Accessories', 'Car Cradles'], 'fr', 'manual', 1, true),

    -- Related high-potential categories (US market)
    (2407761011, 'Cell Phone Car Cradles & Mounts', ARRAY['Cell Phones & Accessories', 'Accessories', 'Car Accessories'], 'com', 'seed', 3, false),
    (7073956011, 'Cell Phone Stands', ARRAY['Electronics', 'Cell Phones & Accessories', 'Accessories', 'Stands'], 'com', 'seed', 4, false),
    (2407755011, 'Cell Phone Armbands', ARRAY['Cell Phones & Accessories', 'Accessories', 'Armbands'], 'com', 'seed', 5, false),
    (7073960011, 'Tablet Stands', ARRAY['Computers & Accessories', 'Tablet Accessories', 'Stands'], 'com', 'seed', 5, false),

    -- FR market expansion
    (7073956011, 'Supports telephone', ARRAY['High-Tech', 'Telephones', 'Accessoires', 'Supports'], 'fr', 'seed', 3, false)
ON CONFLICT (category_id, amazon_domain) DO NOTHING;

-- =============================================================================
-- HELPER FUNCTIONS
-- =============================================================================

-- Function to get next categories to scan based on priority and budget
CREATE OR REPLACE FUNCTION get_next_scan_categories(
    p_available_tokens INTEGER,
    p_max_categories INTEGER DEFAULT 5
)
RETURNS TABLE (
    category_id BIGINT,
    name VARCHAR(255),
    amazon_domain VARCHAR(10),
    priority INTEGER,
    estimated_tokens INTEGER,
    score REAL
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        cr.category_id,
        cr.name,
        cr.amazon_domain,
        cr.priority,
        COALESCE(
            (SELECT AVG(tokens_used)::INTEGER FROM category_performance cp WHERE cp.category_id = cr.category_id),
            100  -- Default estimate
        ) as estimated_tokens,
        -- Composite score: lower = scan first
        (
            cr.priority * 0.3 +
            COALESCE(EXTRACT(EPOCH FROM (NOW() - cr.last_scanned_at)) / 3600 / 24, 30) * -0.01 +  -- Days since scan (negative = older is better)
            COALESCE(cr.conversion_rate, 0) * -10 +  -- Higher conversion = lower score
            COALESCE(cr.avg_opportunity_score, 0) * -0.1  -- Higher avg score = lower score
        )::REAL as score
    FROM category_registry cr
    WHERE cr.is_active = true
      AND (cr.last_scanned_at IS NULL OR cr.last_scanned_at < NOW() - (cr.scan_frequency_hours || ' hours')::INTERVAL)
    ORDER BY score ASC
    LIMIT p_max_categories;
END;
$$ LANGUAGE plpgsql;

-- Function to update category performance after a run
CREATE OR REPLACE FUNCTION update_category_stats(p_category_id BIGINT)
RETURNS VOID AS $$
BEGIN
    UPDATE category_registry
    SET
        total_runs = (SELECT COUNT(*) FROM category_performance WHERE category_id = p_category_id),
        total_opportunities_found = (SELECT COALESCE(SUM(opportunities_found), 0) FROM category_performance WHERE category_id = p_category_id),
        avg_opportunity_score = (SELECT AVG(avg_score) FROM category_performance WHERE category_id = p_category_id),
        best_opportunity_score = (SELECT MAX(max_score) FROM category_performance WHERE category_id = p_category_id),
        conversion_rate = (
            SELECT CASE WHEN SUM(asins_scored) > 0
                   THEN SUM(opportunities_found)::REAL / SUM(asins_scored)
                   ELSE 0 END
            FROM category_performance WHERE category_id = p_category_id
        )
    WHERE category_id = p_category_id;
END;
$$ LANGUAGE plpgsql;

-- =============================================================================
-- COMMENTS
-- =============================================================================
COMMENT ON TABLE category_registry IS 'Registry of all Amazon categories being tracked or discovered';
COMMENT ON TABLE category_performance IS 'Historical performance metrics per category per run';
COMMENT ON TABLE token_budget IS 'Monthly Keepa token budget tracking';
COMMENT ON TABLE scheduler_config IS 'Global scheduler configuration key-value store';
COMMENT ON FUNCTION get_next_scan_categories IS 'Returns next categories to scan based on priority, recency, and performance';
