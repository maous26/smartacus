"""
Smartacus Cache Module
======================

Provides Redis-based caching with fallback to in-memory cache.

Usage:
    from src.cache import get_cache

    cache = get_cache()
    cache.set("key", {"data": "value"}, ttl_hours=24)
    result = cache.get("key")
"""

from .redis_cache import RedisCache, get_cache

__all__ = ["RedisCache", "get_cache"]
