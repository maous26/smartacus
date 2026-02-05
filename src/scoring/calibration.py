"""
Smartacus Scoring Calibration Infrastructure
=============================================

Tools for validating and tuning scoring thresholds against known outcomes.

USAGE:
    from src.scoring.calibration import CalibrationRunner, CalibrationCase

    # Define known outcomes
    cases = [
        CalibrationCase(
            product_data={...},
            expected_status="strong",
            expected_score_range=(65, 85),
            notes="Known successful product Q3 2024",
        ),
        ...
    ]

    runner = CalibrationRunner()
    report = runner.run(cases)
    print(report.summary())

This module does NOT modify thresholds automatically.
It produces a diagnostic report that a human uses to tune scoring_config.py.
"""

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .opportunity_scorer import OpportunityScorer, ScoringResult, OpportunityStatus
from .scoring_config import ScoringConfig, DEFAULT_CONFIG

logger = logging.getLogger(__name__)


@dataclass
class CalibrationCase:
    """
    A single calibration case: product data + expected outcome.

    Represents a "ground truth" observation — a product whose real-world
    performance is known, used to validate scoring accuracy.
    """
    product_data: Dict[str, Any]
    expected_status: str                       # "exceptional", "strong", "moderate", "weak", "rejected"
    expected_score_range: Tuple[int, int]       # (min, max) expected total score
    notes: str = ""
    tags: List[str] = field(default_factory=list)  # e.g. ["q4_2024", "verified"]


@dataclass
class CaseResult:
    """Result of evaluating one calibration case."""
    case: CalibrationCase
    actual_result: ScoringResult
    score_in_range: bool
    status_match: bool
    score_delta: int        # actual - midpoint of expected range
    component_deltas: Dict[str, int] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return self.score_in_range and self.status_match


@dataclass
class CalibrationReport:
    """Aggregated calibration report."""
    config_used: str
    run_at: str
    total_cases: int
    passed: int
    failed: int
    results: List[CaseResult]
    component_stats: Dict[str, Dict[str, float]] = field(default_factory=dict)

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total_cases if self.total_cases > 0 else 0.0

    def summary(self) -> str:
        """Human-readable summary."""
        lines = [
            "=" * 60,
            "SMARTACUS CALIBRATION REPORT",
            "=" * 60,
            f"Run at:      {self.run_at}",
            f"Cases:       {self.total_cases}",
            f"Passed:      {self.passed} ({self.pass_rate:.0%})",
            f"Failed:      {self.failed}",
            "",
        ]

        # Component-level stats
        if self.component_stats:
            lines.append("--- Component Accuracy ---")
            for comp, stats in sorted(self.component_stats.items()):
                lines.append(
                    f"  {comp:15s}  avg_delta={stats['avg_delta']:+.1f}  "
                    f"std={stats['std_delta']:.1f}  "
                    f"bias={'HIGH' if stats['avg_delta'] > 2 else 'LOW' if stats['avg_delta'] < -2 else 'OK'}"
                )
            lines.append("")

        # Failed cases detail
        failed_cases = [r for r in self.results if not r.passed]
        if failed_cases:
            lines.append("--- Failed Cases ---")
            for r in failed_cases:
                pid = r.case.product_data.get("product_id", "?")
                expected_range = r.case.expected_score_range
                lines.append(
                    f"  {pid}: score={r.actual_result.total_score} "
                    f"expected=[{expected_range[0]}-{expected_range[1]}] "
                    f"status={r.actual_result.status.value} "
                    f"expected_status={r.case.expected_status}"
                )
                if r.case.notes:
                    lines.append(f"    notes: {r.case.notes}")
            lines.append("")

        lines.append("=" * 60)
        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        """Serializable dict for JSON export."""
        return {
            "config_used": self.config_used,
            "run_at": self.run_at,
            "total_cases": self.total_cases,
            "passed": self.passed,
            "failed": self.failed,
            "pass_rate": round(self.pass_rate, 3),
            "component_stats": self.component_stats,
            "failed_cases": [
                {
                    "product_id": r.case.product_data.get("product_id", "?"),
                    "actual_score": r.actual_result.total_score,
                    "expected_range": list(r.case.expected_score_range),
                    "actual_status": r.actual_result.status.value,
                    "expected_status": r.case.expected_status,
                    "score_delta": r.score_delta,
                    "notes": r.case.notes,
                }
                for r in self.results if not r.passed
            ],
        }


class CalibrationRunner:
    """
    Runs calibration cases against the scoring engine.

    Does NOT modify any configuration. Produces a read-only report
    that helps identify scoring drift or miscalibration.
    """

    def __init__(self, config: Optional[ScoringConfig] = None):
        self.config = config or DEFAULT_CONFIG
        self.scorer = OpportunityScorer(self.config)

    def run(self, cases: List[CalibrationCase]) -> CalibrationReport:
        """
        Run all calibration cases and produce a report.

        Args:
            cases: List of CalibrationCase with known expected outcomes.

        Returns:
            CalibrationReport with pass/fail details and diagnostics.
        """
        results: List[CaseResult] = []

        for case in cases:
            result = self.scorer.score(case.product_data)

            # Check score range
            lo, hi = case.expected_score_range
            score_in_range = lo <= result.total_score <= hi

            # Check status
            status_match = result.status.value == case.expected_status

            # Delta from midpoint
            midpoint = (lo + hi) // 2
            score_delta = result.total_score - midpoint

            # Component deltas (if expected sub-scores provided)
            component_deltas = {}
            expected_components = case.product_data.get("_expected_components", {})
            for comp_name, expected_score in expected_components.items():
                actual_comp = result.component_scores.get(comp_name)
                if actual_comp:
                    component_deltas[comp_name] = actual_comp.score - expected_score

            results.append(CaseResult(
                case=case,
                actual_result=result,
                score_in_range=score_in_range,
                status_match=status_match,
                score_delta=score_delta,
                component_deltas=component_deltas,
            ))

        # Aggregate component stats
        component_stats = self._compute_component_stats(results)

        passed = sum(1 for r in results if r.passed)
        failed = len(results) - passed

        return CalibrationReport(
            config_used="DEFAULT_CONFIG",
            run_at=datetime.now(timezone.utc).isoformat(),
            total_cases=len(results),
            passed=passed,
            failed=failed,
            results=results,
            component_stats=component_stats,
        )

    def _compute_component_stats(
        self, results: List[CaseResult]
    ) -> Dict[str, Dict[str, float]]:
        """Compute per-component bias and variance."""
        from collections import defaultdict
        import math

        comp_deltas: Dict[str, List[int]] = defaultdict(list)

        for r in results:
            for comp_name, delta in r.component_deltas.items():
                comp_deltas[comp_name].append(delta)

        stats = {}
        for comp_name, deltas in comp_deltas.items():
            if not deltas:
                continue
            avg = sum(deltas) / len(deltas)
            variance = sum((d - avg) ** 2 for d in deltas) / len(deltas)
            stats[comp_name] = {
                "avg_delta": round(avg, 2),
                "std_delta": round(math.sqrt(variance), 2),
                "n": len(deltas),
            }

        return stats

    def save_report(self, report: CalibrationReport, path: Path) -> None:
        """Save calibration report to JSON file."""
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(report.to_dict(), f, indent=2)
        logger.info(f"Calibration report saved to {path}")


# ============================================================================
# BUILT-IN CALIBRATION CASES (Car Phone Mounts niche)
# ============================================================================

NICHE_CALIBRATION_CASES: List[CalibrationCase] = [
    CalibrationCase(
        product_data={
            "product_id": "CAL_EXCEPTIONAL_01",
            "amazon_price": 29.99,
            "alibaba_price": 4.50,
            "shipping_per_unit": 3.00,
            "bsr_current": 8500,
            "bsr_delta_7d": -0.20,
            "bsr_delta_30d": -0.10,
            "reviews_per_month": 35,
            "seller_count": 4,
            "buybox_rotation": 0.35,
            "review_gap_vs_top10": 0.40,
            "negative_review_percent": 0.18,
            "wish_mentions_per_100": 7,
            "unanswered_questions": 12,
            "has_recurring_problems": True,
            "stockout_count_90d": 4,
            "price_trend_30d": 0.08,
            "seller_churn_90d": 2,
            "bsr_acceleration": 0.15,
        },
        expected_status="strong",
        expected_score_range=(68, 80),
        notes="Top-performing mount with strong demand signals and supply gaps",
        tags=["anchor", "niche_typical"],
    ),
    CalibrationCase(
        product_data={
            "product_id": "CAL_STRONG_01",
            "amazon_price": 24.99,
            "alibaba_price": 5.00,
            "shipping_per_unit": 3.50,
            "bsr_current": 15000,
            "bsr_delta_7d": -0.10,
            "bsr_delta_30d": -0.08,
            "reviews_per_month": 25,
            "seller_count": 6,
            "buybox_rotation": 0.25,
            "review_gap_vs_top10": 0.45,
            "negative_review_percent": 0.14,
            "wish_mentions_per_100": 5,
            "unanswered_questions": 8,
            "has_recurring_problems": False,
            "stockout_count_90d": 2,
            "price_trend_30d": 0.05,
            "seller_churn_90d": 1,
            "bsr_acceleration": 0.08,
        },
        expected_status="weak",
        expected_score_range=(48, 58),
        notes="Solid opportunity with decent margins and moderate urgency",
        tags=["anchor", "niche_typical"],
    ),
    CalibrationCase(
        product_data={
            "product_id": "CAL_MODERATE_01",
            "amazon_price": 19.99,
            "alibaba_price": 4.00,
            "shipping_per_unit": 3.50,
            "bsr_current": 35000,
            "bsr_delta_7d": -0.05,
            "bsr_delta_30d": 0.02,
            "reviews_per_month": 12,
            "seller_count": 8,
            "buybox_rotation": 0.15,
            "review_gap_vs_top10": 0.55,
            "negative_review_percent": 0.10,
            "wish_mentions_per_100": 3,
            "unanswered_questions": 5,
            "has_recurring_problems": False,
            "stockout_count_90d": 2,
            "price_trend_30d": 0.03,
            "seller_churn_90d": 1,
            "bsr_acceleration": 0.08,
        },
        expected_status="weak",
        expected_score_range=(35, 50),
        notes="Marginal opportunity — needs deeper analysis before acting",
        tags=["anchor", "niche_typical"],
    ),
    CalibrationCase(
        product_data={
            "product_id": "CAL_REJECTED_NO_WINDOW",
            "amazon_price": 24.99,
            "alibaba_price": 3.50,
            "shipping_per_unit": 2.50,
            "bsr_current": 12000,
            "bsr_delta_7d": -0.10,
            "bsr_delta_30d": -0.05,
            "reviews_per_month": 25,
            "seller_count": 6,
            "buybox_rotation": 0.25,
            "review_gap_vs_top10": 0.35,
            "negative_review_percent": 0.12,
            "wish_mentions_per_100": 4,
            "unanswered_questions": 8,
            "has_recurring_problems": False,
            "stockout_count_90d": 0,
            "price_trend_30d": -0.05,
            "seller_churn_90d": 0,
            "bsr_acceleration": 0.0,
        },
        expected_status="invalid_no_window",
        expected_score_range=(55, 75),
        notes="Good product but NO urgency signals — time_pressure < 3 rule kicks in",
        tags=["anchor", "rejection_rule"],
    ),
    CalibrationCase(
        product_data={
            "product_id": "CAL_WEAK_01",
            "amazon_price": 14.99,
            "alibaba_price": 5.00,
            "shipping_per_unit": 4.00,
            "bsr_current": 80000,
            "bsr_delta_7d": 0.05,
            "bsr_delta_30d": 0.10,
            "reviews_per_month": 3,
            "seller_count": 15,
            "buybox_rotation": 0.08,
            "review_gap_vs_top10": 0.75,
            "negative_review_percent": 0.06,
            "wish_mentions_per_100": 1,
            "unanswered_questions": 2,
            "has_recurring_problems": False,
            "stockout_count_90d": 1,
            "price_trend_30d": 0.02,
            "seller_churn_90d": 1,
            "bsr_acceleration": 0.03,
        },
        expected_status="rejected",
        expected_score_range=(10, 25),
        notes="Low-margin, saturated market, low velocity — not worth pursuing",
        tags=["anchor", "niche_typical"],
    ),
]
