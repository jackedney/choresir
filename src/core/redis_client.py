"""In-memory cache replacement for Redis.

Replaces the Redis client with a simple in-memory dictionary implementation
to remove external dependencies while maintaining the interface.
"""

import asyncio
import logging
import time
from fnmatch import fnmatch
from typing import Any

logger = logging.getLogger(__name__)


class RedisClient:
    """In-memory cache implementation maintaining Redis client interface."""

    def __init__(self) -> None:
        """Initialize in-memory cache."""
        # key -> (value, expiry_timestamp)
        self._cache: dict[str, tuple[str, float | None]] = {}
        self._lock = asyncio.Lock()

    @property
    def is_available(self) -> bool:
        """Check if cache is available (always True for in-memory)."""
        return True

    def get_health_status(self) -> dict[str, Any]:
        """Get cache health status."""
        return {
            "enabled": True,
            "connected": True,
            "type": "in-memory",
            "keys": len(self._cache),
        }

    async def get(self, key: str) -> str | None:
        """Get value from cache."""
        async with self._lock:
            if key not in self._cache:
                return None

            value, expiry = self._cache[key]
            if expiry and time.time() > expiry:
                del self._cache[key]
                return None
            return value

    async def set(self, key: str, value: str, ttl_seconds: int) -> bool:
        """Set value in cache with TTL."""
        async with self._lock:
            expiry = time.time() + ttl_seconds
            self._cache[key] = (value, expiry)
            logger.debug("Cached key: %s (TTL: %ds)", key, ttl_seconds)
            return True

    async def delete(self, *keys: str) -> bool:
        """Delete one or more keys from cache."""
        async with self._lock:
            for key in keys:
                self._cache.pop(key, None)
            return True

    async def delete_with_retry(self, *keys: str) -> bool:
        """Delete keys with retry logic (alias for delete)."""
        return await self.delete(*keys)

    async def keys(self, pattern: str) -> list[str]:
        """Find keys matching a pattern."""
        async with self._lock:
            # Filter expired keys first?
            active_keys = []
            now = time.time()
            keys_to_delete = []

            for key, (value, expiry) in self._cache.items():
                if expiry and now > expiry:
                    keys_to_delete.append(key)
                elif fnmatch(key, pattern):
                    active_keys.append(key)

            for key in keys_to_delete:
                del self._cache[key]

            return active_keys

    async def close(self) -> None:
        """Close cache connection (no-op)."""
        pass

    async def ping(self) -> bool:
        """Ping cache (always True)."""
        return True

    async def set_if_not_exists(self, key: str, value: str, ttl_seconds: int) -> bool:
        """Set value only if key doesn't exist (atomic)."""
        async with self._lock:
            now = time.time()
            if key in self._cache:
                _, expiry = self._cache[key]
                if not expiry or now <= expiry:
                    return False

            expiry = now + ttl_seconds
            self._cache[key] = (value, expiry)
            return True

    async def increment(self, key: str) -> int | None:
        """Increment key value atomically."""
        async with self._lock:
            now = time.time()
            val = 0
            expiry = None

            if key in self._cache:
                v, exp = self._cache[key]
                if exp and now > exp:
                    # Expired, treat as 0
                    pass
                else:
                    try:
                        val = int(v)
                        expiry = exp
                    except ValueError:
                        return None

            val += 1
            # Maintain existing expiry if any
            self._cache[key] = (str(val), expiry)
            return val

    async def expire(self, key: str, ttl_seconds: int) -> bool:
        """Set TTL on existing key."""
        async with self._lock:
            if key not in self._cache:
                return False

            value, old_expiry = self._cache[key]
            if old_expiry and time.time() > old_expiry:
                del self._cache[key]
                return False

            self._cache[key] = (value, time.time() + ttl_seconds)
            return True


# Global Redis client instance
redis_client = RedisClient()
