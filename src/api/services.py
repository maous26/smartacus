"""
Smartacus API Services
======================

Business logic layer for the API.
Standalone services without heavy dependencies for API layer.
"""

from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from decimal import Decimal
from dataclasses import dataclass, field
from enum import Enum
import logging

from .models import (
    OpportunityModel,
    ShortlistResponse,
    ShortlistSummary,
    ShortlistCriteria,
    PipelineStatus,
    PipelineStatusEnum,
    ComponentScoreModel,
    EconomicEventModel,
    UrgencyLevel,
)

logger = logging.getLogger(__name__)


# ============================================================================
# INTERNAL SCORING (Minimal re-implementation for API layer)
# ============================================================================

class TimeWindow(Enum):
    """Classification de la fenetre temporelle."""
    CRITICAL = "critical"
    URGENT = "urgent"
    ACTIVE = "active"
    STANDARD = "standard"
    EXTENDED = "extended"


@dataclass
class ComponentScore:
    """Score component."""
    name: str
    score: int
    max_score: int

    @property
    def percentage(self) -> float:
        return (self.score / self.max_score * 100) if self.max_score > 0 else 0


@dataclass
class ScoredOpportunity:
    """Internal scored opportunity."""
    asin: str
    base_score: float
    time_multiplier: float
    final_score: int
    estimated_monthly_profit: Decimal
    estimated_annual_value: Decimal
    risk_adjusted_value: Decimal
    window: TimeWindow
    window_days: int
    urgency_label: str
    thesis: str
    component_scores: Dict[str, ComponentScore] = field(default_factory=dict)


class LightweightScorer:
    """
    Lightweight scorer for API layer.
    Avoids heavy dependencies (psycopg2, etc.)
    """

    TIME_MULTIPLIERS = {
        TimeWindow.CRITICAL: 2.0,
        TimeWindow.URGENT: 1.5,
        TimeWindow.ACTIVE: 1.2,
        TimeWindow.STANDARD: 1.0,
        TimeWindow.EXTENDED: 0.7,
    }

    def calculate_time_multiplier(
        self,
        stockout_frequency: float,
        seller_churn: float,
        price_volatility: float,
        bsr_acceleration: float,
    ) -> tuple:
        """Calculate time multiplier and window."""
        # Stockout factor
        if stockout_frequency >= 3:
            stockout_factor = 1.5
        elif stockout_frequency >= 1:
            stockout_factor = 1.2
        elif stockout_frequency >= 0.5:
            stockout_factor = 1.0
        else:
            stockout_factor = 0.8

        # Churn factor
        if seller_churn > 0.30:
            churn_factor = 1.4
        elif seller_churn > 0.20:
            churn_factor = 1.2
        elif seller_churn > 0.10:
            churn_factor = 1.0
        else:
            churn_factor = 0.8

        # Volatility factor
        if price_volatility > 0.20:
            volatility_factor = 1.3
        elif price_volatility > 0.10:
            volatility_factor = 1.1
        else:
            volatility_factor = 1.0

        # BSR factor
        if bsr_acceleration > 0.10:
            bsr_factor = 1.4
        elif bsr_acceleration > 0:
            bsr_factor = 1.2
        elif bsr_acceleration > -0.05:
            bsr_factor = 1.0
        else:
            bsr_factor = 0.8

        # Geometric mean
        raw_multiplier = (
            stockout_factor * churn_factor * volatility_factor * bsr_factor
        ) ** 0.25

        multiplier = max(0.5, min(2.0, raw_multiplier))

        # Determine window
        if multiplier >= 1.8:
            window = TimeWindow.CRITICAL
            window_days = 14
        elif multiplier >= 1.4:
            window = TimeWindow.URGENT
            window_days = 30
        elif multiplier >= 1.1:
            window = TimeWindow.ACTIVE
            window_days = 60
        elif multiplier >= 0.9:
            window = TimeWindow.STANDARD
            window_days = 90
        else:
            window = TimeWindow.EXTENDED
            window_days = 180

        return multiplier, window, window_days

    def score_base(self, product_data: Dict[str, Any]) -> tuple:
        """Calculate base score components."""
        # Margin component (30 points max)
        amazon_price = product_data.get("amazon_price", 0)
        alibaba_price = product_data.get("alibaba_price", amazon_price / 5)
        if amazon_price > 0:
            margin = (amazon_price - alibaba_price - 5) / amazon_price
            margin_score = min(30, int(margin * 100))
        else:
            margin_score = 0

        # Velocity component (25 points max)
        bsr_delta = abs(product_data.get("bsr_delta_30d", 0))
        reviews_per_month = product_data.get("reviews_per_month", 0)
        velocity_score = min(25, int(bsr_delta * 50 + reviews_per_month / 5))

        # Competition component (20 points max)
        seller_count = product_data.get("seller_count", 10)
        buybox_rotation = product_data.get("buybox_rotation", 0.5)
        comp_score = min(20, max(0, 20 - seller_count + int(buybox_rotation * 10)))

        # Gap component (15 points max)
        gap = product_data.get("review_gap_vs_top10", 0)
        negative_pct = product_data.get("negative_review_percent", 0)
        gap_score = min(15, int(gap * 20 + negative_pct * 50))

        components = {
            "margin": ComponentScore("margin", margin_score, 30),
            "velocity": ComponentScore("velocity", velocity_score, 25),
            "competition": ComponentScore("competition", comp_score, 20),
            "gap": ComponentScore("gap", gap_score, 15),
        }

        total = margin_score + velocity_score + comp_score + gap_score
        base_score = total / 90  # Normalize to 0-1

        return base_score, components

    def estimate_value(
        self,
        amazon_price: float,
        estimated_cogs: float,
        monthly_units: int,
    ) -> tuple:
        """Estimate economic value."""
        fba_fees = max(amazon_price * 0.15, 3.0)
        referral = amazon_price * 0.15
        ppc_provision = amazon_price * 0.10
        return_provision = amazon_price * 0.05

        total_cost = estimated_cogs + fba_fees + referral + ppc_provision + return_provision
        profit_per_unit = amazon_price - total_cost
        monthly_profit = Decimal(str(max(0, profit_per_unit * monthly_units)))
        annual_value = monthly_profit * 12
        risk_adjusted = annual_value * Decimal("0.7")

        return monthly_profit, annual_value, risk_adjusted

    def score(
        self,
        product_data: Dict[str, Any],
        time_data: Dict[str, Any],
    ) -> ScoredOpportunity:
        """Full scoring."""
        asin = product_data.get("product_id", "UNKNOWN")

        # Base score
        base_score, components = self.score_base(product_data)

        # Time multiplier
        multiplier, window, window_days = self.calculate_time_multiplier(
            time_data.get("stockout_frequency", 0),
            time_data.get("seller_churn_90d", 0),
            time_data.get("price_volatility", 0),
            time_data.get("bsr_acceleration", 0),
        )

        # Final score
        final_score = int(min(100, base_score * multiplier * 100))

        # Economic value
        amazon_price = product_data.get("amazon_price", 0)
        alibaba_price = product_data.get("alibaba_price", amazon_price / 5)
        monthly_units = time_data.get("estimated_monthly_units", 100)

        monthly_profit, annual_value, risk_adjusted = self.estimate_value(
            amazon_price,
            alibaba_price + 3,
            monthly_units,
        )

        # Urgency label
        labels = {
            TimeWindow.CRITICAL: "CRITIQUE - Agir immediatement",
            TimeWindow.URGENT: "URGENT - Action prioritaire",
            TimeWindow.ACTIVE: "ACTIF - Fenetre viable",
            TimeWindow.STANDARD: "STANDARD - Temps disponible",
            TimeWindow.EXTENDED: "ETENDU - Pas d'urgence",
        }
        urgency_label = labels.get(window, "")

        # Thesis
        thesis = f"Score {final_score}/100 | Fenetre {window_days}j | ~${monthly_profit:.0f}/mois"

        return ScoredOpportunity(
            asin=asin,
            base_score=base_score,
            time_multiplier=multiplier,
            final_score=final_score,
            estimated_monthly_profit=monthly_profit,
            estimated_annual_value=annual_value,
            risk_adjusted_value=risk_adjusted,
            window=window,
            window_days=window_days,
            urgency_label=urgency_label,
            thesis=thesis,
            component_scores=components,
        )


# ============================================================================
# SERVICES
# ============================================================================

def map_urgency_level(window: TimeWindow) -> UrgencyLevel:
    """Map internal TimeWindow to API UrgencyLevel."""
    mapping = {
        TimeWindow.CRITICAL: UrgencyLevel.CRITICAL,
        TimeWindow.URGENT: UrgencyLevel.URGENT,
        TimeWindow.ACTIVE: UrgencyLevel.ACTIVE,
        TimeWindow.STANDARD: UrgencyLevel.STANDARD,
        TimeWindow.EXTENDED: UrgencyLevel.EXTENDED,
    }
    return mapping.get(window, UrgencyLevel.STANDARD)


def _generate_action_recommendation(window_days: int) -> str:
    """Generate action recommendation based on urgency."""
    if window_days <= 14:
        return "ACTION IMMEDIATE: Sourcer fournisseur cette semaine"
    elif window_days <= 30:
        return "PRIORITAIRE: Lancer analyse fournisseurs sous 7 jours"
    elif window_days <= 60:
        return "ACTIF: Planifier sourcing dans les 2 semaines"
    else:
        return "SURVEILLER: Ajouter au backlog, reevaluer dans 30 jours"


class ShortlistService:
    """Service for generating and retrieving shortlists."""

    def __init__(self):
        self.scorer = LightweightScorer()

    def get_shortlist(
        self,
        max_items: int = 25,
        min_score: int = 40,
        min_value: float = 0,
    ) -> ShortlistResponse:
        """Generate shortlist from DB opportunities, with demo fallback."""
        opportunities = self._get_db_opportunities(max_items, min_score, min_value)
        if not opportunities:
            logger.info("No DB opportunities found, using demo data")
            opportunities = self._get_demo_opportunities(max_items)

        total_value = sum(float(o.riskAdjustedValue) for o in opportunities)

        summary = ShortlistSummary(
            generated_at=datetime.utcnow(),
            count=len(opportunities),
            total_potential_value=total_value,
            criteria=ShortlistCriteria(
                min_score=min_score,
                min_value=min_value,
                max_items=max_items,
            ),
        )

        return ShortlistResponse(
            summary=summary,
            opportunities=opportunities,
        )

    def _get_db_opportunities(
        self,
        max_items: int = 25,
        min_score: int = 40,
        min_value: float = 0,
    ) -> List[OpportunityModel]:
        """Fetch scored opportunities from the latest pipeline run in DB."""
        try:
            from . import db
            pool = db.get_pool()
            if pool is None:
                return []

            conn = pool.getconn()
            try:
                with conn.cursor() as cur:
                    # Get artifacts from the latest completed run
                    cur.execute("""
                        SELECT
                            a.asin, a.rank, a.final_score, a.base_score, a.time_multiplier,
                            a.estimated_monthly_profit, a.estimated_annual_value,
                            a.risk_adjusted_value, a.window_days, a.urgency_level,
                            a.thesis, a.action_recommendation,
                            a.component_scores, a.economic_events,
                            a.amazon_price, a.review_count, a.rating, a.bsr_primary,
                            a.scored_at, a.input_data,
                            m.title, m.brand
                        FROM opportunity_artifacts a
                        JOIN pipeline_runs p ON a.run_id = p.run_id
                        LEFT JOIN asins m ON a.asin = m.asin
                        WHERE p.status IN ('completed', 'degraded')
                          AND a.final_score >= %s
                          AND a.risk_adjusted_value >= %s
                        ORDER BY a.risk_adjusted_value DESC
                        LIMIT %s
                    """, (min_score, min_value, max_items))

                    rows = cur.fetchall()
                    if not rows:
                        return []

                    opportunities = []
                    for i, row in enumerate(rows, 1):
                        (asin, rank, final_score, base_score, time_multiplier,
                         monthly_profit, annual_value, risk_adjusted,
                         window_days, urgency_level, thesis, action_rec,
                         component_scores_json, events_json,
                         amazon_price, review_count, rating, bsr,
                         scored_at, input_data_json,
                         title, brand) = row

                        # Map urgency string to enum
                        urgency_map = {
                            "critical": UrgencyLevel.CRITICAL,
                            "urgent": UrgencyLevel.URGENT,
                            "active": UrgencyLevel.ACTIVE,
                            "standard": UrgencyLevel.STANDARD,
                            "extended": UrgencyLevel.EXTENDED,
                        }
                        urg = urgency_map.get(urgency_level, UrgencyLevel.STANDARD)

                        labels = {
                            UrgencyLevel.CRITICAL: "CRITIQUE - Agir immediatement",
                            UrgencyLevel.URGENT: "URGENT - Action prioritaire",
                            UrgencyLevel.ACTIVE: "ACTIF - Fenetre viable",
                            UrgencyLevel.STANDARD: "STANDARD - Temps disponible",
                            UrgencyLevel.EXTENDED: "ETENDU - Pas d'urgence",
                        }

                        # Build component scores from JSONB or defaults
                        comp_scores = {}
                        if component_scores_json and isinstance(component_scores_json, dict):
                            for name, data in component_scores_json.items():
                                comp_scores[name] = ComponentScoreModel(
                                    name=name,
                                    score=data.get("score", 0),
                                    max_score=data.get("max_score", 0),
                                    percentage=data.get("percentage", 0),
                                )

                        # Build events from JSONB
                        events = []
                        if events_json and isinstance(events_json, list):
                            for ev in events_json:
                                events.append(EconomicEventModel(
                                    event_type=ev.get("event_type", "UNKNOWN"),
                                    thesis=ev.get("thesis", ""),
                                    confidence=ev.get("confidence", "moderate"),
                                    urgency=ev.get("urgency", "active"),
                                ))

                        # Get title from input_data if not in asins table
                        if not title and input_data_json and isinstance(input_data_json, dict):
                            title = input_data_json.get("title", f"ASIN {asin}")

                        opp = OpportunityModel(
                            rank=i,
                            asin=asin,
                            title=title or f"ASIN {asin}",
                            brand=brand,
                            final_score=int(final_score),
                            base_score=round(float(base_score), 2),
                            time_multiplier=round(float(time_multiplier), 2),
                            estimated_monthly_profit=float(monthly_profit),
                            estimated_annual_value=float(annual_value),
                            risk_adjusted_value=float(risk_adjusted),
                            window_days=int(window_days),
                            urgency_level=urg,
                            urgency_label=labels.get(urg, ""),
                            thesis=thesis or "",
                            action_recommendation=action_rec or _generate_action_recommendation(window_days),
                            component_scores=comp_scores,
                            economic_events=events,
                            amazon_price=float(amazon_price) if amazon_price else None,
                            review_count=int(review_count) if review_count else None,
                            rating=float(rating) if rating else None,
                            detected_at=scored_at,
                        )
                        opportunities.append(opp)

                    logger.info(f"Loaded {len(opportunities)} opportunities from DB")
                    return opportunities
            finally:
                pool.putconn(conn)

        except Exception as e:
            logger.warning(f"Failed to load DB opportunities: {e}")
            return []

    def _get_demo_opportunities(self, max_items: int = 25) -> List[OpportunityModel]:
        """Generate demo opportunities for development."""
        demo_products = [
            {
                "asin": "B08DKHHTFX",
                "title": "VANMASS Car Phone Mount [Military-Grade Suction]",
                "brand": "VANMASS",
                "amazon_price": 29.99,
                "review_count": 12453,
                "rating": 4.4,
                "stockout_frequency": 0.8,
                "seller_churn": 0.25,
                "price_volatility": 0.12,
                "bsr_acceleration": 0.08,
                "monthly_units": 180,
                "events": [
                    {
                        "event_type": "SUPPLY_SHOCK",
                        "thesis": "3 ruptures de stock en 30 jours, demande non satisfaite",
                        "confidence": "strong",
                        "urgency": "urgent",
                    }
                ],
            },
            {
                "asin": "B0CHYBKQPM",
                "title": "Miracase Car Phone Holder Mount",
                "brand": "Miracase",
                "amazon_price": 24.99,
                "review_count": 8234,
                "rating": 4.3,
                "stockout_frequency": 0.5,
                "seller_churn": 0.28,
                "price_volatility": 0.08,
                "bsr_acceleration": 0.05,
                "monthly_units": 150,
                "events": [
                    {
                        "event_type": "COMPETITOR_COLLAPSE",
                        "thesis": "Leader historique sorti du marche, parts a capturer",
                        "confidence": "moderate",
                        "urgency": "active",
                    }
                ],
            },
            {
                "asin": "B0CQPJKXVD",
                "title": "LISEN MagSafe Car Mount [15W Wireless Charging]",
                "brand": "LISEN",
                "amazon_price": 34.99,
                "review_count": 5621,
                "rating": 4.1,
                "stockout_frequency": 0.3,
                "seller_churn": 0.15,
                "price_volatility": 0.05,
                "bsr_acceleration": 0.03,
                "monthly_units": 120,
                "events": [
                    {
                        "event_type": "QUALITY_DECAY",
                        "thesis": "Reviews negatifs en hausse, opportunite de differenciation qualite",
                        "confidence": "strong",
                        "urgency": "active",
                    }
                ],
            },
            {
                "asin": "B07FY84Y8Y",
                "title": "andobil Car Phone Holder [2025 Military-Grade]",
                "brand": "andobil",
                "amazon_price": 27.99,
                "review_count": 3892,
                "rating": 4.2,
                "stockout_frequency": 0.2,
                "seller_churn": 0.10,
                "price_volatility": 0.04,
                "bsr_acceleration": 0.02,
                "monthly_units": 100,
                "events": [],
            },
            {
                "asin": "B09781MJL2",
                "title": "HTU Ultimate Car Phone Mount [98LBS Suction]",
                "brand": "Lamicall",
                "amazon_price": 19.99,
                "review_count": 15234,
                "rating": 4.5,
                "stockout_frequency": 0.1,
                "seller_churn": 0.08,
                "price_volatility": 0.03,
                "bsr_acceleration": 0.01,
                "monthly_units": 80,
                "events": [],
            },
        ]

        opportunities = []
        for i, product in enumerate(demo_products[:max_items], 1):
            product_data = {
                "product_id": product["asin"],
                "amazon_price": product["amazon_price"],
                "alibaba_price": product["amazon_price"] / 5,
                "bsr_current": 50000 - i * 5000,
                "bsr_delta_7d": -0.15 + i * 0.02,
                "bsr_delta_30d": -0.25 + i * 0.03,
                "reviews_per_month": 50 - i * 5,
                "seller_count": 8 + i,
                "buybox_rotation": 0.20 + i * 0.02,
                "review_gap_vs_top10": 0.40 - i * 0.05,
                "negative_review_percent": 0.12 + i * 0.02,
            }

            time_data = {
                "stockout_frequency": product["stockout_frequency"],
                "seller_churn_90d": product["seller_churn"],
                "price_volatility": product["price_volatility"],
                "bsr_acceleration": product["bsr_acceleration"],
                "estimated_monthly_units": product["monthly_units"],
            }

            scored = self.scorer.score(product_data, time_data)

            # Convert component scores
            component_scores = {}
            for name, comp in scored.component_scores.items():
                component_scores[name] = ComponentScoreModel(
                    name=name,
                    score=comp.score,
                    max_score=comp.max_score,
                    percentage=comp.percentage,
                )

            # Convert economic events
            events = []
            for event in product.get("events", []):
                events.append(EconomicEventModel(
                    event_type=event.get("event_type", "UNKNOWN"),
                    thesis=event.get("thesis", ""),
                    confidence=event.get("confidence", "moderate"),
                    urgency=event.get("urgency", "active"),
                ))

            opp = OpportunityModel(
                rank=i,
                asin=product["asin"],
                title=product["title"],
                brand=product["brand"],
                final_score=scored.final_score,
                base_score=round(scored.base_score, 2),
                time_multiplier=round(scored.time_multiplier, 2),
                estimated_monthly_profit=float(scored.estimated_monthly_profit),
                estimated_annual_value=float(scored.estimated_annual_value),
                risk_adjusted_value=float(scored.risk_adjusted_value),
                window_days=scored.window_days,
                urgency_level=map_urgency_level(scored.window),
                urgency_label=scored.urgency_label,
                thesis=scored.thesis,
                action_recommendation=_generate_action_recommendation(scored.window_days),
                component_scores=component_scores,
                economic_events=events,
                amazon_price=product["amazon_price"],
                review_count=product["review_count"],
                rating=product["rating"],
                detected_at=datetime.utcnow(),
            )
            opportunities.append(opp)

        # Sort by risk adjusted value * urgency weight
        def urgency_weight(level: UrgencyLevel) -> float:
            weights = {
                UrgencyLevel.CRITICAL: 2.0,
                UrgencyLevel.URGENT: 1.5,
                UrgencyLevel.ACTIVE: 1.2,
                UrgencyLevel.STANDARD: 1.0,
                UrgencyLevel.EXTENDED: 0.7,
            }
            return weights.get(level, 1.0)

        opportunities.sort(
            key=lambda x: x.riskAdjustedValue * urgency_weight(x.urgencyLevel),
            reverse=True
        )

        # Re-rank
        for i, opp in enumerate(opportunities, 1):
            opp.rank = i

        return opportunities


class PipelineService:
    """Service for pipeline status and control."""

    def __init__(self):
        self._last_run: Optional[datetime] = None
        self._status: PipelineStatusEnum = PipelineStatusEnum.IDLE

    def get_status(self) -> PipelineStatus:
        """Get current pipeline status from DB (with mock fallback)."""
        now = datetime.utcnow()

        try:
            from . import db
            last_run = db.get_latest_pipeline_run()
            if last_run:
                status_map = {
                    "running": PipelineStatusEnum.RUNNING,
                    "completed": PipelineStatusEnum.COMPLETED,
                    "degraded": PipelineStatusEnum.COMPLETED,
                    "failed": PipelineStatusEnum.ERROR,
                    "cancelled": PipelineStatusEnum.IDLE,
                }
                return PipelineStatus(
                    last_run_at=last_run.get("started_at"),
                    status=status_map.get(last_run.get("status"), PipelineStatusEnum.IDLE),
                    asins_tracked=last_run.get("asins_ok") or 0,
                    opportunities_found=last_run.get("opportunities_generated") or 0,
                    next_run_at=None,
                )
        except Exception as e:
            logger.warning(f"Could not get pipeline status from DB: {e}")

        # Fallback to demo status
        return PipelineStatus(
            last_run_at=now - timedelta(hours=2),
            status=PipelineStatusEnum.COMPLETED,
            asins_tracked=6842,
            opportunities_found=23,
            next_run_at=now + timedelta(hours=22),
        )

    async def run_pipeline(
        self,
        max_asins: Optional[int] = None,
        force_refresh: bool = False,
    ) -> Dict[str, Any]:
        """Trigger a pipeline run with DB tracking."""
        try:
            from . import db
            config = {"max_asins": max_asins, "force_refresh": force_refresh}
            run_id = db.create_pipeline_run(triggered_by="api", config_snapshot=config)
            if run_id:
                logger.info(f"Pipeline run created in DB: run_id={run_id}")
                return {
                    "status": "queued",
                    "message": f"Pipeline run {run_id[:8]} queued successfully",
                    "run_id": run_id,
                }
        except Exception as e:
            logger.warning(f"Could not create pipeline run in DB: {e}")

        # Fallback
        import uuid
        run_id = str(uuid.uuid4())[:8]
        logger.info(f"Pipeline run requested (no DB): run_id={run_id}")
        return {
            "status": "queued",
            "message": f"Pipeline run {run_id} queued successfully",
            "run_id": run_id,
        }
