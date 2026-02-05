"""
Smartacus Database Connection
=============================

Lightweight async-compatible DB access for the API layer.
Uses psycopg2 with connection pooling for Railway PostgreSQL.
"""

import os
import logging
from contextlib import contextmanager
from typing import Optional, Any, Dict

logger = logging.getLogger(__name__)

# Lazy import — psycopg2 may not be installed in all environments
_pool = None


def _get_connection_params() -> dict:
    """Build connection params from environment."""
    return {
        "host": os.getenv("DATABASE_HOST", "localhost"),
        "port": int(os.getenv("DATABASE_PORT", "5432")),
        "dbname": os.getenv("DATABASE_NAME", "smartacus"),
        "user": os.getenv("DATABASE_USER", "postgres"),
        "password": os.getenv("DATABASE_PASSWORD", ""),
        "sslmode": os.getenv("DATABASE_SSL_MODE", "prefer"),
        "connect_timeout": int(os.getenv("DATABASE_CONNECT_TIMEOUT", "10")),
    }


def get_pool():
    """Get or create connection pool (lazy singleton)."""
    global _pool
    if _pool is not None:
        return _pool

    try:
        from psycopg2 import pool as pg_pool
        params = _get_connection_params()
        min_conn = int(os.getenv("DATABASE_POOL_MIN", "2"))
        max_conn = int(os.getenv("DATABASE_POOL_MAX", "10"))
        _pool = pg_pool.ThreadedConnectionPool(min_conn, max_conn, **params)
        logger.info(f"DB pool created: {params['host']}:{params['port']}/{params['dbname']}")
        return _pool
    except Exception as e:
        logger.warning(f"Failed to create DB pool: {e}")
        return None


def close_pool():
    """Close the connection pool."""
    global _pool
    if _pool is not None:
        _pool.closeall()
        _pool = None
        logger.info("DB pool closed")


@contextmanager
def get_connection():
    """Get a connection from the pool (context manager)."""
    pool = get_pool()
    if pool is None:
        raise ConnectionError("Database pool not available")
    conn = pool.getconn()
    try:
        yield conn
    finally:
        pool.putconn(conn)


def check_health() -> Dict[str, Any]:
    """
    Check database health. Returns status dict.
    Non-blocking: returns 'disconnected' if DB is not reachable.
    """
    try:
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT version(), pg_database_size(current_database())")
            row = cur.fetchone()
            cur.close()
            version = row[0].split(",")[0] if row[0] else "unknown"
            size_mb = round(row[1] / 1024 / 1024, 2) if row[1] else 0
            return {
                "status": "connected",
                "version": version,
                "size_mb": size_mb,
            }
    except Exception as e:
        logger.warning(f"DB health check failed: {e}")
        return {
            "status": "disconnected",
            "error": str(e),
        }


def get_db_metrics() -> Optional[Dict[str, Any]]:
    """
    Get full DB metrics via the get_db_metrics() SQL function.
    Returns None if DB is not reachable.
    """
    try:
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT get_db_metrics()")
            result = cur.fetchone()
            cur.close()
            return result[0] if result else None
    except Exception as e:
        logger.warning(f"Failed to get DB metrics: {e}")
        return None


def get_latest_pipeline_run() -> Optional[Dict[str, Any]]:
    """Get the most recent pipeline run info."""
    try:
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                SELECT run_id, status, started_at, ended_at,
                       asins_total, asins_ok, asins_failed,
                       duration_total_ms, opportunities_generated,
                       error_rate, error_budget_breached, dq_passed
                FROM pipeline_runs
                ORDER BY started_at DESC
                LIMIT 1
            """)
            row = cur.fetchone()
            cur.close()
            if not row:
                return None
            return {
                "run_id": str(row[0]),
                "status": row[1],
                "started_at": row[2].isoformat() if row[2] else None,
                "ended_at": row[3].isoformat() if row[3] else None,
                "asins_total": row[4],
                "asins_ok": row[5],
                "asins_failed": row[6],
                "duration_total_ms": row[7],
                "opportunities_generated": row[8],
                "error_rate": float(row[9]) if row[9] else None,
                "error_budget_breached": row[10],
                "dq_passed": row[11],
            }
    except Exception as e:
        logger.warning(f"Failed to get latest pipeline run: {e}")
        return None


# ============================================================================
# PIPELINE RUN TRACKING
# ============================================================================

def create_pipeline_run(triggered_by: str = "manual", config_snapshot: dict = None) -> Optional[str]:
    """Create a new pipeline run record. Returns run_id (UUID string)."""
    try:
        import json
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO pipeline_runs (triggered_by, config_snapshot)
                VALUES (%s, %s)
                RETURNING run_id
            """, (triggered_by, json.dumps(config_snapshot) if config_snapshot else None))
            conn.commit()
            run_id = str(cur.fetchone()[0])
            cur.close()
            return run_id
    except Exception as e:
        logger.error(f"Failed to create pipeline run: {e}")
        return None


def update_pipeline_run(run_id: str, **kwargs) -> bool:
    """
    Update pipeline run fields.

    Supported kwargs: status, asins_total, asins_ok, asins_failed, asins_skipped,
    duration_ingestion_ms, duration_events_ms, duration_scoring_ms, duration_refresh_ms,
    duration_total_ms, opportunities_generated, events_generated, shortlist_size,
    keepa_tokens_used, db_size_mb, error_message, error_details, failed_asins,
    config_snapshot, error_rate, error_budget_breached, shortlist_frozen,
    dq_price_missing_pct, dq_bsr_missing_pct, dq_review_missing_pct, dq_passed
    """
    if not kwargs:
        return True
    try:
        import json
        set_clauses = []
        values = []
        for key, val in kwargs.items():
            set_clauses.append(f"{key} = %s")
            if isinstance(val, (dict, list)):
                values.append(json.dumps(val))
            else:
                values.append(val)

        # Auto-set ended_at when status is terminal
        if kwargs.get("status") in ("completed", "failed", "degraded", "cancelled"):
            set_clauses.append("ended_at = NOW()")

        values.append(run_id)
        sql = f"UPDATE pipeline_runs SET {', '.join(set_clauses)} WHERE run_id = %s"

        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute(sql, values)
            conn.commit()
            cur.close()
            return True
    except Exception as e:
        logger.error(f"Failed to update pipeline run {run_id}: {e}")
        return False


# ============================================================================
# MAINTENANCE
# ============================================================================

def run_maintenance(retention_days: int = 180) -> Dict[str, Any]:
    """
    Run cleanup + vacuum on event tables.
    Returns stats about what was cleaned.
    """
    stats = {
        "retention_days": retention_days,
        "rows_deleted": {},
        "db_size_before_mb": None,
        "db_size_after_mb": None,
    }

    try:
        with get_connection() as conn:
            conn.autocommit = True
            cur = conn.cursor()

            # DB size before
            cur.execute("SELECT pg_database_size(current_database())")
            stats["db_size_before_mb"] = round(cur.fetchone()[0] / 1024 / 1024, 2)

            # Cleanup old events
            for table in ["price_events", "bsr_events", "stock_events"]:
                cur.execute(f"""
                    DELETE FROM {table}
                    WHERE detected_at < NOW() - INTERVAL '{retention_days} days'
                """)
                stats["rows_deleted"][table] = cur.rowcount

            # Cleanup archived opportunities
            cur.execute(f"""
                DELETE FROM opportunities
                WHERE status = 'archived'
                AND updated_at < NOW() - INTERVAL '{retention_days} days'
            """)
            stats["rows_deleted"]["opportunities_archived"] = cur.rowcount

            # VACUUM ANALYZE on high-churn tables
            for table in ["asin_snapshots", "price_events", "bsr_events",
                          "stock_events", "opportunity_artifacts"]:
                cur.execute(f"VACUUM (ANALYZE) {table}")

            # DB size after
            cur.execute("SELECT pg_database_size(current_database())")
            stats["db_size_after_mb"] = round(cur.fetchone()[0] / 1024 / 1024, 2)

            cur.close()

            logger.info(
                f"Maintenance complete: deleted {sum(stats['rows_deleted'].values())} rows, "
                f"DB {stats['db_size_before_mb']}→{stats['db_size_after_mb']} MB"
            )
            return stats
    except Exception as e:
        logger.error(f"Maintenance failed: {e}")
        stats["error"] = str(e)
        return stats


def refresh_materialized_views() -> Dict[str, Any]:
    """Refresh all materialized views. Returns timing per view."""
    import time
    results = {}

    try:
        with get_connection() as conn:
            conn.autocommit = True
            cur = conn.cursor()

            views = [
                "mv_latest_snapshots",
                "mv_asin_stats_7d",
                "mv_asin_stats_30d",
                "mv_review_sentiment",
            ]

            for view in views:
                start = time.monotonic()
                try:
                    cur.execute(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {view}")
                    elapsed_ms = int((time.monotonic() - start) * 1000)
                    results[view] = {"status": "ok", "duration_ms": elapsed_ms}
                except Exception as e:
                    elapsed_ms = int((time.monotonic() - start) * 1000)
                    results[view] = {"status": "error", "error": str(e), "duration_ms": elapsed_ms}

            cur.close()
            return results
    except Exception as e:
        logger.error(f"Mat view refresh failed: {e}")
        return {"error": str(e)}
