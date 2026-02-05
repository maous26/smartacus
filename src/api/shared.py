"""
Shared data-loading helpers reused across route modules.
"""

import json
from typing import Optional


def load_profile(conn, asin: str):
    """Load or generate a ProductImprovementProfile for an ASIN.

    Looks in review_improvement_profiles first, falls back to on-the-fly
    extraction from raw reviews.  Returns None when no data exists.
    """
    from ..reviews.review_models import (
        DefectSignal, FeatureRequest, ProductImprovementProfile,
    )
    from ..reviews.review_insights import ReviewInsightAggregator
    from ..reviews.review_signals import ReviewSignalExtractor

    # Try stored profile first
    with conn.cursor() as cur:
        cur.execute("""
            SELECT top_defects, missing_features, dominant_pain,
                   improvement_score, reviews_analyzed, negative_reviews_analyzed,
                   reviews_ready
            FROM review_improvement_profiles
            WHERE asin = %s
            ORDER BY computed_at DESC
            LIMIT 1
        """, (asin,))
        row = cur.fetchone()

    if row:
        top_defects_raw = row[0] if isinstance(row[0], list) else json.loads(row[0] or "[]")
        features_raw = row[1] if isinstance(row[1], list) else json.loads(row[1] or "[]")

        defects = [
            DefectSignal(
                defect_type=d["type"], frequency=d.get("freq", 0),
                severity_score=d.get("severity", 0.0),
                example_quotes=[], total_reviews_scanned=row[4] or 0,
                negative_reviews_scanned=row[5] or 0,
            )
            for d in top_defects_raw
        ]
        features = [
            FeatureRequest(
                feature=f["feature"], mentions=f.get("mentions", 0),
                confidence=f.get("confidence", 0.0),
                wish_strength=f.get("mentions", 0) * 1.5,
            )
            for f in features_raw
        ]

        return ProductImprovementProfile(
            asin=asin, top_defects=defects, missing_features=features,
            dominant_pain=row[2], improvement_score=float(row[3]),
            reviews_analyzed=row[4] or 0, negative_reviews_analyzed=row[5] or 0,
            reviews_ready=row[6] or False,
        )

    # No stored profile — generate on-the-fly
    aggregator = ReviewInsightAggregator()
    reviews = aggregator.load_reviews_from_db(conn, asin)
    if not reviews:
        return None

    extractor = ReviewSignalExtractor()
    defects = extractor.extract_defects(reviews)
    wishes = extractor.extract_wish_patterns(reviews)
    neg_count = sum(1 for r in reviews if r.get("rating", 5) <= 3)

    return aggregator.build_profile(
        asin=asin, defects=defects, wishes=wishes,
        reviews_analyzed=len(reviews), negative_reviews_analyzed=neg_count,
    )
