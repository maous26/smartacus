-- Migration 013: Strategy Decisions Audit Table
-- V3.0 - Intelligent Resource Allocation

-- =============================================================================
-- STRATEGY DECISIONS: Audit trail for allocation decisions
-- =============================================================================
CREATE TABLE IF NOT EXISTS strategy_decisions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    cycle_id VARCHAR(50) UNIQUE NOT NULL,
    decided_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Budget allocation
    budget_total INTEGER NOT NULL,
    budget_exploit INTEGER NOT NULL,
    budget_explore INTEGER NOT NULL,
    budget_reserve INTEGER NOT NULL,

    -- Decision details (JSON for flexibility)
    assessments JSONB NOT NULL,           -- Array of niche assessments
    risk_notes JSONB DEFAULT '[]',        -- Array of risk strings

    -- LLM consultation
    llm_consulted BOOLEAN DEFAULT false,
    llm_override_reason TEXT,

    -- Execution tracking (filled after run)
    executed_at TIMESTAMPTZ,
    execution_result JSONB,               -- Actual results vs planned
    tokens_actually_used INTEGER,
    opportunities_found INTEGER,

    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_strategy_decisions_cycle ON strategy_decisions(cycle_id);
CREATE INDEX idx_strategy_decisions_date ON strategy_decisions(decided_at DESC);

-- =============================================================================
-- ADD category_id TO asins TABLE (for event aggregation)
-- =============================================================================
-- Note: This assumes asins don't have category_id yet. Skip if already exists.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'asins' AND column_name = 'category_id'
    ) THEN
        ALTER TABLE asins ADD COLUMN category_id BIGINT;
        CREATE INDEX idx_asins_category ON asins(category_id);
    END IF;
END $$;

-- =============================================================================
-- COMMENTS
-- =============================================================================
COMMENT ON TABLE strategy_decisions IS 'Audit trail for Strategy Agent allocation decisions';
COMMENT ON COLUMN strategy_decisions.assessments IS 'JSON array of niche assessments with status, tokens, justification';
COMMENT ON COLUMN strategy_decisions.llm_consulted IS 'Whether LLM was consulted for ambiguous decisions';
