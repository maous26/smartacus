"""
Category Discovery
==================

Automatic discovery and scoring of Amazon categories.

Strategy:
1. Start from seed categories (known high-potential niches)
2. Explore related/sibling categories via Keepa
3. Score categories based on opportunity potential
4. Prioritize categories with best performance metrics
"""

import os
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class CategoryInfo:
    """Information about a category."""
    category_id: int
    name: str
    path: List[str]
    amazon_domain: str
    product_count: Optional[int] = None
    avg_price: Optional[float] = None
    parent_id: Optional[int] = None


@dataclass
class CategoryScore:
    """Scoring result for a category."""
    category_id: int
    name: str
    amazon_domain: str

    # Performance metrics
    total_runs: int
    opportunities_found: int
    avg_score: float
    conversion_rate: float

    # Priority score (lower = better)
    priority_score: float

    # Recommendations
    should_activate: bool
    reason: str


class CategoryDiscovery:
    """
    Discovers and scores Amazon categories for opportunity potential.

    Uses Keepa API to explore category hierarchy and historical
    performance data to prioritize categories.
    """

    # Minimum thresholds for category activation
    MIN_PRODUCT_COUNT = 100
    MAX_PRODUCT_COUNT = 50_000
    MIN_AVG_PRICE = 10.0
    MAX_AVG_PRICE = 200.0

    # Score weights for category prioritization
    WEIGHTS = {
        "recency": 0.2,       # How recently scanned
        "performance": 0.4,   # Historical opportunity conversion
        "potential": 0.3,     # Estimated opportunity density
        "priority": 0.1,      # Manual priority override
    }

    def __init__(self, conn=None, keepa_client=None):
        """
        Initialize category discovery.

        Args:
            conn: Optional psycopg2 connection
            keepa_client: Optional KeepaClient instance
        """
        self.conn = conn
        self.keepa = keepa_client
        self._owns_connection = False

    def _get_connection(self):
        """Get or create database connection."""
        if self.conn:
            return self.conn

        import psycopg2
        self.conn = psycopg2.connect(
            host=os.getenv("DATABASE_HOST", "localhost"),
            port=int(os.getenv("DATABASE_PORT", "5432")),
            dbname=os.getenv("DATABASE_NAME", "smartacus"),
            user=os.getenv("DATABASE_USER", "postgres"),
            password=os.getenv("DATABASE_PASSWORD", ""),
            sslmode=os.getenv("DATABASE_SSL_MODE", "prefer"),
        )
        self._owns_connection = True
        return self.conn

    def _get_keepa(self):
        """Get or create Keepa client."""
        if self.keepa:
            return self.keepa

        from src.data.keepa_client import KeepaClient
        self.keepa = KeepaClient()
        return self.keepa

    def get_active_categories(self, domain: Optional[str] = None) -> List[CategoryInfo]:
        """
        Get all active categories from the registry.

        Args:
            domain: Optional filter by Amazon domain

        Returns:
            List of active CategoryInfo
        """
        conn = self._get_connection()

        with conn.cursor() as cur:
            if domain:
                cur.execute("""
                    SELECT category_id, name, path, amazon_domain, estimated_product_count, avg_price, parent_id
                    FROM category_registry
                    WHERE is_active = true AND amazon_domain = %s
                    ORDER BY priority, last_scanned_at NULLS FIRST
                """, (domain,))
            else:
                cur.execute("""
                    SELECT category_id, name, path, amazon_domain, estimated_product_count, avg_price, parent_id
                    FROM category_registry
                    WHERE is_active = true
                    ORDER BY priority, last_scanned_at NULLS FIRST
                """)

            return [
                CategoryInfo(
                    category_id=row[0],
                    name=row[1],
                    path=row[2] or [],
                    amazon_domain=row[3],
                    product_count=row[4],
                    avg_price=row[5],
                    parent_id=row[6],
                )
                for row in cur.fetchall()
            ]

    def get_next_categories_to_scan(
        self,
        max_categories: int = 5,
        available_tokens: int = 1000,
    ) -> List[Tuple[CategoryInfo, int]]:
        """
        Get next categories to scan based on priority and budget.

        Uses the database function get_next_scan_categories.

        Args:
            max_categories: Maximum categories to return
            available_tokens: Available token budget

        Returns:
            List of (CategoryInfo, estimated_tokens) tuples
        """
        conn = self._get_connection()

        with conn.cursor() as cur:
            cur.execute("""
                SELECT * FROM get_next_scan_categories(%s, %s)
            """, (available_tokens, max_categories))

            results = []
            for row in cur.fetchall():
                cat = CategoryInfo(
                    category_id=row[0],
                    name=row[1],
                    path=[],
                    amazon_domain=row[2],
                )
                estimated_tokens = row[4]
                results.append((cat, estimated_tokens))

            return results

    def discover_related_categories(
        self,
        category_id: int,
        domain: str = "com",
        depth: int = 1,
    ) -> List[CategoryInfo]:
        """
        Discover related categories from a known category.

        Uses Keepa to explore sibling and child categories.

        Args:
            category_id: Starting category ID
            domain: Amazon domain
            depth: How deep to explore (1 = immediate siblings/children)

        Returns:
            List of discovered CategoryInfo
        """
        keepa = self._get_keepa()
        discovered = []

        try:
            # Get category info from Keepa
            # Note: This is a simplified version. Full implementation would
            # use Keepa's category lookup and explore the hierarchy.

            # For now, we'll rely on manual seeding + performance tracking
            logger.info(f"Category discovery for {category_id} (depth={depth}) - using seed categories")

        except Exception as e:
            logger.warning(f"Failed to discover categories from {category_id}: {e}")

        return discovered

    def register_category(
        self,
        category_id: int,
        name: str,
        path: List[str],
        domain: str = "com",
        activate: bool = False,
        priority: int = 5,
    ) -> bool:
        """
        Register a new category in the registry.

        Args:
            category_id: Amazon category node ID
            name: Category name
            path: Breadcrumb path
            domain: Amazon domain
            activate: Whether to immediately activate
            priority: Priority (1=highest, 10=lowest)

        Returns:
            True if registered successfully
        """
        conn = self._get_connection()

        try:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO category_registry (category_id, name, path, amazon_domain, discovered_via, is_active, priority)
                    VALUES (%s, %s, %s, %s, 'discovery', %s, %s)
                    ON CONFLICT (category_id, amazon_domain) DO UPDATE SET
                        name = EXCLUDED.name,
                        path = EXCLUDED.path,
                        priority = LEAST(category_registry.priority, EXCLUDED.priority)
                    RETURNING category_id
                """, (category_id, name, path, domain, activate, priority))
                conn.commit()

                result = cur.fetchone()
                if result:
                    logger.info(f"Registered category {category_id}: {name} ({domain})")
                    return True

        except Exception as e:
            logger.error(f"Failed to register category {category_id}: {e}")
            conn.rollback()

        return False

    def activate_category(self, category_id: int, domain: str = "com") -> bool:
        """Activate a category for scanning."""
        conn = self._get_connection()

        try:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE category_registry
                    SET is_active = true
                    WHERE category_id = %s AND amazon_domain = %s
                    RETURNING category_id
                """, (category_id, domain))
                conn.commit()
                return cur.fetchone() is not None

        except Exception as e:
            logger.error(f"Failed to activate category {category_id}: {e}")
            conn.rollback()
            return False

    def deactivate_category(self, category_id: int, domain: str = "com") -> bool:
        """Deactivate a category from scanning."""
        conn = self._get_connection()

        try:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE category_registry
                    SET is_active = false
                    WHERE category_id = %s AND amazon_domain = %s
                    RETURNING category_id
                """, (category_id, domain))
                conn.commit()
                return cur.fetchone() is not None

        except Exception as e:
            logger.error(f"Failed to deactivate category {category_id}: {e}")
            conn.rollback()
            return False

    def record_scan(
        self,
        category_id: int,
        run_id: str,
        asins_discovered: int,
        asins_scored: int,
        opportunities_found: int,
        high_value_opps: int,
        tokens_used: int,
        total_value: float,
        avg_score: float,
        max_score: int,
        duration_seconds: float,
        error_count: int = 0,
    ) -> None:
        """
        Record performance metrics for a category scan.

        Args:
            category_id: Category that was scanned
            run_id: Pipeline run ID
            asins_discovered: ASINs found in discovery
            asins_scored: ASINs that were scored
            opportunities_found: Opportunities with score >= 40
            high_value_opps: Opportunities with score >= 60
            tokens_used: Keepa tokens consumed
            total_value: Sum of risk-adjusted values
            avg_score: Average opportunity score
            max_score: Highest score found
            duration_seconds: Run duration
            error_count: Number of errors
        """
        conn = self._get_connection()

        try:
            with conn.cursor() as cur:
                # Insert performance record
                cur.execute("""
                    INSERT INTO category_performance (
                        category_id, run_id, asins_discovered, asins_scored,
                        opportunities_found, high_value_opps, tokens_used,
                        tokens_per_opportunity, total_potential_value, avg_score,
                        max_score, duration_seconds, error_count, error_rate
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    category_id, run_id, asins_discovered, asins_scored,
                    opportunities_found, high_value_opps, tokens_used,
                    (tokens_used / opportunities_found) if opportunities_found > 0 else None,
                    total_value, avg_score, max_score, duration_seconds,
                    error_count, (error_count / asins_scored) if asins_scored > 0 else 0,
                ))

                # Update category last_scanned_at
                cur.execute("""
                    UPDATE category_registry
                    SET last_scanned_at = NOW()
                    WHERE category_id = %s
                """, (category_id,))

                # Update category stats
                cur.execute("SELECT update_category_stats(%s)", (category_id,))

                conn.commit()

                logger.info(
                    f"Recorded scan for category {category_id}: "
                    f"{opportunities_found} opps, {tokens_used} tokens"
                )

        except Exception as e:
            logger.error(f"Failed to record scan for category {category_id}: {e}")
            conn.rollback()

    def get_category_scores(self, limit: int = 20) -> List[CategoryScore]:
        """
        Get scored categories ranked by potential.

        Categories are scored based on historical performance,
        recency, and estimated potential.

        Args:
            limit: Maximum categories to return

        Returns:
            List of CategoryScore sorted by priority_score (lower = better)
        """
        conn = self._get_connection()

        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    cr.category_id,
                    cr.name,
                    cr.amazon_domain,
                    cr.total_runs,
                    cr.total_opportunities_found,
                    COALESCE(cr.avg_opportunity_score, 0),
                    COALESCE(cr.conversion_rate, 0),
                    cr.priority,
                    cr.last_scanned_at,
                    cr.is_active
                FROM category_registry cr
                ORDER BY
                    cr.is_active DESC,
                    cr.priority ASC,
                    cr.conversion_rate DESC NULLS LAST,
                    cr.last_scanned_at ASC NULLS FIRST
                LIMIT %s
            """, (limit,))

            results = []
            for row in cur.fetchall():
                # Calculate priority score
                priority = row[7] or 5
                conversion_rate = row[6] or 0
                last_scanned = row[8]

                # Days since last scan (0 if never scanned)
                days_since_scan = 30
                if last_scanned:
                    days_since_scan = (datetime.utcnow() - last_scanned).days

                # Composite priority score (lower = better)
                priority_score = (
                    priority * self.WEIGHTS["priority"] +
                    (1 - conversion_rate) * 10 * self.WEIGHTS["performance"] +
                    (30 - min(30, days_since_scan)) * self.WEIGHTS["recency"]
                )

                # Determine if should activate
                should_activate = (
                    not row[9] and  # Not already active
                    conversion_rate >= 0.1 and  # At least 10% conversion
                    row[3] >= 3  # At least 3 runs
                )

                reason = ""
                if should_activate:
                    reason = f"High conversion rate ({conversion_rate:.1%}) with {row[3]} runs"
                elif row[9]:
                    reason = "Currently active"
                elif row[3] < 3:
                    reason = f"Need more data ({row[3]}/3 runs)"
                else:
                    reason = f"Low conversion ({conversion_rate:.1%})"

                results.append(CategoryScore(
                    category_id=row[0],
                    name=row[1],
                    amazon_domain=row[2],
                    total_runs=row[3],
                    opportunities_found=row[4],
                    avg_score=row[5],
                    conversion_rate=conversion_rate,
                    priority_score=priority_score,
                    should_activate=should_activate,
                    reason=reason,
                ))

            return results

    def auto_manage_categories(self, max_active: int = 10) -> Dict[str, Any]:
        """
        Automatically manage category activation based on performance.

        Activates high-performing categories and deactivates poor performers.

        Args:
            max_active: Maximum categories to keep active

        Returns:
            Summary of actions taken
        """
        scores = self.get_category_scores(limit=50)
        active_count = sum(1 for s in scores if s.priority_score < 5)

        activated = []
        deactivated = []

        for score in scores:
            if score.should_activate and active_count < max_active:
                if self.activate_category(score.category_id, score.amazon_domain):
                    activated.append(score.name)
                    active_count += 1

        # Deactivate poor performers if we have too many active
        if active_count > max_active:
            poor_performers = [
                s for s in scores
                if s.conversion_rate < 0.05 and s.total_runs >= 5
            ]
            for score in poor_performers[:active_count - max_active]:
                if self.deactivate_category(score.category_id, score.amazon_domain):
                    deactivated.append(score.name)

        return {
            "activated": activated,
            "deactivated": deactivated,
            "active_count": active_count,
        }

    def close(self):
        """Close connection if we own it."""
        if self._owns_connection and self.conn:
            self.conn.close()
            self.conn = None
