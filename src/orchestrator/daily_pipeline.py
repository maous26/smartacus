"""
Smartacus Daily Pipeline Orchestrator
=====================================

Orchestrates the daily execution of all Smartacus modules:
1. Data Ingestion (Keepa pull)
2. Event Detection
3. Opportunity Scoring
4. Notification preparation
5. Cleanup and maintenance

Features:
    - Idempotent execution (can be safely re-run)
    - Observable (detailed logging and metrics)
    - Resilient (graceful error handling, no crash on partial failure)

Usage:
    from src.orchestrator.daily_pipeline import DailyPipeline

    pipeline = DailyPipeline()
    result = pipeline.run()
"""

import uuid
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from contextlib import contextmanager
from enum import Enum

import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import pool

# Internal imports
from ..data.ingestion_pipeline import IngestionPipeline, DatabaseError
from ..data.config import get_settings
from ..scoring.opportunity_scorer import OpportunityScorer, ScoringResult, OpportunityStatus

# Configure logging
logger = logging.getLogger(__name__)


class PipelineStage(Enum):
    """Pipeline execution stages."""
    INGESTION = "ingestion"
    EVENT_DETECTION = "event_detection"
    SCORING = "scoring"
    NOTIFICATION = "notification"
    CLEANUP = "cleanup"


class PipelineStatus(Enum):
    """Pipeline run status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    PARTIAL_FAILURE = "partial_failure"
    FAILED = "failed"


@dataclass
class StageResult:
    """Result of a single pipeline stage."""
    stage: PipelineStage
    status: PipelineStatus
    started_at: datetime
    completed_at: Optional[datetime] = None
    metrics: Dict[str, Any] = field(default_factory=dict)
    errors: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def duration_seconds(self) -> Optional[float]:
        """Calculate stage duration."""
        if self.completed_at is None:
            return None
        return (self.completed_at - self.started_at).total_seconds()

    def add_error(self, error_type: str, message: str, details: Optional[Dict] = None):
        """Record an error."""
        self.errors.append({
            "type": error_type,
            "message": message,
            "details": details or {},
            "timestamp": datetime.utcnow().isoformat(),
        })


@dataclass
class PipelineResult:
    """Complete pipeline run result."""
    run_id: str
    status: PipelineStatus
    started_at: datetime
    completed_at: Optional[datetime] = None
    stages: Dict[PipelineStage, StageResult] = field(default_factory=dict)
    opportunities_found: int = 0
    opportunities_above_threshold: int = 0

    @property
    def duration_seconds(self) -> Optional[float]:
        """Calculate total pipeline duration."""
        if self.completed_at is None:
            return None
        return (self.completed_at - self.started_at).total_seconds()

    def get_summary(self) -> Dict[str, Any]:
        """Get pipeline run summary."""
        return {
            "run_id": self.run_id,
            "status": self.status.value,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_seconds": self.duration_seconds,
            "stages": {
                stage.value: {
                    "status": result.status.value,
                    "duration_seconds": result.duration_seconds,
                    "metrics": result.metrics,
                    "error_count": len(result.errors),
                }
                for stage, result in self.stages.items()
            },
            "opportunities_found": self.opportunities_found,
            "opportunities_above_threshold": self.opportunities_above_threshold,
        }


@dataclass
class Opportunity:
    """Opportunity record for database persistence."""
    asin: str
    score: int
    status: str
    window_days: int
    window_estimate: str
    component_scores: Dict[str, Dict]
    detected_at: datetime
    run_id: str


class DailyPipeline:
    """
    Daily pipeline orchestrator for Smartacus.

    Executes the complete daily workflow:
    1. INGESTION: Pull fresh data from Keepa
    2. EVENT_DETECTION: Detect significant events (price drops, BSR changes, etc.)
    3. SCORING: Calculate opportunity scores for ASINs with recent events
    4. NOTIFICATION: Prepare notifications for new opportunities
    5. CLEANUP: Refresh views, archive old data

    The pipeline is designed to be:
    - Idempotent: Can be run multiple times safely
    - Observable: Comprehensive logging and metrics
    - Resilient: Continues on partial failures, reports all errors
    """

    # Default scoring threshold (out of 100)
    DEFAULT_SCORE_THRESHOLD = 50

    # Maximum retries for transient failures
    MAX_RETRIES = 3

    def __init__(
        self,
        score_threshold: Optional[int] = None,
        db_pool: Optional[pool.ThreadedConnectionPool] = None,
    ):
        """
        Initialize the daily pipeline.

        Args:
            score_threshold: Minimum score to persist opportunity (default: 50)
            db_pool: Database connection pool (creates new if None)
        """
        self.settings = get_settings()
        self.score_threshold = score_threshold or self.DEFAULT_SCORE_THRESHOLD
        self._db_pool = db_pool
        self._own_pool = db_pool is None

        # Initialize components lazily
        self._ingestion_pipeline: Optional[IngestionPipeline] = None
        self._scorer: Optional[OpportunityScorer] = None

        # Current run state
        self._current_run_id: Optional[str] = None

        logger.info(
            f"DailyPipeline initialized: "
            f"score_threshold={self.score_threshold}"
        )

    @property
    def db_pool(self) -> pool.ThreadedConnectionPool:
        """Lazy-initialize database connection pool."""
        if self._db_pool is None:
            db_config = self.settings.database
            self._db_pool = pool.ThreadedConnectionPool(
                minconn=db_config.pool_min_size,
                maxconn=db_config.pool_max_size,
                **db_config.connection_dict
            )
            logger.info("Database connection pool created")
        return self._db_pool

    @property
    def ingestion_pipeline(self) -> IngestionPipeline:
        """Lazy-initialize ingestion pipeline."""
        if self._ingestion_pipeline is None:
            self._ingestion_pipeline = IngestionPipeline(db_pool=self.db_pool)
        return self._ingestion_pipeline

    @property
    def scorer(self) -> OpportunityScorer:
        """Lazy-initialize opportunity scorer."""
        if self._scorer is None:
            self._scorer = OpportunityScorer()
        return self._scorer

    @contextmanager
    def get_db_connection(self):
        """Get a database connection from the pool."""
        conn = None
        try:
            conn = self.db_pool.getconn()
            yield conn
            conn.commit()
        except Exception as e:
            if conn:
                conn.rollback()
            raise DatabaseError(f"Database operation failed: {e}") from e
        finally:
            if conn:
                self.db_pool.putconn(conn)

    def close(self):
        """Clean up resources."""
        if self._ingestion_pipeline is not None:
            self._ingestion_pipeline.close()
            self._ingestion_pipeline = None

        if self._own_pool and self._db_pool is not None:
            self._db_pool.closeall()
            self._db_pool = None
            logger.info("Database connection pool closed")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    # =========================================================================
    # MAIN ORCHESTRATION
    # =========================================================================

    def run(
        self,
        skip_ingestion: bool = False,
        skip_events: bool = False,
        max_asins: Optional[int] = None,
    ) -> PipelineResult:
        """
        Run the complete daily pipeline.

        Args:
            skip_ingestion: Skip data ingestion step (use existing data)
            skip_events: Skip event detection step
            max_asins: Limit number of ASINs to process

        Returns:
            PipelineResult with complete run details

        The pipeline continues even if individual stages fail,
        capturing all errors for later review.
        """
        run_id = str(uuid.uuid4())
        self._current_run_id = run_id

        result = PipelineResult(
            run_id=run_id,
            status=PipelineStatus.RUNNING,
            started_at=datetime.utcnow(),
        )

        logger.info(f"=== Starting Daily Pipeline (run_id={run_id}) ===")

        has_critical_failure = False

        try:
            # STAGE 1: INGESTION
            if not skip_ingestion:
                stage_result = self._run_ingestion_stage(max_asins)
                result.stages[PipelineStage.INGESTION] = stage_result
                if stage_result.status == PipelineStatus.FAILED:
                    logger.error("Ingestion failed critically, continuing with existing data")
            else:
                logger.info("Skipping ingestion stage (skip_ingestion=True)")

            # STAGE 2: EVENT DETECTION
            if not skip_events:
                stage_result = self._run_event_detection_stage()
                result.stages[PipelineStage.EVENT_DETECTION] = stage_result
            else:
                logger.info("Skipping event detection stage (skip_events=True)")

            # STAGE 3: SCORING
            stage_result = self._run_scoring_stage(max_asins)
            result.stages[PipelineStage.SCORING] = stage_result
            result.opportunities_found = stage_result.metrics.get("total_scored", 0)
            result.opportunities_above_threshold = stage_result.metrics.get("above_threshold", 0)

            # STAGE 4: NOTIFICATION (stub for Phase 2)
            stage_result = self._run_notification_stage()
            result.stages[PipelineStage.NOTIFICATION] = stage_result

            # STAGE 5: CLEANUP
            stage_result = self._run_cleanup_stage()
            result.stages[PipelineStage.CLEANUP] = stage_result

        except Exception as e:
            logger.exception(f"Critical pipeline failure: {e}")
            has_critical_failure = True

        finally:
            result.completed_at = datetime.utcnow()
            self._current_run_id = None

        # Determine final status
        failed_stages = [
            s for s, r in result.stages.items()
            if r.status == PipelineStatus.FAILED
        ]

        if has_critical_failure:
            result.status = PipelineStatus.FAILED
        elif failed_stages:
            result.status = PipelineStatus.PARTIAL_FAILURE
            logger.warning(f"Pipeline completed with failures in: {[s.value for s in failed_stages]}")
        else:
            result.status = PipelineStatus.COMPLETED

        # Log summary
        summary = result.get_summary()
        logger.info(
            f"=== Pipeline Complete ===\n"
            f"  Run ID: {run_id}\n"
            f"  Status: {result.status.value}\n"
            f"  Duration: {result.duration_seconds:.1f}s\n"
            f"  Opportunities: {result.opportunities_above_threshold} above threshold"
        )

        # Persist run metrics
        self._persist_run_metrics(result)

        return result

    # =========================================================================
    # STAGE 1: INGESTION
    # =========================================================================

    def _run_ingestion_stage(self, max_asins: Optional[int] = None) -> StageResult:
        """
        Execute the ingestion stage.

        Calls IngestionPipeline.run_daily_ingestion() to pull fresh data
        from Keepa API.
        """
        stage_result = StageResult(
            stage=PipelineStage.INGESTION,
            status=PipelineStatus.RUNNING,
            started_at=datetime.utcnow(),
        )

        logger.info("--- STAGE 1: INGESTION ---")

        retry_count = 0
        while retry_count < self.MAX_RETRIES:
            try:
                ingestion_result = self.ingestion_pipeline.run_daily_ingestion(
                    max_asins=max_asins
                )

                stage_result.metrics = {
                    "asins_processed": ingestion_result.asins_processed,
                    "asins_inserted": ingestion_result.asins_inserted,
                    "asins_failed": ingestion_result.asins_failed,
                    "snapshots_inserted": ingestion_result.snapshots_inserted,
                    "tokens_consumed": ingestion_result.tokens_consumed,
                    "tokens_remaining": ingestion_result.tokens_remaining,
                    "duration_seconds": ingestion_result.duration_seconds,
                }

                logger.info(
                    f"Ingestion complete: {ingestion_result.asins_processed} ASINs updated, "
                    f"{ingestion_result.snapshots_inserted} snapshots"
                )

                # Check for partial failures
                if ingestion_result.asins_failed > 0:
                    stage_result.status = PipelineStatus.PARTIAL_FAILURE
                    for error in ingestion_result.errors:
                        stage_result.add_error(
                            error.get("error_type", "Unknown"),
                            error.get("message", "Unknown error"),
                            {"asin": error.get("asin")}
                        )
                else:
                    stage_result.status = PipelineStatus.COMPLETED

                break

            except Exception as e:
                retry_count += 1
                logger.warning(f"Ingestion attempt {retry_count} failed: {e}")
                stage_result.add_error("IngestionError", str(e), {"retry": retry_count})

                if retry_count >= self.MAX_RETRIES:
                    stage_result.status = PipelineStatus.FAILED
                    logger.error(f"Ingestion failed after {self.MAX_RETRIES} retries")

        stage_result.completed_at = datetime.utcnow()
        return stage_result

    # =========================================================================
    # STAGE 2: EVENT DETECTION
    # =========================================================================

    def _run_event_detection_stage(self) -> StageResult:
        """
        Execute the event detection stage.

        Processes new snapshots to detect significant events:
        - Price drops > 10%
        - BSR improvements > 20%
        - Stock out events
        - Review velocity changes

        Note: EventProcessor module is in development.
        This stage provides a stub implementation.
        """
        stage_result = StageResult(
            stage=PipelineStage.EVENT_DETECTION,
            status=PipelineStatus.RUNNING,
            started_at=datetime.utcnow(),
        )

        logger.info("--- STAGE 2: EVENT DETECTION ---")

        try:
            # Detect events from recent snapshots
            events = self._detect_events_from_snapshots()

            # Aggregate events by type
            events_by_type = {}
            asins_with_events = set()

            for event in events:
                event_type = event.get("event_type", "unknown")
                events_by_type[event_type] = events_by_type.get(event_type, 0) + 1
                asins_with_events.add(event.get("asin"))

            stage_result.metrics = {
                "total_events_detected": len(events),
                "events_by_type": events_by_type,
                "asins_with_events": len(asins_with_events),
            }

            logger.info(
                f"Event detection complete: {len(events)} events detected "
                f"across {len(asins_with_events)} ASINs"
            )

            for event_type, count in events_by_type.items():
                logger.info(f"  - {event_type}: {count}")

            stage_result.status = PipelineStatus.COMPLETED

        except Exception as e:
            logger.error(f"Event detection failed: {e}")
            stage_result.add_error("EventDetectionError", str(e))
            stage_result.status = PipelineStatus.FAILED

        stage_result.completed_at = datetime.utcnow()
        return stage_result

    def _detect_events_from_snapshots(self) -> List[Dict[str, Any]]:
        """
        Detect events by comparing recent snapshots.

        Compares latest snapshot with previous snapshot to detect:
        - Price drops (>10% decrease)
        - BSR improvements (>20% decrease)
        - Stock outs (transition to out_of_stock)
        """
        events = []

        with self.get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Get ASINs with multiple snapshots in last 48h
                cur.execute("""
                    WITH recent_snapshots AS (
                        SELECT
                            asin,
                            captured_at,
                            price_current,
                            bsr_primary,
                            stock_status,
                            ROW_NUMBER() OVER (
                                PARTITION BY asin
                                ORDER BY captured_at DESC
                            ) as rn
                        FROM asin_snapshots
                        WHERE captured_at >= NOW() - INTERVAL '48 hours'
                    )
                    SELECT
                        curr.asin,
                        curr.price_current as current_price,
                        prev.price_current as prev_price,
                        curr.bsr_primary as current_bsr,
                        prev.bsr_primary as prev_bsr,
                        curr.stock_status as current_stock,
                        prev.stock_status as prev_stock
                    FROM recent_snapshots curr
                    JOIN recent_snapshots prev
                        ON curr.asin = prev.asin
                        AND curr.rn = 1
                        AND prev.rn = 2
                    WHERE prev.price_current IS NOT NULL
                        OR prev.bsr_primary IS NOT NULL
                """)

                for row in cur.fetchall():
                    asin = row["asin"]

                    # Check for price drop > 10%
                    if row["current_price"] and row["prev_price"]:
                        price_change = (row["current_price"] - row["prev_price"]) / row["prev_price"]
                        if price_change <= -0.10:
                            events.append({
                                "asin": asin,
                                "event_type": "price_drop",
                                "change_percent": round(price_change * 100, 1),
                                "old_value": float(row["prev_price"]),
                                "new_value": float(row["current_price"]),
                            })

                    # Check for BSR improvement > 20%
                    if row["current_bsr"] and row["prev_bsr"] and row["prev_bsr"] > 0:
                        bsr_change = (row["current_bsr"] - row["prev_bsr"]) / row["prev_bsr"]
                        if bsr_change <= -0.20:
                            events.append({
                                "asin": asin,
                                "event_type": "bsr_improvement",
                                "change_percent": round(bsr_change * 100, 1),
                                "old_value": row["prev_bsr"],
                                "new_value": row["current_bsr"],
                            })

                    # Check for stock out
                    if row["prev_stock"] != "out_of_stock" and row["current_stock"] == "out_of_stock":
                        events.append({
                            "asin": asin,
                            "event_type": "stock_out",
                            "old_value": row["prev_stock"],
                            "new_value": row["current_stock"],
                        })

        return events

    # =========================================================================
    # STAGE 3: SCORING
    # =========================================================================

    def _run_scoring_stage(self, max_asins: Optional[int] = None) -> StageResult:
        """
        Execute the scoring stage.

        For each ASIN with recent activity:
        1. Retrieve aggregated metrics
        2. Retrieve current product data
        3. Calculate opportunity score
        4. Persist if score > threshold
        """
        stage_result = StageResult(
            stage=PipelineStage.SCORING,
            status=PipelineStatus.RUNNING,
            started_at=datetime.utcnow(),
        )

        logger.info("--- STAGE 3: SCORING ---")

        try:
            # Get ASINs with recent snapshots
            asins_to_score = self._get_asins_for_scoring(max_asins)
            logger.info(f"Scoring {len(asins_to_score)} ASINs")

            scored_count = 0
            above_threshold_count = 0
            opportunities = []

            for asin in asins_to_score:
                try:
                    # Get product data for scoring
                    product_data = self._prepare_product_data_for_scoring(asin)

                    if product_data is None:
                        logger.debug(f"Skipping {asin}: insufficient data")
                        continue

                    # Calculate score
                    scoring_result = self.scorer.score(product_data)
                    scored_count += 1

                    # Check threshold
                    if scoring_result.is_valid and scoring_result.total_score >= self.score_threshold:
                        above_threshold_count += 1
                        opportunities.append(Opportunity(
                            asin=asin,
                            score=scoring_result.total_score,
                            status=scoring_result.status.value,
                            window_days=scoring_result.window_days,
                            window_estimate=scoring_result.window_estimate,
                            component_scores={
                                name: {
                                    "score": comp.score,
                                    "max_score": comp.max_score,
                                    "details": comp.details,
                                }
                                for name, comp in scoring_result.component_scores.items()
                            },
                            detected_at=datetime.utcnow(),
                            run_id=self._current_run_id or "",
                        ))

                        logger.info(
                            f"Opportunity: {asin} - Score {scoring_result.total_score}/100 "
                            f"({scoring_result.status.value})"
                        )

                except Exception as e:
                    logger.warning(f"Failed to score {asin}: {e}")
                    stage_result.add_error("ScoringError", str(e), {"asin": asin})

            # Persist opportunities
            if opportunities:
                persisted = self._persist_opportunities(opportunities)
                logger.info(f"Persisted {persisted} opportunities to database")

            stage_result.metrics = {
                "total_asins": len(asins_to_score),
                "total_scored": scored_count,
                "above_threshold": above_threshold_count,
                "threshold_used": self.score_threshold,
            }

            logger.info(
                f"Scoring complete: {scored_count} scored, "
                f"{above_threshold_count} above threshold ({self.score_threshold})"
            )

            stage_result.status = PipelineStatus.COMPLETED

        except Exception as e:
            logger.error(f"Scoring stage failed: {e}")
            stage_result.add_error("ScoringStageError", str(e))
            stage_result.status = PipelineStatus.FAILED

        stage_result.completed_at = datetime.utcnow()
        return stage_result

    def _get_asins_for_scoring(self, max_asins: Optional[int] = None) -> List[str]:
        """Get list of ASINs that need scoring based on recent activity."""
        with self.get_db_connection() as conn:
            with conn.cursor() as cur:
                query = """
                    SELECT DISTINCT s.asin
                    FROM asin_snapshots s
                    JOIN asins a ON s.asin = a.asin
                    WHERE s.captured_at >= NOW() - INTERVAL '24 hours'
                      AND a.is_active = TRUE
                    ORDER BY s.asin
                """
                if max_asins:
                    query += f" LIMIT {max_asins}"

                cur.execute(query)
                return [row[0] for row in cur.fetchall()]

    def _prepare_product_data_for_scoring(self, asin: str) -> Optional[Dict[str, Any]]:
        """
        Prepare product data dictionary for scoring.

        Aggregates data from multiple sources:
        - Latest snapshot (current prices, BSR, ratings)
        - Historical data (deltas, trends)
        - Competition data (seller count, buybox)
        """
        with self.get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Get latest snapshot
                cur.execute("""
                    SELECT *
                    FROM asin_snapshots
                    WHERE asin = %s
                    ORDER BY captured_at DESC
                    LIMIT 1
                """, (asin,))
                latest = cur.fetchone()

                if not latest:
                    return None

                # Get historical metrics (7d and 30d)
                cur.execute("""
                    WITH snapshots_7d AS (
                        SELECT price_current, bsr_primary
                        FROM asin_snapshots
                        WHERE asin = %s
                          AND captured_at >= NOW() - INTERVAL '7 days'
                        ORDER BY captured_at ASC
                        LIMIT 1
                    ),
                    snapshots_30d AS (
                        SELECT price_current, bsr_primary
                        FROM asin_snapshots
                        WHERE asin = %s
                          AND captured_at >= NOW() - INTERVAL '30 days'
                        ORDER BY captured_at ASC
                        LIMIT 1
                    )
                    SELECT
                        s7.price_current as price_7d_ago,
                        s7.bsr_primary as bsr_7d_ago,
                        s30.price_current as price_30d_ago,
                        s30.bsr_primary as bsr_30d_ago
                    FROM snapshots_7d s7, snapshots_30d s30
                """, (asin, asin))
                history = cur.fetchone() or {}

                # Calculate deltas
                bsr_current = latest.get("bsr_primary") or 999999
                bsr_7d_ago = history.get("bsr_7d_ago")
                bsr_30d_ago = history.get("bsr_30d_ago")
                price_current = latest.get("price_current")
                price_30d_ago = history.get("price_30d_ago")

                bsr_delta_7d = 0
                if bsr_7d_ago and bsr_7d_ago > 0:
                    bsr_delta_7d = (bsr_current - bsr_7d_ago) / bsr_7d_ago

                bsr_delta_30d = 0
                if bsr_30d_ago and bsr_30d_ago > 0:
                    bsr_delta_30d = (bsr_current - bsr_30d_ago) / bsr_30d_ago

                price_trend_30d = 0
                if price_current and price_30d_ago and price_30d_ago > 0:
                    price_trend_30d = (price_current - price_30d_ago) / price_30d_ago

                # Estimate monthly reviews (from rating_count changes)
                reviews_per_month = self._estimate_reviews_per_month(asin, conn)

                # Build product data dict
                product_data = {
                    "product_id": asin,
                    # Margin inputs (using estimates for alibaba price)
                    "amazon_price": float(latest.get("price_current") or 0),
                    "alibaba_price": self._estimate_alibaba_price(float(latest.get("price_current") or 0)),
                    # Velocity inputs
                    "bsr_current": bsr_current,
                    "bsr_delta_7d": bsr_delta_7d,
                    "bsr_delta_30d": bsr_delta_30d,
                    "reviews_per_month": reviews_per_month,
                    # Competition inputs
                    "seller_count": latest.get("seller_count") or 10,
                    "buybox_rotation": 0.15,  # Default estimate
                    "review_gap_vs_top10": 0.50,  # Default estimate
                    "has_amazon_basics": False,
                    "has_brand_dominance": False,
                    # Gap inputs — read real data from review_improvement_profiles
                    **self._load_review_gap_inputs(asin, conn),
                    # Time pressure inputs
                    "stockout_count_90d": self._count_stockouts(asin, conn),
                    "price_trend_30d": price_trend_30d,
                    "seller_churn_90d": 0,  # Would need seller history
                    "bsr_acceleration": self._calculate_bsr_acceleration(asin, conn),
                }

                return product_data

    def _load_review_gap_inputs(self, asin: str, conn) -> dict:
        """Load real review data from review_improvement_profiles for gap scoring.

        Returns a dict with keys expected by score_gap():
        - negative_review_percent
        - wish_mentions_per_100
        - unanswered_questions
        - has_recurring_problems
        """
        defaults = {
            "negative_review_percent": 0.10,
            "wish_mentions_per_100": 3,
            "unanswered_questions": 5,
            "has_recurring_problems": False,
        }
        try:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT improvement_score, dominant_pain,
                           reviews_analyzed, negative_reviews_analyzed,
                           top_defects, missing_features
                    FROM review_improvement_profiles
                    WHERE asin = %s
                    ORDER BY computed_at DESC
                    LIMIT 1
                """, (asin,))
                row = cur.fetchone()
                if not row:
                    return defaults

                reviews_analyzed = row[2] or 0
                negative_analyzed = row[3] or 0
                top_defects = row[4] or []
                missing_features = row[5] or []
                improvement_score = row[0] or 0.0
                dominant_pain = row[1]

                # Compute real negative_review_percent
                neg_pct = (negative_analyzed / reviews_analyzed) if reviews_analyzed > 0 else 0.10

                # Count wish mentions (normalize per 100 reviews)
                total_wish_mentions = sum(f.get("mentions", 0) for f in missing_features) if missing_features else 0
                wish_per_100 = (total_wish_mentions / reviews_analyzed * 100) if reviews_analyzed > 0 else 3

                # has_recurring_problems = dominant pain exists with meaningful score
                has_recurring = bool(dominant_pain and improvement_score > 0.2)

                return {
                    "negative_review_percent": round(neg_pct, 3),
                    "wish_mentions_per_100": round(wish_per_100, 1),
                    "unanswered_questions": 5,  # No Q&A data yet
                    "has_recurring_problems": has_recurring,
                }
        except Exception as e:
            logger.warning(f"Failed to load review gap inputs for {asin}: {e}")
            return defaults

    def _estimate_alibaba_price(self, amazon_price: float) -> float:
        """Estimate Alibaba sourcing price (rough heuristic)."""
        if amazon_price <= 0:
            return 0
        # Car phone mounts typically have 4-6x markup from Alibaba
        return amazon_price / 5.0

    def _estimate_reviews_per_month(self, asin: str, conn) -> int:
        """Estimate monthly review velocity from historical data."""
        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    MAX(review_count) - MIN(review_count) as review_delta
                FROM asin_snapshots
                WHERE asin = %s
                  AND captured_at >= NOW() - INTERVAL '30 days'
                  AND review_count IS NOT NULL
            """, (asin,))
            result = cur.fetchone()
            return max(0, result[0] or 0)

    def _count_stockouts(self, asin: str, conn) -> int:
        """Count stock out events in last 90 days."""
        with conn.cursor() as cur:
            cur.execute("""
                SELECT COUNT(*) as stockout_count
                FROM (
                    SELECT
                        stock_status,
                        LAG(stock_status) OVER (ORDER BY captured_at) as prev_status
                    FROM asin_snapshots
                    WHERE asin = %s
                      AND captured_at >= NOW() - INTERVAL '90 days'
                ) transitions
                WHERE stock_status = 'out_of_stock'
                  AND prev_status != 'out_of_stock'
            """, (asin,))
            result = cur.fetchone()
            return result[0] or 0

    def _calculate_bsr_acceleration(self, asin: str, conn) -> float:
        """
        Calculate BSR acceleration (rate of change of BSR improvement).

        Positive acceleration means BSR is improving at an increasing rate.
        """
        with conn.cursor() as cur:
            cur.execute("""
                WITH weekly_bsr AS (
                    SELECT
                        DATE_TRUNC('week', captured_at) as week,
                        AVG(bsr_primary) as avg_bsr
                    FROM asin_snapshots
                    WHERE asin = %s
                      AND captured_at >= NOW() - INTERVAL '30 days'
                      AND bsr_primary IS NOT NULL
                    GROUP BY DATE_TRUNC('week', captured_at)
                    ORDER BY week
                ),
                weekly_changes AS (
                    SELECT
                        week,
                        (avg_bsr - LAG(avg_bsr) OVER (ORDER BY week)) /
                        NULLIF(LAG(avg_bsr) OVER (ORDER BY week), 0) as change_rate
                    FROM weekly_bsr
                )
                SELECT
                    AVG(change_rate) as avg_change_rate
                FROM weekly_changes
                WHERE change_rate IS NOT NULL
            """, (asin,))
            result = cur.fetchone()
            # Negate because negative BSR change is improvement
            return -(result[0] or 0) if result[0] else 0

    def _persist_opportunities(self, opportunities: List[Opportunity]) -> int:
        """Persist opportunities to database."""
        if not opportunities:
            return 0

        import json

        with self.get_db_connection() as conn:
            with conn.cursor() as cur:
                inserted = 0
                for opp in opportunities:
                    try:
                        cur.execute("""
                            INSERT INTO opportunities (
                                asin, score, status, window_days, window_estimate,
                                component_scores, detected_at, run_id
                            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (asin, detected_at) DO UPDATE SET
                                score = EXCLUDED.score,
                                status = EXCLUDED.status,
                                window_days = EXCLUDED.window_days,
                                window_estimate = EXCLUDED.window_estimate,
                                component_scores = EXCLUDED.component_scores
                        """, (
                            opp.asin,
                            opp.score,
                            opp.status,
                            opp.window_days,
                            opp.window_estimate,
                            json.dumps(opp.component_scores),
                            opp.detected_at,
                            opp.run_id,
                        ))
                        inserted += 1
                    except Exception as e:
                        logger.warning(f"Failed to persist opportunity {opp.asin}: {e}")

                return inserted

    # =========================================================================
    # STAGE 4: NOTIFICATION
    # =========================================================================

    def _run_notification_stage(self) -> StageResult:
        """
        Execute the notification stage (stub for Phase 2).

        Prepares list of new opportunities for notification.
        Actual notification sending will be implemented in Phase 2.
        """
        stage_result = StageResult(
            stage=PipelineStage.NOTIFICATION,
            status=PipelineStatus.RUNNING,
            started_at=datetime.utcnow(),
        )

        logger.info("--- STAGE 4: NOTIFICATION (stub) ---")

        try:
            # Get new opportunities from current run
            new_opportunities = self._get_new_opportunities()

            stage_result.metrics = {
                "new_opportunities": len(new_opportunities),
                "notification_status": "pending_implementation",
            }

            logger.info(f"Prepared {len(new_opportunities)} opportunities for notification")
            logger.info("Note: Notification sending will be implemented in Phase 2")

            # Log opportunity summary for review
            for opp in new_opportunities[:5]:  # Top 5 only
                logger.info(
                    f"  - {opp['asin']}: Score {opp['score']}/100 "
                    f"({opp['status']}, {opp['window_estimate']})"
                )

            if len(new_opportunities) > 5:
                logger.info(f"  ... and {len(new_opportunities) - 5} more")

            stage_result.status = PipelineStatus.COMPLETED

        except Exception as e:
            logger.error(f"Notification stage failed: {e}")
            stage_result.add_error("NotificationError", str(e))
            stage_result.status = PipelineStatus.FAILED

        stage_result.completed_at = datetime.utcnow()
        return stage_result

    def _get_new_opportunities(self) -> List[Dict[str, Any]]:
        """Get opportunities from current run."""
        if not self._current_run_id:
            return []

        with self.get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT asin, score, status, window_days, window_estimate
                    FROM opportunities
                    WHERE run_id = %s
                    ORDER BY score DESC
                """, (self._current_run_id,))
                return [dict(row) for row in cur.fetchall()]

    # =========================================================================
    # STAGE 5: CLEANUP
    # =========================================================================

    def _run_cleanup_stage(self) -> StageResult:
        """
        Execute the cleanup stage.

        - Refresh materialized views
        - Log pipeline statistics
        """
        stage_result = StageResult(
            stage=PipelineStage.CLEANUP,
            status=PipelineStatus.RUNNING,
            started_at=datetime.utcnow(),
        )

        logger.info("--- STAGE 5: CLEANUP ---")

        try:
            # Refresh materialized views
            views_refreshed = self._refresh_materialized_views()

            # Get pipeline statistics
            stats = self._get_pipeline_statistics()

            stage_result.metrics = {
                "views_refreshed": views_refreshed,
                "pipeline_stats": stats,
            }

            logger.info(f"Cleanup complete: {views_refreshed} views refreshed")
            logger.info(f"  - Total tracked ASINs: {stats.get('total_asins', 0)}")
            logger.info(f"  - Snapshots last 24h: {stats.get('snapshots_24h', 0)}")
            logger.info(f"  - Active opportunities: {stats.get('active_opportunities', 0)}")

            stage_result.status = PipelineStatus.COMPLETED

        except Exception as e:
            logger.error(f"Cleanup stage failed: {e}")
            stage_result.add_error("CleanupError", str(e))
            stage_result.status = PipelineStatus.FAILED

        stage_result.completed_at = datetime.utcnow()
        return stage_result

    def _refresh_materialized_views(self) -> int:
        """Refresh materialized views for reporting."""
        views = [
            "mv_latest_snapshots",
            "mv_asin_stats_7d",
            "mv_asin_stats_30d",
        ]

        refreshed = 0

        with self.get_db_connection() as conn:
            with conn.cursor() as cur:
                for view in views:
                    try:
                        cur.execute(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {view}")
                        refreshed += 1
                        logger.debug(f"Refreshed {view}")
                    except Exception as e:
                        logger.warning(f"Failed to refresh {view}: {e}")

        return refreshed

    def _get_pipeline_statistics(self) -> Dict[str, Any]:
        """Get current pipeline statistics."""
        with self.get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                stats = {}

                # Total tracked ASINs
                cur.execute("SELECT COUNT(*) as count FROM asins WHERE is_active = TRUE")
                stats["total_asins"] = cur.fetchone()["count"]

                # Snapshots in last 24h
                cur.execute("""
                    SELECT COUNT(*) as count
                    FROM asin_snapshots
                    WHERE captured_at >= NOW() - INTERVAL '24 hours'
                """)
                stats["snapshots_24h"] = cur.fetchone()["count"]

                # Active opportunities (score >= threshold, recent)
                cur.execute("""
                    SELECT COUNT(*) as count
                    FROM opportunities
                    WHERE score >= %s
                      AND detected_at >= NOW() - INTERVAL '7 days'
                """, (self.score_threshold,))
                stats["active_opportunities"] = cur.fetchone()["count"]

                return stats

    def _persist_run_metrics(self, result: PipelineResult):
        """Persist pipeline run metrics for monitoring."""
        try:
            with self.get_db_connection() as conn:
                with conn.cursor() as cur:
                    import json
                    cur.execute("""
                        INSERT INTO pipeline_runs (
                            run_id, status, started_at, completed_at,
                            duration_seconds, metrics
                        ) VALUES (%s, %s, %s, %s, %s, %s)
                    """, (
                        result.run_id,
                        result.status.value,
                        result.started_at,
                        result.completed_at,
                        result.duration_seconds,
                        json.dumps(result.get_summary()),
                    ))
        except Exception as e:
            logger.warning(f"Failed to persist run metrics: {e}")

    # =========================================================================
    # PUBLIC UTILITIES
    # =========================================================================

    def score_single_asin(self, asin: str) -> Optional[ScoringResult]:
        """
        Score a single ASIN.

        Useful for ad-hoc scoring or debugging.

        Args:
            asin: ASIN to score

        Returns:
            ScoringResult or None if insufficient data
        """
        product_data = self._prepare_product_data_for_scoring(asin)
        if product_data is None:
            logger.warning(f"Cannot score {asin}: insufficient data")
            return None

        return self.scorer.score(product_data)

    def get_active_opportunities(
        self,
        min_score: Optional[int] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Get list of active opportunities.

        Args:
            min_score: Minimum score filter (defaults to threshold)
            limit: Maximum opportunities to return

        Returns:
            List of opportunity dicts sorted by score descending
        """
        min_score = min_score or self.score_threshold

        with self.get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT
                        o.asin,
                        o.score,
                        o.status,
                        o.window_days,
                        o.window_estimate,
                        o.detected_at,
                        a.title,
                        a.brand
                    FROM opportunities o
                    LEFT JOIN asins a ON o.asin = a.asin
                    WHERE o.score >= %s
                      AND o.detected_at >= NOW() - INTERVAL '7 days'
                    ORDER BY o.score DESC
                    LIMIT %s
                """, (min_score, limit))

                return [dict(row) for row in cur.fetchall()]

    def get_last_run_status(self) -> Optional[Dict[str, Any]]:
        """Get status of the last pipeline run."""
        with self.get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute("""
                    SELECT run_id, status, started_at, completed_at,
                           duration_seconds, metrics
                    FROM pipeline_runs
                    ORDER BY started_at DESC
                    LIMIT 1
                """)
                result = cur.fetchone()
                return dict(result) if result else None
