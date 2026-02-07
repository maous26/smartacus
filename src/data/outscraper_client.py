"""
Amazon Review Scraping Client (Apify)
=====================================

Fetches product reviews from Amazon via Apify junglee~amazon-reviews-scraper.

Configuration:
    APIFY_TOKEN: Apify API token (from .env)

Strategy:
    Submit 2 Apify actor runs in parallel:
    - 10 negative reviews (filterByRating=critical, 1-3★)
    - 5 positive reviews (filterByRating=positive, 4-5★)
    Poll until both complete, then merge.

    Apify's junglee actor correctly supports filterByRating on Amazon.fr,
    unlike Outscraper whose filterByStar was silently ignored.

Backward compatibility:
    Class names OutscraperClient / OutscraperError are kept so existing
    callers (review_routes.py, cron_reviews.py) continue to work.
    The api_key init param is accepted but ignored (Apify uses APIFY_TOKEN).
"""

import os
import logging
import time
import requests
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any

logger = logging.getLogger(__name__)


@dataclass
class Review:
    """Parsed Amazon review."""
    review_id: str
    asin: str
    title: str
    content: str
    rating: int
    author: str
    date: Optional[datetime] = None
    helpful_votes: int = 0
    verified_purchase: bool = False
    raw_data: Dict[str, Any] = field(default_factory=dict)


class OutscraperError(Exception):
    """Review scraping API error (kept for backward compat)."""
    pass


class OutscraperClient:
    """
    Amazon review client backed by Apify junglee~amazon-reviews-scraper.

    Class name kept for backward compatibility with existing callers.
    Uses Apify actor that correctly handles filterByRating on Amazon.fr
    and returns real negative reviews with proper ratings and text.
    """

    APIFY_BASE = "https://api.apify.com/v2"
    ACTOR_ID = "junglee~amazon-reviews-scraper"

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize client.

        Args:
            api_key: Ignored (backward compat). Uses APIFY_TOKEN env var.
        """
        self.token = os.getenv("APIFY_TOKEN")

        if not self.token:
            raise OutscraperError(
                "Apify token not configured. Set APIFY_TOKEN in .env"
            )

        self._requests_made = 0
        self._reviews_fetched = 0

    def _run_actor(
        self,
        asin: str,
        domain: str,
        limit: int,
        filter_by_rating: str,
    ) -> str:
        """Submit an Apify actor run. Returns run_id."""
        url = f"{self.APIFY_BASE}/acts/{self.ACTOR_ID}/runs"

        input_data = {
            "productUrls": [
                {"url": f"https://www.amazon.{domain}/dp/{asin}"}
            ],
            "maxReviewsPerProduct": limit,
            "filterByRating": filter_by_rating,
            "sort": "recent",
        }

        response = requests.post(
            url,
            params={"token": self.token},
            json=input_data,
            timeout=30,
        )
        self._requests_made += 1

        if response.status_code == 401:
            raise OutscraperError("Invalid Apify token")
        elif response.status_code != 201:
            raise OutscraperError(
                f"Apify submit error: {response.status_code} - {response.text[:200]}"
            )

        run_data = response.json().get("data", {})
        run_id = run_data.get("id")
        if not run_id:
            raise OutscraperError(f"No run_id in Apify response: {run_data}")

        logger.debug(f"Apify run {run_id} submitted for {asin} ({filter_by_rating})")
        return run_id

    def _poll_run(
        self,
        run_id: str,
        max_wait_seconds: int = 180,
        poll_interval: float = 5.0,
    ) -> List[Dict[str, Any]]:
        """Poll an Apify run until completion. Returns list of review dicts."""
        start_time = time.time()

        while time.time() - start_time < max_wait_seconds:
            response = requests.get(
                f"{self.APIFY_BASE}/actor-runs/{run_id}",
                params={"token": self.token},
                timeout=15,
            )
            self._requests_made += 1

            if response.status_code != 200:
                logger.warning(f"Poll error for {run_id}: {response.status_code}")
                time.sleep(poll_interval)
                continue

            data = response.json().get("data", {})
            status = data.get("status")

            if status == "SUCCEEDED":
                dataset_id = data.get("defaultDatasetId")
                if not dataset_id:
                    return []

                items_resp = requests.get(
                    f"{self.APIFY_BASE}/datasets/{dataset_id}/items",
                    params={"token": self.token, "limit": 200},
                    timeout=30,
                )
                self._requests_made += 1

                if items_resp.status_code == 200:
                    return items_resp.json()
                return []

            elif status in ("FAILED", "ABORTED", "TIMED-OUT"):
                logger.error(f"Apify run {run_id} failed: {status}")
                return []

            else:
                logger.debug(f"Apify run {run_id}: {status}")
                time.sleep(poll_interval)

        logger.warning(f"Apify run {run_id} timed out after {max_wait_seconds}s")
        return []

    def fetch_product_reviews(
        self,
        asin: str,
        domain: str = "fr",
        max_reviews: int = 15,
        target_negative: int = 10,
        target_positive: int = 5,
    ) -> List[Review]:
        """
        Fetch product reviews with controlled star mix via Apify.

        Submits 2 actor runs:
        - critical (1-3★) for defect detection
        - positive (4-5★) for "I wish..." patterns

        Args:
            asin: Amazon product ASIN
            domain: Amazon domain code (e.g., 'fr', 'com', 'de')
            max_reviews: Maximum total reviews (default 15)
            target_negative: Target negative reviews (default 10)
            target_positive: Target positive reviews (default 5)

        Returns:
            List of Review objects with controlled mix
        """
        logger.info(
            f"Fetching reviews for {asin} on amazon.{domain} via Apify "
            f"(target: {target_negative} neg + {target_positive} pos)"
        )

        try:
            # Submit both runs
            run_critical = self._run_actor(
                asin=asin,
                domain=domain,
                limit=target_negative,
                filter_by_rating="critical",
            )

            time.sleep(0.5)

            run_positive = self._run_actor(
                asin=asin,
                domain=domain,
                limit=target_positive,
                filter_by_rating="positive",
            )

            # Poll both
            logger.info(f"Polling Apify runs: critical={run_critical}, positive={run_positive}")

            raw_negative = self._poll_run(run_critical)
            raw_positive = self._poll_run(run_positive)

            # Parse
            negative_reviews = self._parse_reviews(raw_negative, asin, domain)
            positive_reviews = self._parse_reviews(raw_positive, asin, domain)

            # Build balanced mix
            seen_ids = set()
            final_reviews = []

            for r in negative_reviews[:target_negative]:
                if r.review_id not in seen_ids:
                    seen_ids.add(r.review_id)
                    final_reviews.append(r)

            for r in positive_reviews[:target_positive]:
                if r.review_id not in seen_ids:
                    seen_ids.add(r.review_id)
                    final_reviews.append(r)

            final_reviews = final_reviews[:max_reviews]
            self._reviews_fetched += len(final_reviews)

            neg_count = sum(1 for r in final_reviews if r.rating <= 3)
            pos_count = sum(1 for r in final_reviews if r.rating >= 4)

            logger.info(
                f"Apify result: {asin} - {len(final_reviews)} reviews "
                f"({neg_count} negative, {pos_count} positive)"
            )

            return final_reviews

        except OutscraperError:
            raise
        except Exception as e:
            raise OutscraperError(f"Apify request failed: {e}")

    def _parse_reviews(
        self,
        raw_reviews: List[Dict[str, Any]],
        asin: str,
        domain: str,
    ) -> List[Review]:
        """Parse reviews from Apify junglee actor response."""
        reviews = []

        for raw in raw_reviews:
            try:
                review_id = raw.get("reviewId", "")
                if not review_id:
                    title = raw.get("reviewTitle", "")
                    author = raw.get("userId", "")
                    review_id = f"{asin}_{domain}_{hash(title + author) % 100000:05d}"

                rating = int(raw.get("ratingScore", 0))
                if rating < 1 or rating > 5:
                    rating = max(1, min(5, rating))

                title = raw.get("reviewTitle", "")
                content = raw.get("reviewDescription", "")

                # Parse date
                date_str = raw.get("date", "")
                review_date = None
                if date_str:
                    try:
                        review_date = datetime.strptime(date_str, "%Y-%m-%d")
                    except ValueError:
                        review_date = self._parse_date(
                            raw.get("reviewedIn", "")
                        )

                author = raw.get("userId", "")
                verified = raw.get("isVerified", False)
                helpful_votes = raw.get("reviewReaction", 0) or 0

                review = Review(
                    review_id=review_id,
                    asin=raw.get("productOriginalAsin", asin),
                    title=title,
                    content=content,
                    rating=rating,
                    author=author,
                    date=review_date,
                    helpful_votes=helpful_votes,
                    verified_purchase=verified,
                    raw_data=raw,
                )
                reviews.append(review)

            except Exception as e:
                logger.warning(f"Failed to parse review for {asin}: {e}")
                continue

        return reviews

    def _parse_date(self, date_str: str) -> Optional[datetime]:
        """Parse date from Amazon format strings."""
        if not date_str:
            return None

        try:
            import re

            # French: "Commenté en France le 22 janvier 2026"
            french_months = {
                "janvier": 1, "février": 2, "mars": 3, "avril": 4,
                "mai": 5, "juin": 6, "juillet": 7, "août": 8,
                "septembre": 9, "octobre": 10, "novembre": 11, "décembre": 12
            }
            match = re.search(r"(\d+)\s+(\w+)\s+(\d{4})", date_str)
            if match:
                day = int(match.group(1))
                month_str = match.group(2).lower()
                year = int(match.group(3))
                month = french_months.get(month_str)
                if month:
                    return datetime(year, month, day)

            # English: "March 17, 2018"
            match = re.search(r"(\w+\s+\d+,\s+\d{4})", date_str)
            if match:
                return datetime.strptime(match.group(1), "%B %d, %Y")

        except Exception as e:
            logger.debug(f"Failed to parse date '{date_str}': {e}")

        return None

    def get_stats(self) -> Dict[str, Any]:
        """Get client statistics."""
        return {
            "requests_made": self._requests_made,
            "reviews_fetched": self._reviews_fetched,
        }


def test_client():
    """Quick test."""
    import sys

    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

    try:
        client = OutscraperClient()
        print("Review client initialized (Apify)")

        asin = sys.argv[1] if len(sys.argv) > 1 else "B08DKHHTFX"
        print(f"\nFetching reviews for {asin}...\n")

        reviews = client.fetch_product_reviews(
            asin, domain="fr", target_negative=10, target_positive=5,
        )

        print(f"\n{'='*50}")
        print(f"RESULTS for {asin}")
        print(f"{'='*50}")

        negative = [r for r in reviews if r.rating <= 3]
        positive = [r for r in reviews if r.rating >= 4]

        print(f"Total: {len(reviews)} reviews")
        print(f"  - {len(negative)} negative (1-3 stars)")
        print(f"  - {len(positive)} positive (4-5 stars)")

        if negative:
            print(f"\nNegative reviews ({len(negative)}):")
            for r in negative[:5]:
                stars = "*" * r.rating + "." * (5 - r.rating)
                print(f"  [{stars}] {r.title[:60]}")
                if r.content:
                    print(f"           {r.content[:100]}")

        if positive:
            print(f"\nPositive reviews ({len(positive)}):")
            for r in positive[:3]:
                stars = "*" * r.rating + "." * (5 - r.rating)
                print(f"  [{stars}] {r.title[:60]}")

        print(f"\nStats: {client.get_stats()}")

    except OutscraperError as e:
        print(f"Error: {e}")


if __name__ == "__main__":
    test_client()
