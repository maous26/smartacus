"""
Outscraper API Client for Amazon Review Scraping
=================================================

Fetches product reviews from Amazon via Outscraper async API.

Configuration:
    OUTSCRAPER_API_KEY: Outscraper API key (from .env)

Strategy:
    Fetch a large batch of recent reviews (up to 50), then client-side
    split into negative (1-3★) and positive (4-5★) to build a controlled mix.

    NOTE: Outscraper's filterByStar parameter is unreliable on non-US domains
    (returns unfiltered results regardless of value). We therefore fetch ALL
    reviews and filter locally.
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
    """Parsed Amazon review from Outscraper response."""
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
    """Outscraper API error."""
    pass



class OutscraperClient:
    """
    Client for Outscraper Amazon Reviews API using async jobs.

    Strategy: Fetch a large batch (up to 50), then client-side filter
    to build a balanced mix of negative and positive reviews.
    """

    API_BASE = "https://api.app.outscraper.com"

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Outscraper client.

        Args:
            api_key: Outscraper API key (default: from OUTSCRAPER_API_KEY env var)
        """
        self.api_key = api_key or os.getenv("OUTSCRAPER_API_KEY")

        if not self.api_key:
            raise OutscraperError(
                "Outscraper API key not configured. "
                "Set OUTSCRAPER_API_KEY in .env"
            )

        # Stats
        self._requests_made = 0
        self._reviews_fetched = 0
        self._jobs_submitted = 0

    def _get_headers(self) -> Dict[str, str]:
        """Get API headers."""
        return {"X-API-KEY": self.api_key}

    def _submit_reviews_job(
        self,
        asin: str,
        domain: str,
        limit: int,
        filter_by_star: Optional[str] = None,
        sort: str = "recent",
    ) -> str:
        """
        Submit an async reviews job.

        Returns job_id for polling.
        """
        url = f"{self.API_BASE}/amazon/reviews"

        params = {
            "query": f"https://www.amazon.{domain}/dp/{asin}",
            "limit": limit,
            "sort": sort,
            "async": "true",  # Force async mode
        }
        if filter_by_star:
            params["filterByStar"] = filter_by_star

        response = requests.get(url, params=params, headers=self._get_headers(), timeout=30)
        self._requests_made += 1

        if response.status_code == 401:
            raise OutscraperError("Invalid Outscraper API key")
        elif response.status_code == 402:
            raise OutscraperError("Outscraper payment required")
        elif response.status_code not in (200, 202):
            raise OutscraperError(f"API error: {response.status_code} - {response.text[:200]}")

        data = response.json()

        # Async returns job_id
        job_id = data.get("id")
        if not job_id:
            raise OutscraperError(f"No job_id in response: {data}")

        self._jobs_submitted += 1
        logger.debug(f"Submitted job {job_id} for {asin} ({filter_by_star})")

        return job_id

    def _poll_job(
        self,
        job_id: str,
        max_wait_seconds: int = 120,
        poll_interval: float = 3.0,
    ) -> List[Dict[str, Any]]:
        """
        Poll a job until completion.

        Returns list of review dicts.
        """
        url = f"{self.API_BASE}/requests/{job_id}"
        start_time = time.time()

        while time.time() - start_time < max_wait_seconds:
            response = requests.get(url, headers=self._get_headers(), timeout=30)
            self._requests_made += 1

            if response.status_code != 200:
                logger.warning(f"Poll error for {job_id}: {response.status_code}")
                time.sleep(poll_interval)
                continue

            data = response.json()
            status = data.get("status")

            if status == "Success":
                # Extract reviews from data
                results = data.get("data", [])
                if results and isinstance(results[0], list):
                    return results[0]  # First query results
                return results

            elif status == "Pending":
                logger.debug(f"Job {job_id} still pending...")
                time.sleep(poll_interval)
                continue

            elif status == "Error":
                error_msg = data.get("error", "Unknown error")
                logger.error(f"Job {job_id} failed: {error_msg}")
                return []

            else:
                logger.debug(f"Job {job_id} status: {status}")
                time.sleep(poll_interval)

        logger.warning(f"Job {job_id} timed out after {max_wait_seconds}s")
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
        Fetch product reviews with controlled star mix.

        Strategy: Outscraper's filterByStar is unreliable on non-US domains,
        so we fetch a large batch of ALL reviews and client-side filter to
        build a balanced mix of negative (1-3★) and positive (4-5★).

        Args:
            asin: Amazon product ASIN
            domain: Amazon domain code (e.g., 'fr', 'com', 'de')
            max_reviews: Maximum total reviews (default 15)
            target_negative: Target negative reviews (default 10)
            target_positive: Target positive reviews (default 5)

        Returns:
            List of Review objects with controlled mix
        """
        # Fetch more reviews than needed so we can filter client-side.
        # Negative reviews are typically 10-25% of all reviews, so fetch
        # enough to find them.
        fetch_limit = max(50, (target_negative + target_positive) * 4)

        logger.info(
            f"Fetching reviews for {asin} on amazon.{domain} "
            f"(fetching {fetch_limit}, target: {target_negative} neg + {target_positive} pos)"
        )

        try:
            # Single job — no star filter (unreliable), fetch all recent reviews
            job_id = self._submit_reviews_job(
                asin=asin,
                domain=domain,
                limit=fetch_limit,
                sort="recent",
            )

            logger.info(f"Polling job {job_id} for {asin}...")
            raw_reviews = self._poll_job(job_id)

            # Parse all reviews
            all_reviews = self._parse_reviews(raw_reviews, asin, domain)
            logger.info(f"Parsed {len(all_reviews)} reviews for {asin}")

            # Client-side split by rating
            negative = [r for r in all_reviews if r.rating <= 3]
            positive = [r for r in all_reviews if r.rating >= 4]

            logger.info(
                f"Rating split for {asin}: {len(negative)} negative (1-3★), "
                f"{len(positive)} positive (4-5★) out of {len(all_reviews)} total"
            )

            # Build balanced mix: prioritize negatives, fill with positives
            seen_ids = set()
            final_reviews = []

            for r in negative[:target_negative]:
                if r.review_id not in seen_ids:
                    seen_ids.add(r.review_id)
                    final_reviews.append(r)

            for r in positive[:target_positive]:
                if r.review_id not in seen_ids:
                    seen_ids.add(r.review_id)
                    final_reviews.append(r)

            # If we didn't get enough negatives, backfill with more positives
            if len(final_reviews) < max_reviews:
                remaining = max_reviews - len(final_reviews)
                for r in positive[target_positive:target_positive + remaining]:
                    if r.review_id not in seen_ids:
                        seen_ids.add(r.review_id)
                        final_reviews.append(r)

            final_reviews = final_reviews[:max_reviews]
            self._reviews_fetched += len(final_reviews)

            neg_count = sum(1 for r in final_reviews if r.rating <= 3)
            pos_count = sum(1 for r in final_reviews if r.rating >= 4)

            logger.info(
                f"Outscraper result: {asin} - {len(final_reviews)} reviews "
                f"({neg_count} negative, {pos_count} positive) "
                f"[from {len(all_reviews)} fetched]"
            )

            return final_reviews

        except Exception as e:
            error_msg = str(e)
            if "401" in error_msg or "unauthorized" in error_msg.lower():
                raise OutscraperError("Invalid Outscraper API key")
            elif "402" in error_msg:
                raise OutscraperError("Outscraper payment required")
            else:
                raise OutscraperError(f"Outscraper request failed: {e}")

    def _parse_reviews(
        self,
        raw_reviews: List[Dict[str, Any]],
        asin: str,
        domain: str,
    ) -> List[Review]:
        """Parse reviews from Outscraper API response."""
        reviews = []

        for raw in raw_reviews:
            try:
                # Review ID
                review_id = raw.get("id", "")
                if not review_id:
                    title = raw.get("title", "")
                    author = raw.get("author_title", "") or raw.get("author", "")
                    review_id = f"{asin}_{domain}_{hash(title + author) % 100000:05d}"

                # Rating (can be float like 5.0 or int like 50)
                rating_raw = raw.get("rating", 0)
                if isinstance(rating_raw, (int, float)):
                    rating = int(rating_raw)
                else:
                    # Parse from string if needed
                    import re
                    match = re.search(r"(\d+(?:\.\d+)?)", str(rating_raw))
                    rating = int(float(match.group(1))) if match else 0

                # Normalize if in 10x format (50 = 5 stars)
                if rating > 5:
                    rating = rating // 10

                # Date parsing
                date_str = raw.get("date", "")
                review_date = None
                if date_str:
                    review_date = self._parse_date(date_str)

                # Helpful votes
                helpful_str = raw.get("helpful", "") or ""
                helpful_votes = 0
                if helpful_str:
                    import re
                    match = re.search(r"([\d,]+)", str(helpful_str))
                    if match:
                        helpful_votes = int(match.group(1).replace(",", ""))

                # Verified purchase
                badge = raw.get("badge", "") or raw.get("bage", "") or ""
                verified = "verified" in str(badge).lower() or "achat" in str(badge).lower()

                # Clean body: Outscraper sometimes returns Amazon JS instead of text
                body = raw.get("body", "")
                if body and ("function()" in body or "P.when(" in body):
                    body = ""  # Discard JS-contaminated content
                # Strip Amazon's "Lire la suite" / "Read more" suffix
                if body:
                    body = body.replace("Lire la suite", "").replace("Read more", "").strip()

                review = Review(
                    review_id=review_id,
                    asin=raw.get("product_asin", asin),
                    title=raw.get("title", ""),
                    content=body,
                    rating=rating,
                    author=raw.get("author_title", "") or raw.get("author", ""),
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
        """Parse date from various formats."""
        if not date_str:
            return None

        try:
            import re

            # English format: "on March 17, 2018" or "March 17, 2018"
            match = re.search(r"(\w+\s+\d+,\s+\d{4})", date_str)
            if match:
                return datetime.strptime(match.group(1), "%B %d, %Y")

            # French format: "le 17 mars 2018" or "17 mars 2018"
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

            # ISO format: "2018-03-17"
            match = re.search(r"(\d{4})-(\d{2})-(\d{2})", date_str)
            if match:
                return datetime(int(match.group(1)), int(match.group(2)), int(match.group(3)))

        except Exception as e:
            logger.debug(f"Failed to parse date '{date_str}': {e}")

        return None

    def get_stats(self) -> Dict[str, Any]:
        """Get client statistics."""
        return {
            "requests_made": self._requests_made,
            "reviews_fetched": self._reviews_fetched,
        }


def test_outscraper_client():
    """Quick test of Outscraper client with client-side filtering."""
    import sys

    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

    try:
        client = OutscraperClient()
        print("Outscraper client initialized")

        asin = sys.argv[1] if len(sys.argv) > 1 else "B07KY1XKRQ"
        print(f"\nFetching reviews for {asin}...")
        print("(Fetching large batch + client-side filtering)\n")

        reviews = client.fetch_product_reviews(
            asin,
            domain="fr",
            target_negative=10,
            target_positive=5,
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
                title = r.title[:50] if r.title else "(no title)"
                body = r.content[:80] if r.content else ""
                print(f"  [{stars}] {title}")
                if body:
                    print(f"           {body}")

        if positive:
            print(f"\nPositive reviews ({len(positive)}):")
            for r in positive[:3]:
                stars = "*" * r.rating + "." * (5 - r.rating)
                title = r.title[:50] if r.title else "(no title)"
                print(f"  [{stars}] {title}")

        stats = client.get_stats()
        print(f"\nStats: {stats}")

        return reviews

    except OutscraperError as e:
        print(f"Outscraper error: {e}")
        return []


if __name__ == "__main__":
    test_outscraper_client()
