#!/usr/bin/env python3
"""
Smartacus Review Backfill Job
=============================

Fetches individual Amazon reviews for top opportunity ASINs and populates
the `reviews` table. Then triggers review intelligence analysis.

Data sources (--source):
    oxylabs     : Oxylabs SERP Scraper API (recommended, 7-10 reviews per ASIN)
    playwright  : headless Chromium browser (bypasses anti-bot, often blocked)
    csv         : import from local CSV file (for testing or external data)

NOT Keepa — Keepa only provides aggregated rating/count history, not review text.

Design principles:
    - TARGETED: only top N ASINs (not 10k)
    - BUDGETED: max reviews per ASIN, max total reviews per run
    - IDEMPOTENT: dedup on review_id (Amazon's R... ID) via ON CONFLICT
    - INCREMENTAL: skip ASINs that already have fresh reviews
    - RESILIENT: per-ASIN error handling, doesn't crash on single failure
    - POLITE: random delays between requests

Usage:
    python scripts/run_reviews_backfill.py --top-n 20
    python scripts/run_reviews_backfill.py --asins B08L5TNJHG,B0F4MSXW3J
    python scripts/run_reviews_backfill.py --source csv --csv-file data/reviews_export.csv
    python scripts/run_reviews_backfill.py --dry-run

Environment:
    Reads from .env (DATABASE_HOST, DATABASE_PORT, etc.)
"""

import os
import sys
import re
import csv
import json
import time
import random
import hashlib
import logging
import argparse
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv
load_dotenv(project_root / ".env")


# ============================================================================
# LOGGING
# ============================================================================

def setup_logging(verbose: bool = False, log_file: str = None):
    level = logging.DEBUG if verbose else logging.INFO
    fmt = "%(asctime)s [%(levelname)s] %(message)s"
    handlers = [logging.StreamHandler()]
    if log_file:
        handlers.append(logging.FileHandler(log_file))
    logging.basicConfig(level=level, format=fmt, handlers=handlers)

logger = logging.getLogger(__name__)


# ============================================================================
# CONFIG
# ============================================================================

@dataclass
class BackfillConfig:
    """Backfill job configuration."""
    # Data source
    source: str = "oxylabs"                # "oxylabs", "playwright", or "csv"
    csv_file: Optional[str] = None         # path to CSV file for csv source
    amazon_domain: str = "fr"              # Amazon domain for oxylabs (fr, com, de, etc.)

    # Target selection
    top_n: int = 20                        # top N ASINs by score
    asins: List[str] = field(default_factory=list)  # explicit ASIN list

    # Budget limits
    max_reviews_per_asin: int = 200        # max reviews to fetch per ASIN
    max_pages_per_asin: int = 10           # max pages to scrape per ASIN (10 reviews/page)
    max_total_reviews: int = 5000          # global cap for entire run
    freshness_hours: int = 168             # skip if reviews fetched < 7 days ago

    # Request settings
    min_delay_sec: float = 3.0             # minimum delay between requests
    max_delay_sec: float = 7.0             # maximum delay between requests
    request_timeout: int = 20              # page load timeout in seconds
    max_retries: int = 2                   # retries per page on failure

    # Processing
    dry_run: bool = False
    run_analysis: bool = True              # trigger review intelligence after backfill
    verbose: bool = False


# ============================================================================
# REVIEW DATA MODEL
# ============================================================================

@dataclass
class ScrapedReview:
    """Single review extracted from any source."""
    review_id: str
    asin: str
    title: str
    body: str
    rating: float
    author_name: Optional[str] = None
    review_date: Optional[str] = None
    is_verified_purchase: bool = False
    helpful_votes: int = 0
    content_hash: Optional[str] = None

    def __post_init__(self):
        if not self.content_hash:
            text = f"{self.title or ''}{self.body or ''}"
            self.content_hash = hashlib.sha256(text.encode()).hexdigest()


# ============================================================================
# SOURCE: OXYLABS API
# ============================================================================

def fetch_reviews_oxylabs(asin: str, config: BackfillConfig) -> List[ScrapedReview]:
    """
    Fetch reviews using Oxylabs SERP Scraper API.

    Returns 7-10 "Top reviews" per ASIN (Oxylabs limitation).
    All reviews are returned (not filtered by rating) to capture:
    - Negative reviews for defect detection
    - Positive reviews for "I wish..." patterns
    """
    try:
        from src.data.oxylabs_client import OxylabsClient, OxylabsError

        client = OxylabsClient()
        reviews = client.fetch_product_reviews(
            asin=asin,
            domain=config.amazon_domain,
            max_reviews=config.max_reviews_per_asin,
        )

        # Convert OxylabsClient.Review to ScrapedReview
        scraped = []
        for r in reviews:
            scraped.append(ScrapedReview(
                review_id=r.review_id,
                asin=r.asin,
                title=r.title,
                body=r.content,
                rating=float(r.rating),
                author_name=r.author,
                review_date=r.date.strftime("%Y-%m-%d") if r.date else None,
                is_verified_purchase=r.verified_purchase,
                helpful_votes=r.helpful_votes,
            ))

        return scraped

    except ImportError as e:
        logger.error(f"Oxylabs client not available: {e}")
        return []
    except Exception as e:
        logger.error(f"Oxylabs fetch failed for {asin}: {e}")
        return []


# ============================================================================
# SOURCE: PLAYWRIGHT (Headless Chromium)
# ============================================================================

def parse_reviews_html(html: str, asin: str) -> List[ScrapedReview]:
    """Parse Amazon review page HTML and extract individual reviews."""
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    reviews = []

    review_divs = soup.find_all("div", {"data-hook": "review"})

    for div in review_divs:
        try:
            review_id = div.get("id", "")
            if not review_id:
                continue

            # Rating
            rating_el = div.find("i", {"data-hook": "review-star-rating"})
            if not rating_el:
                rating_el = div.find("i", {"data-hook": "cmps-review-star-rating"})
            rating = 5.0
            if rating_el:
                match = re.search(r"(\d+(?:\.\d+)?)", rating_el.get_text(strip=True))
                if match:
                    rating = float(match.group(1))

            # Title
            title_el = div.find("a", {"data-hook": "review-title"})
            if not title_el:
                title_el = div.find("span", {"data-hook": "review-title"})
            title = ""
            if title_el:
                spans = title_el.find_all("span")
                title = spans[-1].get_text(strip=True) if spans else title_el.get_text(strip=True)

            # Body
            body_el = div.find("span", {"data-hook": "review-body"})
            body = body_el.get_text(strip=True) if body_el else ""

            if not body and not title:
                continue

            # Author
            author_el = div.find("span", class_="a-profile-name")
            author_name = author_el.get_text(strip=True) if author_el else None

            # Date
            date_el = div.find("span", {"data-hook": "review-date"})
            review_date = None
            if date_el:
                match = re.search(r"on (\w+ \d{1,2}, \d{4})", date_el.get_text(strip=True))
                if match:
                    try:
                        review_date = datetime.strptime(match.group(1), "%B %d, %Y").strftime("%Y-%m-%d")
                    except ValueError:
                        pass

            # Verified
            is_verified = bool(div.find("span", {"data-hook": "avp-badge"}))

            # Helpful votes
            helpful_el = div.find("span", {"data-hook": "helpful-vote-statement"})
            helpful_votes = 0
            if helpful_el:
                ht = helpful_el.get_text(strip=True)
                match = re.search(r"(\d+)", ht)
                if match:
                    helpful_votes = int(match.group(1))
                elif "one person" in ht.lower():
                    helpful_votes = 1

            reviews.append(ScrapedReview(
                review_id=review_id, asin=asin, title=title, body=body,
                rating=rating, author_name=author_name, review_date=review_date,
                is_verified_purchase=is_verified, helpful_votes=helpful_votes,
            ))
        except Exception as e:
            logger.debug(f"Failed to parse review div: {e}")

    return reviews


def fetch_reviews_playwright(asin: str, config: BackfillConfig) -> List[ScrapedReview]:
    """Fetch reviews using Playwright headless Chromium."""
    from playwright.sync_api import sync_playwright

    all_reviews = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1920, "height": 1080},
            locale="en-US",
            timezone_id="America/New_York",
        )
        # Block unnecessary resources to speed up loading
        context.route("**/*.{png,jpg,jpeg,gif,svg,ico,woff,woff2,ttf}", lambda route: route.abort())
        context.route("**/doubleclick.net/**", lambda route: route.abort())
        context.route("**/googlesyndication.com/**", lambda route: route.abort())

        page = context.new_page()

        for page_num in range(1, config.max_pages_per_asin + 1):
            url = (
                f"https://www.amazon.com/product-reviews/{asin}"
                f"?pageNumber={page_num}&sortBy=recent&reviewerType=all_reviews"
            )

            success = False
            for attempt in range(config.max_retries + 1):
                try:
                    page.goto(url, wait_until="domcontentloaded",
                              timeout=config.request_timeout * 1000)

                    # Wait for reviews to appear (or detect captcha)
                    try:
                        page.wait_for_selector(
                            '[data-hook="review"], #captchacharacters, input[name="amzn-captcha-verify"]',
                            timeout=8000
                        )
                    except Exception:
                        pass  # timeout is OK, page might just be slow

                    html = page.content()

                    # Check for captcha
                    if "captcha" in html.lower() and 'data-hook="review"' not in html:
                        logger.warning(f"  CAPTCHA on page {page_num} attempt {attempt+1}")
                        if attempt < config.max_retries:
                            time.sleep(random.uniform(15, 30))
                            continue
                        break

                    # Check for sign-in redirect
                    if "ap/signin" in page.url:
                        logger.warning(f"  Sign-in redirect on page {page_num}")
                        break

                    reviews = parse_reviews_html(html, asin)
                    if reviews:
                        all_reviews.extend(reviews)
                        success = True
                    break

                except Exception as e:
                    logger.debug(f"  Page {page_num} attempt {attempt+1} error: {e}")
                    if attempt < config.max_retries:
                        time.sleep(5)

            if not success and page_num == 1:
                # First page failed — no point continuing
                break

            if len(all_reviews) >= config.max_reviews_per_asin:
                break

            # Check for next page
            try:
                next_disabled = page.query_selector("li.a-last .a-disabled")
                if next_disabled:
                    break
            except Exception:
                pass

            # Polite delay
            time.sleep(random.uniform(config.min_delay_sec, config.max_delay_sec))

        browser.close()

    return all_reviews[:config.max_reviews_per_asin]


# ============================================================================
# SOURCE: CSV IMPORT
# ============================================================================

def load_reviews_from_csv(csv_path: str, asins_filter: Optional[List[str]] = None) -> List[ScrapedReview]:
    """
    Load reviews from a CSV file.

    Expected columns (flexible — maps common formats):
        review_id (or id), asin, title, body (or text or review_text),
        rating (or stars), author (or author_name), date (or review_date),
        verified (or is_verified_purchase), helpful_votes (or helpful)
    """
    reviews = []
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    with open(path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Flexible column mapping
            asin = row.get("asin", row.get("ASIN", ""))
            if asins_filter and asin not in asins_filter:
                continue

            review_id = row.get("review_id", row.get("id", row.get("reviewId", "")))
            if not review_id:
                review_id = f"csv_{hashlib.md5(json.dumps(row, sort_keys=True).encode()).hexdigest()[:16]}"

            body = row.get("body", row.get("text", row.get("review_text", row.get("reviewBody", ""))))
            title = row.get("title", row.get("review_title", row.get("reviewTitle", "")))
            rating_str = row.get("rating", row.get("stars", row.get("overall", "5")))
            author = row.get("author", row.get("author_name", row.get("reviewerName", None)))
            date_str = row.get("date", row.get("review_date", row.get("reviewDate", None)))
            verified_str = row.get("verified", row.get("is_verified_purchase", row.get("verified_purchase", "")))
            helpful_str = row.get("helpful_votes", row.get("helpful", row.get("helpfulVotes", "0")))

            try:
                rating = float(rating_str) if rating_str else 5.0
            except ValueError:
                rating = 5.0

            is_verified = str(verified_str).lower() in ("true", "1", "yes", "y")

            try:
                helpful = int(helpful_str) if helpful_str else 0
            except ValueError:
                helpful = 0

            # Normalize date
            review_date = None
            if date_str:
                for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%B %d, %Y", "%d/%m/%Y"):
                    try:
                        review_date = datetime.strptime(date_str.strip(), fmt).strftime("%Y-%m-%d")
                        break
                    except ValueError:
                        continue

            if body or title:
                reviews.append(ScrapedReview(
                    review_id=review_id, asin=asin, title=title or "", body=body or "",
                    rating=rating, author_name=author, review_date=review_date,
                    is_verified_purchase=is_verified, helpful_votes=helpful,
                ))

    return reviews


# ============================================================================
# DATABASE OPERATIONS
# ============================================================================

def get_db_connection():
    """Get a database connection."""
    import psycopg2
    return psycopg2.connect(
        host=os.getenv("DATABASE_HOST", "localhost"),
        port=int(os.getenv("DATABASE_PORT", "5432")),
        dbname=os.getenv("DATABASE_NAME", "smartacus"),
        user=os.getenv("DATABASE_USER", "postgres"),
        password=os.getenv("DATABASE_PASSWORD", ""),
        sslmode=os.getenv("DATABASE_SSL_MODE", "prefer"),
        connect_timeout=int(os.getenv("DATABASE_CONNECT_TIMEOUT", "10")),
    )


def get_target_asins(conn, config: BackfillConfig) -> List[str]:
    """Get the list of ASINs to backfill reviews for."""
    if config.asins:
        return config.asins

    with conn.cursor() as cur:
        cur.execute("""
            SELECT oa.asin
            FROM opportunity_artifacts oa
            JOIN (
                SELECT run_id FROM pipeline_runs
                WHERE status = 'completed'
                ORDER BY started_at DESC LIMIT 1
            ) pr ON oa.run_id = pr.run_id
            WHERE oa.final_score > 0
            ORDER BY oa.final_score DESC
            LIMIT %s
        """, (config.top_n,))
        return [row[0] for row in cur.fetchall()]


def get_asins_needing_refresh(conn, asins: List[str], freshness_hours: int) -> List[str]:
    """Filter out ASINs that already have fresh reviews."""
    if not asins:
        return []

    cutoff = datetime.now(tz=None) - timedelta(hours=freshness_hours)

    with conn.cursor() as cur:
        cur.execute("""
            SELECT DISTINCT asin
            FROM reviews
            WHERE asin = ANY(%s) AND captured_at > %s
        """, (asins, cutoff))
        fresh_asins = {row[0] for row in cur.fetchall()}

    return [a for a in asins if a not in fresh_asins]


def save_reviews(conn, reviews: List[ScrapedReview]) -> Dict[str, int]:
    """Save reviews to DB with idempotent upsert."""
    stats = {"inserted": 0, "updated": 0, "skipped": 0}

    if not reviews:
        return stats

    with conn.cursor() as cur:
        for r in reviews:
            try:
                cur.execute("""
                    INSERT INTO reviews (
                        review_id, asin, title, body, rating,
                        author_name, review_date, is_verified_purchase,
                        helpful_votes, content_hash, captured_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (review_id) DO UPDATE SET
                        helpful_votes = GREATEST(reviews.helpful_votes, EXCLUDED.helpful_votes),
                        captured_at = NOW()
                    RETURNING (xmax = 0) AS is_insert
                """, (
                    r.review_id, r.asin, r.title, r.body, r.rating,
                    r.author_name, r.review_date, r.is_verified_purchase,
                    r.helpful_votes, r.content_hash,
                ))
                row = cur.fetchone()
                if row and row[0]:
                    stats["inserted"] += 1
                else:
                    stats["updated"] += 1
            except Exception as e:
                logger.debug(f"Failed to save review {r.review_id}: {e}")
                stats["skipped"] += 1

        conn.commit()

    return stats


# ============================================================================
# REVIEW INTELLIGENCE TRIGGER
# ============================================================================

def run_review_intelligence(conn, asins: List[str]) -> int:
    """Run deterministic review intelligence on backfilled ASINs."""
    try:
        from src.reviews import ReviewSignalExtractor, ReviewInsightAggregator

        extractor = ReviewSignalExtractor()
        aggregator = ReviewInsightAggregator()
        analyzed = 0

        for asin in asins:
            reviews_data = aggregator.load_reviews_from_db(conn, asin)
            if not reviews_data:
                continue

            defects = extractor.extract_defects(reviews_data)
            wishes = extractor.extract_wish_patterns(reviews_data)
            negative_count = sum(1 for r in reviews_data if r.get("rating", 5) <= 3)

            profile = aggregator.build_profile(
                asin=asin, defects=defects, wishes=wishes,
                reviews_analyzed=len(reviews_data),
                negative_reviews_analyzed=negative_count,
            )

            if profile.reviews_ready:
                aggregator.save_profile(conn, profile, run_id=None)
                analyzed += 1
                if profile.improvement_score > 0.4:
                    logger.info(
                        f"  {asin}: score={profile.improvement_score:.3f}, "
                        f"dominant={profile.dominant_pain}, "
                        f"{len(profile.top_defects)} defects, "
                        f"{len(profile.missing_features)} wishes"
                    )

        return analyzed

    except ImportError:
        logger.warning("Review intelligence module not available — skipping analysis")
        return 0


# ============================================================================
# MAIN ORCHESTRATOR
# ============================================================================

@dataclass
class BackfillResult:
    """Result summary for the backfill run."""
    source: str = ""
    asins_targeted: int = 0
    asins_processed: int = 0
    asins_skipped_fresh: int = 0
    asins_failed: int = 0
    reviews_fetched: int = 0
    reviews_inserted: int = 0
    reviews_updated: int = 0
    reviews_skipped: int = 0
    reviews_empty_body_pct: float = 0.0
    reviews_short_body_pct: float = 0.0
    reviews_duplicate_pct: float = 0.0
    asins_analyzed: int = 0
    duration_sec: float = 0.0
    status: str = "completed"
    errors: List[str] = field(default_factory=list)


def run_backfill(config: BackfillConfig) -> BackfillResult:
    """Execute the review backfill job."""
    result = BackfillResult(source=config.source)
    start = time.time()

    print("=" * 60)
    print(f"SMARTACUS REVIEW BACKFILL (source: {config.source})")
    print("=" * 60)

    # Step 1: Connect to DB
    try:
        conn = get_db_connection()
        print(f"  DB connected")
    except Exception as e:
        print(f"  DB connection failed: {e}")
        result.status = "failed"
        result.errors.append(str(e))
        return result

    # Step 2: Get target ASINs
    try:
        if config.source == "csv" and config.csv_file:
            # For CSV mode, ASINs come from the file
            all_asins = config.asins if config.asins else None
            csv_reviews = load_reviews_from_csv(config.csv_file, all_asins)
            unique_asins = list(set(r.asin for r in csv_reviews))
            result.asins_targeted = len(unique_asins)
            print(f"\n  CSV file: {config.csv_file}")
            print(f"  Reviews in file: {len(csv_reviews)}")
            print(f"  Unique ASINs: {len(unique_asins)}")

            if config.dry_run:
                print(f"\n  DRY RUN — would import reviews for:")
                for a in unique_asins[:20]:
                    count = sum(1 for r in csv_reviews if r.asin == a)
                    print(f"    {a}: {count} reviews")
                result.status = "dry_run"
                conn.close()
                return result

            # Save all CSV reviews
            save_stats = save_reviews(conn, csv_reviews)
            result.reviews_fetched = len(csv_reviews)
            result.reviews_inserted = save_stats["inserted"]
            result.reviews_updated = save_stats["updated"]
            result.reviews_skipped = save_stats["skipped"]
            result.asins_processed = len(unique_asins)
            print(f"\n  Imported: +{save_stats['inserted']} new, ~{save_stats['updated']} updated")

            # Run analysis on all imported ASINs
            if config.run_analysis:
                print(f"\n--- Review Intelligence ---")
                result.asins_analyzed = run_review_intelligence(conn, unique_asins)
                print(f"  {result.asins_analyzed} ASINs analyzed")

        else:
            # Oxylabs or Playwright mode: target top ASINs
            all_asins = get_target_asins(conn, config)
            result.asins_targeted = len(all_asins)
            print(f"\n  Target ASINs: {len(all_asins)}")

            if not all_asins:
                print("  No ASINs to process — run the main pipeline first")
                result.status = "completed"
                conn.close()
                return result

            # Filter out fresh ASINs
            asins_to_fetch = get_asins_needing_refresh(conn, all_asins, config.freshness_hours)
            result.asins_skipped_fresh = len(all_asins) - len(asins_to_fetch)

            if result.asins_skipped_fresh > 0:
                print(f"  Skipping {result.asins_skipped_fresh} ASINs with fresh reviews (<{config.freshness_hours}h)")

            print(f"  ASINs to fetch: {len(asins_to_fetch)}")

            if config.dry_run:
                print(f"\n  DRY RUN — would fetch reviews for:")
                for a in asins_to_fetch:
                    print(f"    {a}")
                result.status = "dry_run"
                conn.close()
                return result

            # Select fetch function based on source
            if config.source == "oxylabs":
                fetch_func = fetch_reviews_oxylabs
                source_label = "Oxylabs"
            else:
                fetch_func = fetch_reviews_playwright
                source_label = "Playwright"

            print(f"\n--- Fetching Reviews ({source_label}) ---")
            total_fetched = 0

            for i, asin in enumerate(asins_to_fetch, 1):
                if total_fetched >= config.max_total_reviews:
                    print(f"  Global cap reached ({config.max_total_reviews} reviews)")
                    break

                print(f"  [{i}/{len(asins_to_fetch)}] {asin}...", end="", flush=True)

                try:
                    reviews = fetch_func(asin, config)

                    if not reviews:
                        if config.source == "oxylabs":
                            print(f" 0 reviews (no reviews returned)")
                        else:
                            print(f" 0 reviews (captcha/blocked)")
                        result.asins_failed += 1
                        result.errors.append(f"{asin}: no reviews fetched")
                        continue

                    save_stats = save_reviews(conn, reviews)

                    total_fetched += len(reviews)
                    result.reviews_fetched += len(reviews)
                    result.reviews_inserted += save_stats["inserted"]
                    result.reviews_updated += save_stats["updated"]
                    result.reviews_skipped += save_stats["skipped"]
                    result.asins_processed += 1

                    print(
                        f" {len(reviews)} reviews "
                        f"(+{save_stats['inserted']} new, "
                        f"~{save_stats['updated']} upd)"
                    )

                    # Inter-ASIN delay (shorter for Oxylabs as it has built-in rate limiting)
                    if i < len(asins_to_fetch):
                        if config.source == "oxylabs":
                            delay = 1.0  # Oxylabs client handles its own rate limiting
                        else:
                            delay = random.uniform(config.max_delay_sec, config.max_delay_sec * 2)
                        time.sleep(delay)

                except Exception as e:
                    print(f" ERROR: {e}")
                    result.asins_failed += 1
                    result.errors.append(f"{asin}: {str(e)[:100]}")

            # Run analysis
            if config.run_analysis and result.asins_processed > 0:
                print(f"\n--- Review Intelligence ---")
                analyzed_asins = asins_to_fetch[:result.asins_processed]
                result.asins_analyzed = run_review_intelligence(conn, analyzed_asins)
                print(f"  {result.asins_analyzed} ASINs analyzed")

    except Exception as e:
        print(f"  Error: {e}")
        result.status = "failed"
        result.errors.append(str(e))
        conn.close()
        return result

    # Quality metrics
    if result.reviews_fetched > 0 and result.reviews_updated > 0:
        result.reviews_duplicate_pct = round(result.reviews_updated / result.reviews_fetched * 100, 1)

    # Status
    result.duration_sec = round(time.time() - start, 1)
    if result.asins_failed > 0 and result.asins_processed == 0:
        result.status = "failed"
    elif result.asins_failed > 0:
        result.status = "degraded"

    # Summary
    print(f"\n{'=' * 60}")
    print(f"BACKFILL COMPLETE — {result.status.upper()}")
    print(f"{'=' * 60}")
    print(f"  Source:            {result.source}")
    print(f"  Duration:          {result.duration_sec}s")
    print(f"  ASINs targeted:    {result.asins_targeted}")
    print(f"  ASINs processed:   {result.asins_processed}")
    print(f"  ASINs skipped:     {result.asins_skipped_fresh} (fresh)")
    print(f"  ASINs failed:      {result.asins_failed}")
    print(f"  Reviews fetched:   {result.reviews_fetched}")
    print(f"  Reviews inserted:  {result.reviews_inserted} new")
    print(f"  Reviews updated:   {result.reviews_updated} existing")
    print(f"  Reviews skipped:   {result.reviews_skipped} errors")
    print(f"  Duplicate rate:    {result.reviews_duplicate_pct}%")
    print(f"  ASINs analyzed:    {result.asins_analyzed}")

    if result.errors:
        print(f"\n  Errors ({len(result.errors)}):")
        for err in result.errors[:10]:
            print(f"    - {err}")

    conn.close()
    return result


# ============================================================================
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Backfill Amazon reviews for top opportunity ASINs"
    )
    parser.add_argument(
        "--source", choices=["oxylabs", "playwright", "csv"], default="oxylabs",
        help="Data source: oxylabs (API, recommended), playwright (headless browser), or csv (file import)"
    )
    parser.add_argument(
        "--csv-file", type=str,
        help="Path to CSV file (required for --source csv)"
    )
    parser.add_argument(
        "--domain", type=str, default="fr",
        help="Amazon domain for oxylabs source (default: fr). Options: fr, com, de, uk, etc."
    )
    parser.add_argument(
        "--top-n", type=int, default=20,
        help="Fetch reviews for top N ASINs by score (default: 20)"
    )
    parser.add_argument(
        "--asins", type=str, default="",
        help="Comma-separated list of specific ASINs"
    )
    parser.add_argument(
        "--max-reviews-per-asin", type=int, default=200,
        help="Max reviews to fetch per ASIN (default: 200)"
    )
    parser.add_argument(
        "--max-pages", type=int, default=10,
        help="Max review pages per ASIN (default: 10)"
    )
    parser.add_argument(
        "--max-total", type=int, default=5000,
        help="Global cap on total reviews per run (default: 5000)"
    )
    parser.add_argument(
        "--freshness-hours", type=int, default=168,
        help="Skip ASINs with reviews newer than N hours (default: 168 = 7 days)"
    )
    parser.add_argument(
        "--min-delay", type=float, default=3.0,
        help="Min delay between requests (default: 3.0s)"
    )
    parser.add_argument(
        "--max-delay", type=float, default=7.0,
        help="Max delay between requests (default: 7.0s)"
    )
    parser.add_argument(
        "--no-analysis", action="store_true",
        help="Skip review intelligence analysis after backfill"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would be fetched without actually doing it"
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    parser.add_argument("--log-file", type=str)

    args = parser.parse_args()
    setup_logging(args.verbose, args.log_file)

    if args.source == "csv" and not args.csv_file:
        parser.error("--csv-file is required when --source is csv")

    config = BackfillConfig(
        source=args.source,
        csv_file=args.csv_file,
        amazon_domain=args.domain,
        top_n=args.top_n,
        asins=[a.strip() for a in args.asins.split(",") if a.strip()] if args.asins else [],
        max_reviews_per_asin=args.max_reviews_per_asin,
        max_pages_per_asin=args.max_pages,
        max_total_reviews=args.max_total,
        freshness_hours=args.freshness_hours,
        min_delay_sec=args.min_delay,
        max_delay_sec=args.max_delay,
        dry_run=args.dry_run,
        run_analysis=not args.no_analysis,
        verbose=args.verbose,
    )

    result = run_backfill(config)

    if result.status == "failed":
        sys.exit(1)
    elif result.status == "degraded":
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
