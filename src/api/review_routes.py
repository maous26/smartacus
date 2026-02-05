"""
Review Intelligence API Routes
================================

GET /api/reviews/{asin}/profile — returns full ProductImprovementProfile as JSON.
"""

import logging
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional

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
