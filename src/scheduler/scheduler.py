"""
Smart Scheduler V3.0
====================

Intelligent pipeline scheduling with:
- Monthly token budget management
- Multi-category support with auto-selection
- Performance-based prioritization
- **V3.0**: Strategy Agent for intelligent resource allocation
- Configurable run frequency

Usage:
    scheduler = SmartScheduler()
    scheduler.run()  # Single scheduled run
    scheduler.start_daemon()  # Background daemon

CLI:
    python -m src.scheduler.scheduler --run-once
    python -m src.scheduler.scheduler --daemon
    python -m src.scheduler.scheduler --strategy  # Show strategy decision
"""

import os
import sys
import time
import json
import logging
import argparse
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from .token_budget import TokenBudgetManager, BudgetStatus
from .category_discovery import CategoryDiscovery, CategoryInfo
from .strategy_agent import StrategyAgent, NicheMetrics, NicheStatus, load_niche_metrics_from_db

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
    use_strategy_agent: bool = True   # V3.0: Enable intelligent allocation
    enable_llm_consultation: bool = False  # V3.0: LLM for ambiguous cases

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

        # V3.0: Strategy Agent for intelligent allocation
        self.strategy_agent = StrategyAgent(
            enable_llm=self.config.enable_llm_consultation
        )
        self._last_strategy_decision = None

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

        status = {
            "enabled": self.config.enabled,
            "interval_hours": self.config.run_interval_hours,
            "use_strategy_agent": self.config.use_strategy_agent,
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

        # Add last strategy decision if available
        if self._last_strategy_decision:
            status["last_strategy"] = {
                "cycle_id": self._last_strategy_decision.cycle_id,
                "decided_at": self._last_strategy_decision.decided_at.isoformat(),
                "exploit_count": sum(1 for a in self._last_strategy_decision.assessments if a.status == NicheStatus.EXPLOIT),
                "explore_count": sum(1 for a in self._last_strategy_decision.assessments if a.status == NicheStatus.EXPLORE),
                "pause_count": sum(1 for a in self._last_strategy_decision.assessments if a.status == NicheStatus.PAUSE),
            }

        return status

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

    def get_strategy_decision(self) -> Dict[str, Any]:
        """
        Get strategy decision from Strategy Agent.

        Returns:
            Strategy decision as dictionary
        """
        import psycopg2

        budget = self.budget_manager.get_status()
        available_tokens = min(
            budget.tokens_remaining,
            self.budget_manager.get_daily_budget(),
        )

        # Load niche metrics from DB
        try:
            conn = psycopg2.connect(
                host=os.getenv("DATABASE_HOST", "localhost"),
                port=int(os.getenv("DATABASE_PORT", "5432")),
                dbname=os.getenv("DATABASE_NAME", "smartacus"),
                user=os.getenv("DATABASE_USER", "postgres"),
                password=os.getenv("DATABASE_PASSWORD", ""),
                sslmode=os.getenv("DATABASE_SSL_MODE", "prefer"),
            )

            niches = load_niche_metrics_from_db(conn)
            conn.close()

        except Exception as e:
            logger.error(f"Failed to load niche metrics: {e}")
            return {"error": str(e)}

        if not niches:
            return {"error": "No active niches found"}

        # Get strategy decision
        decision = self.strategy_agent.decide(
            budget=available_tokens,
            niches=niches,
        )

        self._last_strategy_decision = decision
        return decision.to_dict()

    def select_categories(self) -> List[CategoryInfo]:
        """
        Select categories to scan based on priority and budget.

        V3.0: Uses Strategy Agent if enabled, otherwise falls back to simple selection.

        Returns:
            List of categories to scan
        """
        budget = self.budget_manager.get_status()
        available_tokens = min(
            budget.tokens_remaining,
            self.budget_manager.get_daily_budget(),
        )

        # V3.0: Use Strategy Agent for intelligent selection
        if self.config.use_strategy_agent:
            return self._select_via_strategy_agent(available_tokens)

        # Fallback: Simple selection
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

    def _select_via_strategy_agent(self, available_tokens: int) -> List[CategoryInfo]:
        """
        Select categories using Strategy Agent.

        Returns:
            List of CategoryInfo for niches to scan (EXPLOIT + EXPLORE only)
        """
        import psycopg2

        try:
            conn = psycopg2.connect(
                host=os.getenv("DATABASE_HOST", "localhost"),
                port=int(os.getenv("DATABASE_PORT", "5432")),
                dbname=os.getenv("DATABASE_NAME", "smartacus"),
                user=os.getenv("DATABASE_USER", "postgres"),
                password=os.getenv("DATABASE_PASSWORD", ""),
                sslmode=os.getenv("DATABASE_SSL_MODE", "prefer"),
            )

            niches = load_niche_metrics_from_db(conn)
            conn.close()

        except Exception as e:
            logger.error(f"Failed to load niche metrics: {e}")
            # Fallback to simple selection
            return self.category_discovery.get_active_categories()[:self.config.max_categories_per_run]

        if not niches:
            logger.warning("No active niches found for Strategy Agent")
            return []

        # Get strategy decision
        decision = self.strategy_agent.decide(
            budget=available_tokens,
            niches=niches,
        )

        self._last_strategy_decision = decision

        # Log decision summary
        exploit_count = sum(1 for a in decision.assessments if a.status == NicheStatus.EXPLOIT)
        explore_count = sum(1 for a in decision.assessments if a.status == NicheStatus.EXPLORE)
        pause_count = sum(1 for a in decision.assessments if a.status == NicheStatus.PAUSE)

        logger.info(f"Strategy decision {decision.cycle_id}: EXPLOIT={exploit_count}, EXPLORE={explore_count}, PAUSE={pause_count}")

        for note in decision.risk_notes:
            logger.warning(f"  RISK: {note}")

        # Convert assessments to CategoryInfo (only EXPLOIT and EXPLORE)
        selected = []
        for assessment in decision.assessments:
            if assessment.status in (NicheStatus.EXPLOIT, NicheStatus.EXPLORE):
                # Store max_asins as attribute for later use
                cat_info = CategoryInfo(
                    category_id=assessment.niche_id,
                    name=assessment.name,
                    amazon_domain=assessment.domain,
                    priority=1 if assessment.status == NicheStatus.EXPLOIT else 2,
                    is_active=True,
                    total_runs=0,
                    total_opportunities_found=0,
                    conversion_rate=0,
                    avg_opportunity_score=0,
                )
                # Store allocation info as extra attributes
                cat_info._tokens_allocated = assessment.tokens_allocated
                cat_info._max_asins = assessment.max_asins
                cat_info._status = assessment.status.value
                cat_info._justification = assessment.justification

                selected.append(cat_info)

                logger.info(f"  {assessment.status.value}: {assessment.name} ({assessment.domain}) - {assessment.tokens_allocated} tokens, {assessment.max_asins} ASINs")
                logger.debug(f"    Justification: {assessment.justification}")

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
            # Get max_asins from strategy decision or use default
            max_asins = getattr(category, '_max_asins', self.config.max_asins_per_category)

            # Build command
            cmd = [
                sys.executable,
                "scripts/run_controlled.py",
                "--max-asins", str(max_asins),
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
    parser = argparse.ArgumentParser(description="Smartacus Smart Scheduler V3.0")
    parser.add_argument("--run-once", action="store_true", help="Run once and exit")
    parser.add_argument("--daemon", action="store_true", help="Run as background daemon")
    parser.add_argument("--status", action="store_true", help="Show scheduler status")
    parser.add_argument("--strategy", action="store_true", help="Show strategy decision (V3.0)")
    parser.add_argument("--no-strategy", action="store_true", help="Disable Strategy Agent, use simple selection")
    parser.add_argument("--with-llm", action="store_true", help="Enable LLM consultation for ambiguous decisions")
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

    # Create config with strategy agent setting
    config = None
    if args.no_strategy:
        config = SchedulerConfig(use_strategy_agent=False)
    elif args.with_llm:
        config = SchedulerConfig(enable_llm_consultation=True)

    scheduler = SmartScheduler(config=config)

    if args.status:
        status = scheduler.get_status()
        print(json.dumps(status, indent=2))

    elif args.strategy:
        # V3.0: Show strategy decision
        decision = scheduler.get_strategy_decision()
        print(json.dumps(decision, indent=2, default=str))

    elif args.daemon:
        scheduler.start_daemon()

    elif args.run_once:
        result = scheduler.run()
        print(json.dumps(result, indent=2))

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
