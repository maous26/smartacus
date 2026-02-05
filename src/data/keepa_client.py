"""
Smartacus Keepa Client
======================

Robust Keepa API client with intelligent rate limiting, retry logic,
and comprehensive error handling.

Features:
    - Automatic rate limiting respecting Keepa token limits
    - Exponential backoff retry logic
    - Batch processing for efficient API usage
    - Comprehensive error handling and logging
    - Token consumption tracking

Usage:
    from keepa_client import KeepaClient

    client = KeepaClient()
    asins = client.get_category_asins(7072562011)  # Car phone mounts
    products = client.get_product_data(asins[:100])
"""

import time
import logging
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass
import threading

import keepa

from .data_models import (
    ProductData,
    ProductSnapshot,
    ProductMetadata,
    PriceHistory,
    BSRHistory,
    BuyBoxHistory,
    SellerInfo,
    StockStatus,
    FulfillmentType,
)


# Configure logging
logger = logging.getLogger(__name__)


class KeepaAPIError(Exception):
    """Base exception for Keepa API errors."""

    def __init__(self, message: str, error_code: Optional[int] = None, response: Optional[Dict] = None):
        self.message = message
        self.error_code = error_code
        self.response = response
        super().__init__(self.message)


class KeepaRateLimitError(KeepaAPIError):
    """Rate limit exceeded error."""

    def __init__(self, tokens_remaining: int, reset_time: Optional[datetime] = None):
        self.tokens_remaining = tokens_remaining
        self.reset_time = reset_time
        message = f"Rate limit exceeded. Tokens remaining: {tokens_remaining}"
        if reset_time:
            message += f", reset at: {reset_time.isoformat()}"
        super().__init__(message)


class KeepaTokenExhaustedError(KeepaAPIError):
    """All tokens exhausted for the current period."""
    pass


class KeepaDataNotFoundError(KeepaAPIError):
    """Requested data not found (e.g., invalid ASIN)."""
    pass


@dataclass
class RateLimitState:
    """Track rate limit state."""
    tokens_left: int = 0
    tokens_per_minute: int = 200
    last_request_time: Optional[datetime] = None
    refill_rate: float = 0.0  # tokens per second

    def can_make_request(self, tokens_needed: int) -> bool:
        """Check if we have enough tokens for a request."""
        self._refill_tokens()
        return self.tokens_left >= tokens_needed

    def _refill_tokens(self):
        """Refill tokens based on elapsed time."""
        if self.last_request_time is None:
            self.tokens_left = self.tokens_per_minute
            return

        elapsed = (datetime.utcnow() - self.last_request_time).total_seconds()
        refilled = int(elapsed * self.refill_rate)
        self.tokens_left = min(self.tokens_per_minute, self.tokens_left + refilled)

    def consume_tokens(self, tokens: int):
        """Record token consumption."""
        self.tokens_left = max(0, self.tokens_left - tokens)
        self.last_request_time = datetime.utcnow()

    def wait_time_for_tokens(self, tokens_needed: int) -> float:
        """Calculate wait time to get enough tokens."""
        self._refill_tokens()
        if self.tokens_left >= tokens_needed:
            return 0.0

        tokens_deficit = tokens_needed - self.tokens_left
        if self.refill_rate <= 0:
            return 60.0  # Default wait

        return tokens_deficit / self.refill_rate


class KeepaClient:
    """
    Keepa API client with intelligent rate limiting and error handling.

    This client wraps the official keepa Python library and adds:
    - Automatic rate limiting with token tracking
    - Exponential backoff retry logic
    - Batch processing optimization
    - Comprehensive error handling
    - Data transformation to our internal models
    """

    # Keepa API constants
    KEEPA_EPOCH = datetime(2011, 1, 1, 0, 0, 0)

    # Price type indices in Keepa response
    PRICE_AMAZON = 0
    PRICE_NEW = 1
    PRICE_USED = 2
    PRICE_SALES_RANK = 3
    PRICE_LISTING = 4
    PRICE_BUYBOX_NEW = 5
    PRICE_BUYBOX_USED = 6
    PRICE_NEW_FBM = 7
    PRICE_LIGHTNING_DEAL = 8
    PRICE_WAREHOUSE_DEAL = 9
    PRICE_NEW_FBA = 10
    PRICE_COUNT_NEW = 11
    PRICE_COUNT_USED = 12
    PRICE_RATING = 16
    PRICE_REVIEW_COUNT = 17

    def __init__(
        self,
        api_key: Optional[str] = None,
        tokens_per_minute: int = 200,
        max_retries: int = 3,
        retry_base_delay: float = 1.0,
        retry_max_delay: float = 60.0,
        domain_id: int = 1,
    ):
        """
        Initialize Keepa client.

        Args:
            api_key: Keepa API key (if None, loaded from config)
            tokens_per_minute: Rate limit tokens per minute
            max_retries: Maximum retry attempts
            retry_base_delay: Base delay for exponential backoff (seconds)
            retry_max_delay: Maximum delay between retries (seconds)
            domain_id: Amazon marketplace (1=com, 2=co.uk, 3=de, etc.)
        """
        # Load from config if not provided
        if api_key is None:
            from .config import get_settings
            settings = get_settings()
            api_key = settings.keepa.api_key
            tokens_per_minute = settings.keepa.tokens_per_minute
            max_retries = settings.keepa.max_retries
            retry_base_delay = settings.keepa.retry_base_delay
            retry_max_delay = settings.keepa.retry_max_delay
            domain_id = settings.keepa.domain_id

        self.api_key = api_key
        self.domain_id = domain_id
        self.max_retries = max_retries
        self.retry_base_delay = retry_base_delay
        self.retry_max_delay = retry_max_delay

        # Initialize rate limit state
        self._rate_limit = RateLimitState(
            tokens_per_minute=tokens_per_minute,
            tokens_left=tokens_per_minute,
            refill_rate=tokens_per_minute / 60.0,  # tokens per second
        )
        self._rate_limit_lock = threading.Lock()

        # Initialize Keepa API client
        self._api: Optional[keepa.Keepa] = None
        self._api_lock = threading.Lock()

        # Statistics tracking
        self._stats = {
            "total_requests": 0,
            "total_tokens_consumed": 0,
            "total_errors": 0,
            "last_request_time": None,
        }

        logger.info(
            f"KeepaClient initialized: domain={domain_id}, "
            f"tokens/min={tokens_per_minute}, max_retries={max_retries}"
        )

    @property
    def api(self) -> keepa.Keepa:
        """Lazy-initialize and return Keepa API instance."""
        if self._api is None:
            with self._api_lock:
                if self._api is None:
                    self._api = keepa.Keepa(self.api_key)
                    logger.info("Keepa API connection established")
        return self._api

    def _wait_for_rate_limit(self, tokens_needed: int) -> None:
        """
        Wait if necessary to respect rate limits.

        Args:
            tokens_needed: Number of tokens required for the request
        """
        with self._rate_limit_lock:
            wait_time = self._rate_limit.wait_time_for_tokens(tokens_needed)
            if wait_time > 0:
                logger.info(f"Rate limit: waiting {wait_time:.1f}s for {tokens_needed} tokens")
                time.sleep(wait_time)
                # Refill after wait
                self._rate_limit._refill_tokens()

    def _consume_tokens(self, tokens: int) -> None:
        """Record token consumption."""
        with self._rate_limit_lock:
            self._rate_limit.consume_tokens(tokens)
            self._stats["total_tokens_consumed"] += tokens
            self._stats["total_requests"] += 1
            self._stats["last_request_time"] = datetime.utcnow()

    def _retry_with_backoff(self, func, *args, **kwargs) -> Any:
        """
        Execute function with exponential backoff retry.

        Args:
            func: Function to execute
            *args: Positional arguments
            **kwargs: Keyword arguments

        Returns:
            Function result

        Raises:
            KeepaAPIError: If all retries fail
        """
        last_exception = None

        for attempt in range(self.max_retries + 1):
            try:
                return func(*args, **kwargs)

            except keepa.KeepaError as e:
                last_exception = e
                error_msg = str(e).lower()

                # Check for specific error types
                if "not enough tokens" in error_msg or "rate limit" in error_msg:
                    # Rate limit - wait and retry
                    wait_time = min(
                        self.retry_base_delay * (2 ** attempt),
                        self.retry_max_delay
                    )
                    logger.warning(
                        f"Rate limit hit (attempt {attempt + 1}/{self.max_retries + 1}), "
                        f"waiting {wait_time:.1f}s"
                    )
                    time.sleep(wait_time)
                    continue

                elif "invalid" in error_msg and "key" in error_msg:
                    # Invalid API key - don't retry
                    raise KeepaAPIError(
                        f"Invalid API key: {e}",
                        error_code=401
                    )

                else:
                    # Other error - retry with backoff
                    if attempt < self.max_retries:
                        wait_time = min(
                            self.retry_base_delay * (2 ** attempt),
                            self.retry_max_delay
                        )
                        logger.warning(
                            f"Keepa API error (attempt {attempt + 1}/{self.max_retries + 1}): {e}, "
                            f"retrying in {wait_time:.1f}s"
                        )
                        time.sleep(wait_time)
                        continue

            except Exception as e:
                last_exception = e
                self._stats["total_errors"] += 1

                if attempt < self.max_retries:
                    wait_time = min(
                        self.retry_base_delay * (2 ** attempt),
                        self.retry_max_delay
                    )
                    logger.warning(
                        f"Unexpected error (attempt {attempt + 1}/{self.max_retries + 1}): {e}, "
                        f"retrying in {wait_time:.1f}s"
                    )
                    time.sleep(wait_time)
                    continue

        # All retries exhausted
        self._stats["total_errors"] += 1
        raise KeepaAPIError(f"All retries failed: {last_exception}")

    def _keepa_time_to_datetime(self, keepa_minutes: int) -> datetime:
        """Convert Keepa time (minutes since 2011-01-01) to datetime."""
        return self.KEEPA_EPOCH + timedelta(minutes=keepa_minutes)

    def _parse_price_history(self, csv_data: List, price_type: int) -> List[PriceHistory]:
        """
        Parse Keepa price history CSV data.

        Keepa stores history as flat array: [time1, value1, time2, value2, ...]

        Args:
            csv_data: Keepa CSV array
            price_type: Type of price data

        Returns:
            List of PriceHistory objects
        """
        if csv_data is None or len(csv_data) == 0:
            return []

        history = []
        for i in range(0, len(csv_data), 2):
            if i + 1 >= len(csv_data):
                break

            keepa_time = csv_data[i]
            price_cents = csv_data[i + 1]

            # Skip invalid entries (-1 = no data)
            if keepa_time == -1 or price_cents == -1:
                continue

            try:
                timestamp = self._keepa_time_to_datetime(keepa_time)
                history.append(PriceHistory(
                    timestamp=timestamp,
                    price_cents=price_cents,
                    is_deal=(price_type == self.PRICE_LIGHTNING_DEAL),
                ))
            except Exception as e:
                logger.debug(f"Failed to parse price history entry: {e}")
                continue

        return history

    def _parse_bsr_history(self, csv_data: List, category_name: Optional[str] = None) -> List[BSRHistory]:
        """
        Parse Keepa BSR history CSV data.

        Args:
            csv_data: Keepa CSV array
            category_name: Category name for context

        Returns:
            List of BSRHistory objects
        """
        if csv_data is None or len(csv_data) == 0:
            return []

        history = []
        for i in range(0, len(csv_data), 2):
            if i + 1 >= len(csv_data):
                break

            keepa_time = csv_data[i]
            bsr = csv_data[i + 1]

            # Skip invalid entries
            if keepa_time == -1 or bsr == -1:
                continue

            try:
                timestamp = self._keepa_time_to_datetime(keepa_time)
                history.append(BSRHistory(
                    timestamp=timestamp,
                    bsr=bsr,
                    category_name=category_name,
                ))
            except Exception as e:
                logger.debug(f"Failed to parse BSR history entry: {e}")
                continue

        return history

    def _determine_stock_status(self, product: Dict) -> StockStatus:
        """Determine stock status from Keepa product data."""
        # Check availability data if present
        availability = product.get("availabilityAmazon", -1)
        if availability == 0:
            return StockStatus.IN_STOCK
        elif availability == -1:
            return StockStatus.OUT_OF_STOCK

        # Check if there's a current price (indicates in stock)
        csv = product.get("csv", [])
        if csv and len(csv) > self.PRICE_AMAZON:
            amazon_prices = csv[self.PRICE_AMAZON]
            if amazon_prices and len(amazon_prices) >= 2:
                latest_price = amazon_prices[-1]
                if latest_price > 0:
                    return StockStatus.IN_STOCK

        # Check new offers
        if csv and len(csv) > self.PRICE_COUNT_NEW:
            new_count = csv[self.PRICE_COUNT_NEW]
            if new_count and len(new_count) >= 2:
                latest_count = new_count[-1]
                if latest_count > 0:
                    return StockStatus.IN_STOCK

        return StockStatus.UNKNOWN

    def _determine_fulfillment(self, product: Dict) -> FulfillmentType:
        """Determine fulfillment type from Keepa product data."""
        # Check if Amazon is selling
        csv = product.get("csv", [])
        if csv and len(csv) > self.PRICE_AMAZON:
            amazon_prices = csv[self.PRICE_AMAZON]
            if amazon_prices and len(amazon_prices) >= 2:
                if amazon_prices[-1] > 0:
                    return FulfillmentType.AMAZON

        # Check FBA prices
        if csv and len(csv) > self.PRICE_NEW_FBA:
            fba_prices = csv[self.PRICE_NEW_FBA]
            if fba_prices and len(fba_prices) >= 2:
                if fba_prices[-1] > 0:
                    return FulfillmentType.FBA

        # Check FBM prices
        if csv and len(csv) > self.PRICE_NEW_FBM:
            fbm_prices = csv[self.PRICE_NEW_FBM]
            if fbm_prices and len(fbm_prices) >= 2:
                if fbm_prices[-1] > 0:
                    return FulfillmentType.FBM

        return FulfillmentType.UNKNOWN

    def _extract_latest_value(self, csv_data: List) -> Optional[int]:
        """Extract the latest value from Keepa CSV data array."""
        if csv_data is None or len(csv_data) < 2:
            return None

        # Get the last value (skip -1 which means no data)
        for i in range(len(csv_data) - 1, 0, -2):
            value = csv_data[i]
            if value != -1:
                return value

        return None

    def _transform_product(self, product: Dict) -> ProductData:
        """
        Transform Keepa product response to our data models.

        Args:
            product: Keepa product dictionary

        Returns:
            ProductData instance
        """
        asin = product.get("asin", "")
        csv = product.get("csv", [])
        stats = product.get("stats", {})

        # Extract current prices
        price_amazon = None
        price_new = None
        price_used = None
        price_buybox = None

        if csv:
            if len(csv) > self.PRICE_AMAZON:
                price_amazon = self._extract_latest_value(csv[self.PRICE_AMAZON])
            if len(csv) > self.PRICE_NEW:
                price_new = self._extract_latest_value(csv[self.PRICE_NEW])
            if len(csv) > self.PRICE_USED:
                price_used = self._extract_latest_value(csv[self.PRICE_USED])
            if len(csv) > self.PRICE_BUYBOX_NEW:
                price_buybox = self._extract_latest_value(csv[self.PRICE_BUYBOX_NEW])

        # Determine current price (priority: BuyBox > Amazon > New)
        current_price_cents = price_buybox or price_amazon or price_new

        # Extract BSR
        bsr_primary = None
        bsr_category = None
        if csv and len(csv) > self.PRICE_SALES_RANK:
            bsr_primary = self._extract_latest_value(csv[self.PRICE_SALES_RANK])

        # Get category info
        categories = product.get("categoryTree", [])
        if categories:
            bsr_category = categories[-1].get("name") if categories else None

        # Extract rating and reviews
        rating_avg = None
        review_count = None
        if csv:
            if len(csv) > self.PRICE_RATING:
                rating_raw = self._extract_latest_value(csv[self.PRICE_RATING])
                if rating_raw and rating_raw > 0:
                    rating_avg = Decimal(rating_raw) / 10  # Keepa stores as rating * 10
            if len(csv) > self.PRICE_REVIEW_COUNT:
                review_count = self._extract_latest_value(csv[self.PRICE_REVIEW_COUNT])

        # Get seller count
        seller_count = None
        if csv and len(csv) > self.PRICE_COUNT_NEW:
            seller_count = self._extract_latest_value(csv[self.PRICE_COUNT_NEW])

        # Create snapshot
        snapshot = ProductSnapshot(
            asin=asin,
            captured_at=datetime.utcnow(),
            price_current=Decimal(current_price_cents) / 100 if current_price_cents else None,
            price_original=Decimal(product.get("listPrice", 0)) / 100 if product.get("listPrice") else None,
            price_lowest_new=Decimal(price_new) / 100 if price_new else None,
            price_lowest_used=Decimal(price_used) / 100 if price_used else None,
            bsr_primary=bsr_primary,
            bsr_category_name=bsr_category,
            stock_status=self._determine_stock_status(product),
            fulfillment=self._determine_fulfillment(product),
            seller_count=seller_count,
            rating_average=rating_avg,
            review_count=review_count,
            rating_count=stats.get("current", {}).get("COUNT_REVIEWS") if stats else None,
            data_source="keepa",
        )

        # Create metadata
        metadata = ProductMetadata(
            asin=asin,
            title=product.get("title", "Unknown"),
            brand=product.get("brand"),
            manufacturer=product.get("manufacturer"),
            model_number=product.get("model"),
            category_id=product.get("rootCategory"),
            category_path=[c.get("name") for c in categories] if categories else None,
            main_image_url=f"https://images-na.ssl-images-amazon.com/images/I/{product.get('imagesCSV', '').split(',')[0]}" if product.get("imagesCSV") else None,
            is_amazon_choice=product.get("isAmazonChoice", False),
            is_best_seller=product.get("isBestSeller", False),
        )

        # Parse history if available
        price_history = None
        bsr_history = None

        if csv:
            # Use BuyBox price history if available, else Amazon, else New
            if len(csv) > self.PRICE_BUYBOX_NEW and csv[self.PRICE_BUYBOX_NEW]:
                price_history = self._parse_price_history(csv[self.PRICE_BUYBOX_NEW], self.PRICE_BUYBOX_NEW)
            elif len(csv) > self.PRICE_AMAZON and csv[self.PRICE_AMAZON]:
                price_history = self._parse_price_history(csv[self.PRICE_AMAZON], self.PRICE_AMAZON)
            elif len(csv) > self.PRICE_NEW and csv[self.PRICE_NEW]:
                price_history = self._parse_price_history(csv[self.PRICE_NEW], self.PRICE_NEW)

            # BSR history
            if len(csv) > self.PRICE_SALES_RANK and csv[self.PRICE_SALES_RANK]:
                bsr_history = self._parse_bsr_history(csv[self.PRICE_SALES_RANK], bsr_category)

        return ProductData(
            asin=asin,
            metadata=metadata,
            current_snapshot=snapshot,
            price_history=price_history,
            bsr_history=bsr_history,
            fetch_timestamp=datetime.utcnow(),
        )

    def get_tokens_left(self) -> int:
        """Get remaining tokens."""
        with self._rate_limit_lock:
            self._rate_limit._refill_tokens()
            return self._rate_limit.tokens_left

    def get_stats(self) -> Dict[str, Any]:
        """Get client statistics."""
        return {
            **self._stats,
            "tokens_remaining": self.get_tokens_left(),
        }

    def get_category_asins(
        self,
        category_node_id: int,
        include_children: bool = True,
        max_results: Optional[int] = None,
    ) -> List[str]:
        """
        Get all ASINs in a category.

        Args:
            category_node_id: Amazon browse node ID
            include_children: Include child categories
            max_results: Maximum ASINs to return (None = all)

        Returns:
            List of ASIN strings

        Note:
            This operation costs approximately 1 token per 1,000 ASINs.
        """
        logger.info(f"Fetching ASINs for category {category_node_id}")

        def _fetch():
            return self.api.category_lookup(
                category_node_id,
                domain=self.domain_id,
                include_child_categories=include_children,
            )

        try:
            # Estimate tokens needed (conservative)
            self._wait_for_rate_limit(5)

            result = self._retry_with_backoff(_fetch)

            if result is None:
                logger.warning(f"No data returned for category {category_node_id}")
                return []

            # Extract ASINs from result
            asins = []
            if isinstance(result, dict):
                # Category lookup returns dict with category info
                asin_list = result.get("asinList", [])
                if asin_list:
                    asins = asin_list
            elif isinstance(result, list):
                asins = result

            # Track tokens consumed (estimate)
            tokens_consumed = max(1, len(asins) // 1000)
            self._consume_tokens(tokens_consumed)

            # Apply limit if specified
            if max_results and len(asins) > max_results:
                asins = asins[:max_results]

            logger.info(f"Found {len(asins)} ASINs in category {category_node_id}")
            return asins

        except Exception as e:
            logger.error(f"Failed to fetch category ASINs: {e}")
            raise KeepaAPIError(f"Category lookup failed: {e}")

    def get_product_data(
        self,
        asins: List[str],
        include_history: bool = True,
        history_days: int = 90,
        include_buybox: bool = True,
        include_offers: bool = False,
    ) -> List[ProductData]:
        """
        Get detailed product data for a list of ASINs.

        Args:
            asins: List of ASIN strings (max 100 per request)
            include_history: Include price/BSR history
            history_days: Days of history to retrieve (7-365)
            include_buybox: Include BuyBox statistics
            include_offers: Include seller offers (more tokens)

        Returns:
            List of ProductData instances

        Note:
            Token cost varies:
            - Basic product: ~1 token
            - With history: ~2 tokens
            - With offers: ~3 tokens
        """
        if not asins:
            return []

        # Keepa limit is 100 ASINs per request
        if len(asins) > 100:
            logger.warning(f"ASIN list exceeds 100, processing in batches")
            results = []
            for i in range(0, len(asins), 100):
                batch = asins[i:i + 100]
                batch_results = self.get_product_data(
                    batch,
                    include_history=include_history,
                    history_days=history_days,
                    include_buybox=include_buybox,
                    include_offers=include_offers,
                )
                results.extend(batch_results)
            return results

        logger.info(f"Fetching product data for {len(asins)} ASINs")

        # Estimate token cost
        tokens_per_asin = 1
        if include_history:
            tokens_per_asin += 1
        if include_offers:
            tokens_per_asin += 1

        estimated_tokens = len(asins) * tokens_per_asin

        def _fetch():
            return self.api.query(
                asins,
                domain=self.domain_id,
                history=include_history,
                days=history_days if include_history else 0,
                buybox=include_buybox,
                offers=50 if include_offers else 0,  # Get up to 50 offers
                rating=True,
                stats=30,  # Get 30-day stats
            )

        try:
            self._wait_for_rate_limit(estimated_tokens)

            products_raw = self._retry_with_backoff(_fetch)

            if products_raw is None:
                logger.warning("No product data returned")
                return []

            # Track actual token consumption from API response
            if hasattr(self.api, 'tokens_left'):
                with self._rate_limit_lock:
                    self._rate_limit.tokens_left = self.api.tokens_left

            self._consume_tokens(estimated_tokens)

            # Transform to our data models
            results = []
            for product_raw in products_raw:
                if product_raw is None:
                    continue
                try:
                    product = self._transform_product(product_raw)
                    results.append(product)
                except Exception as e:
                    asin = product_raw.get("asin", "unknown")
                    logger.warning(f"Failed to transform product {asin}: {e}")
                    continue

            logger.info(f"Successfully processed {len(results)}/{len(asins)} products")
            return results

        except Exception as e:
            logger.error(f"Failed to fetch product data: {e}")
            raise KeepaAPIError(f"Product query failed: {e}")

    def get_buybox_history(
        self,
        asins: List[str],
        history_days: int = 90,
    ) -> Dict[str, List[BuyBoxHistory]]:
        """
        Get BuyBox ownership history for ASINs.

        Args:
            asins: List of ASIN strings
            history_days: Days of history

        Returns:
            Dictionary mapping ASIN to list of BuyBoxHistory
        """
        if not asins:
            return {}

        logger.info(f"Fetching BuyBox history for {len(asins)} ASINs")

        # Use the product query with buybox enabled
        products = self.get_product_data(
            asins,
            include_history=True,
            history_days=history_days,
            include_buybox=True,
            include_offers=False,
        )

        results = {}
        for product in products:
            # BuyBox history is in the price history with seller info
            # For detailed BuyBox, we'd need offers data
            results[product.asin] = product.buybox_history or []

        return results

    def search_products(
        self,
        keywords: str,
        category_node_id: Optional[int] = None,
        min_price: Optional[int] = None,
        max_price: Optional[int] = None,
        min_reviews: Optional[int] = None,
        min_rating: Optional[int] = None,
        sort_by: str = "current_SALES",
        max_results: int = 1000,
    ) -> List[str]:
        """
        Search for products matching criteria.

        Args:
            keywords: Search keywords
            category_node_id: Limit to category
            min_price: Minimum price in cents
            max_price: Maximum price in cents
            min_reviews: Minimum review count
            min_rating: Minimum rating (10-50, representing 1.0-5.0)
            sort_by: Sort field
            max_results: Maximum results

        Returns:
            List of matching ASINs
        """
        logger.info(f"Searching products: '{keywords}'")

        def _search():
            return self.api.product_finder(
                domain=self.domain_id,
                title=keywords,
                current_SALES_min=1 if category_node_id else None,
                current_SALES_max=max_results * 10,  # BSR filter
                root_category=category_node_id,
                current_AMAZON_min=min_price,
                current_AMAZON_max=max_price,
                current_COUNT_REVIEWS_min=min_reviews,
                current_RATING_min=min_rating,
                sort=[sort_by, "asc"],
                productType=[0],  # Standard products
            )

        try:
            self._wait_for_rate_limit(10)

            results = self._retry_with_backoff(_search)
            self._consume_tokens(10)

            if results is None:
                return []

            asins = results[:max_results] if len(results) > max_results else results
            logger.info(f"Search returned {len(asins)} ASINs")
            return asins

        except Exception as e:
            logger.error(f"Product search failed: {e}")
            raise KeepaAPIError(f"Search failed: {e}")

    def get_best_sellers(
        self,
        category_node_id: int,
        top_n: int = 100,
    ) -> List[str]:
        """
        Get best sellers in a category.

        Args:
            category_node_id: Amazon category node ID
            top_n: Number of top sellers to return

        Returns:
            List of ASINs sorted by BSR
        """
        logger.info(f"Fetching top {top_n} sellers in category {category_node_id}")

        def _fetch():
            return self.api.best_sellers_query(
                category=category_node_id,
                domain=self.domain_id,
            )

        try:
            self._wait_for_rate_limit(5)

            results = self._retry_with_backoff(_fetch)
            self._consume_tokens(5)

            if results is None:
                return []

            # Sort by BSR and return top N
            asins = results[:top_n]
            logger.info(f"Found {len(asins)} best sellers")
            return asins

        except Exception as e:
            logger.error(f"Best sellers query failed: {e}")
            raise KeepaAPIError(f"Best sellers query failed: {e}")

    def health_check(self) -> Dict[str, Any]:
        """
        Check API health and token status.

        Returns:
            Health status dictionary
        """
        try:
            # Simple token check
            tokens = self.get_tokens_left()

            return {
                "status": "healthy",
                "tokens_remaining": tokens,
                "tokens_per_minute": self._rate_limit.tokens_per_minute,
                "stats": self.get_stats(),
            }

        except Exception as e:
            return {
                "status": "unhealthy",
                "error": str(e),
            }
