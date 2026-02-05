-- ============================================================================
-- SMARTACUS - Common Query Patterns
-- Optimized queries for typical use cases
-- ============================================================================

-- ============================================================================
-- 1. DELTA DETECTION QUERIES
-- Compare snapshot N vs N-1 for any ASIN
-- ============================================================================

-- Get latest snapshot with delta vs previous for a specific ASIN
SELECT
    s.asin,
    s.captured_at,
    s.price_current,
    s.price_delta,
    s.price_delta_percent,
    s.bsr_primary,
    s.bsr_delta,
    s.bsr_delta_percent,
    s.stock_status,
    s.review_count,
    s.review_count_delta
FROM asin_snapshots s
WHERE s.asin = 'B0XXXXXXXXX'  -- Replace with actual ASIN
ORDER BY s.captured_at DESC
LIMIT 1;

-- Compare current vs previous snapshot for ALL active ASINs
WITH ranked_snapshots AS (
    SELECT
        s.*,
        ROW_NUMBER() OVER (PARTITION BY s.asin ORDER BY s.captured_at DESC) as rn
    FROM asin_snapshots s
    JOIN asins a ON s.asin = a.asin
    WHERE a.is_active = TRUE
      AND s.captured_at >= NOW() - INTERVAL '7 days'
)
SELECT
    curr.asin,
    curr.captured_at as current_snapshot,
    prev.captured_at as previous_snapshot,
    curr.price_current as current_price,
    prev.price_current as previous_price,
    curr.price_delta_percent,
    curr.bsr_primary as current_bsr,
    prev.bsr_primary as previous_bsr,
    curr.bsr_delta_percent,
    curr.stock_status as current_stock,
    prev.stock_status as previous_stock
FROM ranked_snapshots curr
LEFT JOIN ranked_snapshots prev ON curr.asin = prev.asin AND prev.rn = 2
WHERE curr.rn = 1
ORDER BY ABS(COALESCE(curr.price_delta_percent, 0)) DESC;

-- Find ASINs with significant changes in last 24h
SELECT
    s.asin,
    a.title,
    a.brand,
    s.price_delta_percent,
    s.bsr_delta_percent,
    s.stock_status,
    s.captured_at
FROM asin_snapshots s
JOIN asins a ON s.asin = a.asin
WHERE s.captured_at >= NOW() - INTERVAL '24 hours'
  AND (
      ABS(s.price_delta_percent) > 5
      OR ABS(s.bsr_delta_percent) > 20
      OR s.review_count_delta > 5
  )
ORDER BY s.captured_at DESC;

-- ============================================================================
-- 2. TIME AGGREGATION QUERIES
-- 7 days, 30 days, 90 days analysis
-- ============================================================================

-- Price trend analysis (7d, 30d, 90d) for an ASIN
WITH time_windows AS (
    SELECT
        asin,
        -- 7 day stats
        MIN(price_current) FILTER (WHERE captured_at >= NOW() - INTERVAL '7 days') as price_7d_min,
        MAX(price_current) FILTER (WHERE captured_at >= NOW() - INTERVAL '7 days') as price_7d_max,
        AVG(price_current) FILTER (WHERE captured_at >= NOW() - INTERVAL '7 days') as price_7d_avg,
        -- 30 day stats
        MIN(price_current) FILTER (WHERE captured_at >= NOW() - INTERVAL '30 days') as price_30d_min,
        MAX(price_current) FILTER (WHERE captured_at >= NOW() - INTERVAL '30 days') as price_30d_max,
        AVG(price_current) FILTER (WHERE captured_at >= NOW() - INTERVAL '30 days') as price_30d_avg,
        -- 90 day stats
        MIN(price_current) FILTER (WHERE captured_at >= NOW() - INTERVAL '90 days') as price_90d_min,
        MAX(price_current) FILTER (WHERE captured_at >= NOW() - INTERVAL '90 days') as price_90d_max,
        AVG(price_current) FILTER (WHERE captured_at >= NOW() - INTERVAL '90 days') as price_90d_avg
    FROM asin_snapshots
    WHERE asin = 'B0XXXXXXXXX'
    GROUP BY asin
)
SELECT * FROM time_windows;

-- BSR trend with linear regression (is it improving or declining?)
SELECT
    asin,
    COUNT(*) as data_points,
    MIN(bsr_primary) as bsr_best,
    MAX(bsr_primary) as bsr_worst,
    AVG(bsr_primary)::INTEGER as bsr_avg,
    -- Negative slope = improving BSR
    REGR_SLOPE(bsr_primary, EXTRACT(EPOCH FROM captured_at)) * 86400 as bsr_daily_change,
    REGR_R2(bsr_primary, EXTRACT(EPOCH FROM captured_at)) as trend_confidence
FROM asin_snapshots
WHERE asin = 'B0XXXXXXXXX'
  AND captured_at >= NOW() - INTERVAL '30 days'
GROUP BY asin;

-- Weekly aggregations for dashboard
SELECT
    time_bucket('1 week', captured_at) as week,
    asin,
    AVG(price_current) as avg_price,
    MIN(price_current) as min_price,
    MAX(price_current) as max_price,
    AVG(bsr_primary)::INTEGER as avg_bsr,
    MIN(bsr_primary) as best_bsr,
    SUM(CASE WHEN stock_status = 'out_of_stock' THEN 1 ELSE 0 END) as stockout_snapshots
FROM asin_snapshots
WHERE captured_at >= NOW() - INTERVAL '90 days'
GROUP BY week, asin
ORDER BY week DESC, asin;

-- ============================================================================
-- 3. JOIN QUERIES - ASIN + Latest Snapshot
-- ============================================================================

-- Full product view with latest metrics (most common query)
SELECT
    a.asin,
    a.title,
    a.brand,
    a.category_path,
    a.is_amazon_choice,
    a.is_best_seller,
    ls.price_current,
    ls.price_original,
    ROUND((1 - ls.price_current / NULLIF(ls.price_original, 0)) * 100, 1) as discount_pct,
    ls.bsr_primary,
    ls.bsr_category_name,
    ls.stock_status,
    ls.rating_average,
    ls.review_count,
    ls.price_delta_percent as price_change_24h,
    ls.bsr_delta_percent as bsr_change_24h,
    ls.captured_at as last_updated
FROM asins a
JOIN mv_latest_snapshots ls ON a.asin = ls.asin
WHERE a.is_active = TRUE
ORDER BY ls.bsr_primary ASC NULLS LAST
LIMIT 100;

-- Products with best BSR momentum (improving fast)
SELECT
    a.asin,
    a.title,
    a.brand,
    ls.bsr_primary as current_bsr,
    s30.bsr_trend as daily_bsr_change,
    s30.bsr_best as bsr_30d_best,
    ls.price_current,
    ls.review_count
FROM asins a
JOIN mv_latest_snapshots ls ON a.asin = ls.asin
JOIN mv_asin_stats_30d s30 ON a.asin = s30.asin
WHERE a.is_active = TRUE
  AND s30.bsr_trend < 0  -- Negative = improving
ORDER BY s30.bsr_trend ASC
LIMIT 20;

-- Products currently on sale (price below 30-day average)
SELECT
    a.asin,
    a.title,
    ls.price_current,
    s30.price_avg as price_30d_avg,
    ROUND((1 - ls.price_current / s30.price_avg) * 100, 1) as below_avg_pct,
    ls.bsr_primary
FROM asins a
JOIN mv_latest_snapshots ls ON a.asin = ls.asin
JOIN mv_asin_stats_30d s30 ON a.asin = s30.asin
WHERE a.is_active = TRUE
  AND ls.price_current < s30.price_avg * 0.9  -- 10%+ below average
ORDER BY below_avg_pct DESC;

-- ============================================================================
-- 4. EVENT ANALYSIS QUERIES
-- ============================================================================

-- Recent significant events across all tracked ASINs
SELECT * FROM v_recent_events
ORDER BY detected_at DESC
LIMIT 50;

-- Price events with product context
SELECT
    pe.detected_at,
    pe.asin,
    a.title,
    a.brand,
    pe.price_before,
    pe.price_after,
    pe.price_change_percent,
    pe.direction,
    pe.severity,
    pe.is_deal
FROM price_events pe
JOIN asins a ON pe.asin = a.asin
WHERE pe.detected_at >= NOW() - INTERVAL '7 days'
ORDER BY pe.severity DESC, ABS(pe.price_change_percent) DESC;

-- Stockout events (competitor monitoring gold)
SELECT
    se.detected_at,
    se.asin,
    a.title,
    a.brand,
    se.status_before,
    se.status_after,
    se.event_type,
    ls.bsr_primary as current_bsr
FROM stock_events se
JOIN asins a ON se.asin = a.asin
LEFT JOIN mv_latest_snapshots ls ON se.asin = ls.asin
WHERE se.event_type = 'stockout'
  AND se.detected_at >= NOW() - INTERVAL '30 days'
ORDER BY se.detected_at DESC;

-- Correlated events: Price drop followed by BSR improvement
WITH price_drops AS (
    SELECT asin, detected_at as price_drop_at, price_change_percent
    FROM price_events
    WHERE direction = 'down' AND price_change_percent < -10
      AND detected_at >= NOW() - INTERVAL '30 days'
),
bsr_improvements AS (
    SELECT asin, detected_at as bsr_improve_at, bsr_change_percent
    FROM bsr_events
    WHERE direction = 'up' AND bsr_change_percent < -20  -- Negative = improvement
      AND detected_at >= NOW() - INTERVAL '30 days'
)
SELECT
    pd.asin,
    a.title,
    pd.price_drop_at,
    pd.price_change_percent as price_drop_pct,
    bi.bsr_improve_at,
    bi.bsr_change_percent as bsr_improve_pct,
    bi.bsr_improve_at - pd.price_drop_at as time_to_bsr_impact
FROM price_drops pd
JOIN bsr_improvements bi ON pd.asin = bi.asin
    AND bi.bsr_improve_at > pd.price_drop_at
    AND bi.bsr_improve_at < pd.price_drop_at + INTERVAL '7 days'
JOIN asins a ON pd.asin = a.asin
ORDER BY time_to_bsr_impact;

-- ============================================================================
-- 5. OPPORTUNITY QUERIES
-- ============================================================================

-- Active opportunities dashboard
SELECT * FROM v_active_opportunities
ORDER BY score_total DESC
LIMIT 50;

-- Top opportunities by type
SELECT
    opportunity_type,
    COUNT(*) as count,
    AVG(score_total) as avg_score,
    MAX(score_total) as max_score
FROM opportunities
WHERE status IN ('new', 'reviewing', 'validated')
  AND detected_at >= NOW() - INTERVAL '30 days'
GROUP BY opportunity_type
ORDER BY count DESC;

-- Opportunity conversion funnel
SELECT
    status,
    COUNT(*) as count,
    AVG(score_total) as avg_score,
    AVG(EXTRACT(EPOCH FROM (status_changed_at - detected_at))/3600)::INTEGER as avg_hours_in_status
FROM opportunities
WHERE detected_at >= NOW() - INTERVAL '90 days'
GROUP BY status
ORDER BY
    CASE status
        WHEN 'new' THEN 1
        WHEN 'reviewing' THEN 2
        WHEN 'validated' THEN 3
        WHEN 'acted' THEN 4
        WHEN 'archived' THEN 5
        WHEN 'false_positive' THEN 6
    END;

-- ============================================================================
-- 6. REVIEW ANALYSIS QUERIES
-- ============================================================================

-- Review sentiment summary by ASIN
SELECT
    ra.asin,
    a.title,
    COUNT(*) as analyzed_reviews,
    AVG(ra.sentiment_score) as avg_sentiment,
    SUM(CASE WHEN ra.sentiment IN ('positive', 'very_positive') THEN 1 ELSE 0 END) as positive_count,
    SUM(CASE WHEN ra.sentiment IN ('negative', 'very_negative') THEN 1 ELSE 0 END) as negative_count,
    SUM(CASE WHEN ra.is_complaint THEN 1 ELSE 0 END) as complaint_count
FROM review_analysis ra
JOIN asins a ON ra.asin = a.asin
WHERE ra.analyzed_at >= NOW() - INTERVAL '90 days'
GROUP BY ra.asin, a.title
ORDER BY complaint_count DESC;

-- Common complaints across all products
SELECT
    unnest(complaint_categories) as complaint_type,
    COUNT(*) as count
FROM review_analysis
WHERE is_complaint = TRUE
  AND analyzed_at >= NOW() - INTERVAL '90 days'
GROUP BY complaint_type
ORDER BY count DESC
LIMIT 20;

-- Top keywords in recent reviews
SELECT
    unnest(keywords) as keyword,
    COUNT(*) as frequency
FROM review_analysis
WHERE analyzed_at >= NOW() - INTERVAL '30 days'
GROUP BY keyword
HAVING COUNT(*) > 5
ORDER BY frequency DESC
LIMIT 50;

-- Reviews mentioning competitors
SELECT
    r.review_id,
    r.asin,
    a.title,
    r.rating,
    r.body,
    ra.competitor_asins,
    ra.competitor_comparison_sentiment
FROM reviews r
JOIN review_analysis ra ON r.review_id = ra.review_id
JOIN asins a ON r.asin = a.asin
WHERE ra.mentions_competitor = TRUE
  AND r.review_date >= NOW() - INTERVAL '30 days'
ORDER BY r.review_date DESC;

-- ============================================================================
-- 7. MARKET OVERVIEW QUERIES
-- ============================================================================

-- Niche health metrics
SELECT
    COUNT(DISTINCT a.asin) as total_products,
    COUNT(DISTINCT a.asin) FILTER (WHERE ls.stock_status = 'in_stock') as in_stock_count,
    AVG(ls.price_current) as avg_price,
    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY ls.price_current) as median_price,
    AVG(ls.bsr_primary) as avg_bsr,
    AVG(ls.rating_average) as avg_rating,
    AVG(ls.review_count) as avg_reviews
FROM asins a
JOIN mv_latest_snapshots ls ON a.asin = ls.asin
WHERE a.is_active = TRUE;

-- Brand market share (by product count in top 100 BSR)
WITH top_100 AS (
    SELECT a.asin, a.brand, ls.bsr_primary
    FROM asins a
    JOIN mv_latest_snapshots ls ON a.asin = ls.asin
    WHERE a.is_active = TRUE
    ORDER BY ls.bsr_primary ASC NULLS LAST
    LIMIT 100
)
SELECT
    brand,
    COUNT(*) as products_in_top100,
    MIN(bsr_primary) as best_bsr,
    ROUND(COUNT(*)::DECIMAL / 100 * 100, 1) as market_share_pct
FROM top_100
GROUP BY brand
ORDER BY products_in_top100 DESC;

-- Price distribution analysis
SELECT
    CASE
        WHEN ls.price_current < 10 THEN 'Under $10'
        WHEN ls.price_current < 20 THEN '$10-20'
        WHEN ls.price_current < 30 THEN '$20-30'
        WHEN ls.price_current < 50 THEN '$30-50'
        ELSE '$50+'
    END as price_range,
    COUNT(*) as product_count,
    AVG(ls.bsr_primary)::INTEGER as avg_bsr,
    AVG(ls.review_count)::INTEGER as avg_reviews
FROM asins a
JOIN mv_latest_snapshots ls ON a.asin = ls.asin
WHERE a.is_active = TRUE
GROUP BY price_range
ORDER BY MIN(ls.price_current);

-- ============================================================================
-- 8. DATA QUALITY & MONITORING QUERIES
-- ============================================================================

-- ASINs missing recent snapshots (stale data)
SELECT
    a.asin,
    a.title,
    a.tracking_priority,
    ls.captured_at as last_snapshot,
    NOW() - ls.captured_at as time_since_update
FROM asins a
LEFT JOIN mv_latest_snapshots ls ON a.asin = ls.asin
WHERE a.is_active = TRUE
  AND (ls.captured_at IS NULL OR ls.captured_at < NOW() - INTERVAL '48 hours')
ORDER BY a.tracking_priority DESC, ls.captured_at ASC NULLS FIRST;

-- Snapshot volume by day (monitoring scraper health)
SELECT
    time_bucket('1 day', captured_at) as day,
    COUNT(*) as snapshot_count,
    COUNT(DISTINCT asin) as unique_asins
FROM asin_snapshots
WHERE captured_at >= NOW() - INTERVAL '30 days'
GROUP BY day
ORDER BY day DESC;

-- Data quality scores
SELECT
    CASE
        WHEN data_quality_score >= 0.9 THEN 'Excellent (90%+)'
        WHEN data_quality_score >= 0.7 THEN 'Good (70-90%)'
        WHEN data_quality_score >= 0.5 THEN 'Fair (50-70%)'
        ELSE 'Poor (<50%)'
    END as quality_tier,
    COUNT(*) as count
FROM asins
WHERE is_active = TRUE
GROUP BY quality_tier
ORDER BY MIN(data_quality_score) DESC;

-- Hypertable chunk info (TimescaleDB monitoring)
SELECT
    chunk_schema,
    chunk_name,
    range_start,
    range_end,
    is_compressed,
    pg_size_pretty(total_bytes) as chunk_size
FROM timescaledb_information.chunks
WHERE hypertable_name = 'asin_snapshots'
ORDER BY range_start DESC
LIMIT 20;
