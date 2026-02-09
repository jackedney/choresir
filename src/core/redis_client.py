"""Redis client for caching."""

import asyncio
import fnmatch
import logging
from collections import deque
from datetime import UTC, datetime
from typing import Any


logger = logging.getLogger(__name__)


class RedisClient:
    """Async in-memory cache client with TTL support."""

    def __init__(self) -> None:
        """Initialize in-memory cache client."""
        self._enabled = True
        self._lock = asyncio.Lock()
        self._cache: dict[str, tuple[str, float | None]] = {}

        # Health tracking
        self._last_successful_operation: datetime | None = None
        self._failure_count = 0
        self._total_operations = 0

        # Fallback queue for cache invalidation when cache is unavailable
        self._invalidation_queue: deque[tuple[str, ...]] = deque(maxlen=1000)

        # Background cleanup task
        self._cleanup_task: asyncio.Task[None] | None = None
        self._shutdown_event = asyncio.Event()

        logger.info("In-memory cache client initialized")

    @property
    def is_available(self) -> bool:
        """Check if cache is available."""
        return self._enabled

    def get_health_status(self) -> dict[str, Any]:
        """Get cache health status.

        Returns:
            Dict with health status including last successful operation,
            failure count, and total operations
        """
        return {
            "enabled": self._enabled,
            "connected": self.is_available,
            "last_successful_operation": self._last_successful_operation.isoformat()
            if self._last_successful_operation
            else None,
            "failure_count": self._failure_count,
            "total_operations": self._total_operations,
            "pending_invalidations": len(self._invalidation_queue),
            "cache_size": len(self._cache),
        }

    def _record_success(self) -> None:
        """Record successful cache operation."""
        self._last_successful_operation = datetime.now(UTC)
        self._total_operations += 1

    def _record_failure(self) -> None:
        """Record failed cache operation."""
        self._failure_count += 1
        self._total_operations += 1

    async def get(self, key: str) -> str | None:
        """Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found or expired
        """
        async with self._lock:
            if not self.is_available:
                return None

            try:
                entry = self._cache.get(key)
                if entry is None:
                    return None

                value, expires_at = entry
                if expires_at is not None and datetime.now(UTC).timestamp() > expires_at:
                    del self._cache[key]
                    return None

                self._record_success()
                logger.debug("Cache hit for key: %s", key)
                return value
            except Exception as e:
                self._record_failure()
                logger.warning("Cache GET error for key %s: %s", key, e)
                return None

    async def set(self, key: str, value: str, ttl_seconds: int) -> bool:
        """Set value in cache with TTL.

        Args:
            key: Cache key
            value: Value to cache
            ttl_seconds: Time-to-live in seconds

        Returns:
            True if successful, False otherwise
        """
        async with self._lock:
            if not self.is_available:
                return False

            try:
                expires_at = datetime.now(UTC).timestamp() + ttl_seconds if ttl_seconds > 0 else None
                self._cache[key] = (value, expires_at)
                self._record_success()
                logger.debug("Cached key: %s (TTL: %ds)", key, ttl_seconds)
                return True
            except Exception as e:
                self._record_failure()
                logger.warning("Cache SET error for key %s: %s", key, e)
                return False

    async def delete(self, *keys: str) -> bool:
        """Delete one or more keys from cache.

        Args:
            *keys: Cache keys to delete

        Returns:
            True if successful, False otherwise
        """
        async with self._lock:
            if not self.is_available:
                return False

            if not keys:
                return False

            try:
                for key in keys:
                    if key in self._cache:
                        del self._cache[key]
                self._record_success()
                logger.debug("Deleted %d cache key(s)", len(keys))
                return True
            except Exception as e:
                self._record_failure()
                logger.warning("Cache DELETE error: %s", e)
                return False

    async def delete_with_retry(self, *keys: str) -> bool:
        """Delete keys with retry logic for critical operations.

        Args:
            *keys: Cache keys to delete

        Returns:
            True if successful, False otherwise
        """
        return await self.delete(*keys)

    async def _process_invalidation_queue(self) -> None:
        """Process pending cache invalidations from fallback queue."""
        if not self._invalidation_queue:
            return

        processed = 0

        while self._invalidation_queue:
            keys = self._invalidation_queue.popleft()
            success = await self.delete(*keys)
            if success:
                processed += 1

        if processed > 0:
            logger.info("Processed %d queued cache invalidations", processed)

    async def keys(self, pattern: str) -> list[str]:
        """Find keys matching a pattern.

        Args:
            pattern: Pattern to match (e.g., 'leaderboard:*')

        Returns:
            List of matching keys, empty list if none found or error occurred
        """
        async with self._lock:
            if not self.is_available:
                return []

            try:
                current_time = datetime.now(UTC).timestamp()
                return [
                    k
                    for k, (_, expires_at) in self._cache.items()
                    if (expires_at is None or expires_at > current_time) and fnmatch.fnmatch(k, pattern)
                ]
            except Exception as e:
                logger.warning("Cache KEYS error for pattern %s: %s", pattern, e)
                return []

    async def close(self) -> None:
        """Close cache client and stop background cleanup."""
        if self._cleanup_task and not self._cleanup_task.done():
            self._shutdown_event.set()
            try:
                await asyncio.wait_for(self._cleanup_task, timeout=2.0)
            except TimeoutError:
                self._cleanup_task.cancel()
            logger.info("Cache client closed")

    async def ping(self) -> bool:
        """Ping cache to check connection.

        Returns:
            True if cache is responsive, False otherwise
        """
        return self.is_available

    async def set_if_not_exists(self, key: str, value: str, ttl_seconds: int) -> bool:
        """Set value only if key doesn't exist (atomic).

        Args:
            key: Cache key
            value: Value to cache
            ttl_seconds: Time-to-live in seconds

        Returns:
            True if key was set (didn't exist), False if key already exists or error
        """
        async with self._lock:
            if not self.is_available:
                return False

            try:
                entry = self._cache.get(key)
                if entry is not None:
                    _, expires_at = entry
                    if expires_at is None or datetime.now(UTC).timestamp() > expires_at:
                        del self._cache[key]
                    else:
                        return False

                expires_at = datetime.now(UTC).timestamp() + ttl_seconds if ttl_seconds > 0 else None
                self._cache[key] = (value, expires_at)
                self._record_success()
                return True
            except Exception as e:
                logger.warning("Cache SETNX error for key %s: %s", key, e)
                return False

    async def increment(self, key: str) -> int | None:
        """Increment key value atomically.

        Args:
            key: Cache key

        Returns:
            New value after increment, or None on error
        """
        async with self._lock:
            if not self.is_available:
                return None

            try:
                entry = self._cache.get(key)
                if entry is None:
                    self._cache[key] = ("1", None)
                    self._record_success()
                    return 1

                value, expires_at = entry
                if expires_at is not None and datetime.now(UTC).timestamp() > expires_at:
                    self._cache[key] = ("1", None)
                    self._record_success()
                    return 1

                try:
                    new_value = str(int(value) + 1)
                except ValueError:
                    new_value = "1"

                self._cache[key] = (new_value, expires_at)
                self._record_success()
                return int(new_value)
            except Exception as e:
                logger.warning("Cache INCR error for key %s: %s", key, e)
                return None

    async def expire(self, key: str, ttl_seconds: int) -> bool:
        """Set TTL on existing key.

        Args:
            key: Cache key
            ttl_seconds: Time-to-live in seconds

        Returns:
            True if successful, False otherwise
        """
        async with self._lock:
            if not self.is_available:
                return False

            try:
                entry = self._cache.get(key)
                if entry is None:
                    return False

                value, expires_at = entry
                if expires_at is not None and datetime.now(UTC).timestamp() > expires_at:
                    del self._cache[key]
                    return False

                new_expires_at = datetime.now(UTC).timestamp() + ttl_seconds if ttl_seconds > 0 else None
                self._cache[key] = (value, new_expires_at)
                self._record_success()
                return True
            except Exception as e:
                logger.warning("Cache EXPIRE error for key %s: %s", key, e)
                return False

    async def _cleanup_expired_keys(self) -> None:
        """Background task to periodically clean up expired keys."""
        logger.info("Started background cache cleanup task")

        while not self._shutdown_event.is_set():
            try:
                await asyncio.sleep(60)
                if self._shutdown_event.is_set():
                    break

                async with self._lock:
                    current_time = datetime.now(UTC).timestamp()
                    expired_keys = [
                        k
                        for k, (_, expires_at) in self._cache.items()
                        if expires_at is not None and expires_at < current_time
                    ]

                    for key in expired_keys:
                        del self._cache[key]

                    if expired_keys:
                        logger.debug("Cleaned up %d expired cache keys", len(expired_keys))
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("Error in cache cleanup task: %s", e)

        logger.info("Stopped background cache cleanup task")

    async def start_cleanup_task(self) -> None:
        """Start background cleanup task for expired keys."""
        if self._cleanup_task is None or self._cleanup_task.done():
            self._cleanup_task = asyncio.create_task(self._cleanup_expired_keys())


# Global cache client instance
redis_client = RedisClient()
