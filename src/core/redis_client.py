"""Redis client for caching."""

import asyncio
import logging
from collections import deque
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from functools import wraps
from typing import Any, TypeVar

from redis.asyncio import Redis
from redis.asyncio.connection import ConnectionPool
from redis.exceptions import RedisError

from src.core.config import Constants, settings


logger = logging.getLogger(__name__)

# Type variable for generic retry decorator
T = TypeVar("T")


def with_retry(
    max_retries: int = 3, base_delay: float = 0.1
) -> Callable[[Callable[..., Coroutine[Any, Any, T]]], Callable[..., Coroutine[Any, Any, T]]]:
    """Decorator to retry async functions with exponential backoff.

    Args:
        max_retries: Maximum number of retry attempts (default: 3)
        base_delay: Base delay in seconds for exponential backoff (default: 0.1)

    Returns:
        Decorated function with retry logic
    """

    def decorator(func: Callable[..., Coroutine[Any, Any, T]]) -> Callable[..., Coroutine[Any, Any, T]]:
        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> T:  # noqa: ANN401
            last_exception = None
            for attempt in range(max_retries):
                try:
                    return await func(*args, **kwargs)
                except RedisError as e:
                    last_exception = e
                    if attempt < max_retries - 1:
                        delay = base_delay * (2**attempt)
                        logger.warning(
                            "Redis operation failed (attempt %d/%d): %s. Retrying in %.2fs",
                            attempt + 1,
                            max_retries,
                            e,
                            delay,
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            "Redis operation failed after %d attempts: %s",
                            max_retries,
                            e,
                        )
            # If we get here, all retries failed
            raise last_exception  # type: ignore[misc]

        return wrapper

    return decorator


class RedisClient:
    """Async Redis client wrapper with connection pooling."""

    def __init__(self) -> None:
        """Initialize Redis client."""
        self._client: Redis | None = None
        self._pool: ConnectionPool | None = None
        self._enabled = bool(settings.redis_url)

        # Health tracking
        self._last_successful_operation: datetime | None = None
        self._failure_count = 0
        self._total_operations = 0

        # Fallback queue for cache invalidation when Redis is unavailable
        self._invalidation_queue: deque[tuple[str, ...]] = deque(maxlen=Constants.REDIS_INVALIDATION_QUEUE_MAXLEN)

        if self._enabled and settings.redis_url:
            try:
                # Create connection pool for efficient connection reuse
                self._pool = ConnectionPool.from_url(
                    settings.redis_url,
                    decode_responses=True,
                    max_connections=Constants.REDIS_MAX_CONNECTIONS,
                )
                self._client = Redis(connection_pool=self._pool)
                logger.info("Redis client initialized with URL: %s", settings.redis_url)
            except RedisError as e:
                logger.warning("Failed to initialize Redis client: %s. Running without cache.", e)
                self._enabled = False
                self._client = None
                self._pool = None
        else:
            logger.info("Redis URL not configured. Running without cache.")

    @property
    def is_available(self) -> bool:
        """Check if Redis is available."""
        return self._enabled and self._client is not None

    def get_health_status(self) -> dict[str, Any]:
        """Get Redis health status.

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
        }

    def _record_success(self) -> None:
        """Record successful Redis operation."""
        self._last_successful_operation = datetime.now(UTC)
        self._total_operations += 1

    def _record_failure(self) -> None:
        """Record failed Redis operation."""
        self._failure_count += 1
        self._total_operations += 1

    async def get(self, key: str) -> str | None:
        """Get value from Redis.

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found or error occurred
        """
        if not self.is_available or not self._client:
            return None

        try:
            value = await self._client.get(key)
            self._record_success()
            if value:
                logger.debug("Cache hit for key: %s", key)
            return value
        except RedisError as e:
            self._record_failure()
            logger.warning("Redis GET error for key %s: %s", key, e)
            return None

    async def set(self, key: str, value: str, ttl_seconds: int) -> bool:
        """Set value in Redis with TTL.

        Args:
            key: Cache key
            value: Value to cache
            ttl_seconds: Time-to-live in seconds

        Returns:
            True if successful, False otherwise
        """
        if not self.is_available or not self._client:
            return False

        try:
            await self._client.setex(key, ttl_seconds, value)
            self._record_success()
            logger.debug("Cached key: %s (TTL: %ds)", key, ttl_seconds)
            return True
        except RedisError as e:
            self._record_failure()
            logger.warning("Redis SET error for key %s: %s", key, e)
            return False

    async def delete(self, *keys: str) -> bool:
        """Delete one or more keys from Redis.

        Args:
            *keys: Cache keys to delete

        Returns:
            True if successful, False otherwise
        """
        if not self.is_available or not self._client:
            return False

        if not keys:
            return False

        try:
            await self._client.delete(*keys)
            self._record_success()
            logger.debug("Deleted %d cache key(s)", len(keys))
            return True
        except RedisError as e:
            self._record_failure()
            logger.warning("Redis DELETE error: %s", e)
            return False

    async def delete_with_retry(self, *keys: str) -> bool:
        """Delete keys with retry logic for critical operations.

        Args:
            *keys: Cache keys to delete

        Returns:
            True if successful, False otherwise
        """
        if not self.is_available or not self._client:
            # Add to fallback queue for later processing
            self._invalidation_queue.append(keys)
            logger.info("Redis unavailable, queued %d key(s) for invalidation", len(keys))
            return False

        if not keys:
            return False

        @with_retry(max_retries=3, base_delay=0.1)
        async def _delete_operation() -> None:
            if self._client:
                await self._client.delete(*keys)

        try:
            await _delete_operation()
            self._record_success()
            logger.debug("Deleted %d cache key(s) with retry", len(keys))
            # Process any pending invalidations since Redis is now available
            await self._process_invalidation_queue()
            return True
        except RedisError as e:
            self._record_failure()
            # Add to fallback queue after retry attempts exhausted
            self._invalidation_queue.append(keys)
            logger.error("Redis DELETE failed after retries: %s. Queued for later.", e)
            return False

    async def _process_invalidation_queue(self) -> None:
        """Process pending cache invalidations from fallback queue."""
        if not self._invalidation_queue:
            return

        processed = 0
        failed = 0

        while self._invalidation_queue:
            keys = self._invalidation_queue.popleft()
            try:
                if self._client:
                    await self._client.delete(*keys)
                    processed += 1
                    self._record_success()
            except RedisError as e:
                self._record_failure()
                # Re-queue if still failing
                self._invalidation_queue.append(keys)
                failed += 1
                logger.warning("Failed to process queued invalidation: %s", e)
                break  # Stop processing to avoid infinite loop

        if processed > 0:
            logger.info("Processed %d queued cache invalidations", processed)
        if failed > 0:
            logger.warning("Failed to process %d queued invalidations", failed)

    async def keys(self, pattern: str) -> list[str]:
        """Find keys matching a pattern.

        Args:
            pattern: Pattern to match (e.g., 'leaderboard:*')

        Returns:
            List of matching keys, empty list if none found or error occurred
        """
        if not self.is_available or not self._client:
            return []

        try:
            keys = await self._client.keys(pattern)
            # Handle both bytes and string responses
            return [k.decode() if isinstance(k, bytes) else k for k in keys]
        except RedisError as e:
            logger.warning("Redis KEYS error for pattern %s: %s", pattern, e)
            return []

    async def close(self) -> None:
        """Close Redis connection."""
        if self._client:
            await self._client.aclose()
            logger.info("Redis client closed")

    async def ping(self) -> bool:
        """Ping Redis to check connection.

        Returns:
            True if Redis is responsive, False otherwise
        """
        if not self.is_available or not self._client:
            return False

        try:
            result = await self._client.ping()  # type: ignore[misc]
            return bool(result)
        except RedisError as e:
            logger.warning("Redis PING failed: %s", e)
            return False

    async def set_if_not_exists(self, key: str, value: str, ttl_seconds: int) -> bool:
        """Set value only if key doesn't exist (atomic).

        Args:
            key: Cache key
            value: Value to cache
            ttl_seconds: Time-to-live in seconds

        Returns:
            True if key was set (didn't exist), False if key already exists or error
        """
        if not self.is_available or not self._client:
            return False

        try:
            result = await self._client.set(key, value, ex=ttl_seconds, nx=True)
            return bool(result)
        except RedisError as e:
            logger.warning("Redis SETNX error for key %s: %s", key, e)
            return False

    async def increment(self, key: str) -> int | None:
        """Increment key value atomically.

        Args:
            key: Cache key

        Returns:
            New value after increment, or None on error
        """
        if not self.is_available or not self._client:
            return None

        try:
            return await self._client.incr(key)
        except RedisError as e:
            logger.warning("Redis INCR error for key %s: %s", key, e)
            return None

    async def expire(self, key: str, ttl_seconds: int) -> bool:
        """Set TTL on existing key.

        Args:
            key: Cache key
            ttl_seconds: Time-to-live in seconds

        Returns:
            True if successful, False otherwise
        """
        if not self.is_available or not self._client:
            return False

        try:
            await self._client.expire(key, ttl_seconds)
            return True
        except RedisError as e:
            logger.warning("Redis EXPIRE error for key %s: %s", key, e)
            return False


# Global Redis client instance
redis_client = RedisClient()
