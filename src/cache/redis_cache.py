"""
Redis Cache for Smartacus
=========================

Provides persistent caching via Redis with automatic fallback to in-memory cache.

Features:
- Automatic connection management
- TTL-based expiration
- JSON serialization
- Fallback to in-memory if Redis unavailable
- Namespace prefixing for key isolation

Usage:
    cache = RedisCache()
    cache.set("llm:decision:abc123", {"data": "value"}, ttl_hours=24)
    result = cache.get("llm:decision:abc123")

Environment variables:
    REDIS_URL - Full Redis URL (redis://host:port/db)
    REDIS_HOST - Redis host (default: localhost)
    REDIS_PORT - Redis port (default: 6379)
    REDIS_DB - Redis database number (default: 0)
    REDIS_PASSWORD - Redis password (optional)
    CACHE_PREFIX - Key prefix (default: smartacus)
"""

import os
import json
import logging
import hashlib
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple

logger = logging.getLogger(__name__)

# Global cache instance (singleton)
_cache_instance: Optional["RedisCache"] = None


class RedisCache:
    """
    Redis-based cache with in-memory fallback.

    Automatically falls back to in-memory caching if Redis is unavailable.
    """

    def __init__(
        self,
        redis_url: Optional[str] = None,
        prefix: str = "smartacus",
        fallback_to_memory: bool = True,
    ):
        """
        Initialize Redis cache.

        Args:
            redis_url: Optional Redis URL. If None, reads from env.
            prefix: Key prefix for namespace isolation.
            fallback_to_memory: If True, use in-memory cache when Redis unavailable.
        """
        self.prefix = prefix
        self.fallback_to_memory = fallback_to_memory
        self._redis: Optional[Any] = None
        self._memory_cache: Dict[str, Tuple[datetime, Any]] = {}
        self._use_memory = False

        # Try to connect to Redis
        self._connect(redis_url)

    def _connect(self, redis_url: Optional[str] = None) -> None:
        """Establish Redis connection."""
        try:
            import redis
        except ImportError:
            logger.warning("redis package not installed. Using in-memory cache.")
            self._use_memory = True
            return

        # Build connection URL
        url = redis_url or os.getenv("REDIS_URL")

        if not url:
            # Build from individual components
            host = os.getenv("REDIS_HOST", "localhost")
            port = int(os.getenv("REDIS_PORT", "6379"))
            db = int(os.getenv("REDIS_DB", "0"))
            password = os.getenv("REDIS_PASSWORD")

            if password:
                url = f"redis://:{password}@{host}:{port}/{db}"
            else:
                url = f"redis://{host}:{port}/{db}"

        try:
            self._redis = redis.from_url(
                url,
                decode_responses=True,
                socket_timeout=5,
                socket_connect_timeout=5,
            )
            # Test connection
            self._redis.ping()
            logger.info(f"Redis cache connected: {url.split('@')[-1] if '@' in url else url}")
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}. Using in-memory cache.")
            self._redis = None
            self._use_memory = True

    def _make_key(self, key: str) -> str:
        """Create prefixed key."""
        return f"{self.prefix}:{key}"

    def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/expired
        """
        full_key = self._make_key(key)

        if self._use_memory or self._redis is None:
            return self._memory_get(full_key)

        try:
            value = self._redis.get(full_key)
            if value is None:
                return None
            return json.loads(value)
        except Exception as e:
            logger.warning(f"Redis get failed: {e}")
            return self._memory_get(full_key)

    def set(
        self,
        key: str,
        value: Any,
        ttl_hours: Optional[int] = None,
        ttl_seconds: Optional[int] = None,
    ) -> bool:
        """
        Set value in cache.

        Args:
            key: Cache key
            value: Value to cache (must be JSON serializable)
            ttl_hours: Time to live in hours
            ttl_seconds: Time to live in seconds (overrides ttl_hours)

        Returns:
            True if successful
        """
        full_key = self._make_key(key)

        # Calculate TTL in seconds
        ttl = None
        if ttl_seconds is not None:
            ttl = ttl_seconds
        elif ttl_hours is not None:
            ttl = ttl_hours * 3600

        if self._use_memory or self._redis is None:
            return self._memory_set(full_key, value, ttl)

        try:
            serialized = json.dumps(value)
            if ttl:
                self._redis.setex(full_key, ttl, serialized)
            else:
                self._redis.set(full_key, serialized)
            return True
        except Exception as e:
            logger.warning(f"Redis set failed: {e}")
            return self._memory_set(full_key, value, ttl)

    def delete(self, key: str) -> bool:
        """
        Delete key from cache.

        Args:
            key: Cache key

        Returns:
            True if key was deleted
        """
        full_key = self._make_key(key)

        if self._use_memory or self._redis is None:
            return self._memory_delete(full_key)

        try:
            result = self._redis.delete(full_key)
            return result > 0
        except Exception as e:
            logger.warning(f"Redis delete failed: {e}")
            return self._memory_delete(full_key)

    def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        full_key = self._make_key(key)

        if self._use_memory or self._redis is None:
            return full_key in self._memory_cache

        try:
            return self._redis.exists(full_key) > 0
        except Exception as e:
            logger.warning(f"Redis exists failed: {e}")
            return full_key in self._memory_cache

    def clear_prefix(self, prefix: str) -> int:
        """
        Clear all keys with given prefix.

        Args:
            prefix: Key prefix to clear

        Returns:
            Number of keys deleted
        """
        full_prefix = self._make_key(prefix)

        if self._use_memory or self._redis is None:
            count = 0
            keys_to_delete = [k for k in self._memory_cache if k.startswith(full_prefix)]
            for k in keys_to_delete:
                del self._memory_cache[k]
                count += 1
            return count

        try:
            keys = self._redis.keys(f"{full_prefix}*")
            if keys:
                return self._redis.delete(*keys)
            return 0
        except Exception as e:
            logger.warning(f"Redis clear_prefix failed: {e}")
            return 0

    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        stats = {
            "backend": "memory" if self._use_memory else "redis",
            "connected": not self._use_memory and self._redis is not None,
        }

        if self._use_memory:
            stats["memory_keys"] = len(self._memory_cache)
        else:
            try:
                info = self._redis.info("memory")
                stats["redis_memory_used"] = info.get("used_memory_human", "N/A")
                stats["redis_keys"] = self._redis.dbsize()
            except Exception:
                pass

        return stats

    # =========================================================================
    # MEMORY FALLBACK
    # =========================================================================

    def _memory_get(self, key: str) -> Optional[Any]:
        """Get from in-memory cache."""
        if key not in self._memory_cache:
            return None

        expires_at, value = self._memory_cache[key]
        if expires_at and datetime.utcnow() > expires_at:
            del self._memory_cache[key]
            return None

        return value

    def _memory_set(self, key: str, value: Any, ttl_seconds: Optional[int]) -> bool:
        """Set in in-memory cache."""
        expires_at = None
        if ttl_seconds:
            expires_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)

        self._memory_cache[key] = (expires_at, value)
        return True

    def _memory_delete(self, key: str) -> bool:
        """Delete from in-memory cache."""
        if key in self._memory_cache:
            del self._memory_cache[key]
            return True
        return False

    # =========================================================================
    # UTILITIES
    # =========================================================================

    @staticmethod
    def compute_hash(*args) -> str:
        """
        Compute SHA256 hash from arguments for cache key generation.

        Args:
            *args: Values to hash (will be JSON serialized)

        Returns:
            16-character hex hash
        """
        data = json.dumps(args, sort_keys=True, default=str)
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    def close(self) -> None:
        """Close Redis connection."""
        if self._redis:
            try:
                self._redis.close()
            except Exception:
                pass
            self._redis = None


def get_cache(
    redis_url: Optional[str] = None,
    force_new: bool = False,
) -> RedisCache:
    """
    Get singleton cache instance.

    Args:
        redis_url: Optional Redis URL (only used if creating new instance)
        force_new: If True, create new instance even if one exists

    Returns:
        RedisCache instance
    """
    global _cache_instance

    if _cache_instance is None or force_new:
        _cache_instance = RedisCache(redis_url=redis_url)

    return _cache_instance
