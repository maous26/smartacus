"""
Smart Scheduler
===============

Intelligent pipeline scheduling with:
- Monthly token budget management
- Multi-category support with auto-selection
- Performance-based prioritization
- Configurable run frequency

Usage:
    scheduler = SmartScheduler()
    scheduler.run()  # Single scheduled run
    scheduler.start_daemon()  # Background daemon

CLI:
    python -m src.scheduler.scheduler --run-once
    python -m src.scheduler.scheduler --daemon
"""

import os
import sys
import time
import logging
import argparse
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from .token_budget import TokenBudgetManager, BudgetStatus
from .category_discovery import CategoryDiscovery, CategoryInfo

logger = logging.getLogger(__name__)


@dataclass
class SchedulerConfig:
    """Scheduler configuration."""
    enabled: bool = True
    run_interval_hours: int = 24
    min_tokens_per_run: int = 50
    max_categories_per_run: int = 5
    max_asins_per_category: int = 100
    discovery_enabled: bool = True
    discovery_depth: int = 2
    target_domains: List[str] = None

    def __post_init__(self):
        if self.target_domains is None:
            self.target_domains = ["com", "fr"]


@dataclass
class RunResult:
    """Result of a scheduled run."""
    success: bool
    category_id: int
    category_name: str
    domain: str
    tokens_used: int
    asins_processed: int
    opportunities_found: int
    duration_seconds: float
    error: Optional[str] = None


class SmartScheduler:
    """
    Intelligent scheduler for automated pipeline runs.

    Features:
    - Token budget awareness (monthly limits)
    - Multi-category scanning
    - Performance-based category selection
    - Automatic category discovery
    """

    def __init__(self, config: Optional[SchedulerConfig] = None):
        """
        Initialize scheduler.

        Args:
            config: Optional SchedulerConfig. Loads from DB if None.
        """
        self.config = config or self._load_config()
        self.budget_manager = TokenBudgetManager()
        self.category_discovery = CategoryDiscovery()

    def _load_config(self) -> SchedulerConfig:
        """Load configuration from database."""
        import psycopg2
        import json

        try:
            conn = psycopg2.connect(
                host=os.getenv("DATABASE_HOST", "localhost"),
                port=int(os.getenv("DATABASE_PORT", "5432")),
                dbname=os.getenv("DATABASE_NAME", "smartacus"),
                user=os.getenv("DATABASE_USER", "postgres"),
                password=os.getenv("DATABASE_PASSWORD", ""),
                sslmode=os.getenv("DATABASE_SSL_MODE", "prefer"),
            )

            with conn.cursor() as cur:
                cur.execute("SELECT key, value FROM scheduler_config")
                config_dict = {row[0]: row[1] for row in cur.fetchall()}

            conn.close()

            return SchedulerConfig(
                enabled=config_dict.get("enabled", True) == "true" or config_dict.get("enabled") is True,
                run_interval_hours=int(config_dict.get("run_interval_hours", 24)),
                min_tokens_per_run=int(config_dict.get("min_tokens_per_run", 50)),
                max_categories_per_run=int(config_dict.get("max_categories_per_run", 5)),
                discovery_enabled=config_dict.get("discovery_enabled", "true") == "true",
                discovery_depth=int(config_dict.get("discovery_depth", 2)),
                target_domains=config_dict.get("target_domains", ["com", "fr"]),
            )

        except Exception as e:
            logger.warning(f"Failed to load config from DB, using defaults: {e}")
            return SchedulerConfig()

    def get_status(self) -> Dict[str, Any]:
        """
        Get scheduler status.

        Returns:
            Dict with scheduler state, budget, and category info
        """
        budget = self.budget_manager.get_status()
        active_categories = self.category_discovery.get_active_categories()

        return {
            "enabled": self.config.enabled,
            "interval_hours": self.config.run_interval_hours,
            "budget": {
                "month": budget.month,
                "limit": budget.monthly_limit,
                "used": budget.tokens_used,
                "remaining": budget.tokens_remaining,
                "utilization_pct": budget.utilization_pct,
            },
            "categories": {
                "active_count": len(active_categories),
                "active": [
                    {"id": c.category_id, "name": c.name, "domain": c.amazon_domain}
                    for c in active_categories[:10]
                ],
            },
            "daily_budget": self.budget_manager.get_daily_budget(),
        }

    def should_run(self) -> bool:
        """
        Check if a run should be triggered.

        Returns:
            True if scheduler should run now
        """
        if not self.config.enabled:
            logger.info("Scheduler is disabled")
            return False

        budget = self.budget_manager.get_status()
        if budget.tokens_remaining < self.config.min_tokens_per_run:
            logger.warning(f"Insufficient budget: {budget.tokens_remaining} < {self.config.min_tokens_per_run}")
            return False

        # Check if enough time has passed since last run
        # (In production, would check last_run_at from DB)
        return True

    def select_categories(self) -> List[CategoryInfo]:
        """
        Select categories to scan based on priority and budget.

        Returns:
            List of categories to scan
        """
        budget = self.budget_manager.get_status()
        available_tokens = min(
            budget.tokens_remaining,
            self.budget_manager.get_daily_budget(),
        )

        categories_with_tokens = self.category_discovery.get_next_categories_to_scan(
            max_categories=self.config.max_categories_per_run,
            available_tokens=available_tokens,
        )

        selected = []
        tokens_allocated = 0

        for cat, estimated_tokens in categories_with_tokens:
            if tokens_allocated + estimated_tokens <= available_tokens:
                selected.append(cat)
                tokens_allocated += estimated_tokens
            else:
                break

        logger.info(f"Selected {len(selected)} categories, ~{tokens_allocated} tokens")
        return selected

    def run_category(self, category: CategoryInfo) -> RunResult:
        """
        Run pipeline for a single category.

        Args:
            category: Category to scan

        Returns:
            RunResult with metrics
        """
        import subprocess
        import json
        from datetime import datetime

        start_time = datetime.utcnow()

        logger.info(f"Starting run for {category.name} ({category.amazon_domain})")

        try:
            # Build command
            cmd = [
                sys.executable,
                "scripts/run_controlled.py",
                "--max-asins", str(self.config.max_asins_per_category),
                "--freeze",  # Always freeze in scheduled runs
                "--category", str(category.category_id),
                "--domain", category.amazon_domain,
            ]

            # Run pipeline
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=600,  # 10 minute timeout
                cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            )

            duration = (datetime.utcnow() - start_time).total_seconds()

            if result.returncode != 0:
                logger.error(f"Pipeline failed for {category.name}: {result.stderr}")
                return RunResult(
                    success=False,
                    category_id=category.category_id,
                    category_name=category.name,
                    domain=category.amazon_domain,
                    tokens_used=0,
                    asins_processed=0,
                    opportunities_found=0,
                    duration_seconds=duration,
                    error=result.stderr[:500],
                )

            # Parse output for metrics (would need to enhance run_controlled.py to output JSON)
            # For now, use placeholder values
            tokens_used = 100  # Placeholder
            asins = 50
            opps = 5

            return RunResult(
                success=True,
                category_id=category.category_id,
                category_name=category.name,
                domain=category.amazon_domain,
                tokens_used=tokens_used,
                asins_processed=asins,
                opportunities_found=opps,
                duration_seconds=duration,
            )

        except subprocess.TimeoutExpired:
            duration = (datetime.utcnow() - start_time).total_seconds()
            return RunResult(
                success=False,
                category_id=category.category_id,
                category_name=category.name,
                domain=category.amazon_domain,
                tokens_used=0,
                asins_processed=0,
                opportunities_found=0,
                duration_seconds=duration,
                error="Pipeline timeout (10 min)",
            )
        except Exception as e:
            duration = (datetime.utcnow() - start_time).total_seconds()
            return RunResult(
                success=False,
                category_id=category.category_id,
                category_name=category.name,
                domain=category.amazon_domain,
                tokens_used=0,
                asins_processed=0,
                opportunities_found=0,
                duration_seconds=duration,
                error=str(e),
            )

    def run(self) -> Dict[str, Any]:
        """
        Execute a scheduled run.

        Selects categories, runs pipeline for each, records results.

        Returns:
            Summary of run results
        """
        if not self.should_run():
            return {"status": "skipped", "reason": "conditions not met"}

        logger.info("=" * 60)
        logger.info("SMARTACUS SCHEDULED RUN")
        logger.info("=" * 60)

        categories = self.select_categories()
        if not categories:
            logger.warning("No categories to scan")
            return {"status": "no_categories", "reason": "no active categories ready for scan"}

        results = []
        total_tokens = 0
        total_opps = 0

        for category in categories:
            result = self.run_category(category)
            results.append(result)

            if result.success:
                total_tokens += result.tokens_used
                total_opps += result.opportunities_found

                # Record performance
                self.category_discovery.record_scan(
                    category_id=result.category_id,
                    run_id="scheduled",  # Would need actual run_id
                    asins_discovered=result.asins_processed,
                    asins_scored=result.asins_processed,
                    opportunities_found=result.opportunities_found,
                    high_value_opps=0,
                    tokens_used=result.tokens_used,
                    total_value=0,
                    avg_score=0,
                    max_score=0,
                    duration_seconds=result.duration_seconds,
                )

        # Record budget usage
        self.budget_manager.record_run(
            tokens_used=total_tokens,
            categories_scanned=len(results),
            opportunities_found=total_opps,
        )

        # Auto-manage categories
        if self.config.discovery_enabled:
            management = self.category_discovery.auto_manage_categories()
            logger.info(f"Category management: activated={management['activated']}, deactivated={management['deactivated']}")

        summary = {
            "status": "completed",
            "categories_scanned": len(results),
            "successful": sum(1 for r in results if r.success),
            "failed": sum(1 for r in results if not r.success),
            "total_tokens": total_tokens,
            "opportunities_found": total_opps,
            "results": [
                {
                    "category": r.category_name,
                    "domain": r.domain,
                    "success": r.success,
                    "tokens": r.tokens_used,
                    "opps": r.opportunities_found,
                    "duration": r.duration_seconds,
                    "error": r.error,
                }
                for r in results
            ],
        }

        logger.info(f"Run completed: {summary['successful']}/{summary['categories_scanned']} successful, {total_opps} opportunities")
        return summary

    def start_daemon(self):
        """
        Start scheduler as background daemon.

        Runs continuously, checking for runs at configured interval.
        """
        logger.info("Starting scheduler daemon...")
        logger.info(f"Interval: {self.config.run_interval_hours} hours")

        while True:
            try:
                if self.should_run():
                    self.run()
                else:
                    logger.info("Skipping run (conditions not met)")

            except Exception as e:
                logger.error(f"Scheduler error: {e}")

            # Sleep until next check
            sleep_hours = self.config.run_interval_hours
            logger.info(f"Sleeping for {sleep_hours} hours...")
            time.sleep(sleep_hours * 3600)


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Smartacus Smart Scheduler")
    parser.add_argument("--run-once", action="store_true", help="Run once and exit")
    parser.add_argument("--daemon", action="store_true", help="Run as background daemon")
    parser.add_argument("--status", action="store_true", help="Show scheduler status")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Load .env
    from dotenv import load_dotenv
    load_dotenv()

    scheduler = SmartScheduler()

    if args.status:
        import json
        status = scheduler.get_status()
        print(json.dumps(status, indent=2))

    elif args.daemon:
        scheduler.start_daemon()

    elif args.run_once:
        result = scheduler.run()
        import json
        print(json.dumps(result, indent=2))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
