"""
Smartacus Orchestrator CLI
==========================

Command-line interface for the Smartacus pipeline.

Commands:
    run         - Execute the full daily pipeline
    status      - Show last run status
    opportunities - List active opportunities
    score       - Score a specific ASIN
    health      - Check pipeline health

Usage:
    python -m src.orchestrator.cli run
    python -m src.orchestrator.cli status
    python -m src.orchestrator.cli opportunities --min-score 60
    python -m src.orchestrator.cli score --asin B09XXXXX
    python -m src.orchestrator.cli health
"""

import argparse
import json
import logging
import sys
from datetime import datetime
from typing import Optional

from .daily_pipeline import DailyPipeline, PipelineStatus
from .monitoring import PipelineMonitor


def setup_logging(verbose: bool = False):
    """Configure logging for CLI."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def cmd_run(args):
    """Execute the daily pipeline."""
    print("=" * 60)
    print("SMARTACUS DAILY PIPELINE")
    print("=" * 60)
    print(f"Started at: {datetime.utcnow().isoformat()}")
    print()

    try:
        with DailyPipeline(score_threshold=args.threshold) as pipeline:
            result = pipeline.run(
                skip_ingestion=args.skip_ingestion,
                skip_events=args.skip_events,
                max_asins=args.max_asins,
            )

        print()
        print("=" * 60)
        print("PIPELINE COMPLETE")
        print("=" * 60)
        print(f"Status: {result.status.value}")
        print(f"Duration: {result.duration_seconds:.1f} seconds")
        print(f"Opportunities found: {result.opportunities_found}")
        print(f"Above threshold ({args.threshold}): {result.opportunities_above_threshold}")
        print()

        # Show stage summaries
        print("Stage Results:")
        for stage, stage_result in result.stages.items():
            status_icon = "✓" if stage_result.status == PipelineStatus.COMPLETED else "✗"
            duration = f"{stage_result.duration_seconds:.1f}s" if stage_result.duration_seconds else "N/A"
            print(f"  {status_icon} {stage.value}: {stage_result.status.value} ({duration})")

        # Exit code based on status
        if result.status == PipelineStatus.FAILED:
            return 1
        return 0

    except Exception as e:
        print(f"\nERROR: Pipeline execution failed: {e}")
        logging.exception("Pipeline failed")
        return 1


def cmd_status(args):
    """Show last run status."""
    try:
        with DailyPipeline() as pipeline:
            status = pipeline.get_last_run_status()

        if status is None:
            print("No previous runs found.")
            return 0

        print("=" * 60)
        print("LAST PIPELINE RUN")
        print("=" * 60)
        print(f"Run ID: {status.get('run_id', 'N/A')}")
        print(f"Status: {status.get('status', 'N/A')}")
        print(f"Started: {status.get('started_at', 'N/A')}")
        print(f"Completed: {status.get('completed_at', 'N/A')}")
        print(f"Duration: {status.get('duration_seconds', 0):.1f} seconds")

        if args.json:
            print()
            print("Full metrics:")
            print(json.dumps(status.get('metrics', {}), indent=2, default=str))

        return 0

    except Exception as e:
        print(f"ERROR: Failed to get status: {e}")
        return 1


def cmd_opportunities(args):
    """List active opportunities."""
    try:
        with DailyPipeline(score_threshold=args.min_score) as pipeline:
            opportunities = pipeline.get_active_opportunities(
                min_score=args.min_score,
                limit=args.limit,
            )

        if not opportunities:
            print(f"No opportunities found with score >= {args.min_score}")
            return 0

        print("=" * 60)
        print(f"ACTIVE OPPORTUNITIES (score >= {args.min_score})")
        print("=" * 60)
        print()

        for i, opp in enumerate(opportunities, 1):
            print(f"{i}. {opp['asin']}")
            print(f"   Score: {opp['score']}/100 ({opp['status']})")
            print(f"   Window: {opp['window_estimate']} ({opp['window_days']} days)")
            if opp.get('title'):
                title = opp['title'][:50] + "..." if len(opp.get('title', '')) > 50 else opp.get('title', '')
                print(f"   Title: {title}")
            if opp.get('brand'):
                print(f"   Brand: {opp['brand']}")
            print(f"   Detected: {opp['detected_at']}")
            print()

        print(f"Total: {len(opportunities)} opportunities")

        if args.json:
            print()
            print("JSON output:")
            print(json.dumps(opportunities, indent=2, default=str))

        return 0

    except Exception as e:
        print(f"ERROR: Failed to list opportunities: {e}")
        return 1


def cmd_score(args):
    """Score a specific ASIN."""
    if not args.asin:
        print("ERROR: --asin is required")
        return 1

    try:
        with DailyPipeline() as pipeline:
            result = pipeline.score_single_asin(args.asin)

        if result is None:
            print(f"Cannot score {args.asin}: insufficient data")
            return 1

        print("=" * 60)
        print(f"SCORING RESULT: {args.asin}")
        print("=" * 60)
        print()
        print(f"Total Score: {result.total_score}/100")
        print(f"Status: {result.status.value}")
        print(f"Actionable: {'Yes' if result.is_valid else 'No'}")
        print(f"Window: {result.window_estimate} ({result.window_days} days)")
        print()

        print("Component Scores:")
        for name, comp in result.component_scores.items():
            bar_length = int(comp.score / comp.max_score * 20) if comp.max_score > 0 else 0
            bar = "█" * bar_length + "░" * (20 - bar_length)
            print(f"  {name:15} [{bar}] {comp.score}/{comp.max_score}")
            if comp.details and args.verbose:
                for key, value in comp.details.items():
                    print(f"    - {key}: {value}")
        print()

        if not result.is_valid:
            print(f"⚠ Not actionable: {result.rejection_reason}")

        if args.json:
            print()
            print("JSON output:")
            output = {
                "asin": args.asin,
                "total_score": result.total_score,
                "status": result.status.value,
                "is_valid": result.is_valid,
                "window_days": result.window_days,
                "window_estimate": result.window_estimate,
                "components": {
                    name: {
                        "score": comp.score,
                        "max_score": comp.max_score,
                        "details": comp.details,
                    }
                    for name, comp in result.component_scores.items()
                },
            }
            print(json.dumps(output, indent=2))

        return 0

    except Exception as e:
        print(f"ERROR: Failed to score ASIN: {e}")
        return 1


def cmd_health(args):
    """Check pipeline health."""
    try:
        monitor = PipelineMonitor()
        health = monitor.get_pipeline_health()

        print("=" * 60)
        print("PIPELINE HEALTH CHECK")
        print("=" * 60)
        print()

        overall_status = "HEALTHY" if health.get("is_healthy", False) else "UNHEALTHY"
        status_icon = "✓" if health.get("is_healthy", False) else "✗"
        print(f"Overall Status: {status_icon} {overall_status}")
        print()

        print("Component Status:")
        components = health.get("components", {})
        for component, status in components.items():
            icon = "✓" if status.get("healthy", False) else "✗"
            print(f"  {icon} {component}: {status.get('message', 'Unknown')}")

        print()
        print("Data Freshness:")
        freshness = health.get("data_freshness", {})
        for metric, value in freshness.items():
            print(f"  - {metric}: {value}")

        if args.json:
            print()
            print("JSON output:")
            print(json.dumps(health, indent=2, default=str))

        return 0 if health.get("is_healthy", False) else 1

    except Exception as e:
        print(f"ERROR: Health check failed: {e}")
        return 1


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog="smartacus",
        description="Smartacus Pipeline Orchestrator CLI",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose output",
    )

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # run command
    run_parser = subparsers.add_parser("run", help="Execute the daily pipeline")
    run_parser.add_argument(
        "--threshold",
        type=int,
        default=50,
        help="Minimum score threshold (default: 50)",
    )
    run_parser.add_argument(
        "--max-asins",
        type=int,
        help="Limit number of ASINs to process",
    )
    run_parser.add_argument(
        "--skip-ingestion",
        action="store_true",
        help="Skip data ingestion (use existing data)",
    )
    run_parser.add_argument(
        "--skip-events",
        action="store_true",
        help="Skip event detection",
    )

    # status command
    status_parser = subparsers.add_parser("status", help="Show last run status")
    status_parser.add_argument(
        "--json",
        action="store_true",
        help="Output full metrics as JSON",
    )

    # opportunities command
    opp_parser = subparsers.add_parser("opportunities", help="List active opportunities")
    opp_parser.add_argument(
        "--min-score",
        type=int,
        default=50,
        help="Minimum score filter (default: 50)",
    )
    opp_parser.add_argument(
        "--limit",
        type=int,
        default=20,
        help="Maximum opportunities to show (default: 20)",
    )
    opp_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )

    # score command
    score_parser = subparsers.add_parser("score", help="Score a specific ASIN")
    score_parser.add_argument(
        "--asin",
        required=True,
        help="ASIN to score",
    )
    score_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )

    # health command
    health_parser = subparsers.add_parser("health", help="Check pipeline health")
    health_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON",
    )

    args = parser.parse_args()
    setup_logging(args.verbose)

    if args.command is None:
        parser.print_help()
        return 1

    # Dispatch to command handler
    commands = {
        "run": cmd_run,
        "status": cmd_status,
        "opportunities": cmd_opportunities,
        "score": cmd_score,
        "health": cmd_health,
    }

    handler = commands.get(args.command)
    if handler:
        return handler(args)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
