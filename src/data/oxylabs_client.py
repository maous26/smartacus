"""
Oxylabs API Client for Amazon Review Scraping
==============================================

Fetches product reviews from Amazon via Oxylabs SERP Scraper API.

Configuration:
    OXYLABS_USERNAME: Oxylabs API username (from .env)
    OXYLABS_PASSWORD: Oxylabs API password (from .env)

Note: Uses `amazon_product` source which returns 7-10 "Top reviews" per product.
For full review access, would need E-Commerce Scraper API (separate product).
"""

import os
import time
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Optional, Dict, Any
import requests
from requests.auth import HTTPBasicAuth

logger = logging.getLogger(__name__)


@dataclass
class Review:
    """Parsed Amazon review from Oxylabs response."""
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


class OxylabsError(Exception):
    """Oxylabs API error."""
    pass


class OxylabsClient:
    """
    Client for Oxylabs SERP Scraper API.

    Fetches Amazon product data including reviews.
    Rate limited to 1 request/second by default.
    """

    API_URL = "https://realtime.oxylabs.io/v1/queries"

    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        rate_limit_seconds: float = 1.0,
    ):
        """
        Initialize Oxylabs client.

        Args:
            username: Oxylabs API username (default: from OXYLABS_USERNAME env var)
            password: Oxylabs API password (default: from OXYLABS_PASSWORD env var)
            rate_limit_seconds: Minimum seconds between requests (default: 1.0)
        """
        self.username = username or os.getenv("OXYLABS_USERNAME")
        self.password = password or os.getenv("OXYLABS_PASSWORD")

        if not self.username or not self.password:
            raise OxylabsError(
                "Oxylabs credentials not configured. "
                "Set OXYLABS_USERNAME and OXYLABS_PASSWORD in .env"
            )

        self.rate_limit = rate_limit_seconds
        self._last_request_time: float = 0

        # Stats
        self._requests_made = 0
        self._reviews_fetched = 0

    def _wait_for_rate_limit(self):
        """Enforce rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)
        self._last_request_time = time.time()

    def fetch_product_reviews(
        self,
        asin: str,
        domain: str = "fr",
        max_reviews: int = 20,
    ) -> List[Review]:
        """
        Fetch product reviews from Amazon via Oxylabs.

        Args:
            asin: Amazon product ASIN
            domain: Amazon domain (e.g., 'fr', 'com', 'de')
            max_reviews: Maximum reviews to return

        Returns:
            List of Review objects

        Note:
            Oxylabs `amazon_product` source returns 7-10 "Top reviews".
            All reviews are returned (not filtered by rating) to capture
            both negative reviews (for defects) and positive ones (for "I wish..." patterns).
        """
        self._wait_for_rate_limit()

        payload = {
            "source": "amazon_product",
            "domain": domain,
            "query": asin,
            "parse": True,
        }

        try:
            logger.debug(f"Oxylabs request: ASIN={asin}, domain={domain}")

            response = requests.post(
                self.API_URL,
                json=payload,
                auth=HTTPBasicAuth(self.username, self.password),
                timeout=30,
            )

            self._requests_made += 1

            if response.status_code == 401:
                raise OxylabsError("Invalid Oxylabs credentials")
            elif response.status_code == 403:
                raise OxylabsError("Oxylabs access denied (check subscription)")
            elif response.status_code == 429:
                raise OxylabsError("Oxylabs rate limit exceeded")
            elif response.status_code != 200:
                raise OxylabsError(
                    f"Oxylabs API error: {response.status_code} - {response.text[:200]}"
                )

            data = response.json()

            # Extract reviews from response
            reviews = self._parse_reviews(data, asin, domain)
            self._reviews_fetched += len(reviews)

            logger.info(f"Oxylabs: fetched {len(reviews)} reviews for {asin}")
            return reviews[:max_reviews]

        except requests.RequestException as e:
            raise OxylabsError(f"Request failed: {e}")

    def _parse_reviews(
        self,
        response_data: Dict[str, Any],
        asin: str,
        domain: str,
    ) -> List[Review]:
        """Parse reviews from Oxylabs response."""
        import json as json_module
        reviews = []

        try:
            results = response_data.get("results", [])
            if not results:
                logger.warning(f"No results in Oxylabs response for {asin}")
                return []

            result = results[0]
            status_code = result.get("status_code", 0)

            # Check for HTTP errors
            if status_code == 404:
                logger.warning(f"Product not found on Amazon: {asin}")
                return []
            if status_code != 200:
                logger.warning(f"Oxylabs returned status {status_code} for {asin}")
                return []

            content = result.get("content", {})

            # Content may be a JSON string - parse it if so
            if isinstance(content, str):
                if not content:
                    logger.warning(f"Empty content from Oxylabs for {asin}")
                    return []
                try:
                    content = json_module.loads(content)
                except json_module.JSONDecodeError:
                    logger.warning(f"Failed to parse content as JSON for {asin}")
                    return []

            # Reviews are in 'reviews' key
            raw_reviews = content.get("reviews", [])

            for i, raw in enumerate(raw_reviews):
                try:
                    # Generate stable review_id from content
                    title = raw.get("title", "")
                    author = raw.get("author", "")
                    review_id = f"{asin}_{domain}_{hash(title + author) % 100000:05d}"

                    # Parse rating (can be string like "4.0 out of 5 stars" or int)
                    rating_raw = raw.get("rating", 0)
                    if isinstance(rating_raw, str):
                        # Extract first number
                        import re
                        match = re.search(r"(\d+(?:\.\d+)?)", rating_raw)
                        rating = int(float(match.group(1))) if match else 0
                    else:
                        rating = int(rating_raw) if rating_raw else 0

                    # Parse date
                    date_str = raw.get("timestamp", "") or raw.get("date", "")
                    review_date = None
                    if date_str:
                        try:
                            # Try common formats
                            for fmt in ["%Y-%m-%d", "%B %d, %Y", "%d %B %Y"]:
                                try:
                                    review_date = datetime.strptime(date_str, fmt)
                                    break
                                except ValueError:
                                    continue
                        except Exception:
                            pass

                    # Parse helpful votes
                    helpful_raw = raw.get("helpful_vote_statement", "") or ""
                    helpful_votes = 0
                    if helpful_raw:
                        import re
                        match = re.search(r"(\d+)", helpful_raw)
                        if match:
                            helpful_votes = int(match.group(1))

                    review = Review(
                        review_id=review_id,
                        asin=asin,
                        title=title,
                        content=raw.get("content", ""),
                        rating=rating,
                        author=author,
                        date=review_date,
                        helpful_votes=helpful_votes,
                        verified_purchase=raw.get("is_verified", False),
                        raw_data=raw,
                    )
                    reviews.append(review)

                except Exception as e:
                    logger.warning(f"Failed to parse review {i} for {asin}: {e}")
                    continue

        except Exception as e:
            logger.error(f"Failed to parse Oxylabs response for {asin}: {e}")

        return reviews

    def get_stats(self) -> Dict[str, Any]:
        """Get client statistics."""
        return {
            "requests_made": self._requests_made,
            "reviews_fetched": self._reviews_fetched,
        }


def test_oxylabs_client():
    """Quick test of Oxylabs client."""
    try:
        client = OxylabsClient()
        print(f"Oxylabs client initialized")

        # Test with a known ASIN
        asin = "B07KY1XKRQ"
        reviews = client.fetch_product_reviews(asin, domain="fr")

        print(f"\nFetched {len(reviews)} reviews for {asin}:")
        for r in reviews[:5]:
            print(f"  [{r.rating}*] {r.title[:50]}...")
            print(f"       {r.content[:80]}...")

        # Show stats
        stats = client.get_stats()
        print(f"\nStats: {stats}")

        return reviews

    except OxylabsError as e:
        print(f"Oxylabs error: {e}")
        return []


if __name__ == "__main__":
    test_oxylabs_client()
