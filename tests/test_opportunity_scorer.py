"""
Tests unitaires pour le module de scoring Smartacus.

Ces tests vérifient:
1. Le déterminisme du scoring (mêmes inputs → mêmes outputs)
2. La règle critique time_pressure < 3 → rejet
3. La cohérence des seuils et calculs
4. Les cas limites

Utilisation:
    python3 tests/test_opportunity_scorer.py
    # ou avec pytest si installé:
    pytest tests/test_opportunity_scorer.py -v
"""

try:
    import pytest
    HAS_PYTEST = True
except ImportError:
    HAS_PYTEST = False

import sys
sys.path.insert(0, '/Users/moussa/Documents/PROJETS/smartacus')

from src.scoring.opportunity_scorer import (
    OpportunityScorer,
    OpportunityStatus,
    ScoringResult,
)
from src.scoring.scoring_config import ScoringConfig, DEFAULT_CONFIG


class TestScoringDeterminism:
    """Vérifie que le scoring est 100% déterministe."""

    def setup_method(self):
        self.scorer = OpportunityScorer()
        self.sample_product = {
            "product_id": "B09TEST001",
            "amazon_price": 25.00,
            "alibaba_price": 4.00,
            "shipping_per_unit": 3.00,
            "bsr_current": 15000,
            "bsr_delta_7d": -0.10,
            "bsr_delta_30d": -0.05,
            "reviews_per_month": 20,
            "seller_count": 5,
            "buybox_rotation": 0.30,
            "review_gap_vs_top10": 0.40,
            "negative_review_percent": 0.15,
            "wish_mentions_per_100": 5,
            "unanswered_questions": 10,
            "stockout_count_90d": 3,
            "price_trend_30d": 0.05,
            "seller_churn_90d": 1,
            "bsr_acceleration": 0.10,
        }

    def test_same_input_same_output(self):
        """Le même input doit toujours produire le même output."""
        result1 = self.scorer.score(self.sample_product)
        result2 = self.scorer.score(self.sample_product)

        assert result1.total_score == result2.total_score
        assert result1.status == result2.status
        assert result1.is_valid == result2.is_valid

    def test_multiple_runs_consistent(self):
        """100 exécutions doivent donner le même résultat."""
        first_result = self.scorer.score(self.sample_product)

        for _ in range(100):
            result = self.scorer.score(self.sample_product)
            assert result.total_score == first_result.total_score


class TestTimePressureCriticalRule:
    """Vérifie la règle critique: time_pressure < 3 → rejet."""

    def setup_method(self):
        self.scorer = OpportunityScorer()

    def test_time_pressure_below_3_invalid(self):
        """Un time_pressure < 3 doit invalider l'opportunité."""
        product = {
            "product_id": "B09NOWINDOW",
            # Excellente marge
            "amazon_price": 30.00,
            "alibaba_price": 3.00,
            # Excellente vélocité
            "bsr_current": 5000,
            "bsr_delta_7d": -0.30,
            "bsr_delta_30d": -0.20,
            "reviews_per_month": 60,
            # Excellente compétition
            "seller_count": 2,
            "buybox_rotation": 0.50,
            "review_gap_vs_top10": 0.20,
            # Bon gap
            "negative_review_percent": 0.25,
            "wish_mentions_per_100": 12,
            "unanswered_questions": 25,
            # MAIS: time_pressure = 0
            "stockout_count_90d": 0,
            "price_trend_30d": -0.15,
            "seller_churn_90d": 0,
            "bsr_acceleration": -0.05,
        }

        result = self.scorer.score(product)

        assert result.is_valid is False
        assert result.status == OpportunityStatus.INVALID_NO_WINDOW
        assert result.rejection_reason is not None
        assert "Time Pressure" in result.rejection_reason

    def test_time_pressure_exactly_3_valid(self):
        """Un time_pressure = 3 doit être valide (seuil inclus)."""
        product = {
            "product_id": "B09MINIMAL",
            "amazon_price": 25.00,
            "alibaba_price": 5.00,
            "bsr_current": 30000,
            "bsr_delta_7d": 0.0,
            "bsr_delta_30d": 0.0,
            "reviews_per_month": 10,
            "seller_count": 10,
            "buybox_rotation": 0.10,
            "review_gap_vs_top10": 0.60,
            "negative_review_percent": 0.08,
            "wish_mentions_per_100": 2,
            "unanswered_questions": 3,
            # time_pressure = 3 (juste au seuil)
            "stockout_count_90d": 3,  # 2 pts
            "price_trend_30d": 0.0,   # 1 pt
            "seller_churn_90d": 0,    # 0 pts
            "bsr_acceleration": 0.0,  # 0 pts
        }

        result = self.scorer.score(product)

        assert result.component_scores["time_pressure"].score == 3
        assert result.is_valid is True

    def test_time_pressure_2_invalid(self):
        """Un time_pressure = 2 doit être invalide."""
        product = {
            "product_id": "B09ALMOSTTHERE",
            "amazon_price": 25.00,
            "alibaba_price": 5.00,
            "bsr_current": 30000,
            "bsr_delta_7d": 0.0,
            "bsr_delta_30d": 0.0,
            "reviews_per_month": 10,
            "seller_count": 10,
            "buybox_rotation": 0.10,
            "review_gap_vs_top10": 0.60,
            "negative_review_percent": 0.08,
            "wish_mentions_per_100": 2,
            "unanswered_questions": 3,
            # time_pressure = 2 (juste en dessous du seuil)
            "stockout_count_90d": 1,  # 1 pt
            "price_trend_30d": 0.02,  # 1 pt
            "seller_churn_90d": 0,    # 0 pts
            "bsr_acceleration": 0.0,  # 0 pts
        }

        result = self.scorer.score(product)

        assert result.component_scores["time_pressure"].score == 2
        assert result.is_valid is False


class TestMarginScoring:
    """Tests pour le scoring MARGIN."""

    def setup_method(self):
        self.scorer = OpportunityScorer()

    def test_margin_above_35_percent(self):
        """Marge > 35% doit donner 30 points."""
        product = {
            "product_id": "B09HIGHMARGIN",
            "amazon_price": 35.00,
            "alibaba_price": 3.00,
            "shipping_per_unit": 2.00,
            # Minimum time_pressure pour être valide
            "stockout_count_90d": 5,
            "price_trend_30d": 0.15,
            "seller_churn_90d": 3,
            "bsr_acceleration": 0.20,
        }

        result = self.scorer.score(product)
        margin = result.component_scores["margin"]

        assert margin.score == 30
        assert margin.details["net_margin"] > 0.35

    def test_margin_below_15_percent(self):
        """Marge < 15% doit donner 0 points."""
        product = {
            "product_id": "B09LOWMARGIN",
            "amazon_price": 15.00,
            "alibaba_price": 8.00,
            "shipping_per_unit": 4.00,
            "stockout_count_90d": 5,
            "price_trend_30d": 0.15,
            "seller_churn_90d": 3,
            "bsr_acceleration": 0.20,
        }

        result = self.scorer.score(product)
        margin = result.component_scores["margin"]

        assert margin.score == 0
        assert margin.details["net_margin"] < 0.15

    def test_margin_includes_all_costs(self):
        """La marge doit inclure tous les coûts (FBA, referral, provisions)."""
        product = {
            "product_id": "B09COSTCHECK",
            "amazon_price": 25.00,
            "alibaba_price": 5.00,
            "shipping_per_unit": 3.00,
            "stockout_count_90d": 3,
        }

        result = self.scorer.score(product)
        margin = result.component_scores["margin"]

        total_cost = margin.details["total_cost"]

        # Vérifier que le coût total est supérieur au simple coût produit
        simple_cost = 5.00 + 3.00  # Alibaba + shipping
        assert total_cost > simple_cost * 2  # Au moins le double avec tous les frais


class TestVelocityScoring:
    """Tests pour le scoring VELOCITY."""

    def setup_method(self):
        self.scorer = OpportunityScorer()

    def test_excellent_velocity(self):
        """BSR excellent avec bon momentum doit scorer haut."""
        product = {
            "product_id": "B09FASTMOVER",
            "amazon_price": 25.00,
            "alibaba_price": 5.00,
            "bsr_current": 3000,
            "bsr_delta_7d": -0.35,
            "bsr_delta_30d": -0.25,
            "reviews_per_month": 55,
            "stockout_count_90d": 5,
            "price_trend_30d": 0.20,
            "seller_churn_90d": 3,
            "bsr_acceleration": 0.25,
        }

        result = self.scorer.score(product)
        velocity = result.component_scores["velocity"]

        assert velocity.score >= 20  # Au moins 80% du max

    def test_stagnant_product_penalty(self):
        """Un produit stagnant doit recevoir une pénalité."""
        product = {
            "product_id": "B09STAGNANT",
            "amazon_price": 25.00,
            "alibaba_price": 5.00,
            "bsr_current": 50000,
            "bsr_delta_7d": 0.02,    # Quasi stable
            "bsr_delta_30d": 0.03,   # Quasi stable
            "reviews_per_month": 3,  # Très faible
            "stockout_count_90d": 3,
        }

        result = self.scorer.score(product)
        velocity = result.component_scores["velocity"]

        assert velocity.details["is_stagnant"] is True
        assert velocity.details["sub_scores"]["stagnant_penalty"] < 0


class TestCompetitionScoring:
    """Tests pour le scoring COMPETITION."""

    def setup_method(self):
        self.scorer = OpportunityScorer()

    def test_amazon_basics_penalty(self):
        """La présence d'Amazon Basics doit pénaliser le score."""
        base_product = {
            "product_id": "B09NOAMAZON",
            "amazon_price": 25.00,
            "alibaba_price": 5.00,
            "seller_count": 5,
            "buybox_rotation": 0.30,
            "review_gap_vs_top10": 0.40,
            "has_amazon_basics": False,
            "stockout_count_90d": 3,
        }

        with_amazon = base_product.copy()
        with_amazon["product_id"] = "B09WITHAMAZON"
        with_amazon["has_amazon_basics"] = True

        result_without = self.scorer.score(base_product)
        result_with = self.scorer.score(with_amazon)

        diff = (
            result_without.component_scores["competition"].score -
            result_with.component_scores["competition"].score
        )

        assert diff == 4  # Pénalité de -4 pour Amazon Basics

    def test_open_market_high_score(self):
        """Un marché ouvert (peu de vendeurs, buy box instable) doit scorer haut."""
        product = {
            "product_id": "B09OPENMARKET",
            "amazon_price": 25.00,
            "alibaba_price": 5.00,
            "seller_count": 2,
            "buybox_rotation": 0.50,
            "review_gap_vs_top10": 0.25,
            "has_amazon_basics": False,
            "has_brand_dominance": False,
            "stockout_count_90d": 3,
        }

        result = self.scorer.score(product)
        competition = result.component_scores["competition"]

        assert competition.score >= 16  # Au moins 80% du max


class TestGapScoring:
    """Tests pour le scoring GAP."""

    def setup_method(self):
        self.scorer = OpportunityScorer()

    def test_recurring_problems_multiplier(self):
        """Les problèmes récurrents doivent amplifier le score."""
        base_product = {
            "product_id": "B09GAPTEST",
            "amazon_price": 25.00,
            "alibaba_price": 5.00,
            "negative_review_percent": 0.20,
            "wish_mentions_per_100": 8,
            "unanswered_questions": 15,
            "has_recurring_problems": False,
            "stockout_count_90d": 3,
        }

        with_recurring = base_product.copy()
        with_recurring["product_id"] = "B09RECURRING"
        with_recurring["has_recurring_problems"] = True

        result_without = self.scorer.score(base_product)
        result_with = self.scorer.score(with_recurring)

        # Le score avec problèmes récurrents doit être plus élevé
        assert (
            result_with.component_scores["gap"].score >
            result_without.component_scores["gap"].score
        )

    def test_gap_not_exceeding_max(self):
        """Le score GAP ne doit jamais dépasser le maximum (15 pts)."""
        product = {
            "product_id": "B09MAXGAP",
            "amazon_price": 25.00,
            "alibaba_price": 5.00,
            "negative_review_percent": 0.50,  # Très élevé
            "wish_mentions_per_100": 20,      # Très élevé
            "unanswered_questions": 50,       # Très élevé
            "has_recurring_problems": True,   # Multiplicateur
            "stockout_count_90d": 3,
        }

        result = self.scorer.score(product)
        gap = result.component_scores["gap"]

        assert gap.score <= gap.max_score


class TestWindowEstimation:
    """Tests pour l'estimation de fenêtre temporelle."""

    def setup_method(self):
        self.scorer = OpportunityScorer()

    def test_high_time_pressure_short_window(self):
        """Time pressure élevé = fenêtre courte."""
        window, days = self.scorer.estimate_window(9)
        assert "CRITIQUE" in window
        assert days <= 14

    def test_medium_time_pressure_medium_window(self):
        """Time pressure moyen = fenêtre moyenne."""
        window, days = self.scorer.estimate_window(5)
        assert "COURT TERME" in window
        assert 30 <= days <= 60

    def test_low_time_pressure_no_window(self):
        """Time pressure insuffisant = pas de fenêtre."""
        window, days = self.scorer.estimate_window(2)
        assert "PAS DE FENÊTRE" in window
        assert days == 0


class TestBatchScoring:
    """Tests pour le scoring en batch."""

    def setup_method(self):
        self.scorer = OpportunityScorer()
        self.products = [
            {
                "product_id": "B09PRODUCT1",
                "amazon_price": 30.00,
                "alibaba_price": 4.00,
                "bsr_current": 5000,
                "bsr_delta_7d": -0.20,
                "reviews_per_month": 40,
                "seller_count": 3,
                "buybox_rotation": 0.40,
                "review_gap_vs_top10": 0.30,
                "negative_review_percent": 0.18,
                "wish_mentions_per_100": 8,
                "unanswered_questions": 15,
                "stockout_count_90d": 4,
                "price_trend_30d": 0.10,
                "seller_churn_90d": 2,
                "bsr_acceleration": 0.15,
            },
            {
                "product_id": "B09PRODUCT2",
                "amazon_price": 20.00,
                "alibaba_price": 6.00,
                "bsr_current": 80000,
                "bsr_delta_7d": 0.10,
                "reviews_per_month": 5,
                "seller_count": 15,
                "buybox_rotation": 0.05,
                "review_gap_vs_top10": 0.80,
                "negative_review_percent": 0.05,
                "wish_mentions_per_100": 1,
                "unanswered_questions": 2,
                "stockout_count_90d": 0,
                "price_trend_30d": -0.08,
                "seller_churn_90d": 0,
                "bsr_acceleration": -0.05,
            },
        ]

    def test_batch_sorting(self):
        """Le batch doit être trié par validité puis score décroissant."""
        results = self.scorer.score_batch(self.products)

        # Vérifier que les valides sont en premier
        valid_indices = [i for i, r in enumerate(results) if r.is_valid]
        invalid_indices = [i for i, r in enumerate(results) if not r.is_valid]

        if valid_indices and invalid_indices:
            assert max(valid_indices) < min(invalid_indices)

    def test_get_top_opportunities(self):
        """get_top_opportunities doit filtrer correctement."""
        # Ajouter un 3ème produit valide mais faible
        self.products.append({
            "product_id": "B09PRODUCT3",
            "amazon_price": 25.00,
            "alibaba_price": 5.00,
            "stockout_count_90d": 3,
            "price_trend_30d": 0.05,
        })

        top = self.scorer.get_top_opportunities(self.products, n=2, min_score=50)

        assert len(top) <= 2
        for result in top:
            assert result.is_valid
            assert result.total_score >= 50


class TestConfigValidation:
    """Tests pour la validation de configuration."""

    def test_default_config_valid(self):
        """La configuration par défaut doit être valide."""
        config = ScoringConfig()
        assert config.validate() is True

    def test_max_points_sum_to_100(self):
        """La somme des points max doit égaler 100."""
        config = DEFAULT_CONFIG
        total = (
            config.margin.max_points +
            config.velocity.max_points +
            config.competition.max_points +
            config.gap.max_points +
            config.time_pressure.max_points
        )
        assert total == 100


def run_tests():
    """Execute all tests manually (no pytest required)."""
    test_classes = [
        TestScoringDeterminism,
        TestTimePressureCriticalRule,
        TestMarginScoring,
        TestVelocityScoring,
        TestCompetitionScoring,
        TestGapScoring,
        TestWindowEstimation,
        TestBatchScoring,
        TestConfigValidation,
    ]

    total_tests = 0
    passed_tests = 0
    failed_tests = []

    for test_class in test_classes:
        print(f"\n=== {test_class.__name__} ===")
        instance = test_class()

        # Get all test methods
        test_methods = [m for m in dir(instance) if m.startswith("test_")]

        for method_name in test_methods:
            total_tests += 1
            try:
                # Setup if exists
                if hasattr(instance, "setup_method"):
                    instance.setup_method()

                # Run test
                getattr(instance, method_name)()
                print(f"  {method_name}: PASSED")
                passed_tests += 1

            except AssertionError as e:
                print(f"  {method_name}: FAILED - {e}")
                failed_tests.append((test_class.__name__, method_name, str(e)))
            except Exception as e:
                print(f"  {method_name}: ERROR - {e}")
                failed_tests.append((test_class.__name__, method_name, str(e)))

    # Summary
    print("\n" + "=" * 60)
    print(f"RESULTS: {passed_tests}/{total_tests} tests passed")
    if failed_tests:
        print("\nFAILED TESTS:")
        for cls, method, error in failed_tests:
            print(f"  - {cls}.{method}: {error}")
    else:
        print("\nALL TESTS PASSED!")
    print("=" * 60)

    return len(failed_tests) == 0


if __name__ == "__main__":
    if HAS_PYTEST and len(sys.argv) > 1 and "--pytest" in sys.argv:
        pytest.main([__file__, "-v"])
    else:
        success = run_tests()
        sys.exit(0 if success else 1)
