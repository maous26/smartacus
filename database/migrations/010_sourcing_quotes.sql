-- Migration 010: Sourcing Quotes table for supplier cost data
-- V2.0 Remediation - Priority 3: Precise Cost Calculation

-- Create sourcing_quotes table (enriched schema)
CREATE TABLE IF NOT EXISTS sourcing_quotes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asin VARCHAR(20) NOT NULL REFERENCES asins(asin) ON DELETE CASCADE,

    -- Supplier info
    supplier_name VARCHAR(255),
    supplier_contact TEXT,                      -- email or contact info

    -- Pricing
    unit_price REAL NOT NULL,                   -- price in specified currency
    currency VARCHAR(10) DEFAULT 'USD',         -- USD, EUR, CNY, etc.
    unit_price_usd REAL,                        -- converted to USD (calculated)
    moq INTEGER,                                -- minimum order quantity
    price_breaks JSONB,                         -- volume discounts: [{"qty": 1000, "price": 4.20}, ...]

    -- Logistics
    lead_time_days INTEGER,                     -- production + shipping time
    shipping_cost_usd REAL,                     -- per-unit shipping cost in USD
    incoterm VARCHAR(10),                       -- EXW, FOB, DDP, CIF, etc.

    -- Terms
    payment_terms TEXT,                         -- "30% deposit, 70% before shipping", "T/T", etc.
    valid_until TIMESTAMPTZ,                    -- quote expiration date

    -- Source tracking
    source VARCHAR(50),                         -- alibaba, 1688, manual, negotiator_agent
    source_url TEXT,                            -- link to product/quote page
    negotiation_notes TEXT,                     -- free-form notes from negotiation

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    is_active BOOLEAN DEFAULT true              -- soft delete / invalidate

    -- Note: No UNIQUE constraint - multiple quotes per ASIN allowed
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_sourcing_quotes_asin ON sourcing_quotes(asin);

-- Partial index for active quotes only (most common query)
CREATE INDEX IF NOT EXISTS idx_sourcing_quotes_active
ON sourcing_quotes(asin, unit_price_usd ASC)
WHERE is_active = true AND (valid_until IS NULL OR valid_until > NOW());

-- Index by source for analytics
CREATE INDEX IF NOT EXISTS idx_sourcing_quotes_source ON sourcing_quotes(source);

-- Trigger to auto-update updated_at
CREATE OR REPLACE FUNCTION update_sourcing_quotes_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_sourcing_quotes_updated ON sourcing_quotes;
CREATE TRIGGER trg_sourcing_quotes_updated
    BEFORE UPDATE ON sourcing_quotes
    FOR EACH ROW
    EXECUTE FUNCTION update_sourcing_quotes_timestamp();

-- Add comments for documentation
COMMENT ON TABLE sourcing_quotes IS 'Supplier quotes for product sourcing with multi-currency support and validity tracking';
COMMENT ON COLUMN sourcing_quotes.unit_price IS 'Unit price in the currency specified by currency field';
COMMENT ON COLUMN sourcing_quotes.unit_price_usd IS 'Unit price converted to USD for comparison (may be calculated externally)';
COMMENT ON COLUMN sourcing_quotes.incoterm IS 'International Commercial Terms: EXW (Ex Works), FOB (Free On Board), DDP (Delivered Duty Paid), CIF (Cost Insurance Freight)';
COMMENT ON COLUMN sourcing_quotes.price_breaks IS 'Volume discounts as JSON array: [{"qty": 1000, "price": 4.20}, {"qty": 5000, "price": 3.80}]';
