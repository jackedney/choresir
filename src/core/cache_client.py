"""In-memory cache with TTL support."""

import fnmatch
import logging
import threading
import time
from typing import Any


logger = logging.getLogger(__name__)


class InMemoryCache:
    """Thread-safe in-memory cache with TTL support."""

    def __init__(self) -> None:
        """Initialize in-memory cache."""
        self._data: dict[str, str] = {}
        self._expiry: dict[str, float] = {}
        self._lock = threading.Lock()

        # Health tracking
        self._last_successful_operation: float | None = None
        self._total_operations = 0

    @property
    def is_available(self) -> bool:
        """Check if cache is available (always true for in-memory)."""
        return True

    def get_health_status(self) -> dict[str, Any]:
        """Get cache health status.

        Returns:
            Dict with health status including last successful operation and total operations
        """
        return {
            "enabled": True,
            "connected": True,
            "last_successful_operation": self._last_successful_operation,
            "total_operations": self._total_operations,
            "entries": len(self._data),
        }

    def _record_success(self) -> None:
        """Record successful cache operation."""
        self._last_successful_operation = time.time()
        self._total_operations += 1

    def _cleanup_expired(self, keys: list[str] | None = None) -> None:
        """Clean up expired entries.

        Args:
            keys: Specific keys to check. If None, checks all keys.
        """
        now = time.time()
        keys_to_check = list(self._expiry.keys()) if keys is None else keys

        for key in keys_to_check:
            expiry = self._expiry.get(key)
            if expiry and expiry < now:
                self._data.pop(key, None)
                self._expiry.pop(key, None)

    async def get(self, key: str) -> str | None:
        """Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found or expired
        """
        with self._lock:
            # Clean up expired entries for this key
            self._cleanup_expired([key])

            value = self._data.get(key)
            if value:
                self._record_success()
                logger.debug("Cache hit for key: %s", key)
            return value

    async def set(self, key: str, value: str, ttl_seconds: int) -> bool:
        """Set value in cache with TTL.

        Args:
            key: Cache key
            value: Value to cache
            ttl_seconds: Time-to-live in seconds

        Returns:
            True if successful
        """
        with self._lock:
            self._data[key] = value
            if ttl_seconds > 0:
                self._expiry[key] = time.time() + ttl_seconds
            self._record_success()
            logger.debug("Cached key: %s (TTL: %ds)", key, ttl_seconds)
            return True

    async def delete(self, *keys: str) -> bool:
        """Delete one or more keys from cache.

        Args:
            *keys: Cache keys to delete

        Returns:
            True if successful
        """
        if not keys:
            return False

        with self._lock:
            for key in keys:
                self._data.pop(key, None)
                self._expiry.pop(key, None)
            self._record_success()
            logger.debug("Deleted %d cache key(s)", len(keys))
            return True

    async def keys(self, pattern: str) -> list[str]:
        """Find keys matching a pattern.

        Args:
            pattern: Pattern to match (e.g., 'leaderboard:*')

        Returns:
            List of matching keys
        """
        with self._lock:
            # Clean up expired entries
            self._cleanup_expired()

            # Match pattern against all keys
            return [key for key in self._data if fnmatch.fnmatch(key, pattern)]

    async def ping(self) -> bool:
        """Ping cache to check availability.

        Returns:
            True (always available for in-memory cache)
        """
        return True

    async def set_if_not_exists(self, key: str, value: str, ttl_seconds: int) -> bool:
        """Set value only if key doesn't exist (atomic).

        Args:
            key: Cache key
            value: Value to cache
            ttl_seconds: Time-to-live in seconds

        Returns:
            True if key was set (didn't exist), False if key already exists
        """
        with self._lock:
            # Check if key exists and is not expired
            self._cleanup_expired([key])

            if key in self._data:
                return False

            self._data[key] = value
            if ttl_seconds > 0:
                self._expiry[key] = time.time() + ttl_seconds
            self._record_success()
            return True

    async def increment(self, key: str) -> int | None:
        """Increment key value atomically.

        Args:
            key: Cache key

        Returns:
            New value after increment, or None on error
        """
        with self._lock:
            # Clean up expired entries for this key
            self._cleanup_expired([key])

            current_value = self._data.get(key)
            if current_value is None:
                new_value = "1"
            else:
                try:
                    new_value = str(int(current_value) + 1)
                except (ValueError, TypeError):
                    logger.warning("Cannot increment non-numeric key: %s", key)
                    return None

            self._data[key] = new_value
            self._record_success()
            return int(new_value)

    async def expire(self, key: str, ttl_seconds: int) -> bool:
        """Set TTL on existing key.

        Args:
            key: Cache key
            ttl_seconds: Time-to-live in seconds

        Returns:
            True if successful, False if key doesn't exist
        """
        with self._lock:
            # Check if key exists and is not expired
            self._cleanup_expired([key])

            if key not in self._data:
                return False

            if ttl_seconds > 0:
                self._expiry[key] = time.time() + ttl_seconds
            else:
                self._expiry.pop(key, None)

            self._record_success()
            return True

    async def close(self) -> None:
        """Close cache connection (no-op for in-memory cache)."""
        logger.info("In-memory cache closed")


# Global cache client instance
cache_client = InMemoryCache()
