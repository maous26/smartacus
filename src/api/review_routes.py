"""
Review Intelligence API Routes
================================

GET  /api/reviews/{asin}/profile — returns full ProductImprovementProfile as JSON.
POST /api/reviews/{asin}/backfill — fetch reviews from Outscraper and run analysis.
"""

import logging
import os
from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/reviews", tags=["Reviews"])


class DefectSignalResponse(BaseModel):
    defect_type: str
    frequency: int
    severity_score: float
    frequency_rate: float
    example_quotes: List[str]


class FeatureRequestResponse(BaseModel):
    feature: str
    mentions: int
    confidence: float
    wish_strength: float
    source_quotes: List[str]


class ReviewProfileResponse(BaseModel):
    asin: str
    improvement_score: float
    dominant_pain: Optional[str] = None
    reviews_analyzed: int
    negative_reviews_analyzed: int
    reviews_ready: bool
    has_actionable_insights: bool
    thesis_fragment: str
    top_defects: List[DefectSignalResponse]
    missing_features: List[FeatureRequestResponse]


@router.get("/{asin}/profile", response_model=ReviewProfileResponse)
async def get_review_profile(asin: str):
    """Returns the full ProductImprovementProfile for an ASIN."""
    from . import db
    from .shared import load_profile

    try:
        pool = db.get_pool()
        conn = pool.getconn()
        try:
            profile = load_profile(conn, asin)
            if not profile:
                raise HTTPException(
                    status_code=404,
                    detail=f"No review data for ASIN {asin}.",
                )

            return ReviewProfileResponse(
                asin=profile.asin,
                improvement_score=profile.improvement_score,
                dominant_pain=profile.dominant_pain,
                reviews_analyzed=profile.reviews_analyzed,
                negative_reviews_analyzed=profile.negative_reviews_analyzed,
                reviews_ready=profile.reviews_ready,
                has_actionable_insights=profile.has_actionable_insights,
                thesis_fragment=profile.to_thesis_fragment(),
                top_defects=[
                    DefectSignalResponse(
                        defect_type=d.defect_type,
                        frequency=d.frequency,
                        severity_score=d.severity_score,
                        frequency_rate=d.frequency_rate,
                        example_quotes=d.example_quotes[:3],
                    )
                    for d in profile.top_defects
                ],
                missing_features=[
                    FeatureRequestResponse(
                        feature=f.feature,
                        mentions=f.mentions,
                        confidence=f.confidence,
                        wish_strength=f.wish_strength,
                        source_quotes=f.source_quotes[:3],
                    )
                    for f in profile.missing_features
                ],
            )
        finally:
            pool.putconn(conn)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Review profile fetch failed for {asin}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# BACKFILL ENDPOINT
# ============================================================================

class BackfillRequest(BaseModel):
    domain: str = "fr"
    force: bool = False  # Force refresh even if fresh reviews exist


class BackfillResponse(BaseModel):
    asin: str
    status: str  # "success", "pending", "skipped", "error"
    reviews_fetched: int
    reviews_inserted: int
    reviews_updated: int
    analysis_triggered: bool
    message: str
    profile: Optional[ReviewProfileResponse] = None


# Track in-progress backfills to avoid duplicates
_backfill_in_progress: set = set()


def _run_backfill_sync(asin: str, domain: str) -> dict:
    """
    Synchronous backfill function that fetches reviews via Outscraper and runs analysis.

    Args:
        asin: Amazon product ASIN
        domain: Amazon domain (fr, com, de, etc.)

    Returns dict with results.
    """
    from . import db
    from .shared import load_profile

    result = {
        "asin": asin,
        "reviews_fetched": 0,
        "reviews_inserted": 0,
        "reviews_updated": 0,
        "analysis_triggered": False,
        "error": None,
    }

    try:
        from src.data.outscraper_client import OutscraperClient, OutscraperError

        # Oxylabs credentials (env vars read inside OutscraperClient)
        if not os.getenv("OXYLABS_USERNAME") or not os.getenv("OXYLABS_PASSWORD"):
            result["error"] = "OXYLABS_USERNAME/OXYLABS_PASSWORD not configured"
            return result

        client = OutscraperClient()
        reviews = client.fetch_product_reviews(
            asin,
            domain=domain,
            max_reviews=15,
            target_negative=10,
            target_positive=5,
        )

        result["reviews_fetched"] = len(reviews)

        if not reviews:
            result["error"] = "No reviews found"
            return result

        # Save to database
        pool = db.get_pool()
        if not pool:
            result["error"] = "Database not available"
            return result

        conn = pool.getconn()
        try:
            with conn.cursor() as cur:
                for review in reviews:
                    # Upsert review (using correct column names from schema)
                    cur.execute("""
                        INSERT INTO reviews (
                            review_id, asin, title, body, rating, author_name,
                            review_date, helpful_votes, is_verified_purchase, captured_at
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                        ON CONFLICT (review_id) DO UPDATE SET
                            title = EXCLUDED.title,
                            body = EXCLUDED.body,
                            rating = EXCLUDED.rating,
                            helpful_votes = EXCLUDED.helpful_votes,
                            captured_at = NOW()
                        RETURNING (xmax = 0) AS inserted
                    """, (
                        review.review_id,
                        review.asin,
                        review.title,
                        review.content,  # maps to 'body' column
                        review.rating,
                        review.author,   # maps to 'author_name' column
                        review.date,     # maps to 'review_date' column
                        review.helpful_votes,
                        review.verified_purchase,  # maps to 'is_verified_purchase'
                    ))
                    row = cur.fetchone()
                    if row and row[0]:
                        result["reviews_inserted"] += 1
                    else:
                        result["reviews_updated"] += 1

                conn.commit()

            # Run Review Intelligence analysis
            from src.reviews import ReviewSignalExtractor, ReviewInsightAggregator

            extractor = ReviewSignalExtractor()
            aggregator = ReviewInsightAggregator()

            reviews_data = aggregator.load_reviews_from_db(conn, asin)
            if reviews_data:
                defects = extractor.extract_defects(reviews_data)
                wishes = extractor.extract_wish_patterns(reviews_data)
                negative_count = sum(1 for r in reviews_data if r.get("rating", 5) <= 3)

                profile = aggregator.build_profile(
                    asin=asin,
                    defects=defects,
                    wishes=wishes,
                    reviews_analyzed=len(reviews_data),
                    negative_reviews_analyzed=negative_count,
                )

                if profile.reviews_ready:
                    aggregator.save_profile(conn, profile, run_id=None)
                    conn.commit()
                    result["analysis_triggered"] = True
                    logger.info(
                        f"Review Intelligence: {asin}, score={profile.improvement_score:.3f}, "
                        f"{len(profile.top_defects)} defects, {len(profile.missing_features)} wishes"
                    )

        finally:
            pool.putconn(conn)

        return result

    except Exception as e:
        logger.error(f"Backfill error for {asin}: {e}")
        result["error"] = str(e)
        return result


@router.post("/{asin}/backfill", response_model=BackfillResponse)
async def backfill_reviews(
    asin: str,
    request: BackfillRequest = None,
    background_tasks: BackgroundTasks = None,
):
    """
    Fetch reviews for an ASIN from Outscraper and run Review Intelligence analysis.

    Uses star-filtered async API: 10 negative (1-3 stars) + 5 positive (4-5 stars).

    Args:
        asin: Amazon product ASIN
        domain: Amazon domain (fr, com, de, etc.) - default: fr
        force: Force refresh even if fresh reviews exist
    """
    from . import db
    from .shared import load_profile

    if request is None:
        request = BackfillRequest()

    # Check if already in progress
    if asin in _backfill_in_progress:
        return BackfillResponse(
            asin=asin,
            status="pending",
            reviews_fetched=0,
            reviews_inserted=0,
            reviews_updated=0,
            analysis_triggered=False,
            message="Backfill already in progress for this ASIN",
        )

    # Check if fresh reviews exist (< 24 hours)
    if not request.force:
        try:
            pool = db.get_pool()
            if pool:
                conn = pool.getconn()
                try:
                    with conn.cursor() as cur:
                        cur.execute("""
                            SELECT COUNT(*), MAX(fetched_at)
                            FROM reviews
                            WHERE asin = %s
                              AND fetched_at > NOW() - INTERVAL '24 hours'
                        """, (asin,))
                        count, last_fetch = cur.fetchone()

                        if count and count > 0:
                            # Fresh reviews exist, return existing profile
                            profile = load_profile(conn, asin)
                            profile_response = None
                            if profile:
                                profile_response = ReviewProfileResponse(
                                    asin=profile.asin,
                                    improvement_score=profile.improvement_score,
                                    dominant_pain=profile.dominant_pain,
                                    reviews_analyzed=profile.reviews_analyzed,
                                    negative_reviews_analyzed=profile.negative_reviews_analyzed,
                                    reviews_ready=profile.reviews_ready,
                                    has_actionable_insights=profile.has_actionable_insights,
                                    thesis_fragment=profile.to_thesis_fragment(),
                                    top_defects=[
                                        DefectSignalResponse(
                                            defect_type=d.defect_type,
                                            frequency=d.frequency,
                                            severity_score=d.severity_score,
                                            frequency_rate=d.frequency_rate,
                                            example_quotes=d.example_quotes[:3],
                                        )
                                        for d in profile.top_defects
                                    ],
                                    missing_features=[
                                        FeatureRequestResponse(
                                            feature=f.feature,
                                            mentions=f.mentions,
                                            confidence=f.confidence,
                                            wish_strength=f.wish_strength,
                                            source_quotes=f.source_quotes[:3],
                                        )
                                        for f in profile.missing_features
                                    ],
                                )

                            return BackfillResponse(
                                asin=asin,
                                status="skipped",
                                reviews_fetched=0,
                                reviews_inserted=0,
                                reviews_updated=0,
                                analysis_triggered=False,
                                message=f"Fresh reviews exist ({count} reviews, last fetch: {last_fetch})",
                                profile=profile_response,
                            )
                finally:
                    pool.putconn(conn)
        except Exception as e:
            logger.warning(f"Failed to check fresh reviews: {e}")

    # Mark as in progress
    _backfill_in_progress.add(asin)

    try:
        # Run backfill synchronously via Outscraper
        result = _run_backfill_sync(asin, request.domain)

        if result.get("error"):
            return BackfillResponse(
                asin=asin,
                status="error",
                reviews_fetched=result["reviews_fetched"],
                reviews_inserted=result["reviews_inserted"],
                reviews_updated=result["reviews_updated"],
                analysis_triggered=result["analysis_triggered"],
                message=f"Error: {result['error']}",
            )

        # Load updated profile
        profile_response = None
        try:
            pool = db.get_pool()
            if pool:
                conn = pool.getconn()
                try:
                    profile = load_profile(conn, asin)
                    if profile:
                        profile_response = ReviewProfileResponse(
                            asin=profile.asin,
                            improvement_score=profile.improvement_score,
                            dominant_pain=profile.dominant_pain,
                            reviews_analyzed=profile.reviews_analyzed,
                            negative_reviews_analyzed=profile.negative_reviews_analyzed,
                            reviews_ready=profile.reviews_ready,
                            has_actionable_insights=profile.has_actionable_insights,
                            thesis_fragment=profile.to_thesis_fragment(),
                            top_defects=[
                                DefectSignalResponse(
                                    defect_type=d.defect_type,
                                    frequency=d.frequency,
                                    severity_score=d.severity_score,
                                    frequency_rate=d.frequency_rate,
                                    example_quotes=d.example_quotes[:3],
                                )
                                for d in profile.top_defects
                            ],
                            missing_features=[
                                FeatureRequestResponse(
                                    feature=f.feature,
                                    mentions=f.mentions,
                                    confidence=f.confidence,
                                    wish_strength=f.wish_strength,
                                    source_quotes=f.source_quotes[:3],
                                )
                                for f in profile.missing_features
                            ],
                        )
                finally:
                    pool.putconn(conn)
        except Exception as e:
            logger.warning(f"Failed to load profile after backfill: {e}")

        return BackfillResponse(
            asin=asin,
            status="success",
            reviews_fetched=result["reviews_fetched"],
            reviews_inserted=result["reviews_inserted"],
            reviews_updated=result["reviews_updated"],
            analysis_triggered=result["analysis_triggered"],
            message=f"Fetched {result['reviews_fetched']} reviews, inserted {result['reviews_inserted']}, updated {result['reviews_updated']}",
            profile=profile_response,
        )

    finally:
        # Remove from in-progress set
        _backfill_in_progress.discard(asin)
