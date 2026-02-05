"""
Integration tests for the full Smartacus pipeline.

Tests the complete flow: Events → Scoring → Economic Scoring → Shortlist

These tests verify that all layers work together correctly without
requiring a database or external API. Each layer is tested with
realistic data flowing through the complete chain.

Usage:
    pytest tests/test_integration_pipeline.py -v
"""

import pytest
from decimal import Decimal
from datetime import datetime

from src.scoring.opportunity_scorer import (
    OpportunityScorer,
    OpportunityStatus,
    ScoringResult,
)
from src.scoring.economic_scorer import (
    EconomicScorer,
    EconomicOpportunity,
    TimeWindow,
)
from src.events.economic_events import (
    EconomicEventDetector,
    EconomicEventType,
    EventConfidence,
    SupplyShockEvent,
)
# Mock external dependencies not needed for integration tests
import sys
from unittest.mock import MagicMock

for mod in [
    "psycopg2", "psycopg2.extras", "psycopg2.pool",
    "dotenv", "keepa", "openai", "httpx",
]:
    sys.modules.setdefault(mod, MagicMock())

from src.orchestrator.shortlist import ShortlistGenerator, ShortlistItem


# =============================================================================
# Test Data Fixtures
# =============================================================================

def make_product(
    asin="B09TEST001",
    amazon_price=25.00,
    alibaba_price=5.00,
    bsr_current=15000,
    bsr_delta_7d=-0.10,
    reviews_per_month=20,
    seller_count=5,
    buybox_rotation=0.30,
    negative_review_percent=0.15,
    stockout_count_90d=3,
    price_trend_30d=0.05,
    **overrides,
):
    """Create a product data dict with sensible defaults."""
    data = {
        "product_id": asin,
        "amazon_price": amazon_price,
        "alibaba_price": alibaba_price,
        "shipping_per_unit": 3.00,
        "bsr_current": bsr_current,
        "bsr_delta_7d": bsr_delta_7d,
        "bsr_delta_30d": overrides.get("bsr_delta_30d", bsr_delta_7d * 1.5),
        "reviews_per_month": reviews_per_month,
        "seller_count": seller_count,
        "buybox_rotation": buybox_rotation,
        "review_gap_vs_top10": overrides.get("review_gap_vs_top10", 0.40),
        "negative_review_percent": negative_review_percent,
        "wish_mentions_per_100": overrides.get("wish_mentions_per_100", 5),
        "unanswered_questions": overrides.get("unanswered_questions", 10),
        "stockout_count_90d": stockout_count_90d,
        "price_trend_30d": price_trend_30d,
        "seller_churn_90d": overrides.get("seller_churn_90d", 1),
        "bsr_acceleration": overrides.get("bsr_acceleration", 0.10),
    }
    data.update(overrides)
    return data


def make_time_data(
    stockout_frequency=1.0,
    seller_churn_90d=0.15,
    price_volatility=0.10,
    bsr_acceleration=0.05,
    estimated_monthly_units=150,
    **overrides,
):
    """Create time data dict with sensible defaults."""
    data = {
        "stockout_frequency": stockout_frequency,
        "seller_churn_90d": seller_churn_90d,
        "price_volatility": price_volatility,
        "bsr_acceleration": bsr_acceleration,
        "estimated_monthly_units": estimated_monthly_units,
    }
    data.update(overrides)
    return data


def make_metrics(
    stockouts_90d=3,
    bsr_change_30d=-0.25,
    price_change_30d=0.05,
    seller_churn_90d=0.20,
    negative_review_pct=0.18,
    **overrides,
):
    """Create event metrics dict with sensible defaults."""
    data = {
        "stockouts_90d": stockouts_90d,
        "bsr_change_30d": bsr_change_30d,
        "price_change_30d": price_change_30d,
        "competitors_stockout": overrides.get("competitors_stockout", 1),
        "seller_churn_90d": seller_churn_90d,
        "top_seller_gone": overrides.get("top_seller_gone", False),
        "buybox_rotation_change": overrides.get("buybox_rotation_change", 0.15),
        "new_entrants": overrides.get("new_entrants", 1),
        "negative_review_pct": negative_review_pct,
        "negative_review_trend": overrides.get("negative_review_trend", 0.05),
        "wish_mentions": overrides.get("wish_mentions", 6),
        "common_complaints": overrides.get("common_complaints", ["flimsy mount"]),
        "rating_30d_ago": overrides.get("rating_30d_ago", 4.1),
        "rating_now": overrides.get("rating_now", 3.9),
    }
    data.update(overrides)
    return data


# =============================================================================
# Integration: Events → Scoring → Shortlist
# =============================================================================

class TestFullPipelineIntegration:
    """
    End-to-end integration test: Events → Scoring → Economic Scoring → Shortlist.
    """

    def setup_method(self):
        self.detector = EconomicEventDetector()
        self.base_scorer = OpportunityScorer()
        self.economic_scorer = EconomicScorer()
        self.shortlist_gen = ShortlistGenerator()

    def test_complete_flow_strong_opportunity(self):
        """
        Test the full flow for a strong opportunity:
        1. Detect economic events
        2. Base score the product
        3. Economic score with time multiplier
        4. Generate shortlist
        """
        # === STEP 1: Event Detection ===
        metrics = make_metrics(
            stockouts_90d=4,
            bsr_change_30d=-0.35,
            price_change_30d=0.08,
            competitors_stockout=2,
            seller_churn_90d=0.30,
            top_seller_gone=True,
            negative_review_pct=0.22,
            wish_mentions=8,
        )

        events = self.detector.detect_all_events("B09STRONG", metrics)
        assert len(events) >= 1
        event_names = [e.event_type.value for e in events]

        # === STEP 2: Base Scoring ===
        product = make_product(
            asin="B09STRONG",
            amazon_price=30.00,
            alibaba_price=4.00,
            bsr_current=8000,
            bsr_delta_7d=-0.25,
            reviews_per_month=40,
            seller_count=3,
            buybox_rotation=0.40,
            negative_review_percent=0.22,
            stockout_count_90d=4,
            price_trend_30d=0.12,
            seller_churn_90d=3,
            bsr_acceleration=0.15,
        )

        base_result = self.base_scorer.score(product)
        assert base_result.is_valid is True
        assert base_result.total_score >= 50

        # === STEP 3: Economic Scoring ===
        time_data = make_time_data(
            stockout_frequency=1.5,
            seller_churn_90d=0.30,
            price_volatility=0.15,
            bsr_acceleration=0.12,
            estimated_monthly_units=250,
        )

        econ_result = self.economic_scorer.score_economic(
            product, time_data, economic_events=event_names,
        )

        assert econ_result.final_score >= 40
        assert econ_result.estimated_annual_value > 0
        assert len(econ_result.economic_events) >= 1

        # === STEP 4: Shortlist ===
        shortlist = self.shortlist_gen.generate([econ_result])

        # Should appear in shortlist if score + value meet thresholds
        if econ_result.final_score >= 50 and float(econ_result.risk_adjusted_value) >= 5000:
            assert len(shortlist) == 1
            assert shortlist[0].asin == "B09STRONG"
            assert shortlist[0].thesis is not None
            assert shortlist[0].action_recommendation is not None

    def test_complete_flow_rejected_opportunity(self):
        """
        Test the full flow for a product that gets rejected (no time window).
        """
        # Product with great scores but NO time pressure
        product = make_product(
            asin="B09REJECT",
            amazon_price=30.00,
            alibaba_price=3.00,
            bsr_current=3000,
            bsr_delta_7d=-0.30,
            reviews_per_month=60,
            seller_count=2,
            buybox_rotation=0.50,
            negative_review_percent=0.25,
            # No time pressure signals
            stockout_count_90d=0,
            price_trend_30d=-0.15,
            seller_churn_90d=0,
            bsr_acceleration=-0.05,
        )

        base_result = self.base_scorer.score(product)

        # Should be rejected: time_pressure < 3
        assert base_result.is_valid is False
        assert base_result.status == OpportunityStatus.INVALID_NO_WINDOW

    def test_multiple_products_ranked_correctly(self):
        """
        Test that multiple products are ranked correctly in shortlist.
        Best product (highest rank_score) should be first.
        """
        products_and_times = [
            # Excellent product, high urgency
            (
                make_product(
                    asin="B09TOP",
                    amazon_price=35.00,
                    alibaba_price=4.00,
                    bsr_current=5000,
                    bsr_delta_7d=-0.25,
                    reviews_per_month=45,
                    seller_count=3,
                    stockout_count_90d=5,
                    price_trend_30d=0.15,
                    seller_churn_90d=3,
                    bsr_acceleration=0.20,
                ),
                make_time_data(
                    stockout_frequency=2.0,
                    seller_churn_90d=0.35,
                    price_volatility=0.20,
                    bsr_acceleration=0.15,
                    estimated_monthly_units=300,
                ),
            ),
            # Good product, moderate urgency
            (
                make_product(
                    asin="B09MID",
                    amazon_price=25.00,
                    alibaba_price=5.00,
                    bsr_current=20000,
                    bsr_delta_7d=-0.10,
                    reviews_per_month=20,
                    seller_count=6,
                    stockout_count_90d=3,
                    price_trend_30d=0.05,
                ),
                make_time_data(
                    stockout_frequency=1.0,
                    seller_churn_90d=0.15,
                    price_volatility=0.08,
                    bsr_acceleration=0.05,
                    estimated_monthly_units=150,
                ),
            ),
            # Mediocre product, low urgency
            (
                make_product(
                    asin="B09LOW",
                    amazon_price=18.00,
                    alibaba_price=6.00,
                    bsr_current=60000,
                    bsr_delta_7d=0.05,
                    reviews_per_month=8,
                    seller_count=12,
                    stockout_count_90d=3,
                    price_trend_30d=0.02,
                ),
                make_time_data(
                    stockout_frequency=0.3,
                    seller_churn_90d=0.08,
                    price_volatility=0.03,
                    bsr_acceleration=0.0,
                    estimated_monthly_units=80,
                ),
            ),
        ]

        opportunities = []
        for product, time_data in products_and_times:
            opp = self.economic_scorer.score_economic(product, time_data)
            opportunities.append(opp)

        shortlist = self.shortlist_gen.generate(opportunities)

        # Verify ordering if multiple items in shortlist
        if len(shortlist) >= 2:
            for i in range(len(shortlist) - 1):
                assert shortlist[i].rank < shortlist[i + 1].rank

        # B09TOP should be first if it meets thresholds
        if shortlist:
            top_asins = [s.asin for s in shortlist]
            if "B09TOP" in top_asins:
                assert shortlist[0].asin == "B09TOP"


class TestEventsToScoringIntegration:
    """
    Test that detected events correctly influence scoring decisions.
    """

    def setup_method(self):
        self.detector = EconomicEventDetector()
        self.scorer = EconomicScorer()

    def test_supply_shock_increases_urgency(self):
        """
        A supply shock event should correlate with higher time multiplier
        when the corresponding market dynamics are present.
        """
        # Metrics that would trigger supply shock
        metrics = make_metrics(stockouts_90d=5, bsr_change_30d=-0.40, competitors_stockout=3)
        events = self.detector.detect_all_events("B09SHOCK", metrics)

        supply_shock = next(
            (e for e in events if e.event_type == EconomicEventType.SUPPLY_SHOCK),
            None,
        )
        assert supply_shock is not None

        # The same signals in time_data should produce high multiplier
        time_data = make_time_data(
            stockout_frequency=5 / 3,  # 5 stockouts in 3 months
            seller_churn_90d=0.20,
            price_volatility=0.10,
            bsr_acceleration=0.10,
        )

        product = make_product(
            asin="B09SHOCK",
            stockout_count_90d=5,
            price_trend_30d=0.10,
            seller_churn_90d=2,
            bsr_acceleration=0.10,
        )

        result = self.scorer.score_economic(
            product,
            time_data,
            economic_events=[supply_shock.event_type.value],
        )

        assert result.time_multiplier >= 1.0
        assert "supply_shock" in result.economic_events

    def test_calm_market_no_events_low_urgency(self):
        """Calm market = no events detected = low time multiplier."""
        metrics = make_metrics(
            stockouts_90d=0,
            bsr_change_30d=0.02,
            price_change_30d=-0.01,
            seller_churn_90d=0.05,
            negative_review_pct=0.04,
        )

        events = self.detector.detect_all_events("B09CALM", metrics)
        assert len(events) == 0

        time_data = make_time_data(
            stockout_frequency=0.0,
            seller_churn_90d=0.05,
            price_volatility=0.02,
            bsr_acceleration=-0.02,
        )

        product = make_product(
            asin="B09CALM",
            stockout_count_90d=0,
            price_trend_30d=-0.01,
            seller_churn_90d=0,
            bsr_acceleration=-0.02,
        )

        result = self.scorer.score_economic(product, time_data, economic_events=[])

        assert result.time_multiplier <= 1.0


class TestShortlistConstraints:
    """
    Test shortlist generation rules and constraints.
    """

    def setup_method(self):
        self.scorer = EconomicScorer()
        self.shortlist_gen = ShortlistGenerator()

    def test_max_5_items(self):
        """Shortlist should never exceed 5 items."""
        opportunities = []
        for i in range(20):
            product = make_product(
                asin=f"B09ITEM{i:03d}",
                amazon_price=30.00,
                alibaba_price=4.00,
                bsr_current=10000 + i * 1000,
                stockout_count_90d=4,
                price_trend_30d=0.10,
                seller_churn_90d=2,
                bsr_acceleration=0.15,
            )
            time_data = make_time_data(
                stockout_frequency=1.5,
                seller_churn_90d=0.25,
                estimated_monthly_units=200,
            )
            opp = self.scorer.score_economic(product, time_data)
            opportunities.append(opp)

        shortlist = self.shortlist_gen.generate(opportunities)

        assert len(shortlist) <= 5

    def test_min_score_filter(self):
        """Items below MIN_SCORE should not appear in shortlist."""
        # Create a weak product that scores low
        product = make_product(
            asin="B09WEAK",
            amazon_price=12.00,
            alibaba_price=8.00,
            bsr_current=200000,
            bsr_delta_7d=0.20,
            reviews_per_month=2,
            seller_count=25,
            stockout_count_90d=3,
        )
        time_data = make_time_data(
            stockout_frequency=0.3,
            seller_churn_90d=0.05,
            estimated_monthly_units=20,
        )

        opp = self.scorer.score_economic(product, time_data)
        shortlist = self.shortlist_gen.generate([opp])

        # If score < 50, should not be in shortlist
        if opp.final_score < self.shortlist_gen.MIN_SCORE:
            assert len(shortlist) == 0

    def test_min_value_filter(self):
        """Items below MIN_VALUE should not appear in shortlist."""
        # Product with tiny value
        product = make_product(
            asin="B09TINY",
            amazon_price=8.00,
            alibaba_price=5.00,
            stockout_count_90d=3,
            price_trend_30d=0.05,
        )
        time_data = make_time_data(estimated_monthly_units=5)

        opp = self.scorer.score_economic(product, time_data)
        shortlist = self.shortlist_gen.generate([opp])

        # Value too low = not in shortlist
        if float(opp.risk_adjusted_value) < self.shortlist_gen.MIN_VALUE:
            assert len(shortlist) == 0

    def test_action_recommendation_by_window(self):
        """Action recommendation should match window urgency."""
        products_windows = [
            (14, "IMMÉDIATE"),
            (30, "PRIORITAIRE"),
            (60, "ACTIF"),
            (120, "SURVEILLER"),
        ]

        for window_days, expected_keyword in products_windows:
            opp = EconomicOpportunity(
                asin=f"B09W{window_days}",
                base_score=0.7,
                time_multiplier=1.5,
                final_score=75,
                estimated_monthly_profit=Decimal("2000"),
                estimated_annual_value=Decimal("24000"),
                risk_adjusted_value=Decimal("16800"),
                window=TimeWindow.ACTIVE,
                window_days=window_days,
                urgency_label="Test",
                thesis="Test",
                rank_score=20000,
            )

            shortlist = self.shortlist_gen.generate([opp])
            if shortlist:
                assert expected_keyword in shortlist[0].action_recommendation

    def test_shortlist_display_format(self):
        """print_shortlist should produce readable output."""
        opp = EconomicOpportunity(
            asin="B09DISPLAY",
            base_score=0.75,
            time_multiplier=1.3,
            final_score=78,
            estimated_monthly_profit=Decimal("2500"),
            estimated_annual_value=Decimal("30000"),
            risk_adjusted_value=Decimal("21000"),
            window=TimeWindow.URGENT,
            window_days=30,
            urgency_label="URGENT",
            thesis="Supply shock + high margin",
            rank_score=25000,
        )

        shortlist = self.shortlist_gen.generate([opp])
        output = self.shortlist_gen.print_shortlist(shortlist)

        assert "B09DISPLAY" in output
        assert "SHORTLIST" in output

    def test_shortlist_empty(self):
        """Empty shortlist should produce meaningful message."""
        output = self.shortlist_gen.print_shortlist([])
        assert "Aucune" in output

    def test_shortlist_json_export(self):
        """JSON export should contain all required fields."""
        opp = EconomicOpportunity(
            asin="B09JSON",
            base_score=0.70,
            time_multiplier=1.2,
            final_score=72,
            estimated_monthly_profit=Decimal("1800"),
            estimated_annual_value=Decimal("21600"),
            risk_adjusted_value=Decimal("15120"),
            window=TimeWindow.ACTIVE,
            window_days=60,
            urgency_label="ACTIF",
            thesis="Viable product",
            rank_score=18000,
        )

        shortlist = self.shortlist_gen.generate([opp])
        json_out = self.shortlist_gen.to_json(shortlist)

        assert "generated_at" in json_out
        assert "criteria" in json_out
        assert json_out["criteria"]["min_score"] == 50
        assert json_out["criteria"]["min_value"] == 5000
        assert "items" in json_out
        assert "total_potential_value" in json_out


class TestEdgeCases:
    """Edge cases and boundary conditions across the pipeline."""

    def setup_method(self):
        self.scorer = OpportunityScorer()
        self.economic_scorer = EconomicScorer()

    def test_zero_price_product(self):
        """Product with zero price should not crash."""
        product = make_product(asin="B09ZERO", amazon_price=0.0, alibaba_price=0.0)

        result = self.scorer.score(product)
        assert isinstance(result, ScoringResult)

    def test_extreme_bsr(self):
        """Extremely high BSR should score 0 for BSR absolute component."""
        product = make_product(
            asin="B09HIGHBSR",
            bsr_current=9999999,
            stockout_count_90d=3,
        )

        result = self.scorer.score(product)
        assert result.component_scores["velocity"].details["sub_scores"]["bsr_absolute"] == 0

    def test_all_maximum_values(self):
        """Product with all maximum signals should score near 100."""
        product = make_product(
            asin="B09MAX",
            amazon_price=50.00,
            alibaba_price=3.00,
            bsr_current=2000,
            bsr_delta_7d=-0.40,
            bsr_delta_30d=-0.30,
            reviews_per_month=70,
            seller_count=2,
            buybox_rotation=0.55,
            review_gap_vs_top10=0.20,
            negative_review_percent=0.30,
            wish_mentions_per_100=15,
            unanswered_questions=25,
            has_recurring_problems=True,
            stockout_count_90d=6,
            price_trend_30d=0.20,
            seller_churn_90d=4,
            bsr_acceleration=0.25,
        )

        result = self.scorer.score(product)
        assert result.is_valid is True
        assert result.total_score >= 70

    def test_scoring_determinism_across_layers(self):
        """Same inputs through full pipeline should always produce same output."""
        product = make_product(asin="B09DETER")
        time_data = make_time_data()

        results = []
        for _ in range(20):
            opp = self.economic_scorer.score_economic(product, time_data)
            results.append(opp.final_score)

        assert len(set(results)) == 1  # All identical
