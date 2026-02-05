#!/usr/bin/env python3
"""
Smartacus Daily Ingestion Script
================================

Run the daily Keepa data ingestion pipeline.

Usage:
    # Full ingestion (discover + filter + fetch)
    python scripts/run_ingestion.py

    # Quick test with limited ASINs
    python scripts/run_ingestion.py --max-asins 100

    # Incremental update only
    python scripts/run_ingestion.py --mode incremental

    # Check health status
    python scripts/run_ingestion.py --mode health

    # View statistics
    python scripts/run_ingestion.py --mode stats

Environment:
    Set KEEPA_API_KEY and DATABASE_PASSWORD in .env or environment.
"""

import os
import sys
import logging
import argparse
from datetime import datetime
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.data import (
    IngestionPipeline,
    KeepaClient,
    KeepaAPIError,
    DatabaseError,
)


def setup_logging(verbose: bool = False, log_file: str = None):
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    format_str = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"

    handlers = [logging.StreamHandler()]
    if log_file:
        handlers.append(logging.FileHandler(log_file))

    logging.basicConfig(
        level=level,
        format=format_str,
        handlers=handlers,
    )


def run_health_check():
    """Run health check on all components."""
    print("\n" + "=" * 60)
    print("SMARTACUS HEALTH CHECK")
    print("=" * 60 + "\n")

    try:
        with IngestionPipeline() as pipeline:
            health = pipeline.health_check()

            print(f"Overall Status: {health['status'].upper()}")
            print(f"Timestamp: {health['timestamp']}")
            print()

            for component, status in health['components'].items():
                icon = "[OK]" if status.get('status') == 'healthy' else "[!!]"
                print(f"  {icon} {component.upper()}")
                if status.get('error'):
                    print(f"      Error: {status['error']}")
                if 'tokens_remaining' in status:
                    print(f"      Tokens: {status['tokens_remaining']}")

    except Exception as e:
        print(f"[FAIL] Health check failed: {e}")
        return 1

    return 0


def run_stats():
    """Display current statistics."""
    print("\n" + "=" * 60)
    print("SMARTACUS STATISTICS")
    print("=" * 60 + "\n")

    try:
        with IngestionPipeline() as pipeline:
            stats = pipeline.get_ingestion_stats()

            print("DATABASE:")
            db_stats = stats.get('database', {})
            print(f"  Total tracked ASINs:    {db_stats.get('total_tracked_asins', 'N/A'):,}")
            print(f"  Snapshots (24h):        {db_stats.get('snapshots_last_24h', 'N/A'):,}")
            print(f"  ASINs updated (24h):    {db_stats.get('asins_updated_24h', 'N/A'):,}")
            print(f"  Latest snapshot:        {db_stats.get('latest_snapshot', 'N/A')}")
            print()

            print("KEEPA API:")
            keepa_stats = stats.get('keepa', {})
            print(f"  Tokens remaining:       {keepa_stats.get('tokens_remaining', 'N/A')}")
            print(f"  Total requests:         {keepa_stats.get('total_requests', 'N/A')}")
            print(f"  Total tokens consumed:  {keepa_stats.get('total_tokens_consumed', 'N/A')}")

    except Exception as e:
        print(f"[FAIL] Stats retrieval failed: {e}")
        return 1

    return 0


def run_ingestion(
    mode: str,
    max_asins: int = None,
    skip_filter: bool = False,
    verbose: bool = False,
):
    """Run the ingestion pipeline."""
    print("\n" + "=" * 60)
    print(f"SMARTACUS INGESTION - {mode.upper()} MODE")
    print("=" * 60 + "\n")

    start_time = datetime.utcnow()
    print(f"Started at: {start_time.isoformat()}")
    print()

    try:
        with IngestionPipeline() as pipeline:
            if mode == 'full':
                result = pipeline.run_daily_ingestion(
                    max_asins=max_asins,
                    skip_filtering=skip_filter,
                )
            elif mode == 'incremental':
                asins = pipeline._get_tracked_asins()
                if max_asins:
                    asins = asins[:max_asins]
                result = pipeline.run_incremental_update(asins)
            else:
                print(f"Unknown mode: {mode}")
                return 1

            # Print results
            print("\n" + "-" * 40)
            print("RESULTS:")
            print("-" * 40)
            print(f"  Batch ID:          {result.batch_id}")
            print(f"  ASINs requested:   {result.asins_requested:,}")
            print(f"  ASINs processed:   {result.asins_processed:,}")
            print(f"  Snapshots created: {result.snapshots_inserted:,}")
            print(f"  Failed:            {result.asins_failed:,}")
            print(f"  Success rate:      {result.success_rate:.1f}%")
            print()
            print(f"  Tokens consumed:   {result.tokens_consumed:,}")
            print(f"  Tokens remaining:  {result.tokens_remaining:,}")
            print()
            print(f"  Duration:          {result.duration_seconds:.1f} seconds")

            if result.errors:
                print()
                print(f"  Errors ({len(result.errors)}):")
                for error in result.errors[:5]:  # Show first 5
                    print(f"    - [{error['error_type']}] {error['asin']}: {error['message'][:50]}")
                if len(result.errors) > 5:
                    print(f"    ... and {len(result.errors) - 5} more")

            return 0 if result.success_rate > 50 else 1

    except KeepaAPIError as e:
        print(f"\n[ERROR] Keepa API error: {e}")
        return 1
    except DatabaseError as e:
        print(f"\n[ERROR] Database error: {e}")
        return 1
    except Exception as e:
        print(f"\n[ERROR] Unexpected error: {e}")
        if verbose:
            import traceback
            traceback.print_exc()
        return 1


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Smartacus Keepa Ingestion Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )

    parser.add_argument(
        '--mode',
        choices=['full', 'incremental', 'health', 'stats'],
        default='full',
        help='Ingestion mode (default: full)',
    )
    parser.add_argument(
        '--max-asins',
        type=int,
        default=None,
        help='Maximum ASINs to process',
    )
    parser.add_argument(
        '--skip-filter',
        action='store_true',
        help='Skip criteria filtering',
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging',
    )
    parser.add_argument(
        '--log-file',
        type=str,
        default=None,
        help='Log file path',
    )

    args = parser.parse_args()

    # Setup logging
    setup_logging(verbose=args.verbose, log_file=args.log_file)

    # Check environment
    if not os.environ.get('KEEPA_API_KEY'):
        # Try loading from .env
        try:
            from dotenv import load_dotenv
            load_dotenv(project_root / '.env')
        except ImportError:
            pass

    if not os.environ.get('KEEPA_API_KEY'):
        print("ERROR: KEEPA_API_KEY environment variable not set")
        print("Set it in .env file or export it in your shell")
        return 1

    # Run appropriate mode
    if args.mode == 'health':
        return run_health_check()
    elif args.mode == 'stats':
        return run_stats()
    else:
        return run_ingestion(
            mode=args.mode,
            max_asins=args.max_asins,
            skip_filter=args.skip_filter,
            verbose=args.verbose,
        )


if __name__ == '__main__':
    sys.exit(main())
