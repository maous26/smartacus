"""
Smartacus Pipeline Monitoring
=============================

Health monitoring and metrics tracking for the pipeline.

Features:
    - Data freshness checks
    - Component health monitoring
    - Alert generation on failures
    - Run metrics persistence

Usage:
    from src.orchestrator.monitoring import PipelineMonitor

    monitor = PipelineMonitor()
    health = monitor.get_pipeline_health()
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field

import psycopg2
from psycopg2.extras import RealDictCursor
from psycopg2 import pool

from ..data.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class HealthCheckResult:
    """Result of a health check."""
    component: str
    healthy: bool
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    checked_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class AlertCondition:
    """Definition of an alert condition."""
    name: str
    severity: str  # "warning", "critical"
    condition_met: bool
    message: str
    triggered_at: Optional[datetime] = None


class PipelineMonitor:
    """
    Health monitoring for the Smartacus pipeline.

    Monitors:
        - Database connectivity
        - Data freshness
        - Pipeline run history
        - Resource usage
    """

    # Thresholds
    MAX_DATA_AGE_HOURS = 48  # Data older than this is stale
    MAX_CONSECUTIVE_FAILURES = 3
    MIN_ASIN_COUNT = 1000  # Minimum ASINs expected

    def __init__(self, db_pool: Optional[pool.ThreadedConnectionPool] = None):
        """
        Initialize the monitor.

        Args:
            db_pool: Database connection pool (creates new if None)
        """
        self.settings = get_settings()
        self._db_pool = db_pool
        self._own_pool = db_pool is None

    @property
    def db_pool(self) -> pool.ThreadedConnectionPool:
        """Lazy-initialize database connection pool."""
        if self._db_pool is None:
            db_config = self.settings.database
            self._db_pool = pool.ThreadedConnectionPool(
                minconn=1,
                maxconn=5,
                **db_config.connection_dict
            )
        return self._db_pool

    def close(self):
        """Clean up resources."""
        if self._own_pool and self._db_pool is not None:
            self._db_pool.closeall()
            self._db_pool = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    # =========================================================================
    # Health Checks
    # =========================================================================

    def get_pipeline_health(self) -> Dict[str, Any]:
        """
        Get comprehensive pipeline health status.

        Returns:
            Dictionary with health status and component details
        """
        checks = []

        # Check database connectivity
        checks.append(self._check_database_connectivity())

        # Check data freshness
        checks.append(self._check_data_freshness())

        # Check recent runs
        checks.append(self._check_run_history())

        # Check ASIN coverage
        checks.append(self._check_asin_coverage())

        # Aggregate results
        all_healthy = all(c.healthy for c in checks)

        return {
            "is_healthy": all_healthy,
            "checked_at": datetime.utcnow().isoformat(),
            "components": {
                c.component: {
                    "healthy": c.healthy,
                    "message": c.message,
                    "details": c.details,
                }
                for c in checks
            },
            "data_freshness": self._get_freshness_metrics(),
            "alerts": self._check_alert_conditions(),
        }

    def _check_database_connectivity(self) -> HealthCheckResult:
        """Check database connectivity."""
        try:
            conn = self.db_pool.getconn()
            try:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                return HealthCheckResult(
                    component="database",
                    healthy=True,
                    message="Database connection successful",
                )
            finally:
                self.db_pool.putconn(conn)
        except Exception as e:
            return HealthCheckResult(
                component="database",
                healthy=False,
                message=f"Database connection failed: {e}",
            )

    def _check_data_freshness(self) -> HealthCheckResult:
        """Check if data is fresh (recent snapshots exist)."""
        try:
            conn = self.db_pool.getconn()
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT
                            MAX(captured_at) as latest_snapshot,
                            COUNT(*) as snapshots_24h
                        FROM asin_snapshots
                        WHERE captured_at >= NOW() - INTERVAL '24 hours'
                    """)
                    result = cur.fetchone()

                    if result is None or result['latest_snapshot'] is None:
                        return HealthCheckResult(
                            component="data_freshness",
                            healthy=False,
                            message="No recent snapshots found",
                        )

                    latest = result['latest_snapshot']
                    age_hours = (datetime.utcnow() - latest).total_seconds() / 3600

                    if age_hours > self.MAX_DATA_AGE_HOURS:
                        return HealthCheckResult(
                            component="data_freshness",
                            healthy=False,
                            message=f"Data is stale ({age_hours:.1f} hours old)",
                            details={
                                "latest_snapshot": latest.isoformat(),
                                "age_hours": age_hours,
                                "snapshots_24h": result['snapshots_24h'],
                            },
                        )

                    return HealthCheckResult(
                        component="data_freshness",
                        healthy=True,
                        message=f"Data is fresh ({age_hours:.1f} hours old)",
                        details={
                            "latest_snapshot": latest.isoformat(),
                            "age_hours": age_hours,
                            "snapshots_24h": result['snapshots_24h'],
                        },
                    )
            finally:
                self.db_pool.putconn(conn)
        except Exception as e:
            return HealthCheckResult(
                component="data_freshness",
                healthy=False,
                message=f"Failed to check data freshness: {e}",
            )

    def _check_run_history(self) -> HealthCheckResult:
        """Check recent pipeline run history."""
        try:
            conn = self.db_pool.getconn()
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    # Get last 5 runs
                    cur.execute("""
                        SELECT run_id, status, started_at, completed_at
                        FROM pipeline_runs
                        ORDER BY started_at DESC
                        LIMIT 5
                    """)
                    runs = cur.fetchall()

                    if not runs:
                        return HealthCheckResult(
                            component="run_history",
                            healthy=True,
                            message="No pipeline runs recorded yet",
                        )

                    # Count consecutive failures
                    consecutive_failures = 0
                    for run in runs:
                        if run['status'] == 'failed':
                            consecutive_failures += 1
                        else:
                            break

                    if consecutive_failures >= self.MAX_CONSECUTIVE_FAILURES:
                        return HealthCheckResult(
                            component="run_history",
                            healthy=False,
                            message=f"{consecutive_failures} consecutive failures",
                            details={
                                "consecutive_failures": consecutive_failures,
                                "last_run_status": runs[0]['status'],
                            },
                        )

                    return HealthCheckResult(
                        component="run_history",
                        healthy=True,
                        message=f"Last run: {runs[0]['status']}",
                        details={
                            "last_run_status": runs[0]['status'],
                            "last_run_at": runs[0]['started_at'].isoformat() if runs[0]['started_at'] else None,
                        },
                    )
            finally:
                self.db_pool.putconn(conn)
        except Exception as e:
            return HealthCheckResult(
                component="run_history",
                healthy=False,
                message=f"Failed to check run history: {e}",
            )

    def _check_asin_coverage(self) -> HealthCheckResult:
        """Check ASIN coverage meets minimum threshold."""
        try:
            conn = self.db_pool.getconn()
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    cur.execute("""
                        SELECT COUNT(*) as total_asins
                        FROM asins
                        WHERE is_active = TRUE
                    """)
                    result = cur.fetchone()
                    count = result['total_asins'] if result else 0

                    if count < self.MIN_ASIN_COUNT:
                        return HealthCheckResult(
                            component="asin_coverage",
                            healthy=False,
                            message=f"Low ASIN coverage: {count} (min: {self.MIN_ASIN_COUNT})",
                            details={"total_asins": count},
                        )

                    return HealthCheckResult(
                        component="asin_coverage",
                        healthy=True,
                        message=f"ASIN coverage: {count}",
                        details={"total_asins": count},
                    )
            finally:
                self.db_pool.putconn(conn)
        except Exception as e:
            return HealthCheckResult(
                component="asin_coverage",
                healthy=False,
                message=f"Failed to check ASIN coverage: {e}",
            )

    def _get_freshness_metrics(self) -> Dict[str, Any]:
        """Get data freshness metrics."""
        try:
            conn = self.db_pool.getconn()
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    metrics = {}

                    # Latest snapshot
                    cur.execute("SELECT MAX(captured_at) as latest FROM asin_snapshots")
                    result = cur.fetchone()
                    metrics["latest_snapshot"] = (
                        result['latest'].isoformat() if result and result['latest'] else None
                    )

                    # Snapshots by time range
                    cur.execute("""
                        SELECT
                            COUNT(*) FILTER (WHERE captured_at >= NOW() - INTERVAL '24 hours') as last_24h,
                            COUNT(*) FILTER (WHERE captured_at >= NOW() - INTERVAL '7 days') as last_7d,
                            COUNT(*) as total
                        FROM asin_snapshots
                    """)
                    result = cur.fetchone()
                    if result:
                        metrics["snapshots_24h"] = result['last_24h']
                        metrics["snapshots_7d"] = result['last_7d']
                        metrics["snapshots_total"] = result['total']

                    # Active opportunities
                    cur.execute("""
                        SELECT COUNT(*) as count
                        FROM opportunities
                        WHERE detected_at >= NOW() - INTERVAL '7 days'
                    """)
                    result = cur.fetchone()
                    metrics["active_opportunities"] = result['count'] if result else 0

                    return metrics
            finally:
                self.db_pool.putconn(conn)
        except Exception as e:
            logger.warning(f"Failed to get freshness metrics: {e}")
            return {}

    def _check_alert_conditions(self) -> List[Dict[str, Any]]:
        """Check for alert conditions."""
        alerts = []

        try:
            conn = self.db_pool.getconn()
            try:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    # Check for stale data
                    cur.execute("""
                        SELECT MAX(captured_at) as latest
                        FROM asin_snapshots
                    """)
                    result = cur.fetchone()
                    if result and result['latest']:
                        age_hours = (datetime.utcnow() - result['latest']).total_seconds() / 3600
                        if age_hours > 48:
                            alerts.append({
                                "name": "stale_data",
                                "severity": "critical",
                                "message": f"Data is {age_hours:.1f} hours old",
                            })
                        elif age_hours > 24:
                            alerts.append({
                                "name": "aging_data",
                                "severity": "warning",
                                "message": f"Data is {age_hours:.1f} hours old",
                            })

                    # Check for failed runs
                    cur.execute("""
                        SELECT COUNT(*) as failures
                        FROM pipeline_runs
                        WHERE status = 'failed'
                          AND started_at >= NOW() - INTERVAL '24 hours'
                    """)
                    result = cur.fetchone()
                    if result and result['failures'] >= 2:
                        alerts.append({
                            "name": "multiple_failures",
                            "severity": "critical",
                            "message": f"{result['failures']} pipeline failures in 24h",
                        })

            finally:
                self.db_pool.putconn(conn)
        except Exception as e:
            logger.warning(f"Failed to check alert conditions: {e}")

        return alerts

    # =========================================================================
    # Metrics Tracking
    # =========================================================================

    def track_run_metrics(self, run_id: str, metrics: Dict[str, Any]):
        """
        Record metrics for a pipeline run.

        Args:
            run_id: Pipeline run identifier
            metrics: Metrics dictionary to store
        """
        try:
            import json
            conn = self.db_pool.getconn()
            try:
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE pipeline_runs
                        SET metrics = %s
                        WHERE run_id = %s
                    """, (json.dumps(metrics), run_id))
                    conn.commit()
            finally:
                self.db_pool.putconn(conn)
        except Exception as e:
            logger.warning(f"Failed to track run metrics: {e}")

    def check_data_freshness(self) -> bool:
        """
        Quick check if data is fresh enough.

        Returns:
            True if data is fresh, False otherwise
        """
        check = self._check_data_freshness()
        return check.healthy

    def alert_on_failure(self, error: Exception, context: Dict[str, Any] = None):
        """
        Handle pipeline failure alerting.

        Args:
            error: The exception that caused the failure
            context: Additional context about the failure

        Note: Actual alerting (email, Slack, etc.) to be implemented in Phase 2
        """
        logger.error(f"Pipeline failure alert: {error}")
        if context:
            logger.error(f"Context: {context}")

        # TODO: Implement actual alerting (email, Slack, PagerDuty)
        # For now, just log the failure
