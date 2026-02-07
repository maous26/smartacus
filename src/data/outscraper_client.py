"""
Amazon Review Scraping Client (Oxylabs)
=======================================

Fetches product reviews from Amazon via Oxylabs Web Scraper API.

Configuration:
    OXYLABS_USERNAME: Oxylabs API username (from .env)
    OXYLABS_PASSWORD: Oxylabs API password (from .env)

Strategy:
    Use Oxylabs amazon_product source which returns ~13 top reviews per
    product page with accurate ratings (1-5) and clean text.
    Reviews are client-side split into negative (1-3★) and positive (4-5★).

    Migrated from Outscraper whose filterByStar was broken on non-US
    domains and only returned ~10 reviews with corrupted bodies.

Backward compatibility:
    Class names OutscraperClient / OutscraperError are kept so existing
    callers (review_routes.py, cron_reviews.py) continue to work.
    The api_key init param is accepted but ignored (Oxylabs uses user/pass).
"""

import os
import re
import logging
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
    Amazon review client backed by Oxylabs Web Scraper API.

    Class name kept for backward compatibility with existing callers.
    Uses Oxylabs amazon_product source (realtime API) which returns
    ~13 top reviews with correct ratings and clean body text.
    """

    OXYLABS_URL = "https://realtime.oxylabs.io/v1/queries"

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize client.

        Args:
            api_key: Ignored (kept for backward compat).
                     Uses OXYLABS_USERNAME/OXYLABS_PASSWORD env vars.
        """
        self.username = os.getenv("OXYLABS_USERNAME")
        self.password = os.getenv("OXYLABS_PASSWORD")

        if not self.username or not self.password:
            raise OutscraperError(
                "Oxylabs credentials not configured. "
                "Set OXYLABS_USERNAME and OXYLABS_PASSWORD in .env"
            )

        # Stats
        self._requests_made = 0
        self._reviews_fetched = 0

    def fetch_product_reviews(
        self,
        asin: str,
        domain: str = "fr",
        max_reviews: int = 15,
        target_negative: int = 10,
        target_positive: int = 5,
    ) -> List[Review]:
        """
        Fetch product reviews via Oxylabs amazon_product.

        Returns ~13 top reviews from the product page, split client-side
        into negative (1-3★) and positive (4-5★).

        Args:
            asin: Amazon product ASIN
            domain: Amazon domain code (e.g., 'fr', 'com', 'de')
            max_reviews: Maximum total reviews to return (default 15)
            target_negative: Target negative reviews (default 10)
            target_positive: Target positive reviews (default 5)

        Returns:
            List of Review objects with balanced mix
        """
        logger.info(
            f"Fetching reviews for {asin} on amazon.{domain} via Oxylabs "
            f"(target: {target_negative} neg + {target_positive} pos)"
        )

        try:
            # Oxylabs realtime API — synchronous, returns parsed JSON
            payload = {
                "source": "amazon_product",
                "query": asin,
                "domain": domain,
                "parse": True,
            }

            response = requests.post(
                self.OXYLABS_URL,
                auth=(self.username, self.password),
                json=payload,
                timeout=60,
            )
            self._requests_made += 1

            if response.status_code == 401:
                raise OutscraperError("Invalid Oxylabs credentials")
            elif response.status_code == 403:
                raise OutscraperError("Oxylabs access forbidden — check subscription")
            elif response.status_code != 200:
                raise OutscraperError(
                    f"Oxylabs API error: {response.status_code} - {response.text[:200]}"
                )

            data = response.json()
            results = data.get("results", [])

            if not results:
                logger.warning(f"No results from Oxylabs for {asin}")
                return []

            content = results[0].get("content", {})
            raw_reviews = content.get("reviews", [])
            total_on_amazon = content.get("reviews_count", 0)

            logger.info(
                f"Oxylabs returned {len(raw_reviews)} reviews for {asin} "
                f"(Amazon total: {total_on_amazon})"
            )

            # Parse reviews
            all_reviews = self._parse_reviews(raw_reviews, asin, domain)

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

            # If we didn't get enough, backfill with remaining reviews
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
                f"Review result: {asin} - {len(final_reviews)} reviews "
                f"({neg_count} negative, {pos_count} positive) "
                f"[from {len(all_reviews)} scraped, {total_on_amazon} on Amazon]"
            )

            return final_reviews

        except OutscraperError:
            raise
        except Exception as e:
            raise OutscraperError(f"Oxylabs request failed: {e}")

    def _parse_reviews(
        self,
        raw_reviews: List[Dict[str, Any]],
        asin: str,
        domain: str,
    ) -> List[Review]:
        """Parse reviews from Oxylabs amazon_product response."""
        reviews = []

        for raw in raw_reviews:
            try:
                # Review ID
                review_id = raw.get("id", "")
                if not review_id:
                    title = raw.get("title", "")
                    author = raw.get("author", "")
                    review_id = f"{asin}_{domain}_{hash(title + author) % 100000:05d}"

                # Rating — Oxylabs returns clean 1-5 integer
                rating = int(raw.get("rating", 0))
                if rating < 1 or rating > 5:
                    rating = max(1, min(5, rating))

                # Title — Oxylabs sometimes prefixes with "X,0 sur 5 étoiles"
                title = raw.get("title", "")
                # Strip star prefix: "5,0 sur 5\xa0étoiles Super" → "Super"
                title = re.sub(
                    r'^\d+[.,]\d+\s+sur\s+\d+\s*[ée]toiles\s*',
                    '', title
                ).strip()

                # Content — clean text from Oxylabs
                content = raw.get("content", "")
                # Strip "Lire la suite" / "Read more" suffix
                if content:
                    content = (content
                               .replace("Lire la suite", "")
                               .replace("Read more", "")
                               .strip())

                # Date — "Avis laissé en France le 22 janvier 2026"
                date_str = raw.get("timestamp", "")
                review_date = self._parse_date(date_str) if date_str else None

                # Author
                author = raw.get("author", "")

                # Verified purchase
                verified = raw.get("is_verified", False)

                # Helpful votes
                helpful_votes = raw.get("helpful_count", 0) or 0

                review = Review(
                    review_id=review_id,
                    asin=asin,
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
        """Parse date from various Amazon formats."""
        if not date_str:
            return None

        try:
            # English: "on March 17, 2018" or "March 17, 2018"
            match = re.search(r"(\w+\s+\d+,\s+\d{4})", date_str)
            if match:
                return datetime.strptime(match.group(1), "%B %d, %Y")

            # French: "le 17 mars 2018" or "17 mars 2018"
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

            # ISO: "2018-03-17"
            match = re.search(r"(\d{4})-(\d{2})-(\d{2})", date_str)
            if match:
                return datetime(
                    int(match.group(1)), int(match.group(2)), int(match.group(3))
                )

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
    """Quick test of review client."""
    import sys

    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

    try:
        client = OutscraperClient()
        print("Review client initialized (Oxylabs)")

        asin = sys.argv[1] if len(sys.argv) > 1 else "B08DKHHTFX"
        print(f"\nFetching reviews for {asin}...\n")

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
                print(f"  [{stars}] {r.title[:60]}")
                if r.content:
                    print(f"           {r.content[:100]}")

        if positive:
            print(f"\nPositive reviews ({len(positive)}):")
            for r in positive[:3]:
                stars = "*" * r.rating + "." * (5 - r.rating)
                print(f"  [{stars}] {r.title[:60]}")

        print(f"\nStats: {client.get_stats()}")
        return reviews

    except OutscraperError as e:
        print(f"Error: {e}")
        return []


if __name__ == "__main__":
    test_client()
