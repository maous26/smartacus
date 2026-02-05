"""
Smartacus Data Models
=====================

Dataclasses representing the core data structures for Keepa data transformation.
These models serve as the intermediate representation between Keepa API responses
and our PostgreSQL database schema.

Models:
    - ProductSnapshot: Point-in-time product data (price, BSR, stock, ratings)
    - PriceHistory: Historical price data points
    - BSRHistory: Historical Best Seller Rank data points
    - SellerInfo: Seller/BuyBox information
    - ProductData: Complete product data container
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, List, Dict, Any


class StockStatus(Enum):
    """Product availability status."""
    IN_STOCK = "in_stock"
    LOW_STOCK = "low_stock"
    OUT_OF_STOCK = "out_of_stock"
    BACK_ORDERED = "back_ordered"
    UNKNOWN = "unknown"


class FulfillmentType(Enum):
    """Fulfillment method."""
    FBA = "fba"           # Fulfilled by Amazon
    FBM = "fbm"           # Fulfilled by Merchant
    AMAZON = "amazon"     # Sold and shipped by Amazon
    UNKNOWN = "unknown"


@dataclass
class PriceHistory:
    """
    Historical price data point.

    Keepa stores prices in cents, we convert to dollars.
    Time is stored as Keepa minutes (minutes since 2011-01-01).
    """
    timestamp: datetime
    price_cents: int
    price_usd: Decimal = field(init=False)
    is_deal: bool = False
    deal_type: Optional[str] = None  # Lightning Deal, Deal of the Day, etc.

    def __post_init__(self):
        """Convert cents to USD decimal."""
        self.price_usd = Decimal(self.price_cents) / 100

    @classmethod
    def from_keepa_minutes(cls, keepa_minutes: int, price_cents: int, **kwargs) -> "PriceHistory":
        """
        Create from Keepa timestamp format.

        Keepa uses minutes since 2011-01-01 00:00:00 UTC.

        Args:
            keepa_minutes: Keepa timestamp (minutes since epoch)
            price_cents: Price in cents

        Returns:
            PriceHistory instance
        """
        # Keepa epoch: January 1, 2011 00:00:00 UTC
        keepa_epoch = datetime(2011, 1, 1, 0, 0, 0)
        from datetime import timedelta
        timestamp = keepa_epoch + timedelta(minutes=keepa_minutes)
        return cls(timestamp=timestamp, price_cents=price_cents, **kwargs)


@dataclass
class BSRHistory:
    """
    Historical Best Seller Rank data point.

    BSR indicates sales velocity - lower is better.
    """
    timestamp: datetime
    bsr: int
    category_name: Optional[str] = None
    category_id: Optional[int] = None

    @classmethod
    def from_keepa_minutes(cls, keepa_minutes: int, bsr: int, **kwargs) -> "BSRHistory":
        """
        Create from Keepa timestamp format.

        Args:
            keepa_minutes: Keepa timestamp
            bsr: Best Seller Rank value

        Returns:
            BSRHistory instance
        """
        keepa_epoch = datetime(2011, 1, 1, 0, 0, 0)
        from datetime import timedelta
        timestamp = keepa_epoch + timedelta(minutes=keepa_minutes)
        return cls(timestamp=timestamp, bsr=bsr, **kwargs)


@dataclass
class SellerInfo:
    """
    Seller/BuyBox information.

    Tracks who owns the BuyBox and seller details.
    """
    seller_id: str
    seller_name: Optional[str] = None
    is_fba: bool = False
    is_amazon: bool = False
    price_cents: Optional[int] = None
    price_usd: Optional[Decimal] = field(init=False)
    condition: str = "new"  # new, used, refurbished, collectible
    feedback_rating: Optional[float] = None
    feedback_count: Optional[int] = None
    ships_from_country: Optional[str] = None

    def __post_init__(self):
        """Convert price to USD."""
        if self.price_cents is not None:
            self.price_usd = Decimal(self.price_cents) / 100
        else:
            self.price_usd = None


@dataclass
class BuyBoxHistory:
    """BuyBox ownership history point."""
    timestamp: datetime
    seller_id: Optional[str] = None
    is_amazon: bool = False
    is_fba: bool = False
    price_cents: Optional[int] = None

    @property
    def price_usd(self) -> Optional[Decimal]:
        """Convert price to USD."""
        if self.price_cents is not None:
            return Decimal(self.price_cents) / 100
        return None


@dataclass
class ProductSnapshot:
    """
    Point-in-time product data snapshot.

    Represents the current state of a product at capture time.
    Maps directly to the asin_snapshots table.
    """
    # Identification
    asin: str
    captured_at: datetime = field(default_factory=datetime.utcnow)

    # Pricing
    price_current: Optional[Decimal] = None
    price_original: Optional[Decimal] = None  # List price
    price_lowest_new: Optional[Decimal] = None
    price_lowest_used: Optional[Decimal] = None
    price_currency: str = "USD"
    coupon_discount_percent: Optional[Decimal] = None
    coupon_discount_amount: Optional[Decimal] = None
    deal_type: Optional[str] = None

    # Sales Rank
    bsr_primary: Optional[int] = None
    bsr_category_name: Optional[str] = None
    bsr_subcategory: Optional[int] = None
    bsr_subcategory_name: Optional[str] = None

    # Availability
    stock_status: StockStatus = StockStatus.UNKNOWN
    stock_quantity: Optional[int] = None
    fulfillment: FulfillmentType = FulfillmentType.UNKNOWN
    seller_count: Optional[int] = None

    # Ratings and Reviews
    rating_average: Optional[Decimal] = None
    rating_count: Optional[int] = None
    review_count: Optional[int] = None
    rating_distribution: Optional[Dict[int, Decimal]] = None  # {5: 0.72, 4: 0.15, ...}

    # Metadata
    data_source: str = "keepa"
    scrape_session_id: Optional[str] = None
    scrape_duration_ms: Optional[int] = None

    def to_db_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for database insertion.

        Returns:
            Dictionary matching asin_snapshots table columns
        """
        result = {
            "asin": self.asin,
            "captured_at": self.captured_at,
            "price_current": float(self.price_current) if self.price_current else None,
            "price_original": float(self.price_original) if self.price_original else None,
            "price_lowest_new": float(self.price_lowest_new) if self.price_lowest_new else None,
            "price_lowest_used": float(self.price_lowest_used) if self.price_lowest_used else None,
            "price_currency": self.price_currency,
            "coupon_discount_percent": float(self.coupon_discount_percent) if self.coupon_discount_percent else None,
            "coupon_discount_amount": float(self.coupon_discount_amount) if self.coupon_discount_amount else None,
            "deal_type": self.deal_type,
            "bsr_primary": self.bsr_primary,
            "bsr_category_name": self.bsr_category_name,
            "bsr_subcategory": self.bsr_subcategory,
            "bsr_subcategory_name": self.bsr_subcategory_name,
            "stock_status": self.stock_status.value,
            "stock_quantity": self.stock_quantity,
            "fulfillment": self.fulfillment.value,
            "seller_count": self.seller_count,
            "rating_average": float(self.rating_average) if self.rating_average else None,
            "rating_count": self.rating_count,
            "review_count": self.review_count,
            "data_source": self.data_source,
            "scrape_session_id": self.scrape_session_id,
            "scrape_duration_ms": self.scrape_duration_ms,
        }

        # Add rating distribution if available
        if self.rating_distribution:
            result["rating_5_star_percent"] = float(self.rating_distribution.get(5, 0))
            result["rating_4_star_percent"] = float(self.rating_distribution.get(4, 0))
            result["rating_3_star_percent"] = float(self.rating_distribution.get(3, 0))
            result["rating_2_star_percent"] = float(self.rating_distribution.get(2, 0))
            result["rating_1_star_percent"] = float(self.rating_distribution.get(1, 0))

        return result


@dataclass
class ProductMetadata:
    """
    Static/semi-static product information.

    Maps to the asins table for master product catalog.
    """
    asin: str

    # Product identification
    title: str
    brand: Optional[str] = None
    manufacturer: Optional[str] = None
    model_number: Optional[str] = None

    # Categorization
    category_id: Optional[int] = None
    category_path: Optional[List[str]] = None
    subcategory: Optional[str] = None

    # Product characteristics
    color: Optional[str] = None
    size: Optional[str] = None
    material: Optional[str] = None
    weight_grams: Optional[int] = None
    dimensions_cm: Optional[Dict[str, float]] = None  # {"length": x, "width": y, "height": z}

    # Listing details
    main_image_url: Optional[str] = None
    bullet_points: Optional[List[str]] = None
    description: Optional[str] = None

    # Status flags
    is_amazon_choice: bool = False
    is_best_seller: bool = False

    # Tracking metadata
    first_seen_at: Optional[datetime] = None
    last_updated_at: Optional[datetime] = None
    is_active: bool = True
    tracking_priority: int = 5

    def to_db_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary for database insertion/update.

        Returns:
            Dictionary matching asins table columns
        """
        import json
        return {
            "asin": self.asin,
            "title": self.title,
            "brand": self.brand,
            "manufacturer": self.manufacturer,
            "model_number": self.model_number,
            "category_id": self.category_id,
            "category_path": self.category_path,
            "subcategory": self.subcategory,
            "color": self.color,
            "size": self.size,
            "material": self.material,
            "weight_grams": self.weight_grams,
            "dimensions_cm": json.dumps(self.dimensions_cm) if self.dimensions_cm else None,
            "main_image_url": self.main_image_url,
            "bullet_points": self.bullet_points,
            "description": self.description,
            "is_amazon_choice": self.is_amazon_choice,
            "is_best_seller": self.is_best_seller,
            "first_seen_at": self.first_seen_at or datetime.utcnow(),
            "last_updated_at": datetime.utcnow(),
            "is_active": self.is_active,
            "tracking_priority": self.tracking_priority,
        }


@dataclass
class ProductData:
    """
    Complete product data container.

    Aggregates all product information from Keepa API response.
    """
    # Core data
    asin: str
    metadata: ProductMetadata
    current_snapshot: ProductSnapshot

    # Historical data (optional, may not always be requested)
    price_history: Optional[List[PriceHistory]] = None
    bsr_history: Optional[List[BSRHistory]] = None
    buybox_history: Optional[List[BuyBoxHistory]] = None

    # Seller information
    buybox_seller: Optional[SellerInfo] = None
    other_sellers: Optional[List[SellerInfo]] = None

    # Fetch metadata
    fetch_timestamp: datetime = field(default_factory=datetime.utcnow)
    tokens_consumed: int = 0

    def has_price_history(self) -> bool:
        """Check if price history data is available."""
        return self.price_history is not None and len(self.price_history) > 0

    def has_bsr_history(self) -> bool:
        """Check if BSR history data is available."""
        return self.bsr_history is not None and len(self.bsr_history) > 0

    def get_price_trend_7d(self) -> Optional[float]:
        """
        Calculate 7-day price trend as percentage change.

        Returns:
            Percentage change (positive = increase, negative = decrease)
        """
        if not self.has_price_history():
            return None

        from datetime import timedelta
        cutoff = datetime.utcnow() - timedelta(days=7)
        recent_prices = [p for p in self.price_history if p.timestamp >= cutoff]

        if len(recent_prices) < 2:
            return None

        # Sort by timestamp
        recent_prices.sort(key=lambda p: p.timestamp)
        oldest = recent_prices[0].price_usd
        newest = recent_prices[-1].price_usd

        if oldest == 0:
            return None

        return float((newest - oldest) / oldest * 100)

    def get_bsr_trend_7d(self) -> Optional[float]:
        """
        Calculate 7-day BSR trend as percentage change.

        Note: Negative change = improvement (lower BSR is better)

        Returns:
            Percentage change
        """
        if not self.has_bsr_history():
            return None

        from datetime import timedelta
        cutoff = datetime.utcnow() - timedelta(days=7)
        recent_bsr = [b for b in self.bsr_history if b.timestamp >= cutoff]

        if len(recent_bsr) < 2:
            return None

        recent_bsr.sort(key=lambda b: b.timestamp)
        oldest = recent_bsr[0].bsr
        newest = recent_bsr[-1].bsr

        if oldest == 0:
            return None

        return float((newest - oldest) / oldest * 100)


@dataclass
class CategoryInfo:
    """Amazon category information."""
    category_id: int
    name: str
    path: List[str] = field(default_factory=list)
    product_count: Optional[int] = None
    parent_id: Optional[int] = None


@dataclass
class IngestionResult:
    """Result of an ingestion batch operation."""
    batch_id: str
    started_at: datetime
    completed_at: Optional[datetime] = None

    # Counts
    asins_requested: int = 0
    asins_processed: int = 0
    asins_inserted: int = 0
    asins_updated: int = 0
    asins_skipped: int = 0
    asins_failed: int = 0

    # Token usage
    tokens_consumed: int = 0
    tokens_remaining: Optional[int] = None

    # Errors
    errors: List[Dict[str, Any]] = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        """Calculate success rate as percentage."""
        if self.asins_requested == 0:
            return 0.0
        return (self.asins_processed - self.asins_failed) / self.asins_requested * 100

    @property
    def duration_seconds(self) -> Optional[float]:
        """Calculate duration in seconds."""
        if self.completed_at is None:
            return None
        return (self.completed_at - self.started_at).total_seconds()

    def add_error(self, asin: str, error_type: str, message: str):
        """Record an error."""
        self.errors.append({
            "asin": asin,
            "error_type": error_type,
            "message": message,
            "timestamp": datetime.utcnow().isoformat(),
        })
        self.asins_failed += 1
