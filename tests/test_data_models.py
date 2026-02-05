"""
Tests for Smartacus data models.
"""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal

from src.data.data_models import (
    ProductSnapshot,
    ProductMetadata,
    ProductData,
    PriceHistory,
    BSRHistory,
    SellerInfo,
    StockStatus,
    FulfillmentType,
    IngestionResult,
)


class TestPriceHistory:
    """Tests for PriceHistory model."""

    def test_price_conversion(self):
        """Test price cents to USD conversion."""
        history = PriceHistory(
            timestamp=datetime.utcnow(),
            price_cents=2999,
        )
        assert history.price_usd == Decimal("29.99")

    def test_from_keepa_minutes(self):
        """Test conversion from Keepa timestamp format."""
        # Keepa epoch is 2011-01-01
        # 1 year in minutes = 525600
        keepa_minutes = 525600  # Approximately 2012-01-01

        history = PriceHistory.from_keepa_minutes(
            keepa_minutes=keepa_minutes,
            price_cents=1999,
        )

        assert history.price_usd == Decimal("19.99")
        assert history.timestamp.year == 2012

    def test_deal_flag(self):
        """Test deal flag setting."""
        history = PriceHistory(
            timestamp=datetime.utcnow(),
            price_cents=1500,
            is_deal=True,
            deal_type="Lightning Deal",
        )
        assert history.is_deal is True
        assert history.deal_type == "Lightning Deal"


class TestBSRHistory:
    """Tests for BSRHistory model."""

    def test_basic_creation(self):
        """Test basic BSR history creation."""
        history = BSRHistory(
            timestamp=datetime.utcnow(),
            bsr=5000,
            category_name="Cell Phone Automobile Cradles",
        )
        assert history.bsr == 5000
        assert history.category_name == "Cell Phone Automobile Cradles"

    def test_from_keepa_minutes(self):
        """Test conversion from Keepa timestamp."""
        history = BSRHistory.from_keepa_minutes(
            keepa_minutes=1000000,
            bsr=12500,
            category_name="Test Category",
        )
        assert history.bsr == 12500


class TestSellerInfo:
    """Tests for SellerInfo model."""

    def test_price_conversion(self):
        """Test seller price conversion."""
        seller = SellerInfo(
            seller_id="A1B2C3D4E5",
            seller_name="Test Seller",
            price_cents=2499,
            is_fba=True,
        )
        assert seller.price_usd == Decimal("24.99")
        assert seller.is_fba is True

    def test_amazon_seller(self):
        """Test Amazon as seller."""
        seller = SellerInfo(
            seller_id="ATVPDKIKX0DER",  # Amazon's seller ID
            seller_name="Amazon.com",
            is_amazon=True,
            price_cents=1999,
        )
        assert seller.is_amazon is True


class TestProductSnapshot:
    """Tests for ProductSnapshot model."""

    def test_basic_creation(self):
        """Test basic snapshot creation."""
        snapshot = ProductSnapshot(
            asin="B08XYZ1234",
            price_current=Decimal("29.99"),
            bsr_primary=5000,
            stock_status=StockStatus.IN_STOCK,
            fulfillment=FulfillmentType.FBA,
        )
        assert snapshot.asin == "B08XYZ1234"
        assert snapshot.price_current == Decimal("29.99")
        assert snapshot.stock_status == StockStatus.IN_STOCK

    def test_to_db_dict(self):
        """Test conversion to database dictionary."""
        snapshot = ProductSnapshot(
            asin="B08XYZ1234",
            price_current=Decimal("29.99"),
            price_original=Decimal("39.99"),
            bsr_primary=5000,
            bsr_category_name="Car Phone Mounts",
            stock_status=StockStatus.IN_STOCK,
            fulfillment=FulfillmentType.FBA,
            rating_average=Decimal("4.5"),
            review_count=150,
        )

        db_dict = snapshot.to_db_dict()

        assert db_dict["asin"] == "B08XYZ1234"
        assert db_dict["price_current"] == 29.99
        assert db_dict["bsr_primary"] == 5000
        assert db_dict["stock_status"] == "in_stock"
        assert db_dict["fulfillment"] == "fba"

    def test_rating_distribution(self):
        """Test rating distribution in db dict."""
        snapshot = ProductSnapshot(
            asin="B08XYZ1234",
            rating_distribution={
                5: Decimal("0.72"),
                4: Decimal("0.15"),
                3: Decimal("0.08"),
                2: Decimal("0.03"),
                1: Decimal("0.02"),
            }
        )

        db_dict = snapshot.to_db_dict()

        assert db_dict["rating_5_star_percent"] == 0.72
        assert db_dict["rating_1_star_percent"] == 0.02


class TestProductMetadata:
    """Tests for ProductMetadata model."""

    def test_basic_creation(self):
        """Test basic metadata creation."""
        metadata = ProductMetadata(
            asin="B08XYZ1234",
            title="Car Phone Mount, Universal Dashboard Mount",
            brand="PhoneMaster",
            category_id=7072562011,
        )
        assert metadata.asin == "B08XYZ1234"
        assert metadata.brand == "PhoneMaster"

    def test_to_db_dict(self):
        """Test conversion to database dictionary."""
        metadata = ProductMetadata(
            asin="B08XYZ1234",
            title="Test Product",
            brand="TestBrand",
            dimensions_cm={"length": 15.0, "width": 10.0, "height": 5.0},
            bullet_points=["Feature 1", "Feature 2"],
            is_amazon_choice=True,
        )

        db_dict = metadata.to_db_dict()

        assert db_dict["asin"] == "B08XYZ1234"
        assert db_dict["is_amazon_choice"] is True
        assert '"length": 15.0' in db_dict["dimensions_cm"]


class TestProductData:
    """Tests for ProductData container."""

    def test_basic_creation(self):
        """Test basic product data creation."""
        metadata = ProductMetadata(
            asin="B08XYZ1234",
            title="Test Product",
        )
        snapshot = ProductSnapshot(
            asin="B08XYZ1234",
            price_current=Decimal("29.99"),
        )

        product = ProductData(
            asin="B08XYZ1234",
            metadata=metadata,
            current_snapshot=snapshot,
        )

        assert product.asin == "B08XYZ1234"
        assert product.metadata.title == "Test Product"

    def test_has_history_flags(self):
        """Test history availability checks."""
        metadata = ProductMetadata(asin="B08XYZ1234", title="Test")
        snapshot = ProductSnapshot(asin="B08XYZ1234")

        product = ProductData(
            asin="B08XYZ1234",
            metadata=metadata,
            current_snapshot=snapshot,
            price_history=[],
            bsr_history=None,
        )

        assert product.has_price_history() is False
        assert product.has_bsr_history() is False

    def test_price_trend_calculation(self):
        """Test 7-day price trend calculation."""
        metadata = ProductMetadata(asin="B08XYZ1234", title="Test")
        snapshot = ProductSnapshot(asin="B08XYZ1234")

        # Create price history with clear trend
        now = datetime.utcnow()
        price_history = [
            PriceHistory(timestamp=now - timedelta(days=6), price_cents=2000),
            PriceHistory(timestamp=now - timedelta(days=3), price_cents=2200),
            PriceHistory(timestamp=now - timedelta(days=1), price_cents=2400),
        ]

        product = ProductData(
            asin="B08XYZ1234",
            metadata=metadata,
            current_snapshot=snapshot,
            price_history=price_history,
        )

        trend = product.get_price_trend_7d()
        assert trend is not None
        assert trend > 0  # Price increased


class TestIngestionResult:
    """Tests for IngestionResult model."""

    def test_success_rate_calculation(self):
        """Test success rate calculation."""
        result = IngestionResult(
            batch_id="test-batch",
            started_at=datetime.utcnow(),
            asins_requested=100,
            asins_processed=95,
            asins_failed=5,
        )

        assert result.success_rate == 90.0

    def test_duration_calculation(self):
        """Test duration calculation."""
        start = datetime.utcnow()
        result = IngestionResult(
            batch_id="test-batch",
            started_at=start,
            completed_at=start + timedelta(seconds=120),
        )

        assert result.duration_seconds == 120.0

    def test_add_error(self):
        """Test error recording."""
        result = IngestionResult(
            batch_id="test-batch",
            started_at=datetime.utcnow(),
        )

        result.add_error("B08XYZ1234", "KeepaAPIError", "Rate limit exceeded")

        assert len(result.errors) == 1
        assert result.asins_failed == 1
        assert result.errors[0]["asin"] == "B08XYZ1234"


class TestStockStatus:
    """Tests for StockStatus enum."""

    def test_all_values(self):
        """Test all stock status values exist."""
        assert StockStatus.IN_STOCK.value == "in_stock"
        assert StockStatus.LOW_STOCK.value == "low_stock"
        assert StockStatus.OUT_OF_STOCK.value == "out_of_stock"
        assert StockStatus.BACK_ORDERED.value == "back_ordered"
        assert StockStatus.UNKNOWN.value == "unknown"


class TestFulfillmentType:
    """Tests for FulfillmentType enum."""

    def test_all_values(self):
        """Test all fulfillment type values exist."""
        assert FulfillmentType.FBA.value == "fba"
        assert FulfillmentType.FBM.value == "fbm"
        assert FulfillmentType.AMAZON.value == "amazon"
        assert FulfillmentType.UNKNOWN.value == "unknown"
