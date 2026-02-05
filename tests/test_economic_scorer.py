"""
Tests for Smartacus Economic Scorer (time multiplier).

Tests the economic scoring layer that integrates:
- Time multiplier calculation from market dynamics
- Economic value estimation
- Final score = base_score × time_multiplier
- Ranking and shortlist generation

Scenarios tested:
- Frequent stockouts + high churn (urgent)
- Zero volatility (stable, no urgency)
- Low churn (no window)
- Mixed signals
- Edge cases (all max, all min)

Usage:
    pytest tests/test_economic_scorer.py -v
"""

import pytest
from decimal import Decimal

from src.scoring.economic_scorer import (
    EconomicScorer,
    EconomicOpportunity,
    TimeWindow,
    TimeMultiplierResult,
)


class TestTimeMultiplierCalculation:
    """Tests for the time multiplier calculation."""

    def setup_method(self):
        self.scorer = EconomicScorer()

    def test_high_urgency_multiplier(self):
        """Frequent stockouts + high churn + volatility = high multiplier."""
        result = self.scorer.calculate_time_multiplier(
            stockout_frequency=4.0,
            seller_churn=0.40,
            price_volatility=0.25,
            bsr_acceleration=0.15,
        )

        # Geometric mean of (1.5, 1.4, 1.3, 1.4) ≈ 1.40
        assert result.multiplier >= 1.2
        assert result.window in (TimeWindow.CRITICAL, TimeWindow.URGENT, TimeWindow.ACTIVE)
        assert result.window_days <= 60
        assert result.confidence >= 0.75

    def test_low_urgency_multiplier(self):
        """No stockouts + low churn + stable = low multiplier."""
        result = self.scorer.calculate_time_multiplier(
            stockout_frequency=0.0,
            seller_churn=0.05,
            price_volatility=0.03,
            bsr_acceleration=-0.10,
        )

        assert result.multiplier <= 0.9
        assert result.window in (TimeWindow.STANDARD, TimeWindow.EXTENDED)
        assert result.window_days >= 90

    def test_neutral_multiplier(self):
        """Mixed moderate signals = neutral multiplier around 1.0."""
        result = self.scorer.calculate_time_multiplier(
            stockout_frequency=0.5,
            seller_churn=0.10,
            price_volatility=0.05,
            bsr_acceleration=0.0,
        )

        assert 0.85 <= result.multiplier <= 1.15

    def test_multiplier_clamped_min(self):
        """Multiplier should never go below 0.5."""
        result = self.scorer.calculate_time_multiplier(
            stockout_frequency=0.0,
            seller_churn=0.0,
            price_volatility=0.0,
            bsr_acceleration=-1.0,
        )

        assert result.multiplier >= 0.5

    def test_multiplier_clamped_max(self):
        """Multiplier should never exceed 2.0."""
        result = self.scorer.calculate_time_multiplier(
            stockout_frequency=100.0,
            seller_churn=1.0,
            price_volatility=1.0,
            bsr_acceleration=1.0,
        )

        assert result.multiplier <= 2.0

    def test_factors_recorded(self):
        """All 4 factors should be recorded in result."""
        result = self.scorer.calculate_time_multiplier(
            stockout_frequency=2.0,
            seller_churn=0.25,
            price_volatility=0.15,
            bsr_acceleration=0.08,
        )

        assert "stockouts" in result.factors
        assert "seller_churn" in result.factors
        assert "price_volatility" in result.factors
        assert "bsr_acceleration" in result.factors

    def test_erosion_rate_bounded(self):
        """Erosion rate should be between 0 and 1."""
        for sf in [0, 1, 5]:
            for sc in [0, 0.2, 0.5]:
                result = self.scorer.calculate_time_multiplier(
                    stockout_frequency=sf,
                    seller_churn=sc,
                    price_volatility=0.1,
                    bsr_acceleration=0.05,
                )
                assert 0 <= result.erosion_rate <= 1.0

    def test_confidence_based_on_strong_signals(self):
        """More strong signals (factor >= 1.2) = higher confidence."""
        # All strong
        result_strong = self.scorer.calculate_time_multiplier(
            stockout_frequency=5.0,
            seller_churn=0.40,
            price_volatility=0.25,
            bsr_acceleration=0.15,
        )

        # All weak
        result_weak = self.scorer.calculate_time_multiplier(
            stockout_frequency=0.1,
            seller_churn=0.05,
            price_volatility=0.03,
            bsr_acceleration=-0.10,
        )

        assert result_strong.confidence > result_weak.confidence


class TestEconomicValueEstimation:
    """Tests for economic value calculations."""

    def setup_method(self):
        self.scorer = EconomicScorer()

    def test_positive_margin_product(self):
        """Product with good margin should have positive value."""
        monthly, annual, risk_adj = self.scorer.estimate_economic_value(
            amazon_price=30.0,
            estimated_cogs=8.0,
            estimated_monthly_units=200,
        )

        assert monthly > 0
        assert annual == monthly * 12
        assert risk_adj < annual  # Risk discount applied

    def test_negative_margin_product(self):
        """Product with negative margin should have zero profit."""
        monthly, annual, risk_adj = self.scorer.estimate_economic_value(
            amazon_price=10.0,
            estimated_cogs=15.0,
            estimated_monthly_units=100,
        )

        assert monthly == Decimal("0")
        assert annual == Decimal("0")

    def test_risk_factor_applied(self):
        """Risk factor should discount the annual value."""
        _, annual_no_risk, _ = self.scorer.estimate_economic_value(
            amazon_price=25.0,
            estimated_cogs=7.0,
            estimated_monthly_units=150,
            risk_factor=0.0,
        )

        _, _, risk_adjusted = self.scorer.estimate_economic_value(
            amazon_price=25.0,
            estimated_cogs=7.0,
            estimated_monthly_units=150,
            risk_factor=0.3,
        )

        assert risk_adjusted < annual_no_risk
        # 30% risk = 70% of value
        expected = annual_no_risk * Decimal("0.7")
        assert abs(risk_adjusted - expected) < Decimal("1")

    def test_costs_include_all_fees(self):
        """Total cost should include FBA, referral, PPC, and returns."""
        monthly, _, _ = self.scorer.estimate_economic_value(
            amazon_price=25.0,
            estimated_cogs=5.0,
            estimated_monthly_units=100,
        )

        # With amazon_price=25, cogs=5:
        # FBA = max(25*0.15, 3.0) = 3.75
        # Referral = 25*0.15 = 3.75
        # PPC = 25*0.10 = 2.50
        # Returns = 25*0.05 = 1.25
        # Total cost = 5 + 3.75 + 3.75 + 2.50 + 1.25 = 16.25
        # Profit/unit = 25 - 16.25 = 8.75
        # Monthly = 8.75 * 100 = 875
        assert monthly == Decimal("875.0")


class TestScoreEconomic:
    """Tests for the complete economic scoring function."""

    def setup_method(self):
        self.scorer = EconomicScorer()
        self.good_product = {
            "product_id": "B09GOOD001",
            "amazon_price": 30.00,
            "alibaba_price": 4.00,
            "shipping_per_unit": 2.00,
            "bsr_current": 8000,
            "bsr_delta_7d": -0.20,
            "bsr_delta_30d": -0.15,
            "reviews_per_month": 35,
            "seller_count": 4,
            "buybox_rotation": 0.35,
            "review_gap_vs_top10": 0.30,
            "negative_review_percent": 0.18,
            "wish_mentions_per_100": 7,
            "unanswered_questions": 12,
            "stockout_count_90d": 4,
            "price_trend_30d": 0.10,
            "seller_churn_90d": 2,
            "bsr_acceleration": 0.12,
        }
        self.good_time_data = {
            "stockout_frequency": 1.5,
            "seller_churn_90d": 0.25,
            "price_volatility": 0.15,
            "bsr_acceleration": 0.10,
            "estimated_monthly_units": 200,
        }

    def test_score_economic_returns_opportunity(self):
        """score_economic should return an EconomicOpportunity."""
        result = self.scorer.score_economic(
            self.good_product,
            self.good_time_data,
        )

        assert isinstance(result, EconomicOpportunity)
        assert result.asin == "B09GOOD001"
        assert 0 <= result.final_score <= 100
        assert 0.5 <= result.time_multiplier <= 2.0
        assert result.estimated_monthly_profit >= 0

    def test_time_multiplier_amplifies_score(self):
        """High urgency time data should produce higher final score."""
        # Low urgency
        low_time = {
            "stockout_frequency": 0.0,
            "seller_churn_90d": 0.05,
            "price_volatility": 0.02,
            "bsr_acceleration": -0.05,
            "estimated_monthly_units": 100,
        }

        # High urgency
        high_time = {
            "stockout_frequency": 4.0,
            "seller_churn_90d": 0.40,
            "price_volatility": 0.25,
            "bsr_acceleration": 0.20,
            "estimated_monthly_units": 100,
        }

        result_low = self.scorer.score_economic(self.good_product, low_time)
        result_high = self.scorer.score_economic(self.good_product, high_time)

        assert result_high.final_score >= result_low.final_score
        assert result_high.time_multiplier > result_low.time_multiplier

    def test_thesis_generated(self):
        """Thesis should be a non-empty string."""
        result = self.scorer.score_economic(
            self.good_product,
            self.good_time_data,
        )

        assert isinstance(result.thesis, str)
        assert len(result.thesis) > 10

    def test_economic_events_passed_through(self):
        """Economic events should be stored in the result."""
        events = ["supply_shock", "competitor_collapse"]
        result = self.scorer.score_economic(
            self.good_product,
            self.good_time_data,
            economic_events=events,
        )

        assert result.economic_events == events

    def test_rank_score_calculated(self):
        """Rank score should be risk_adjusted_value × urgency_weight."""
        result = self.scorer.score_economic(
            self.good_product,
            self.good_time_data,
        )

        assert result.rank_score > 0

    def test_to_dict_serializable(self):
        """to_dict should return a fully serializable dict."""
        result = self.scorer.score_economic(
            self.good_product,
            self.good_time_data,
        )

        d = result.to_dict()
        assert d["asin"] == "B09GOOD001"
        assert isinstance(d["final_score"], int)
        assert isinstance(d["time_multiplier"], float)
        assert isinstance(d["estimated_annual_value"], float)


class TestRankOpportunities:
    """Tests for opportunity ranking."""

    def setup_method(self):
        self.scorer = EconomicScorer()

    def _make_opportunity(self, asin, score, rank_score):
        """Helper to create a minimal EconomicOpportunity."""
        return EconomicOpportunity(
            asin=asin,
            base_score=score / 100,
            time_multiplier=1.0,
            final_score=score,
            estimated_monthly_profit=Decimal("1000"),
            estimated_annual_value=Decimal("12000"),
            risk_adjusted_value=Decimal("8400"),
            window=TimeWindow.ACTIVE,
            window_days=60,
            urgency_label="Test",
            thesis="Test thesis",
            rank_score=rank_score,
        )

    def test_rank_by_rank_score(self):
        """Opportunities should be ranked by rank_score descending."""
        opps = [
            self._make_opportunity("B09A", 60, 5000),
            self._make_opportunity("B09B", 80, 15000),
            self._make_opportunity("B09C", 70, 10000),
        ]

        ranked = self.scorer.rank_opportunities(opps)

        assert ranked[0].asin == "B09B"
        assert ranked[1].asin == "B09C"
        assert ranked[2].asin == "B09A"

    def test_rank_filters_low_score(self):
        """Opportunities with final_score < 40 should be excluded."""
        opps = [
            self._make_opportunity("B09GOOD", 60, 10000),
            self._make_opportunity("B09BAD", 30, 5000),
        ]

        ranked = self.scorer.rank_opportunities(opps)

        assert len(ranked) == 1
        assert ranked[0].asin == "B09GOOD"

    def test_rank_top_n(self):
        """Should return at most top_n items."""
        opps = [self._make_opportunity(f"B09{i}", 50 + i, 1000 * i) for i in range(20)]

        ranked = self.scorer.rank_opportunities(opps, top_n=5)

        assert len(ranked) == 5

    def test_generate_shortlist_format(self):
        """Shortlist should have correct format."""
        opps = [
            self._make_opportunity("B09A", 75, 12000),
            self._make_opportunity("B09B", 82, 18000),
        ]

        shortlist = self.scorer.generate_shortlist(opps, max_items=5)

        assert len(shortlist) == 2
        assert shortlist[0]["rank"] == 1
        assert shortlist[0]["asin"] == "B09B"  # Higher rank_score
        assert "score" in shortlist[0]
        assert "thesis" in shortlist[0]


class TestTimeMultiplierScenarios:
    """Specific scenarios from audit recommendations."""

    def setup_method(self):
        self.scorer = EconomicScorer()

    def test_scenario_frequent_stockouts(self):
        """Frequent stockouts = very short window."""
        result = self.scorer.calculate_time_multiplier(
            stockout_frequency=5.0,
            seller_churn=0.20,
            price_volatility=0.10,
            bsr_acceleration=0.08,
        )

        assert result.multiplier > 1.0
        assert "+" in result.factors["stockouts"]

    def test_scenario_zero_volatility(self):
        """Zero volatility = stable market, no urgency."""
        result = self.scorer.calculate_time_multiplier(
            stockout_frequency=0.3,
            seller_churn=0.08,
            price_volatility=0.0,
            bsr_acceleration=0.0,
        )

        assert result.multiplier <= 1.0
        assert "neutre" in result.factors["price_volatility"].lower()

    def test_scenario_low_churn(self):
        """Low churn = established sellers, hard to enter."""
        result = self.scorer.calculate_time_multiplier(
            stockout_frequency=0.2,
            seller_churn=0.03,
            price_volatility=0.05,
            bsr_acceleration=-0.02,
        )

        assert "-" in result.factors["seller_churn"]

    def test_scenario_all_factors_positive(self):
        """All positive factors = high multiplier."""
        result = self.scorer.calculate_time_multiplier(
            stockout_frequency=5.0,
            seller_churn=0.50,
            price_volatility=0.30,
            bsr_acceleration=0.20,
        )

        # Geometric mean dampens extremes: (1.5*1.4*1.3*1.4)^0.25 ≈ 1.40
        assert result.multiplier >= 1.2
        assert result.window in (TimeWindow.CRITICAL, TimeWindow.URGENT, TimeWindow.ACTIVE)

    def test_scenario_all_factors_negative(self):
        """All negative factors = no urgency."""
        result = self.scorer.calculate_time_multiplier(
            stockout_frequency=0.0,
            seller_churn=0.02,
            price_volatility=0.01,
            bsr_acceleration=-0.20,
        )

        assert result.multiplier < 1.0
        assert result.window in (TimeWindow.STANDARD, TimeWindow.EXTENDED)

    def test_determinism(self):
        """Same inputs should always produce same multiplier."""
        kwargs = {
            "stockout_frequency": 2.0,
            "seller_churn": 0.25,
            "price_volatility": 0.12,
            "bsr_acceleration": 0.07,
        }

        results = [self.scorer.calculate_time_multiplier(**kwargs) for _ in range(50)]

        assert all(r.multiplier == results[0].multiplier for r in results)
        assert all(r.window == results[0].window for r in results)
