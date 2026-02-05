"""
Smartacus Event Models
======================

Dataclasses representing event structures for the event detection system.
These models serve as the interface between raw snapshot data and the
scoring/aggregation systems.

Models:
    - PriceEvent: Significant price change detection
    - BSREvent: Best Seller Rank movement detection
    - StockEvent: Stock status transition detection
    - SellerChurnMetrics: Seller turnover analysis over 90 days
    - BuyboxMetrics: Buy box stability/rotation analysis
"""

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, List, Dict, Any


class EventSeverity(Enum):
    """Event importance classification."""
    LOW = "low"           # Minor change, informational (5-10% price change)
    MEDIUM = "medium"     # Notable change, worth monitoring (10-20%)
    HIGH = "high"         # Significant change, potential opportunity (20-30%)
    CRITICAL = "critical" # Major event, immediate attention (>30%)


class MovementDirection(Enum):
    """Direction of price/BSR movements."""
    UP = "up"
    DOWN = "down"
    STABLE = "stable"


class StockTransitionType(Enum):
    """Type of stock status transition."""
    STOCKOUT = "stockout"           # in_stock/low_stock -> out_of_stock
    RESTOCK = "restock"             # out_of_stock -> in_stock
    LOW_STOCK_ALERT = "low_stock_alert"  # -> low_stock
    STATUS_CHANGE = "status_change"  # Other transitions


@dataclass
class PriceEvent:
    """
    Represents a significant price change event.

    DETECTION CRITERIA:
    - Variation > 5% triggers event creation
    - Severity based on magnitude:
        * LOW: 5-10%
        * MEDIUM: 10-20%
        * HIGH: 20-30%
        * CRITICAL: >30%

    Attributes:
        asin: Amazon Standard Identification Number
        detected_at: Timestamp of detection
        price_before: Price before the change
        price_after: Price after the change
        price_change: Absolute price difference
        price_change_percent: Percentage change
        direction: UP (price increase) or DOWN (price decrease)
        severity: Event importance classification
        is_deal: Whether this is part of a deal/promotion
        deal_type: Type of deal (Lightning Deal, etc.) if applicable
        is_coupon: Whether a coupon is involved
        snapshot_before_at: Timestamp of previous snapshot
        snapshot_after_at: Timestamp of current snapshot
    """
    asin: str
    detected_at: datetime
    price_before: Decimal
    price_after: Decimal
    price_change: Decimal
    price_change_percent: float
    direction: MovementDirection
    severity: EventSeverity
    is_deal: bool = False
    deal_type: Optional[str] = None
    is_coupon: bool = False
    snapshot_before_at: Optional[datetime] = None
    snapshot_after_at: Optional[datetime] = None

    def to_db_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database insertion."""
        return {
            "asin": self.asin,
            "detected_at": self.detected_at,
            "price_before": float(self.price_before),
            "price_after": float(self.price_after),
            "price_change": float(self.price_change),
            "price_change_percent": self.price_change_percent,
            "direction": self.direction.value,
            "severity": self.severity.value,
            "is_deal": self.is_deal,
            "deal_type": self.deal_type,
            "is_coupon": self.is_coupon,
            "snapshot_before_at": self.snapshot_before_at,
            "snapshot_after_at": self.snapshot_after_at,
        }

    @classmethod
    def from_db_row(cls, row: Dict[str, Any]) -> "PriceEvent":
        """Create PriceEvent from database row."""
        return cls(
            asin=row["asin"],
            detected_at=row["detected_at"],
            price_before=Decimal(str(row["price_before"])),
            price_after=Decimal(str(row["price_after"])),
            price_change=Decimal(str(row["price_change"])),
            price_change_percent=float(row["price_change_percent"]),
            direction=MovementDirection(row["direction"]),
            severity=EventSeverity(row["severity"]),
            is_deal=row.get("is_deal", False),
            deal_type=row.get("deal_type"),
            is_coupon=row.get("is_coupon", False),
            snapshot_before_at=row.get("snapshot_before_at"),
            snapshot_after_at=row.get("snapshot_after_at"),
        )


@dataclass
class BSREvent:
    """
    Represents a significant BSR (Best Seller Rank) movement event.

    DETECTION CRITERIA:
    - Variation > 20% OR > 10,000 positions triggers event
    - Direction interpretation:
        * IMPROVEMENT (direction=UP): BSR number decreases (better rank)
        * DEGRADATION (direction=DOWN): BSR number increases (worse rank)

    Note: Lower BSR = better sales rank, so "improvement" means BSR going DOWN

    Attributes:
        asin: Amazon Standard Identification Number
        detected_at: Timestamp of detection
        bsr_before: BSR before the change
        bsr_after: BSR after the change
        bsr_change: Absolute BSR difference
        bsr_change_percent: Percentage change
        direction: UP (improving/lower BSR) or DOWN (worsening/higher BSR)
        severity: Event importance classification
        category_name: Category for this BSR
        change_velocity: Positions changed per hour
        is_sustained: Whether change held for multiple snapshots
        likely_cause: Detected cause (price_drop, promotion, etc.)
        snapshot_before_at: Timestamp of previous snapshot
        snapshot_after_at: Timestamp of current snapshot
    """
    asin: str
    detected_at: datetime
    bsr_before: int
    bsr_after: int
    bsr_change: int
    bsr_change_percent: float
    direction: MovementDirection  # UP = improving (lower BSR), DOWN = worsening
    severity: EventSeverity
    category_name: Optional[str] = None
    change_velocity: Optional[float] = None
    is_sustained: bool = False
    likely_cause: Optional[str] = None
    snapshot_before_at: Optional[datetime] = None
    snapshot_after_at: Optional[datetime] = None

    def to_db_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database insertion."""
        return {
            "asin": self.asin,
            "detected_at": self.detected_at,
            "bsr_before": self.bsr_before,
            "bsr_after": self.bsr_after,
            "bsr_change": self.bsr_change,
            "bsr_change_percent": self.bsr_change_percent,
            "direction": self.direction.value,
            "severity": self.severity.value,
            "category_name": self.category_name,
            "change_velocity": self.change_velocity,
            "is_sustained": self.is_sustained,
            "likely_cause": self.likely_cause,
            "snapshot_before_at": self.snapshot_before_at,
            "snapshot_after_at": self.snapshot_after_at,
        }

    @classmethod
    def from_db_row(cls, row: Dict[str, Any]) -> "BSREvent":
        """Create BSREvent from database row."""
        return cls(
            asin=row["asin"],
            detected_at=row["detected_at"],
            bsr_before=row["bsr_before"],
            bsr_after=row["bsr_after"],
            bsr_change=row["bsr_change"],
            bsr_change_percent=float(row["bsr_change_percent"]),
            direction=MovementDirection(row["direction"]),
            severity=EventSeverity(row["severity"]),
            category_name=row.get("category_name"),
            change_velocity=row.get("change_velocity"),
            is_sustained=row.get("is_sustained", False),
            likely_cause=row.get("likely_cause"),
            snapshot_before_at=row.get("snapshot_before_at"),
            snapshot_after_at=row.get("snapshot_after_at"),
        )


@dataclass
class StockEvent:
    """
    Represents a stock status transition event.

    DETECTION CRITERIA:
    - Transition in_stock/low_stock -> out_of_stock = STOCKOUT (severity: HIGH)
    - Transition out_of_stock -> in_stock/low_stock = RESTOCK (severity: MEDIUM)
    - Transition to low_stock = LOW_STOCK_ALERT (severity: LOW)

    Stockouts are critical signals of:
    - High demand exceeding supply
    - Competitor vulnerability
    - Market opportunity

    Attributes:
        asin: Amazon Standard Identification Number
        detected_at: Timestamp of detection
        status_before: Stock status before transition
        status_after: Stock status after transition
        quantity_before: Stock quantity before (if known)
        quantity_after: Stock quantity after (if known)
        event_type: Classification of the transition
        severity: Event importance classification
        stockout_started_at: When stockout began (for tracking duration)
        stockout_duration_hours: How long product was out
        seller_id: Seller identifier if known
        seller_name: Seller name if known
        is_primary_seller: Whether this is the main/buybox seller
        snapshot_before_at: Timestamp of previous snapshot
        snapshot_after_at: Timestamp of current snapshot
    """
    asin: str
    detected_at: datetime
    status_before: str
    status_after: str
    event_type: StockTransitionType
    severity: EventSeverity
    quantity_before: Optional[int] = None
    quantity_after: Optional[int] = None
    stockout_started_at: Optional[datetime] = None
    stockout_duration_hours: Optional[int] = None
    seller_id: Optional[str] = None
    seller_name: Optional[str] = None
    is_primary_seller: bool = True
    snapshot_before_at: Optional[datetime] = None
    snapshot_after_at: Optional[datetime] = None

    def to_db_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for database insertion."""
        return {
            "asin": self.asin,
            "detected_at": self.detected_at,
            "status_before": self.status_before,
            "status_after": self.status_after,
            "quantity_before": self.quantity_before,
            "quantity_after": self.quantity_after,
            "event_type": self.event_type.value,
            "severity": self.severity.value,
            "stockout_started_at": self.stockout_started_at,
            "stockout_duration_hours": self.stockout_duration_hours,
            "seller_id": self.seller_id,
            "seller_name": self.seller_name,
            "is_primary_seller": self.is_primary_seller,
            "snapshot_before_at": self.snapshot_before_at,
            "snapshot_after_at": self.snapshot_after_at,
        }

    @classmethod
    def from_db_row(cls, row: Dict[str, Any]) -> "StockEvent":
        """Create StockEvent from database row."""
        return cls(
            asin=row["asin"],
            detected_at=row["detected_at"],
            status_before=row["status_before"],
            status_after=row["status_after"],
            event_type=StockTransitionType(row["event_type"]),
            severity=EventSeverity(row["severity"]),
            quantity_before=row.get("quantity_before"),
            quantity_after=row.get("quantity_after"),
            stockout_started_at=row.get("stockout_started_at"),
            stockout_duration_hours=row.get("stockout_duration_hours"),
            seller_id=row.get("seller_id"),
            seller_name=row.get("seller_name"),
            is_primary_seller=row.get("is_primary_seller", True),
            snapshot_before_at=row.get("snapshot_before_at"),
            snapshot_after_at=row.get("snapshot_after_at"),
        )


@dataclass
class SellerChurnMetrics:
    """
    Metrics for seller turnover analysis over a 90-day period.

    High seller churn indicates:
    - Market difficulty/competition pressure
    - Potential opportunity if established sellers are leaving
    - Price war fatigue

    Attributes:
        asin: Amazon Standard Identification Number
        analysis_period_start: Start of 90-day analysis window
        analysis_period_end: End of 90-day analysis window
        seller_churn_rate: Percentage of sellers that changed (entered/exited)
        sellers_entered: Number of new sellers
        sellers_exited: Number of departed sellers
        sellers_at_start: Total sellers at period start
        sellers_at_end: Total sellers at period end
        net_seller_change: Net change in seller count
        dominant_seller_retained: Whether the top seller remained throughout
        seller_ids_entered: List of new seller IDs (if tracked)
        seller_ids_exited: List of departed seller IDs (if tracked)
    """
    asin: str
    analysis_period_start: datetime
    analysis_period_end: datetime
    seller_churn_rate: float
    sellers_entered: int
    sellers_exited: int
    sellers_at_start: int
    sellers_at_end: int
    net_seller_change: int = field(init=False)
    dominant_seller_retained: bool = True
    seller_ids_entered: List[str] = field(default_factory=list)
    seller_ids_exited: List[str] = field(default_factory=list)

    def __post_init__(self):
        """Calculate derived fields."""
        self.net_seller_change = self.sellers_at_end - self.sellers_at_start

    @property
    def is_high_churn(self) -> bool:
        """Check if churn rate is considered high (>30%)."""
        return self.seller_churn_rate > 0.30

    @property
    def total_movement(self) -> int:
        """Total seller movement (entries + exits)."""
        return self.sellers_entered + self.sellers_exited

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage/API."""
        return {
            "asin": self.asin,
            "analysis_period_start": self.analysis_period_start.isoformat(),
            "analysis_period_end": self.analysis_period_end.isoformat(),
            "seller_churn_rate": self.seller_churn_rate,
            "sellers_entered": self.sellers_entered,
            "sellers_exited": self.sellers_exited,
            "sellers_at_start": self.sellers_at_start,
            "sellers_at_end": self.sellers_at_end,
            "net_seller_change": self.net_seller_change,
            "dominant_seller_retained": self.dominant_seller_retained,
            "is_high_churn": self.is_high_churn,
            "total_movement": self.total_movement,
        }


@dataclass
class BuyboxMetrics:
    """
    Metrics for Buy Box stability/rotation analysis over a 30-day period.

    Buy Box rotation indicates:
    - Competitive pricing pressure
    - Opportunity to capture Buy Box with right strategy
    - Market fragmentation

    High rotation (>40%) = competitive market with opportunities
    Low rotation (<10%) = dominant seller, harder to penetrate

    Attributes:
        asin: Amazon Standard Identification Number
        analysis_period_start: Start of 30-day analysis window
        analysis_period_end: End of 30-day analysis window
        buybox_rotation_rate: Percentage of time Buy Box changed hands
        dominant_seller_id: Seller with most Buy Box ownership
        dominant_seller_name: Name of dominant seller
        dominant_seller_share: Percentage of time dominant seller held Buy Box
        unique_sellers_count: Number of different sellers that held Buy Box
        amazon_share: Percentage of time Amazon held Buy Box
        fba_share: Percentage of time FBA sellers held Buy Box
        price_at_rotation: Average price when Buy Box rotated
        rotation_triggers: Detected causes of rotation (price, stock, etc.)
    """
    asin: str
    analysis_period_start: datetime
    analysis_period_end: datetime
    buybox_rotation_rate: float
    dominant_seller_id: Optional[str] = None
    dominant_seller_name: Optional[str] = None
    dominant_seller_share: float = 0.0
    unique_sellers_count: int = 0
    amazon_share: float = 0.0
    fba_share: float = 0.0
    price_at_rotation: Optional[Decimal] = None
    rotation_triggers: List[str] = field(default_factory=list)

    @property
    def is_highly_competitive(self) -> bool:
        """Check if market is highly competitive (rotation >40%)."""
        return self.buybox_rotation_rate > 0.40

    @property
    def is_dominated(self) -> bool:
        """Check if market is dominated (dominant share >80%)."""
        return self.dominant_seller_share > 0.80

    @property
    def amazon_presence(self) -> bool:
        """Check if Amazon is a significant competitor."""
        return self.amazon_share > 0.10

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage/API."""
        return {
            "asin": self.asin,
            "analysis_period_start": self.analysis_period_start.isoformat(),
            "analysis_period_end": self.analysis_period_end.isoformat(),
            "buybox_rotation_rate": self.buybox_rotation_rate,
            "dominant_seller_id": self.dominant_seller_id,
            "dominant_seller_name": self.dominant_seller_name,
            "dominant_seller_share": self.dominant_seller_share,
            "unique_sellers_count": self.unique_sellers_count,
            "amazon_share": self.amazon_share,
            "fba_share": self.fba_share,
            "price_at_rotation": float(self.price_at_rotation) if self.price_at_rotation else None,
            "rotation_triggers": self.rotation_triggers,
            "is_highly_competitive": self.is_highly_competitive,
            "is_dominated": self.is_dominated,
            "amazon_presence": self.amazon_presence,
        }


@dataclass
class AggregatedEventMetrics:
    """
    Aggregated event metrics for scoring integration.

    This dataclass provides the exact format expected by OpportunityScorer
    for the time_pressure component calculation.

    Attributes:
        asin: Amazon Standard Identification Number
        analysis_date: Date of analysis
        stockout_count_90d: Number of stockout events in last 90 days
        price_trend_30d: Price trend over 30 days (% change)
        seller_churn_90d: Number of seller changes in 90 days
        bsr_acceleration: BSR momentum acceleration (second derivative)
        price_events_count: Total price events detected
        bsr_events_count: Total BSR events detected
        stock_events_count: Total stock events detected
        last_stockout_at: Timestamp of most recent stockout
        last_price_drop_at: Timestamp of most recent price drop
        avg_price_volatility: Average price volatility over period
        bsr_trend_7d: BSR trend over 7 days (% change)
        bsr_trend_30d: BSR trend over 30 days (% change)
    """
    asin: str
    analysis_date: datetime
    stockout_count_90d: int = 0
    price_trend_30d: float = 0.0
    seller_churn_90d: int = 0
    bsr_acceleration: float = 0.0
    price_events_count: int = 0
    bsr_events_count: int = 0
    stock_events_count: int = 0
    last_stockout_at: Optional[datetime] = None
    last_price_drop_at: Optional[datetime] = None
    avg_price_volatility: float = 0.0
    bsr_trend_7d: float = 0.0
    bsr_trend_30d: float = 0.0

    def to_scoring_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary format expected by OpportunityScorer.

        Returns:
            Dictionary with keys matching OpportunityScorer.score_time_pressure()
        """
        return {
            "stockout_count_90d": self.stockout_count_90d,
            "price_trend_30d": self.price_trend_30d,
            "seller_churn_90d": self.seller_churn_90d,
            "bsr_acceleration": self.bsr_acceleration,
        }

    def to_full_dict(self) -> Dict[str, Any]:
        """Convert to full dictionary for storage/API."""
        return {
            "asin": self.asin,
            "analysis_date": self.analysis_date.isoformat(),
            "stockout_count_90d": self.stockout_count_90d,
            "price_trend_30d": self.price_trend_30d,
            "seller_churn_90d": self.seller_churn_90d,
            "bsr_acceleration": self.bsr_acceleration,
            "price_events_count": self.price_events_count,
            "bsr_events_count": self.bsr_events_count,
            "stock_events_count": self.stock_events_count,
            "last_stockout_at": self.last_stockout_at.isoformat() if self.last_stockout_at else None,
            "last_price_drop_at": self.last_price_drop_at.isoformat() if self.last_price_drop_at else None,
            "avg_price_volatility": self.avg_price_volatility,
            "bsr_trend_7d": self.bsr_trend_7d,
            "bsr_trend_30d": self.bsr_trend_30d,
        }


@dataclass
class MarketSignals:
    """
    Market-level signals aggregated from events across a category.

    Provides a bird's-eye view of market conditions for strategic decisions.

    Attributes:
        category_name: Category being analyzed
        analysis_date: Date of analysis
        total_asins_analyzed: Number of ASINs in analysis
        stockouts_total: Total stockout events in category
        stockout_rate: Percentage of ASINs with stockouts
        avg_price_trend: Average price trend across category
        price_drops_count: Number of significant price drops
        price_increases_count: Number of significant price increases
        bsr_improvers_count: ASINs with improving BSR
        bsr_decliners_count: ASINs with declining BSR
        high_churn_asins: ASINs with high seller churn
        competitive_asins: ASINs with high buy box rotation
        opportunity_signals: Summary of detected opportunity signals
    """
    category_name: str
    analysis_date: datetime
    total_asins_analyzed: int
    stockouts_total: int = 0
    stockout_rate: float = 0.0
    avg_price_trend: float = 0.0
    price_drops_count: int = 0
    price_increases_count: int = 0
    bsr_improvers_count: int = 0
    bsr_decliners_count: int = 0
    high_churn_asins: int = 0
    competitive_asins: int = 0
    opportunity_signals: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage/API."""
        return {
            "category_name": self.category_name,
            "analysis_date": self.analysis_date.isoformat(),
            "total_asins_analyzed": self.total_asins_analyzed,
            "stockouts_total": self.stockouts_total,
            "stockout_rate": self.stockout_rate,
            "avg_price_trend": self.avg_price_trend,
            "price_drops_count": self.price_drops_count,
            "price_increases_count": self.price_increases_count,
            "bsr_improvers_count": self.bsr_improvers_count,
            "bsr_decliners_count": self.bsr_decliners_count,
            "high_churn_asins": self.high_churn_asins,
            "competitive_asins": self.competitive_asins,
            "opportunity_signals": self.opportunity_signals,
        }
