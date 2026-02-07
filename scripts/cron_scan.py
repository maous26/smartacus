#!/usr/bin/env python3
"""
Smartacus Cron Scan Runner
===========================

Lightweight cron entry point for Railway or any cron scheduler.
Runs a single scheduled scan cycle, then exits.

Railway Cron: Schedule this as a cron job (e.g., every 24h)
    Command: python scripts/cron_scan.py

Local cron:
    0 6 * * * cd /path/to/smartacus && python scripts/cron_scan.py >> data/cron.log 2>&1
"""

import os
import sys
import json
import logging
from pathlib import Path
from datetime import datetime

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("smartacus.cron")


def main():
    from src.scheduler.scheduler import SmartScheduler

    logger.info("=" * 60)
    logger.info(f"SMARTACUS CRON SCAN — {datetime.utcnow().isoformat()}Z")
    logger.info("=" * 60)

    scheduler = SmartScheduler()

    # Run a single cycle
    result = scheduler.run()

    logger.info(f"Result: {json.dumps(result, indent=2, default=str)}")

    # Exit with code based on result
    status = result.get("status", "unknown")
    if status in ("completed", "skipped", "no_categories"):
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
