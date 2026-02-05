"""
Tests for Smartacus Keepa client.

Note: These tests use mocking to avoid actual API calls.
For integration tests, set KEEPA_API_KEY environment variable.
"""

import pytest
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import Mock, patch, MagicMock

from src.data.keepa_client import (
    KeepaClient,
    KeepaAPIError,
    KeepaRateLimitError,
    RateLimitState,
)
from src.data.data_models import StockStatus, FulfillmentType


class TestRateLimitState:
    """Tests for rate limit tracking."""

    def test_initial_state(self):
        """Test initial rate limit state."""
        state = RateLimitState(
            tokens_per_minute=200,
            tokens_left=200,
            refill_rate=200 / 60,
        )
        assert state.tokens_left == 200
        assert state.can_make_request(10) is True

    def test_token_consumption(self):
        """Test token consumption tracking."""
        state = RateLimitState(
            tokens_per_minute=200,
            tokens_left=200,
            refill_rate=200 / 60,
        )

        state.consume_tokens(50)
        assert state.tokens_left == 150

    def test_can_make_request(self):
        """Test request availability check."""
        state = RateLimitState(
            tokens_per_minute=200,
            tokens_left=10,
            refill_rate=200 / 60,
        )

        assert state.can_make_request(10) is True
        assert state.can_make_request(15) is False  # Before refill

    def test_wait_time_calculation(self):
        """Test wait time calculation for token deficit."""
        state = RateLimitState(
            tokens_per_minute=60,  # 1 token per second
            tokens_left=0,
            refill_rate=1.0,
            last_request_time=datetime.utcnow(),
        )

        wait_time = state.wait_time_for_tokens(10)
        assert wait_time >= 9.0  # Should need ~10 seconds


class TestKeepaClientInit:
    """Tests for KeepaClient initialization."""

    @patch.dict('os.environ', {
        'KEEPA_API_KEY': 'test_key_12345',
        'DATABASE_PASSWORD': 'test_password',
    })
    def test_init_from_env(self):
        """Test initialization from environment variables."""
        client = KeepaClient()
        assert client.api_key == 'test_key_12345'
        assert client.domain_id == 1  # Default

    def test_init_with_params(self):
        """Test initialization with explicit parameters."""
        client = KeepaClient(
            api_key="explicit_key",
            tokens_per_minute=300,
            max_retries=5,
            domain_id=2,  # UK
        )

        assert client.api_key == "explicit_key"
        assert client.max_retries == 5
        assert client.domain_id == 2


class TestKeepaClientDataTransform:
    """Tests for data transformation methods."""

    def setup_method(self):
        """Set up test fixtures."""
        self.client = KeepaClient(api_key="test_key")

    def test_keepa_time_conversion(self):
        """Test Keepa time to datetime conversion."""
        # Keepa epoch is 2011-01-01
        # Test 1 year (525600 minutes)
        result = self.client._keepa_time_to_datetime(525600)
        assert result.year == 2012

    def test_extract_latest_value(self):
        """Test extracting latest value from Keepa CSV array."""
        # Keepa format: [time1, value1, time2, value2, ...]
        csv_data = [100, 2999, 200, 3499, 300, 2899]

        result = self.client._extract_latest_value(csv_data)
        assert result == 2899  # Last value

    def test_extract_latest_value_skips_invalid(self):
        """Test that -1 values are skipped."""
        csv_data = [100, 2999, 200, -1, 300, -1]

        result = self.client._extract_latest_value(csv_data)
        assert result == 2999  # First valid value from end

    def test_determine_stock_status_in_stock(self):
        """Test stock status determination for in-stock product."""
        product = {
            "availabilityAmazon": 0,
        }
        status = self.client._determine_stock_status(product)
        assert status == StockStatus.IN_STOCK

    def test_determine_stock_status_out_of_stock(self):
        """Test stock status determination for out-of-stock product."""
        product = {
            "availabilityAmazon": -1,
            "csv": [],
        }
        status = self.client._determine_stock_status(product)
        assert status == StockStatus.OUT_OF_STOCK

    def test_determine_fulfillment_amazon(self):
        """Test fulfillment type for Amazon-sold product."""
        # Amazon price type index is 0
        product = {
            "csv": [[100, 2999, 200, 3499]],  # Amazon price history
        }
        fulfillment = self.client._determine_fulfillment(product)
        assert fulfillment == FulfillmentType.AMAZON


class TestKeepaClientAPIOperations:
    """Tests for API operations (mocked)."""

    def setup_method(self):
        """Set up test fixtures."""
        self.client = KeepaClient(api_key="test_key")

    @patch.object(KeepaClient, 'api', new_callable=MagicMock)
    def test_get_category_asins(self, mock_api):
        """Test category ASIN discovery."""
        mock_api.category_lookup.return_value = {
            "asinList": ["B08ABC1234", "B08DEF5678", "B08GHI9012"],
        }

        asins = self.client.get_category_asins(7072562011)

        assert len(asins) == 3
        assert "B08ABC1234" in asins
        mock_api.category_lookup.assert_called_once()

    @patch.object(KeepaClient, 'api', new_callable=MagicMock)
    def test_get_category_asins_with_limit(self, mock_api):
        """Test category ASIN discovery with max results."""
        mock_api.category_lookup.return_value = {
            "asinList": [f"B08{i:07d}" for i in range(1000)],
        }

        asins = self.client.get_category_asins(7072562011, max_results=100)

        assert len(asins) == 100

    @patch.object(KeepaClient, 'api', new_callable=MagicMock)
    def test_get_product_data(self, mock_api):
        """Test product data retrieval."""
        mock_api.query.return_value = [
            {
                "asin": "B08ABC1234",
                "title": "Test Car Phone Mount",
                "brand": "TestBrand",
                "csv": [
                    [100, 2999],  # Amazon price
                    [100, 2599],  # New price
                    None,         # Used price
                    [100, 5000],  # BSR
                ],
                "categoryTree": [
                    {"name": "Electronics"},
                    {"name": "Cell Phone Automobile Cradles"},
                ],
            }
        ]

        products = self.client.get_product_data(["B08ABC1234"])

        assert len(products) == 1
        assert products[0].asin == "B08ABC1234"
        assert products[0].metadata.title == "Test Car Phone Mount"
        mock_api.query.assert_called_once()

    @patch.object(KeepaClient, 'api', new_callable=MagicMock)
    def test_get_product_data_batch_split(self, mock_api):
        """Test that large ASIN lists are split into batches."""
        mock_api.query.return_value = []

        # Request more than 100 ASINs
        asins = [f"B08{i:07d}" for i in range(250)]
        self.client.get_product_data(asins)

        # Should make 3 calls (100 + 100 + 50)
        assert mock_api.query.call_count == 3

    @patch.object(KeepaClient, 'api', new_callable=MagicMock)
    def test_health_check(self, mock_api):
        """Test health check."""
        health = self.client.health_check()

        assert "status" in health
        assert "tokens_remaining" in health


class TestKeepaClientRetry:
    """Tests for retry logic."""

    def setup_method(self):
        """Set up test fixtures."""
        self.client = KeepaClient(
            api_key="test_key",
            max_retries=3,
            retry_base_delay=0.01,  # Fast for tests
            retry_max_delay=0.1,
        )

    def test_retry_on_failure(self):
        """Test that failed requests are retried."""
        import keepa

        call_count = 0

        def failing_then_success(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise keepa.KeepaError("Temporary error")
            return "success"

        result = self.client._retry_with_backoff(failing_then_success)

        assert result == "success"
        assert call_count == 3

    def test_max_retries_exceeded(self):
        """Test that KeepaAPIError is raised after max retries."""
        def always_fails(*args, **kwargs):
            raise Exception("Permanent error")

        with pytest.raises(KeepaAPIError):
            self.client._retry_with_backoff(always_fails)


class TestKeepaClientStats:
    """Tests for statistics tracking."""

    def setup_method(self):
        """Set up test fixtures."""
        self.client = KeepaClient(api_key="test_key")

    def test_initial_stats(self):
        """Test initial statistics state."""
        stats = self.client.get_stats()

        assert stats["total_requests"] == 0
        assert stats["total_tokens_consumed"] == 0
        assert stats["total_errors"] == 0

    def test_token_consumption_tracking(self):
        """Test token consumption is tracked."""
        self.client._consume_tokens(50)
        self.client._consume_tokens(30)

        stats = self.client.get_stats()
        assert stats["total_tokens_consumed"] == 80
        assert stats["total_requests"] == 2


# Integration tests (require actual API key)
@pytest.mark.skipif(
    not pytest.importorskip("os").environ.get("KEEPA_API_KEY"),
    reason="KEEPA_API_KEY not set"
)
class TestKeepaClientIntegration:
    """Integration tests with actual Keepa API."""

    def setup_method(self):
        """Set up test fixtures."""
        self.client = KeepaClient()

    def test_health_check_live(self):
        """Test actual health check."""
        health = self.client.health_check()
        assert health["status"] in ("healthy", "degraded")

    def test_get_single_product(self):
        """Test fetching a single product."""
        # Use a known stable ASIN
        products = self.client.get_product_data(
            ["B07X4FQBSM"],  # Example ASIN
            include_history=False,
        )

        assert len(products) <= 1  # May not exist
