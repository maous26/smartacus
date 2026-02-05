"""
Smartacus Configuration Module
==============================

Centralized configuration management using environment variables.
Supports both .env files and system environment variables.

Environment Variables:
    KEEPA_API_KEY: Keepa API authentication key (required)
    KEEPA_TOKENS_PER_MINUTE: Rate limit tokens (default: 200)
    KEEPA_MAX_RETRIES: Maximum retry attempts (default: 3)

    DATABASE_HOST: PostgreSQL host (default: localhost)
    DATABASE_PORT: PostgreSQL port (default: 5432)
    DATABASE_NAME: Database name (default: smartacus)
    DATABASE_USER: Database user (default: smartacus_app)
    DATABASE_PASSWORD: Database password (required)
    DATABASE_POOL_MIN: Minimum pool connections (default: 2)
    DATABASE_POOL_MAX: Maximum pool connections (default: 10)

    INGESTION_BATCH_SIZE: ASIN batch size for processing (default: 100)
    INGESTION_CATEGORY_NODE_ID: Amazon category node ID (default: 7072562011)
    INGESTION_MIN_PRICE: Minimum price filter USD (default: 5.0)
    INGESTION_MAX_PRICE: Maximum price filter USD (default: 100.0)
    INGESTION_MIN_REVIEWS: Minimum reviews filter (default: 10)
    INGESTION_MIN_RATING: Minimum rating filter (default: 3.0)
"""

import os
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path
from dotenv import load_dotenv


# Load environment variables from .env file if present
env_path = Path(__file__).parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    # Try project root
    project_root = Path(__file__).parent.parent.parent.parent / ".env"
    if project_root.exists():
        load_dotenv(project_root)


def get_env(key: str, default: Optional[str] = None, required: bool = False) -> Optional[str]:
    """
    Get environment variable with optional default and required validation.

    Args:
        key: Environment variable name
        default: Default value if not set
        required: If True, raises ValueError when not set

    Returns:
        Environment variable value or default

    Raises:
        ValueError: If required=True and variable is not set
    """
    value = os.getenv(key, default)
    if required and value is None:
        raise ValueError(f"Required environment variable '{key}' is not set")
    return value


def get_env_int(key: str, default: int) -> int:
    """Get environment variable as integer."""
    value = os.getenv(key)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        raise ValueError(f"Environment variable '{key}' must be an integer, got: {value}")


def get_env_float(key: str, default: float) -> float:
    """Get environment variable as float."""
    value = os.getenv(key)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError:
        raise ValueError(f"Environment variable '{key}' must be a float, got: {value}")


def get_env_bool(key: str, default: bool) -> bool:
    """Get environment variable as boolean."""
    value = os.getenv(key)
    if value is None:
        return default
    return value.lower() in ("true", "1", "yes", "on")


@dataclass
class KeepaConfig:
    """Keepa API configuration."""

    api_key: str = field(default_factory=lambda: get_env("KEEPA_API_KEY", required=True))

    # Rate limiting (Plan 49 EUR = ~300 tokens/minute, conservative default)
    tokens_per_minute: int = field(default_factory=lambda: get_env_int("KEEPA_TOKENS_PER_MINUTE", 200))

    # Retry configuration
    max_retries: int = field(default_factory=lambda: get_env_int("KEEPA_MAX_RETRIES", 3))
    retry_base_delay: float = field(default_factory=lambda: get_env_float("KEEPA_RETRY_BASE_DELAY", 1.0))
    retry_max_delay: float = field(default_factory=lambda: get_env_float("KEEPA_RETRY_MAX_DELAY", 60.0))

    # Request timeout in seconds
    request_timeout: int = field(default_factory=lambda: get_env_int("KEEPA_REQUEST_TIMEOUT", 120))

    # Domain (Amazon marketplace)
    # 1=com, 2=co.uk, 3=de, 4=fr, 5=co.jp, 6=ca, 7=cn, 8=it, 9=es, 10=in, 11=com.mx
    domain_id: int = field(default_factory=lambda: get_env_int("KEEPA_DOMAIN_ID", 1))

    def __post_init__(self):
        """Validate configuration after initialization."""
        if not self.api_key:
            raise ValueError("KEEPA_API_KEY is required")
        if self.tokens_per_minute <= 0:
            raise ValueError("tokens_per_minute must be positive")
        if self.max_retries < 0:
            raise ValueError("max_retries cannot be negative")


@dataclass
class DatabaseConfig:
    """PostgreSQL database configuration."""

    host: str = field(default_factory=lambda: get_env("DATABASE_HOST", "localhost"))
    port: int = field(default_factory=lambda: get_env_int("DATABASE_PORT", 5432))
    name: str = field(default_factory=lambda: get_env("DATABASE_NAME", "smartacus"))
    user: str = field(default_factory=lambda: get_env("DATABASE_USER", "smartacus_app"))
    password: str = field(default_factory=lambda: get_env("DATABASE_PASSWORD", required=True))

    # Connection pool settings
    pool_min_size: int = field(default_factory=lambda: get_env_int("DATABASE_POOL_MIN", 2))
    pool_max_size: int = field(default_factory=lambda: get_env_int("DATABASE_POOL_MAX", 10))

    # Connection timeout
    connect_timeout: int = field(default_factory=lambda: get_env_int("DATABASE_CONNECT_TIMEOUT", 10))

    # SSL mode: disable, allow, prefer, require, verify-ca, verify-full
    ssl_mode: str = field(default_factory=lambda: get_env("DATABASE_SSL_MODE", "prefer"))

    @property
    def connection_string(self) -> str:
        """Build PostgreSQL connection string."""
        return (
            f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.name}"
            f"?sslmode={self.ssl_mode}&connect_timeout={self.connect_timeout}"
        )

    @property
    def connection_dict(self) -> dict:
        """Connection parameters as dictionary for psycopg2."""
        return {
            "host": self.host,
            "port": self.port,
            "dbname": self.name,
            "user": self.user,
            "password": self.password,
            "sslmode": self.ssl_mode,
            "connect_timeout": self.connect_timeout,
        }

    def __post_init__(self):
        """Validate configuration."""
        if not self.password:
            raise ValueError("DATABASE_PASSWORD is required")
        if self.pool_min_size > self.pool_max_size:
            raise ValueError("pool_min_size cannot exceed pool_max_size")


@dataclass
class IngestionConfig:
    """Data ingestion pipeline configuration."""

    # Processing batch sizes
    batch_size: int = field(default_factory=lambda: get_env_int("INGESTION_BATCH_SIZE", 100))

    # Target Amazon category (Cell Phone Automobile Cradles)
    category_node_id: int = field(default_factory=lambda: get_env_int("INGESTION_CATEGORY_NODE_ID", 7072562011))

    # ASIN filtering criteria
    min_price_usd: float = field(default_factory=lambda: get_env_float("INGESTION_MIN_PRICE", 5.0))
    max_price_usd: float = field(default_factory=lambda: get_env_float("INGESTION_MAX_PRICE", 100.0))
    min_reviews: int = field(default_factory=lambda: get_env_int("INGESTION_MIN_REVIEWS", 10))
    min_rating: float = field(default_factory=lambda: get_env_float("INGESTION_MIN_RATING", 3.0))
    max_bsr: int = field(default_factory=lambda: get_env_int("INGESTION_MAX_BSR", 500000))

    # Target ASIN volume
    target_asin_count: int = field(default_factory=lambda: get_env_int("INGESTION_TARGET_ASIN_COUNT", 10000))

    # Processing options
    parallel_workers: int = field(default_factory=lambda: get_env_int("INGESTION_PARALLEL_WORKERS", 4))
    enable_buybox_history: bool = field(default_factory=lambda: get_env_bool("INGESTION_ENABLE_BUYBOX", True))

    # Data freshness threshold (hours) - skip if data is newer than this
    freshness_threshold_hours: int = field(default_factory=lambda: get_env_int("INGESTION_FRESHNESS_HOURS", 24))

    def __post_init__(self):
        """Validate configuration."""
        if self.min_price_usd >= self.max_price_usd:
            raise ValueError("min_price must be less than max_price")
        if self.batch_size <= 0:
            raise ValueError("batch_size must be positive")


@dataclass
class LoggingConfig:
    """Logging configuration."""

    level: str = field(default_factory=lambda: get_env("LOG_LEVEL", "INFO"))
    format: str = field(default_factory=lambda: get_env(
        "LOG_FORMAT",
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    ))
    log_file: Optional[str] = field(default_factory=lambda: get_env("LOG_FILE"))

    # Structured logging
    json_logs: bool = field(default_factory=lambda: get_env_bool("LOG_JSON", False))


@dataclass
class Settings:
    """Main application settings container."""

    keepa: KeepaConfig = field(default_factory=KeepaConfig)
    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    ingestion: IngestionConfig = field(default_factory=IngestionConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)

    # Application metadata
    app_name: str = "smartacus"
    app_version: str = "1.0.0"
    environment: str = field(default_factory=lambda: get_env("ENVIRONMENT", "development"))

    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment.lower() in ("production", "prod")

    def is_development(self) -> bool:
        """Check if running in development environment."""
        return self.environment.lower() in ("development", "dev")


def load_settings() -> Settings:
    """
    Load and validate all application settings.

    Returns:
        Fully configured Settings instance

    Raises:
        ValueError: If required configuration is missing or invalid
    """
    return Settings()


# Global settings instance (lazy-loaded)
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """
    Get the global settings instance (singleton pattern).

    Returns:
        Global Settings instance
    """
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings


# Convenience access
settings = property(lambda self: get_settings())


# Export settings for direct import
# Usage: from config import settings
class _SettingsProxy:
    """Proxy class for lazy settings access."""

    def __getattr__(self, name):
        return getattr(get_settings(), name)


settings = _SettingsProxy()
