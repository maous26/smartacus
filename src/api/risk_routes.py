"""
Risk Journal API Routes
=======================

Endpoints for tracking user risk overrides.

Philosophy: "Les gens prendront des risques. Le rôle du système n'est pas
de les infantiliser, mais de rendre le risque conscient et traçable."
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timedelta
import logging

from . import db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/risk", tags=["Risk Journal"])


# ============================================================================
# MODELS
# ============================================================================

class RiskOverrideCreate(BaseModel):
    """Request to log a risk override."""
    asin: str = Field(..., min_length=10, max_length=10)
    confidence_level: str = Field(..., pattern="^(eclaire|incomplet|fragile)$")
    confidence_score: Optional[float] = Field(None, ge=0, le=1)
    hypothesis: str = Field(..., min_length=3, max_length=500)
    hypothesis_reason: str = Field(
        ...,
        pattern="^(product_improvement|marketing_advantage|low_volume_test|market_knowledge|other)$"
    )
    missing_info: List[str] = Field(default_factory=list)
    run_id: Optional[str] = None
    user_id: Optional[str] = "default"


class RiskOverrideResponse(BaseModel):
    """Response after creating a risk override."""
    id: str
    asin: str
    hypothesis: str
    confidence_level: str
    created_at: str
    message: str


class RiskOverrideOutcome(BaseModel):
    """Request to record outcome of a risk override."""
    outcome: str = Field(..., pattern="^(success|partial|failure|abandoned)$")
    notes: Optional[str] = None


class RiskOverrideSummary(BaseModel):
    """Summary of a risk override for listing."""
    id: str
    asin: str
    confidence_level: str
    hypothesis: str
    hypothesis_reason: str
    outcome: Optional[str]
    created_at: str
    outcome_recorded_at: Optional[str]


# ============================================================================
# ENDPOINTS
# ============================================================================

@router.post("/overrides", response_model=RiskOverrideResponse)
async def create_risk_override(override: RiskOverrideCreate):
    """
    Log a risk override when user proceeds despite incomplete analysis.

    This does NOT validate the decision - it records it for audit.
    """
    pool = db.get_pool()
    if pool is None:
        raise HTTPException(status_code=503, detail="Database not available")

    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            # Verify ASIN exists
            cur.execute("SELECT 1 FROM asins WHERE asin = %s", (override.asin,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail=f"ASIN {override.asin} not found")

            # Insert override
            cur.execute("""
                INSERT INTO risk_overrides (
                    asin, run_id, user_id, confidence_level, confidence_score,
                    hypothesis, hypothesis_reason, missing_info
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id, created_at
            """, (
                override.asin,
                override.run_id,
                override.user_id or "default",
                override.confidence_level,
                override.confidence_score,
                override.hypothesis,
                override.hypothesis_reason,
                override.missing_info,
            ))

            row = cur.fetchone()
            conn.commit()

            logger.info(
                f"Risk override logged: {override.asin} "
                f"[{override.confidence_level}] - {override.hypothesis_reason}"
            )

            return RiskOverrideResponse(
                id=str(row[0]),
                asin=override.asin,
                hypothesis=override.hypothesis,
                confidence_level=override.confidence_level,
                created_at=row[1].isoformat(),
                message="Décision enregistrée. Vous assumez ce risque en connaissance de cause.",
            )
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        logger.error(f"Error creating risk override: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        pool.putconn(conn)


@router.get("/overrides", response_model=List[RiskOverrideSummary])
async def list_risk_overrides(
    user_id: str = Query("default", description="Filter by user"),
    limit: int = Query(50, ge=1, le=200),
    confidence_level: Optional[str] = Query(None, description="Filter by confidence level"),
    has_outcome: Optional[bool] = Query(None, description="Filter by outcome recorded"),
):
    """
    List risk overrides for a user.

    Used for:
    - Audit trail
    - Post-mortem analysis
    - Learning from past decisions
    """
    pool = db.get_pool()
    if pool is None:
        raise HTTPException(status_code=503, detail="Database not available")

    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            query = """
                SELECT id, asin, confidence_level, hypothesis, hypothesis_reason,
                       outcome, created_at, outcome_recorded_at
                FROM risk_overrides
                WHERE user_id = %s
            """
            params = [user_id]

            if confidence_level:
                query += " AND confidence_level = %s"
                params.append(confidence_level)

            if has_outcome is not None:
                if has_outcome:
                    query += " AND outcome IS NOT NULL"
                else:
                    query += " AND outcome IS NULL"

            query += " ORDER BY created_at DESC LIMIT %s"
            params.append(limit)

            cur.execute(query, params)
            rows = cur.fetchall()

            return [
                RiskOverrideSummary(
                    id=str(row[0]),
                    asin=row[1],
                    confidence_level=row[2],
                    hypothesis=row[3],
                    hypothesis_reason=row[4],
                    outcome=row[5],
                    created_at=row[6].isoformat() if row[6] else None,
                    outcome_recorded_at=row[7].isoformat() if row[7] else None,
                )
                for row in rows
            ]
    except Exception as e:
        logger.error(f"Error listing risk overrides: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        pool.putconn(conn)


@router.get("/overrides/{asin}")
async def get_risk_overrides_for_asin(asin: str):
    """
    Get all risk overrides for a specific ASIN.

    Useful for understanding decision history on an opportunity.
    """
    pool = db.get_pool()
    if pool is None:
        raise HTTPException(status_code=503, detail="Database not available")

    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, user_id, confidence_level, confidence_score,
                       hypothesis, hypothesis_reason, missing_info,
                       outcome, outcome_notes, created_at, outcome_recorded_at
                FROM risk_overrides
                WHERE asin = %s
                ORDER BY created_at DESC
            """, (asin,))
            rows = cur.fetchall()

            return [
                {
                    "id": str(row[0]),
                    "user_id": row[1],
                    "confidence_level": row[2],
                    "confidence_score": float(row[3]) if row[3] else None,
                    "hypothesis": row[4],
                    "hypothesis_reason": row[5],
                    "missing_info": row[6] or [],
                    "outcome": row[7],
                    "outcome_notes": row[8],
                    "created_at": row[9].isoformat() if row[9] else None,
                    "outcome_recorded_at": row[10].isoformat() if row[10] else None,
                }
                for row in rows
            ]
    except Exception as e:
        logger.error(f"Error fetching risk overrides for {asin}: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        pool.putconn(conn)


@router.patch("/overrides/{override_id}/outcome")
async def record_outcome(override_id: str, outcome: RiskOverrideOutcome):
    """
    Record the outcome of a risk override decision.

    Called by user after enough time has passed to evaluate the decision.
    This is for learning, not judgment.
    """
    pool = db.get_pool()
    if pool is None:
        raise HTTPException(status_code=503, detail="Database not available")

    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE risk_overrides
                SET outcome = %s,
                    outcome_notes = %s,
                    outcome_recorded_at = NOW()
                WHERE id = %s
                RETURNING asin
            """, (outcome.outcome, outcome.notes, override_id))

            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Override not found")

            conn.commit()

            logger.info(f"Outcome recorded for override {override_id}: {outcome.outcome}")

            return {
                "message": "Outcome recorded",
                "override_id": override_id,
                "asin": row[0],
                "outcome": outcome.outcome,
            }
    except HTTPException:
        raise
    except Exception as e:
        conn.rollback()
        logger.error(f"Error recording outcome: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        pool.putconn(conn)


@router.get("/pending-postmortems")
async def get_pending_postmortems(
    user_id: str = Query("default"),
    days_threshold: int = Query(14, ge=7, le=30, description="Days since override to trigger reminder"),
):
    """
    Get risk overrides awaiting post-mortem feedback.

    V3.2: Post-mortem loop system.
    Returns overrides that:
    - Have no outcome recorded yet
    - Are older than `days_threshold` days (default: 14)

    Philosophy: Learning from decisions requires reflection.
    After 14 days, we ask: "Comment ça s'est passé?"
    """
    pool = db.get_pool()
    if pool is None:
        raise HTTPException(status_code=503, detail="Database not available")

    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            cutoff_date = datetime.utcnow() - timedelta(days=days_threshold)

            cur.execute("""
                SELECT ro.id, ro.asin, ro.confidence_level, ro.hypothesis,
                       ro.hypothesis_reason, ro.missing_info, ro.created_at,
                       a.title, a.brand
                FROM risk_overrides ro
                LEFT JOIN asins a ON ro.asin = a.asin
                WHERE ro.user_id = %s
                  AND ro.outcome IS NULL
                  AND ro.created_at <= %s
                ORDER BY ro.created_at ASC
            """, (user_id, cutoff_date))
            rows = cur.fetchall()

            return {
                "pending_count": len(rows),
                "days_threshold": days_threshold,
                "overrides": [
                    {
                        "id": str(row[0]),
                        "asin": row[1],
                        "confidence_level": row[2],
                        "hypothesis": row[3],
                        "hypothesis_reason": row[4],
                        "missing_info": row[5] or [],
                        "created_at": row[6].isoformat() if row[6] else None,
                        "days_ago": (datetime.utcnow() - row[6]).days if row[6] else None,
                        "product_title": row[7],
                        "product_brand": row[8],
                    }
                    for row in rows
                ],
                "message": f"{len(rows)} décision(s) en attente de retour d'expérience" if rows else "Aucun post-mortem en attente",
            }
    except Exception as e:
        logger.error(f"Error fetching pending postmortems: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        pool.putconn(conn)


@router.get("/stats")
async def get_risk_stats(user_id: str = Query("default")):
    """
    Get risk override statistics for a user.

    Useful for understanding decision patterns and outcomes.
    """
    pool = db.get_pool()
    if pool is None:
        raise HTTPException(status_code=503, detail="Database not available")

    conn = pool.getconn()
    try:
        with conn.cursor() as cur:
            # Total overrides by confidence level
            cur.execute("""
                SELECT confidence_level, COUNT(*) as count
                FROM risk_overrides
                WHERE user_id = %s
                GROUP BY confidence_level
            """, (user_id,))
            by_confidence = {row[0]: row[1] for row in cur.fetchall()}

            # Outcomes
            cur.execute("""
                SELECT outcome, COUNT(*) as count
                FROM risk_overrides
                WHERE user_id = %s AND outcome IS NOT NULL
                GROUP BY outcome
            """, (user_id,))
            by_outcome = {row[0]: row[1] for row in cur.fetchall()}

            # Hypothesis reasons
            cur.execute("""
                SELECT hypothesis_reason, COUNT(*) as count
                FROM risk_overrides
                WHERE user_id = %s
                GROUP BY hypothesis_reason
                ORDER BY count DESC
            """, (user_id,))
            by_reason = {row[0]: row[1] for row in cur.fetchall()}

            # Total
            cur.execute("""
                SELECT COUNT(*), COUNT(outcome)
                FROM risk_overrides
                WHERE user_id = %s
            """, (user_id,))
            totals = cur.fetchone()

            return {
                "total_overrides": totals[0],
                "outcomes_recorded": totals[1],
                "by_confidence_level": by_confidence,
                "by_outcome": by_outcome,
                "by_hypothesis_reason": by_reason,
                "success_rate": (
                    by_outcome.get("success", 0) / sum(by_outcome.values())
                    if by_outcome else None
                ),
            }
    except Exception as e:
        logger.error(f"Error fetching risk stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        pool.putconn(conn)
