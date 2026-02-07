#!/usr/bin/env python3
"""
Smartacus Cron Review Backfill
===============================

Processes ASINs tagged as review_needed by the scan pipeline.
Fetches reviews via Outscraper (async API) and builds review profiles.

This runs independently from the scan pipeline — reviews don't block scanning.

Railway Cron: Schedule every 6-12h
    Command: python scripts/cron_reviews.py

Env vars:
    OUTSCRAPER_API_KEY: Required
    REVIEW_BATCH_SIZE: ASINs to process per run (default: 20)
    REVIEW_AMAZON_DOMAIN: Amazon domain (default: amazon.com)
"""

import os
import sys
import json
import time
import logging
from pathlib import Path
from datetime import datetime

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("smartacus.cron_reviews")


def main():
    import psycopg2

    api_key = os.getenv("OUTSCRAPER_API_KEY")
    if not api_key:
        logger.error("OUTSCRAPER_API_KEY not configured")
        return 1

    batch_size = int(os.getenv("REVIEW_BATCH_SIZE", "20"))
    domain = os.getenv("REVIEW_AMAZON_DOMAIN", "amazon.com")

    logger.info("=" * 60)
    logger.info(f"REVIEW BACKFILL CRON — {datetime.utcnow().isoformat()}Z")
    logger.info(f"Batch size: {batch_size}, Domain: {domain}")
    logger.info("=" * 60)

    # Connect to DB
    conn = psycopg2.connect(
        host=os.getenv("DATABASE_HOST", "localhost"),
        port=int(os.getenv("DATABASE_PORT", "5432")),
        dbname=os.getenv("DATABASE_NAME", "smartacus"),
        user=os.getenv("DATABASE_USER", "postgres"),
        password=os.getenv("DATABASE_PASSWORD", ""),
        sslmode=os.getenv("DATABASE_SSL_MODE", "prefer"),
    )

    # Fetch ASINs tagged as review_needed
    with conn.cursor() as cur:
        cur.execute("""
            SELECT asin FROM asins
            WHERE review_needed = true
            ORDER BY updated_at ASC
            LIMIT %s
        """, (batch_size,))
        asins_to_process = [row[0] for row in cur.fetchall()]

    if not asins_to_process:
        logger.info("No ASINs need review backfill. Done.")
        conn.close()
        return 0

    logger.info(f"Processing {len(asins_to_process)} ASINs for review backfill")

    from src.data.outscraper_client import OutscraperClient, OutscraperError

    client = OutscraperClient(api_key=api_key)
    success_count = 0
    error_count = 0

    for asin in asins_to_process:
        try:
            logger.info(f"  Fetching reviews for {asin}...")
            reviews = client.fetch_product_reviews(
                asin=asin,
                domain=domain,
                max_reviews=15,
                target_negative=10,
                target_positive=5,
            )

            if reviews:
                # Insert reviews into DB
                with conn.cursor() as cur:
                    for rev in reviews:
                        cur.execute("""
                            INSERT INTO reviews (asin, review_id, rating, title, body, author, review_date, verified, source)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'outscraper')
                            ON CONFLICT (asin, review_id) DO NOTHING
                        """, (
                            asin,
                            rev.get("id", rev.get("review_id", "")),
                            rev.get("rating", 0),
                            rev.get("title", "")[:500],
                            rev.get("body", rev.get("review_body", ""))[:5000],
                            rev.get("author", rev.get("author_title", ""))[:200],
                            rev.get("date", rev.get("review_date")),
                            rev.get("verified", False),
                        ))

                    # Clear the review_needed flag
                    cur.execute("""
                        UPDATE asins SET review_needed = false WHERE asin = %s
                    """, (asin,))

                conn.commit()
                success_count += 1
                logger.info(f"    {asin}: {len(reviews)} reviews saved")
            else:
                # No reviews found — clear flag anyway to avoid retry loop
                with conn.cursor() as cur:
                    cur.execute("""
                        UPDATE asins SET review_needed = false WHERE asin = %s
                    """, (asin,))
                conn.commit()
                logger.info(f"    {asin}: no reviews returned")

            # Rate limit: wait between requests
            time.sleep(2)

        except OutscraperError as e:
            error_count += 1
            logger.error(f"    {asin}: Outscraper error: {e}")
        except Exception as e:
            error_count += 1
            logger.error(f"    {asin}: unexpected error: {e}")

    conn.close()

    logger.info("=" * 60)
    logger.info(f"Review backfill complete: {success_count} success, {error_count} errors")
    logger.info("=" * 60)

    return 0 if error_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
