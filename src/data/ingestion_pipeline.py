"""
Smartacus Ingestion Pipeline
============================

Orchestrates the daily data pull from Keepa API, transforms data to our schema,
and performs batch insertions into PostgreSQL.

Features:
    - ASIN discovery and filtering based on configurable criteria
    - Incremental updates (skip recently updated ASINs)
    - Batch processing with progress tracking
    - Robust error handling and recovery
    - Comprehensive logging and metrics

Usage:
    from ingestion_pipeline import IngestionPipeline

    pipeline = IngestionPipeline()
    result = pipeline.run_daily_ingestion()
"""

import uuid
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Dict, Optional, Any, Tuple, Generator
from contextlib import contextmanager
import json

import psycopg2
from psycopg2.extras import execute_values, RealDictCursor
from psycopg2 import pool

from .keepa_client import KeepaClient, KeepaAPIError
from .data_models import (
    ProductData,
    ProductSnapshot,
    ProductMetadata,
    IngestionResult,
    StockStatus,
    FulfillmentType,
)


# Configure logging
logger = logging.getLogger(__name__)


class DatabaseError(Exception):
    """Database operation error."""
    pass


class IngestionPipeline:
    """
    Orchestrates Keepa data ingestion into PostgreSQL.

    This pipeline:
    1. Discovers ASINs in target category
    2. Filters ASINs based on configured criteria
    3. Fetches product data from Keepa in batches
    4. Transforms data to our database schema
    5. Performs batch upserts into PostgreSQL
    6. Generates ingestion reports
    """

    def __init__(
        self,
        keepa_client: Optional[KeepaClient] = None,
        db_pool: Optional[pool.ThreadedConnectionPool] = None,
    ):
        """
        Initialize the ingestion pipeline.

        Args:
            keepa_client: Keepa API client (creates new if None)
            db_pool: Database connection pool (creates new if None)
        """
        # Load configuration
        from .config import get_settings
        self.settings = get_settings()

        # Initialize Keepa client
        self.keepa = keepa_client or KeepaClient()

        # Initialize database pool
        self._db_pool = db_pool
        self._own_pool = db_pool is None

        # Pipeline state
        self._current_batch_id: Optional[str] = None
        self._session_stats = {
            "asins_discovered": 0,
            "asins_filtered": 0,
            "asins_processed": 0,
            "snapshots_inserted": 0,
            "errors": [],
        }

        logger.info(
            f"IngestionPipeline initialized: "
            f"category={self.settings.ingestion.category_node_id}, "
            f"batch_size={self.settings.ingestion.batch_size}"
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

    @contextmanager
    def get_db_connection(self):
        """
        Get a database connection from the pool.

        Yields:
            psycopg2 connection object

        Example:
            with self.get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
        """
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
    # ASIN Discovery and Filtering
    # =========================================================================

    def discover_category_asins(self) -> List[str]:
        """
        Discover all ASINs in the target category.

        Returns:
            List of discovered ASINs
        """
        category_id = self.settings.ingestion.category_node_id
        logger.info(f"Discovering ASINs in category {category_id}")

        try:
            asins = self.keepa.get_category_asins(
                category_node_id=category_id,
                include_children=True,
                max_results=self.settings.ingestion.target_asin_count * 2,  # Over-fetch for filtering
            )

            self._session_stats["asins_discovered"] = len(asins)
            logger.info(f"Discovered {len(asins)} ASINs in category")
            return asins

        except KeepaAPIError as e:
            logger.error(f"Failed to discover category ASINs: {e}")
            raise

    def get_asins_needing_update(self, asins: List[str]) -> List[str]:
        """
        Filter ASINs to only those needing an update.

        Excludes ASINs that have been updated within the freshness threshold.

        Args:
            asins: List of ASINs to check

        Returns:
            List of ASINs that need updating
        """
        if not asins:
            return []

        freshness_hours = self.settings.ingestion.freshness_threshold_hours
        cutoff = datetime.utcnow() - timedelta(hours=freshness_hours)

        with self.get_db_connection() as conn:
            with conn.cursor() as cur:
                # Find ASINs with recent snapshots
                cur.execute(
                    """
                    SELECT DISTINCT asin
                    FROM asin_snapshots
                    WHERE asin = ANY(%s)
                      AND captured_at >= %s
                    """,
                    (asins, cutoff)
                )
                recent_asins = {row[0] for row in cur.fetchall()}

        # Return ASINs not recently updated
        needs_update = [a for a in asins if a not in recent_asins]
        logger.info(
            f"Filtered {len(asins)} ASINs: {len(needs_update)} need update, "
            f"{len(recent_asins)} recently updated"
        )
        return needs_update

    def filter_asins_by_criteria(self, asins: List[str]) -> List[str]:
        """
        Filter ASINs based on configured criteria (price, reviews, rating, BSR).

        This requires fetching basic product data first, so it's done
        in batches to manage token usage.

        Args:
            asins: List of ASINs to filter

        Returns:
            List of ASINs meeting criteria
        """
        config = self.settings.ingestion
        logger.info(
            f"Filtering {len(asins)} ASINs by criteria: "
            f"price ${config.min_price_usd}-${config.max_price_usd}, "
            f"reviews >= {config.min_reviews}, "
            f"rating >= {config.min_rating}, "
            f"BSR <= {config.max_bsr}"
        )

        filtered = []
        batch_size = config.batch_size

        for i in range(0, len(asins), batch_size):
            batch = asins[i:i + batch_size]

            try:
                # Fetch basic data (no history to save tokens)
                products = self.keepa.get_product_data(
                    batch,
                    include_history=False,
                    include_buybox=False,
                    include_offers=False,
                )

                for product in products:
                    snapshot = product.current_snapshot

                    # Apply filters
                    if not self._product_meets_criteria(snapshot, config):
                        continue

                    filtered.append(product.asin)

            except KeepaAPIError as e:
                logger.warning(f"Batch filtering failed, skipping {len(batch)} ASINs: {e}")
                continue

            # Progress logging
            progress = min(i + batch_size, len(asins))
            logger.info(f"Filtering progress: {progress}/{len(asins)} ({len(filtered)} passed)")

        self._session_stats["asins_filtered"] = len(filtered)
        logger.info(f"Filtered to {len(filtered)} ASINs meeting criteria")
        return filtered

    def _product_meets_criteria(self, snapshot: ProductSnapshot, config) -> bool:
        """Check if a product snapshot meets filtering criteria."""
        # Price filter
        if snapshot.price_current:
            price = float(snapshot.price_current)
            if price < config.min_price_usd or price > config.max_price_usd:
                return False

        # Review count filter
        if snapshot.review_count is not None:
            if snapshot.review_count < config.min_reviews:
                return False

        # Rating filter
        if snapshot.rating_average is not None:
            if float(snapshot.rating_average) < config.min_rating:
                return False

        # BSR filter
        if snapshot.bsr_primary is not None:
            if snapshot.bsr_primary > config.max_bsr:
                return False

        return True

    # =========================================================================
    # Data Fetching and Transformation
    # =========================================================================

    def fetch_product_batch(
        self,
        asins: List[str],
        include_history: bool = True,
    ) -> List[ProductData]:
        """
        Fetch detailed product data for a batch of ASINs.

        Args:
            asins: List of ASINs (max 100)
            include_history: Include price/BSR history

        Returns:
            List of ProductData objects
        """
        try:
            return self.keepa.get_product_data(
                asins,
                include_history=include_history,
                history_days=90,
                include_buybox=self.settings.ingestion.enable_buybox_history,
                include_offers=False,
            )
        except KeepaAPIError as e:
            logger.error(f"Failed to fetch batch of {len(asins)} ASINs: {e}")
            raise

    def generate_batches(
        self,
        asins: List[str],
        batch_size: Optional[int] = None,
    ) -> Generator[List[str], None, None]:
        """
        Generate ASIN batches for processing.

        Args:
            asins: Full list of ASINs
            batch_size: Size of each batch (default from config)

        Yields:
            Lists of ASINs
        """
        size = batch_size or self.settings.ingestion.batch_size
        for i in range(0, len(asins), size):
            yield asins[i:i + size]

    # =========================================================================
    # Database Operations
    # =========================================================================

    def upsert_asin_metadata(self, products: List[ProductData]) -> int:
        """
        Insert or update ASIN metadata in the asins table.

        Args:
            products: List of ProductData objects

        Returns:
            Number of rows affected
        """
        if not products:
            return 0

        values = []
        for product in products:
            meta = product.metadata
            values.append((
                meta.asin,
                meta.title,
                meta.brand,
                meta.manufacturer,
                meta.model_number,
                meta.category_id,
                meta.category_path,
                meta.subcategory,
                meta.color,
                meta.size,
                meta.material,
                meta.weight_grams,
                json.dumps(meta.dimensions_cm) if meta.dimensions_cm else None,
                meta.main_image_url,
                meta.bullet_points,
                meta.description,
                meta.is_amazon_choice,
                meta.is_best_seller,
                datetime.utcnow(),
            ))

        with self.get_db_connection() as conn:
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    """
                    INSERT INTO asins (
                        asin, title, brand, manufacturer, model_number,
                        category_id, category_path, subcategory,
                        color, size, material, weight_grams, dimensions_cm,
                        main_image_url, bullet_points, description,
                        is_amazon_choice, is_best_seller, last_updated_at
                    ) VALUES %s
                    ON CONFLICT (asin) DO UPDATE SET
                        title = EXCLUDED.title,
                        brand = EXCLUDED.brand,
                        manufacturer = EXCLUDED.manufacturer,
                        model_number = EXCLUDED.model_number,
                        category_id = EXCLUDED.category_id,
                        category_path = EXCLUDED.category_path,
                        subcategory = EXCLUDED.subcategory,
                        color = EXCLUDED.color,
                        size = EXCLUDED.size,
                        material = EXCLUDED.material,
                        weight_grams = EXCLUDED.weight_grams,
                        dimensions_cm = EXCLUDED.dimensions_cm,
                        main_image_url = EXCLUDED.main_image_url,
                        bullet_points = EXCLUDED.bullet_points,
                        description = EXCLUDED.description,
                        is_amazon_choice = EXCLUDED.is_amazon_choice,
                        is_best_seller = EXCLUDED.is_best_seller,
                        last_updated_at = EXCLUDED.last_updated_at
                    """,
                    values,
                    page_size=100
                )
                affected = cur.rowcount

        logger.debug(f"Upserted {affected} ASIN metadata records")
        return affected

    def insert_snapshots(self, products: List[ProductData], session_id: str) -> int:
        """
        Insert product snapshots into asin_snapshots table.

        Args:
            products: List of ProductData objects
            session_id: Current ingestion session ID

        Returns:
            Number of rows inserted
        """
        if not products:
            return 0

        values = []
        for product in products:
            snap = product.current_snapshot
            values.append((
                snap.asin,
                snap.captured_at,
                float(snap.price_current) if snap.price_current else None,
                float(snap.price_original) if snap.price_original else None,
                float(snap.price_lowest_new) if snap.price_lowest_new else None,
                float(snap.price_lowest_used) if snap.price_lowest_used else None,
                snap.price_currency,
                float(snap.coupon_discount_percent) if snap.coupon_discount_percent else None,
                float(snap.coupon_discount_amount) if snap.coupon_discount_amount else None,
                snap.deal_type,
                snap.bsr_primary,
                snap.bsr_category_name,
                snap.bsr_subcategory,
                snap.bsr_subcategory_name,
                snap.stock_status.value,
                snap.stock_quantity,
                snap.fulfillment.value,
                snap.seller_count,
                float(snap.rating_average) if snap.rating_average else None,
                snap.rating_count,
                snap.review_count,
                snap.rating_distribution.get(5) if snap.rating_distribution else None,
                snap.rating_distribution.get(4) if snap.rating_distribution else None,
                snap.rating_distribution.get(3) if snap.rating_distribution else None,
                snap.rating_distribution.get(2) if snap.rating_distribution else None,
                snap.rating_distribution.get(1) if snap.rating_distribution else None,
                session_id,
                snap.data_source,
            ))

        with self.get_db_connection() as conn:
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    """
                    INSERT INTO asin_snapshots (
                        asin, captured_at,
                        price_current, price_original, price_lowest_new, price_lowest_used,
                        price_currency, coupon_discount_percent, coupon_discount_amount,
                        deal_type,
                        bsr_primary, bsr_category_name, bsr_subcategory, bsr_subcategory_name,
                        stock_status, stock_quantity, fulfillment, seller_count,
                        rating_average, rating_count, review_count,
                        rating_5_star_percent, rating_4_star_percent,
                        rating_3_star_percent, rating_2_star_percent, rating_1_star_percent,
                        scrape_session_id, data_source
                    ) VALUES %s
                    ON CONFLICT (asin, captured_at) DO NOTHING
                    """,
                    values,
                    page_size=100
                )
                affected = cur.rowcount

        logger.debug(f"Inserted {affected} snapshot records")
        return affected

    def refresh_materialized_views(self) -> None:
        """Refresh materialized views after ingestion."""
        logger.info("Refreshing materialized views")

        views = [
            "mv_latest_snapshots",
            "mv_asin_stats_7d",
            "mv_asin_stats_30d",
        ]

        with self.get_db_connection() as conn:
            with conn.cursor() as cur:
                for view in views:
                    try:
                        cur.execute(f"REFRESH MATERIALIZED VIEW CONCURRENTLY {view}")
                        logger.debug(f"Refreshed {view}")
                    except Exception as e:
                        logger.warning(f"Failed to refresh {view}: {e}")

    # =========================================================================
    # Main Pipeline Orchestration
    # =========================================================================

    def run_daily_ingestion(
        self,
        asins: Optional[List[str]] = None,
        skip_discovery: bool = False,
        skip_filtering: bool = False,
        max_asins: Optional[int] = None,
    ) -> IngestionResult:
        """
        Run the complete daily ingestion pipeline.

        Args:
            asins: Pre-defined ASIN list (skips discovery if provided)
            skip_discovery: Skip category discovery step
            skip_filtering: Skip criteria filtering step
            max_asins: Limit number of ASINs to process

        Returns:
            IngestionResult with statistics

        Process:
            1. Discover ASINs in category (or use provided list)
            2. Filter to ASINs needing update
            3. Filter by criteria (price, reviews, rating, BSR)
            4. Fetch product data in batches
            5. Insert metadata and snapshots
            6. Refresh materialized views
        """
        batch_id = str(uuid.uuid4())
        self._current_batch_id = batch_id

        result = IngestionResult(
            batch_id=batch_id,
            started_at=datetime.utcnow(),
        )

        logger.info(f"Starting daily ingestion pipeline (batch_id={batch_id})")

        try:
            # Step 1: Discover ASINs
            if asins is not None:
                logger.info(f"Using provided ASIN list ({len(asins)} ASINs)")
                target_asins = asins
            elif skip_discovery:
                # Get existing ASINs from database
                target_asins = self._get_tracked_asins()
            else:
                target_asins = self.discover_category_asins()

            if not target_asins:
                logger.warning("No ASINs to process")
                result.completed_at = datetime.utcnow()
                return result

            # Step 2: Filter to ASINs needing update
            target_asins = self.get_asins_needing_update(target_asins)

            if not target_asins:
                logger.info("All ASINs are up to date")
                result.completed_at = datetime.utcnow()
                return result

            # Step 3: Apply criteria filtering
            if not skip_filtering:
                target_asins = self.filter_asins_by_criteria(target_asins)

            if not target_asins:
                logger.info("No ASINs passed filtering criteria")
                result.completed_at = datetime.utcnow()
                return result

            # Apply max limit if specified
            if max_asins and len(target_asins) > max_asins:
                logger.info(f"Limiting to {max_asins} ASINs (from {len(target_asins)})")
                target_asins = target_asins[:max_asins]

            result.asins_requested = len(target_asins)

            # Step 4 & 5: Process in batches
            batch_size = self.settings.ingestion.batch_size
            total_batches = (len(target_asins) + batch_size - 1) // batch_size

            for batch_num, asin_batch in enumerate(self.generate_batches(target_asins), 1):
                logger.info(f"Processing batch {batch_num}/{total_batches} ({len(asin_batch)} ASINs)")

                try:
                    # Fetch product data
                    products = self.fetch_product_batch(asin_batch, include_history=True)

                    if not products:
                        logger.warning(f"No products returned for batch {batch_num}")
                        continue

                    # Insert metadata
                    self.upsert_asin_metadata(products)

                    # Insert snapshots
                    inserted = self.insert_snapshots(products, batch_id)

                    result.asins_processed += len(products)
                    result.snapshots_inserted += inserted

                    # Track token usage
                    keepa_stats = self.keepa.get_stats()
                    result.tokens_consumed = keepa_stats.get("total_tokens_consumed", 0)
                    result.tokens_remaining = keepa_stats.get("tokens_remaining", 0)

                    logger.info(
                        f"Batch {batch_num} complete: "
                        f"{len(products)} products, {inserted} snapshots, "
                        f"{result.tokens_remaining} tokens remaining"
                    )

                except KeepaAPIError as e:
                    logger.error(f"Batch {batch_num} failed: {e}")
                    for asin in asin_batch:
                        result.add_error(asin, "KeepaAPIError", str(e))
                    continue

                except DatabaseError as e:
                    logger.error(f"Database error in batch {batch_num}: {e}")
                    for asin in asin_batch:
                        result.add_error(asin, "DatabaseError", str(e))
                    continue

            # Step 6: Refresh materialized views
            try:
                self.refresh_materialized_views()
            except Exception as e:
                logger.warning(f"Failed to refresh materialized views: {e}")

            result.completed_at = datetime.utcnow()
            result.asins_inserted = result.snapshots_inserted
            result.asins_skipped = result.asins_requested - result.asins_processed

            logger.info(
                f"Ingestion complete: "
                f"{result.asins_processed} processed, "
                f"{result.asins_failed} failed, "
                f"{result.snapshots_inserted} snapshots in "
                f"{result.duration_seconds:.1f}s"
            )

            return result

        except Exception as e:
            logger.error(f"Ingestion pipeline failed: {e}")
            result.completed_at = datetime.utcnow()
            result.add_error("pipeline", "PipelineError", str(e))
            raise

        finally:
            self._current_batch_id = None

    def run_incremental_update(
        self,
        asins: List[str],
        force: bool = False,
    ) -> IngestionResult:
        """
        Run incremental update for specific ASINs.

        Args:
            asins: List of ASINs to update
            force: Force update even if recently updated

        Returns:
            IngestionResult with statistics
        """
        if not force:
            asins = self.get_asins_needing_update(asins)

        return self.run_daily_ingestion(
            asins=asins,
            skip_discovery=True,
            skip_filtering=True,
        )

    def _get_tracked_asins(self) -> List[str]:
        """Get list of currently tracked ASINs from database."""
        with self.get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT asin FROM asins
                    WHERE is_active = TRUE AND deleted_at IS NULL
                    ORDER BY tracking_priority DESC, last_updated_at ASC
                    LIMIT %s
                    """,
                    (self.settings.ingestion.target_asin_count,)
                )
                return [row[0] for row in cur.fetchall()]

    # =========================================================================
    # Reporting and Monitoring
    # =========================================================================

    def get_ingestion_stats(self) -> Dict[str, Any]:
        """
        Get current ingestion statistics.

        Returns:
            Dictionary with statistics
        """
        with self.get_db_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Total tracked ASINs
                cur.execute("SELECT COUNT(*) as count FROM asins WHERE is_active = TRUE")
                total_asins = cur.fetchone()["count"]

                # Snapshots in last 24h
                cur.execute(
                    """
                    SELECT COUNT(*) as count
                    FROM asin_snapshots
                    WHERE captured_at >= NOW() - INTERVAL '24 hours'
                    """
                )
                snapshots_24h = cur.fetchone()["count"]

                # ASINs updated in last 24h
                cur.execute(
                    """
                    SELECT COUNT(DISTINCT asin) as count
                    FROM asin_snapshots
                    WHERE captured_at >= NOW() - INTERVAL '24 hours'
                    """
                )
                asins_updated_24h = cur.fetchone()["count"]

                # Latest snapshot time
                cur.execute("SELECT MAX(captured_at) as latest FROM asin_snapshots")
                latest_snapshot = cur.fetchone()["latest"]

        keepa_stats = self.keepa.get_stats()

        return {
            "database": {
                "total_tracked_asins": total_asins,
                "snapshots_last_24h": snapshots_24h,
                "asins_updated_24h": asins_updated_24h,
                "latest_snapshot": latest_snapshot.isoformat() if latest_snapshot else None,
            },
            "keepa": keepa_stats,
            "session": self._session_stats,
        }

    def health_check(self) -> Dict[str, Any]:
        """
        Perform health check on pipeline components.

        Returns:
            Health status dictionary
        """
        health = {
            "status": "healthy",
            "components": {},
            "timestamp": datetime.utcnow().isoformat(),
        }

        # Check database
        try:
            with self.get_db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
            health["components"]["database"] = {"status": "healthy"}
        except Exception as e:
            health["components"]["database"] = {"status": "unhealthy", "error": str(e)}
            health["status"] = "unhealthy"

        # Check Keepa API
        keepa_health = self.keepa.health_check()
        health["components"]["keepa"] = keepa_health
        if keepa_health.get("status") != "healthy":
            health["status"] = "degraded"

        return health


# =========================================================================
# CLI Entry Point
# =========================================================================

def main():
    """Command-line entry point for running ingestion."""
    import argparse

    parser = argparse.ArgumentParser(description="Smartacus Keepa Ingestion Pipeline")
    parser.add_argument(
        "--mode",
        choices=["full", "incremental", "stats", "health"],
        default="full",
        help="Ingestion mode"
    )
    parser.add_argument(
        "--max-asins",
        type=int,
        default=None,
        help="Maximum ASINs to process"
    )
    parser.add_argument(
        "--skip-filter",
        action="store_true",
        help="Skip criteria filtering"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args()

    # Configure logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    with IngestionPipeline() as pipeline:
        if args.mode == "health":
            health = pipeline.health_check()
            print(json.dumps(health, indent=2, default=str))

        elif args.mode == "stats":
            stats = pipeline.get_ingestion_stats()
            print(json.dumps(stats, indent=2, default=str))

        elif args.mode == "full":
            result = pipeline.run_daily_ingestion(
                max_asins=args.max_asins,
                skip_filtering=args.skip_filter,
            )
            print(f"\nIngestion Complete:")
            print(f"  Processed: {result.asins_processed}")
            print(f"  Snapshots: {result.snapshots_inserted}")
            print(f"  Failed: {result.asins_failed}")
            print(f"  Duration: {result.duration_seconds:.1f}s")
            print(f"  Tokens used: {result.tokens_consumed}")

        elif args.mode == "incremental":
            # Get ASINs from database for incremental update
            asins = pipeline._get_tracked_asins()
            if args.max_asins:
                asins = asins[:args.max_asins]

            result = pipeline.run_incremental_update(asins)
            print(f"\nIncremental Update Complete:")
            print(f"  Processed: {result.asins_processed}")
            print(f"  Snapshots: {result.snapshots_inserted}")


if __name__ == "__main__":
    main()
