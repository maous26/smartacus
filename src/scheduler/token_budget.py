"""
Token Budget Manager
====================

Manages monthly Keepa token budget allocation and tracking.

Token Economics (current plan):
- Refill rate: 21 tokens/min = 1,260 tokens/hour = 30,240 tokens/day
- Monthly capacity: ~907,200 tokens (30 days)
- Discovery query: ~5 tokens
- Product query: ~2 tokens/ASIN

Allocation Strategy:
- 20% for category discovery (exploring new niches)
- 80% for regular scanning (tracking known categories)
"""

import os
import logging
from datetime import datetime
from typing import Optional, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class BudgetStatus:
    """Current budget status."""
    month: str
    monthly_limit: int
    tokens_used: int
    tokens_remaining: int
    discovery_budget: int
    scanning_budget: int
    discovery_used: int
    scanning_used: int
    runs_completed: int
    categories_scanned: int
    utilization_pct: float


class TokenBudgetManager:
    """
    Manages monthly Keepa token budget.

    Tracks usage, enforces limits, and allocates tokens between
    discovery (finding new categories) and scanning (regular pipeline runs).

    Environment Variables:
        KEEPA_MONTHLY_TOKEN_LIMIT: Monthly token budget (default: 900000)
        KEEPA_TOKENS_PER_MINUTE: Refill rate (default: 21)
        KEEPA_DISCOVERY_BUDGET_PCT: % for discovery (default: 20)
        KEEPA_SCANNING_BUDGET_PCT: % for scanning (default: 80)
        KEEPA_TOKENS_PER_ASIN: Tokens per ASIN query (default: 2)
        KEEPA_TOKENS_PER_DISCOVERY: Tokens per discovery query (default: 5)
    """

    def __init__(self, conn=None):
        """
        Initialize budget manager.

        Args:
            conn: Optional psycopg2 connection. If None, creates new connection.
        """
        self.conn = conn
        self._owns_connection = False

        # Load from env with sensible defaults
        self.monthly_limit = int(os.getenv("KEEPA_MONTHLY_TOKEN_LIMIT", "900000"))
        self.tokens_per_minute = int(os.getenv("KEEPA_TOKENS_PER_MINUTE", "21"))
        self.discovery_pct = int(os.getenv("KEEPA_DISCOVERY_BUDGET_PCT", "20"))
        self.scanning_pct = int(os.getenv("KEEPA_SCANNING_BUDGET_PCT", "80"))
        self.tokens_per_asin = int(os.getenv("KEEPA_TOKENS_PER_ASIN", "2"))
        self.tokens_per_discovery = int(os.getenv("KEEPA_TOKENS_PER_DISCOVERY", "5"))

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

    def _current_month(self) -> str:
        """Get current month as YYYY-MM string."""
        return datetime.utcnow().strftime("%Y-%m")

    def ensure_budget_exists(self, month: Optional[str] = None) -> None:
        """
        Ensure budget record exists for the given month.

        Creates with default values if not exists.
        """
        month = month or self._current_month()
        conn = self._get_connection()

        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO token_budget (month_year, monthly_limit, discovery_allocation_pct, scanning_allocation_pct)
                VALUES (%s, %s, %s, %s)
                ON CONFLICT (month_year) DO NOTHING
            """, (month, self.monthly_limit, self.discovery_pct, self.scanning_pct))
            conn.commit()

    def get_status(self, month: Optional[str] = None) -> BudgetStatus:
        """
        Get current budget status.

        Returns:
            BudgetStatus with all budget metrics
        """
        month = month or self._current_month()
        self.ensure_budget_exists(month)
        conn = self._get_connection()

        with conn.cursor() as cur:
            cur.execute("""
                SELECT
                    month_year,
                    monthly_limit,
                    tokens_used,
                    tokens_remaining,
                    discovery_allocation_pct,
                    scanning_allocation_pct,
                    runs_completed,
                    categories_scanned,
                    opportunities_found
                FROM token_budget
                WHERE month_year = %s
            """, (month,))
            row = cur.fetchone()

            if not row:
                # Should not happen after ensure_budget_exists
                raise RuntimeError(f"Budget not found for {month}")

            monthly_limit = row[1]
            tokens_used = row[2]
            discovery_pct = row[4]
            scanning_pct = row[5]

            discovery_budget = int(monthly_limit * discovery_pct / 100)
            scanning_budget = int(monthly_limit * scanning_pct / 100)

            return BudgetStatus(
                month=row[0],
                monthly_limit=monthly_limit,
                tokens_used=tokens_used,
                tokens_remaining=row[3],
                discovery_budget=discovery_budget,
                scanning_budget=scanning_budget,
                discovery_used=0,  # TODO: track separately
                scanning_used=tokens_used,
                runs_completed=row[6],
                categories_scanned=row[7],
                utilization_pct=(tokens_used / monthly_limit * 100) if monthly_limit > 0 else 0,
            )

    def can_run(self, estimated_tokens: int, month: Optional[str] = None) -> bool:
        """
        Check if we have budget for a run.

        Args:
            estimated_tokens: Estimated tokens needed for the run
            month: Optional month to check

        Returns:
            True if budget allows the run
        """
        status = self.get_status(month)
        return status.tokens_remaining >= estimated_tokens

    def reserve_tokens(self, amount: int, run_type: str = "scanning") -> bool:
        """
        Reserve tokens for a run.

        Args:
            amount: Number of tokens to reserve
            run_type: "discovery" or "scanning"

        Returns:
            True if reservation successful
        """
        if not self.can_run(amount):
            logger.warning(f"Cannot reserve {amount} tokens - budget exceeded")
            return False

        month = self._current_month()
        conn = self._get_connection()

        with conn.cursor() as cur:
            cur.execute("""
                UPDATE token_budget
                SET tokens_used = tokens_used + %s,
                    updated_at = NOW()
                WHERE month_year = %s
                RETURNING tokens_remaining
            """, (amount, month))
            row = cur.fetchone()
            conn.commit()

            if row:
                logger.info(f"Reserved {amount} tokens for {run_type}. Remaining: {row[0]}")
                return True

        return False

    def record_run(
        self,
        tokens_used: int,
        categories_scanned: int = 1,
        opportunities_found: int = 0,
    ) -> None:
        """
        Record a completed run.

        Args:
            tokens_used: Actual tokens consumed
            categories_scanned: Number of categories scanned
            opportunities_found: Number of opportunities found
        """
        month = self._current_month()
        conn = self._get_connection()

        with conn.cursor() as cur:
            cur.execute("""
                UPDATE token_budget
                SET
                    tokens_used = tokens_used + %s,
                    runs_completed = runs_completed + 1,
                    categories_scanned = categories_scanned + %s,
                    opportunities_found = opportunities_found + %s,
                    updated_at = NOW()
                WHERE month_year = %s
            """, (tokens_used, categories_scanned, opportunities_found, month))
            conn.commit()

        logger.info(f"Recorded run: {tokens_used} tokens, {categories_scanned} categories, {opportunities_found} opportunities")

    def get_daily_budget(self) -> int:
        """
        Calculate recommended daily token budget.

        Returns:
            Tokens to use per day to spread evenly across month
        """
        status = self.get_status()
        today = datetime.utcnow().day
        days_in_month = 30  # Approximation
        days_remaining = max(1, days_in_month - today + 1)

        return status.tokens_remaining // days_remaining

    def get_tokens_for_asins(self, asin_count: int) -> int:
        """
        Estimate tokens needed for a given number of ASINs.

        Uses configurable per-ASIN and per-discovery costs.

        Args:
            asin_count: Number of ASINs to query

        Returns:
            Estimated tokens needed
        """
        return self.tokens_per_discovery + (asin_count * self.tokens_per_asin)

    def close(self):
        """Close connection if we own it."""
        if self._owns_connection and self.conn:
            self.conn.close()
            self.conn = None
