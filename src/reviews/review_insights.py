"""
Review Insight Aggregator
==========================

Aggregates defect signals and feature requests into a single
ProductImprovementProfile per ASIN. This profile can be used
by the scoring engine (as a gap_score bonus) and by AI agents.

Usage:
    aggregator = ReviewInsightAggregator()
    profile = aggregator.build_profile(asin, defects, wishes, reviews_meta)
    aggregator.save_profile(conn, profile, run_id)
"""

import json
import logging
from typing import List, Optional, Dict

from .review_models import (
    DefectSignal,
    FeatureRequest,
    ProductImprovementProfile,
)

logger = logging.getLogger(__name__)


class ReviewInsightAggregator:
    """
    Aggregates review signals into per-ASIN improvement profiles.

    The improvement_score is designed to be used as a ranking bonus
    (NOT injected into the base_score, to respect the 15-point gap cap).
    """

    def build_profile(
        self,
        asin: str,
        defects: List[DefectSignal],
        wishes: List[FeatureRequest],
        reviews_analyzed: int = 0,
        negative_reviews_analyzed: int = 0,
    ) -> ProductImprovementProfile:
        """
        Build an improvement profile from extracted signals.

        improvement_score formula:
            weighted_avg(defect_severities) * frequency_coverage + wish_bonus

        The score ranges 0.0–1.0 where:
            > 0.7 = strong improvement opportunity (clear, fixable defects)
            > 0.4 = moderate opportunity
            < 0.4 = limited differentiation potential
        """
        if not defects and not wishes:
            return ProductImprovementProfile(
                asin=asin,
                top_defects=[],
                missing_features=[],
                dominant_pain=None,
                improvement_score=0.0,
                reviews_analyzed=reviews_analyzed,
                negative_reviews_analyzed=negative_reviews_analyzed,
                reviews_ready=reviews_analyzed > 0,
            )

        # Top 5 defects by severity
        top_defects = defects[:5]

        # Top 5 wishes by mentions
        top_wishes = wishes[:5]

        # Dominant pain = highest severity defect
        dominant_pain = top_defects[0].defect_type if top_defects else None

        # Compute improvement_score
        if top_defects:
            # Weighted average of top defect severities (heavier weight for top defects)
            weights = [3, 2, 1.5, 1, 1][:len(top_defects)]
            weighted_sum = sum(d.severity_score * w for d, w in zip(top_defects, weights))
            weighted_avg = weighted_sum / sum(weights[:len(top_defects)])

            # Frequency coverage: what % of negative reviews have at least one defect
            if negative_reviews_analyzed > 0:
                total_defect_mentions = sum(d.frequency for d in top_defects)
                # Cap at 1.0 (reviews can have multiple defects)
                coverage = min(1.0, total_defect_mentions / negative_reviews_analyzed)
            else:
                coverage = 0.0

            defect_score = weighted_avg * (0.5 + 0.5 * coverage)
        else:
            defect_score = 0.0

        # Wish bonus: +0.1 per distinct wish with 3+ mentions, capped at 0.2
        wish_bonus = min(0.2, sum(0.1 for w in top_wishes if w.mentions >= 3))

        improvement_score = round(min(1.0, defect_score + wish_bonus), 3)

        return ProductImprovementProfile(
            asin=asin,
            top_defects=top_defects,
            missing_features=top_wishes,
            dominant_pain=dominant_pain,
            improvement_score=improvement_score,
            reviews_analyzed=reviews_analyzed,
            negative_reviews_analyzed=negative_reviews_analyzed,
            reviews_ready=reviews_analyzed > 0,
        )

    def save_profile(self, conn, profile: ProductImprovementProfile, run_id: Optional[str] = None):
        """Save profile and its constituent defects/wishes to DB."""
        try:
            with conn.cursor() as cur:
                # Save individual defects
                for defect in profile.top_defects:
                    cur.execute("""
                        INSERT INTO review_defects (
                            asin, run_id, defect_type, frequency, severity_score,
                            example_quotes, total_reviews_scanned, negative_reviews_scanned
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, (
                        profile.asin, run_id, defect.defect_type,
                        defect.frequency, defect.severity_score,
                        defect.example_quotes,
                        defect.total_reviews_scanned,
                        defect.negative_reviews_scanned,
                    ))

                # Save feature requests
                for wish in profile.missing_features:
                    cur.execute("""
                        INSERT INTO review_feature_requests (
                            asin, run_id, feature, mentions, confidence, source_quotes
                        ) VALUES (%s, %s, %s, %s, %s, %s)
                    """, (
                        profile.asin, run_id, wish.feature,
                        wish.mentions, wish.confidence,
                        wish.source_quotes,
                    ))

                # Save aggregated profile
                defects_json = json.dumps([
                    {"type": d.defect_type, "freq": d.frequency, "severity": d.severity_score}
                    for d in profile.top_defects
                ])
                features_json = json.dumps([
                    {"feature": f.feature, "mentions": f.mentions, "confidence": f.confidence}
                    for f in profile.missing_features
                ])

                cur.execute("""
                    INSERT INTO review_improvement_profiles (
                        asin, run_id, top_defects, missing_features,
                        dominant_pain, improvement_score,
                        reviews_analyzed, negative_reviews_analyzed,
                        reviews_ready
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (asin, run_id) DO UPDATE SET
                        top_defects = EXCLUDED.top_defects,
                        missing_features = EXCLUDED.missing_features,
                        dominant_pain = EXCLUDED.dominant_pain,
                        improvement_score = EXCLUDED.improvement_score,
                        reviews_analyzed = EXCLUDED.reviews_analyzed,
                        negative_reviews_analyzed = EXCLUDED.negative_reviews_analyzed,
                        reviews_ready = EXCLUDED.reviews_ready,
                        computed_at = NOW()
                """, (
                    profile.asin, run_id, defects_json, features_json,
                    profile.dominant_pain, profile.improvement_score,
                    profile.reviews_analyzed, profile.negative_reviews_analyzed,
                    profile.reviews_ready,
                ))

                conn.commit()
                logger.info(
                    f"Saved improvement profile for {profile.asin}: "
                    f"score={profile.improvement_score:.3f}, "
                    f"{len(profile.top_defects)} defects, "
                    f"{len(profile.missing_features)} wishes"
                )

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to save improvement profile for {profile.asin}: {e}")
            raise

    def load_reviews_from_db(self, conn, asin: str) -> List[Dict]:
        """Load reviews for an ASIN from the reviews table."""
        with conn.cursor() as cur:
            cur.execute("""
                SELECT review_id, body, rating, title, review_date
                FROM reviews
                WHERE asin = %s AND body IS NOT NULL AND body != ''
                ORDER BY review_date DESC
                LIMIT 500
            """, (asin,))
            rows = cur.fetchall()

        return [
            {
                "review_id": r[0],
                "body": r[1],
                "rating": float(r[2]) if r[2] else 5.0,
                "title": r[3],
                "review_date": r[4],
            }
            for r in rows
        ]
