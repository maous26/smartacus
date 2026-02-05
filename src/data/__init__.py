"""
Smartacus Data Module
=====================

Keepa API integration and data ingestion pipeline for Amazon product tracking.

This module provides:
    - KeepaClient: Robust API client with rate limiting and retry logic
    - IngestionPipeline: Orchestrates daily data pulls and database updates
    - Data models: ProductSnapshot, PriceHistory, BSRHistory, SellerInfo

Quick Start:
    from src.data import KeepaClient, IngestionPipeline

    # Run daily ingestion
    with IngestionPipeline() as pipeline:
        result = pipeline.run_daily_ingestion()
        print(f"Processed {result.asins_processed} ASINs")

    # Or use client directly
    client = KeepaClient()
    products = client.get_product_data(["B08XYZ1234", "B09ABC5678"])

Configuration:
    Set environment variables or create a .env file.
    See .env.example for all available options.

Required Environment Variables:
    KEEPA_API_KEY: Your Keepa API key
    DATABASE_PASSWORD: PostgreSQL password
"""

from .config import settings, get_settings, Settings
from .data_models import (
    ProductSnapshot,
    ProductMetadata,
    ProductData,
    PriceHistory,
    BSRHistory,
    BuyBoxHistory,
    SellerInfo,
    StockStatus,
    FulfillmentType,
    IngestionResult,
)
from .keepa_client import (
    KeepaClient,
    KeepaAPIError,
    KeepaRateLimitError,
    KeepaTokenExhaustedError,
    KeepaDataNotFoundError,
)
from .ingestion_pipeline import IngestionPipeline, DatabaseError

__version__ = "1.0.0"

__all__ = [
    # Configuration
    "settings",
    "get_settings",
    "Settings",
    # Data models
    "ProductSnapshot",
    "ProductMetadata",
    "ProductData",
    "PriceHistory",
    "BSRHistory",
    "BuyBoxHistory",
    "SellerInfo",
    "StockStatus",
    "FulfillmentType",
    "IngestionResult",
    # Keepa client
    "KeepaClient",
    "KeepaAPIError",
    "KeepaRateLimitError",
    "KeepaTokenExhaustedError",
    "KeepaDataNotFoundError",
    # Pipeline
    "IngestionPipeline",
    "DatabaseError",
]
