"""Redis client for caching."""

import logging

from redis.asyncio import Redis
from redis.asyncio.connection import ConnectionPool
from redis.exceptions import RedisError

from src.core.config import settings


logger = logging.getLogger(__name__)


class RedisClient:
    """Async Redis client wrapper with connection pooling."""

    def __init__(self) -> None:
        """Initialize Redis client."""
        self._client: Redis | None = None
        self._pool: ConnectionPool | None = None
        self._enabled = bool(settings.redis_url)

        if self._enabled and settings.redis_url:
            try:
                # Create connection pool for efficient connection reuse
                self._pool = ConnectionPool.from_url(
                    settings.redis_url,
                    decode_responses=True,
                    max_connections=10,
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
            if value:
                logger.debug("Cache hit for key: %s", key)
            return value
        except RedisError as e:
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
            logger.debug("Cached key: %s (TTL: %ds)", key, ttl_seconds)
            return True
        except RedisError as e:
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
            logger.debug("Deleted %d cache key(s)", len(keys))
            return True
        except RedisError as e:
            logger.warning("Redis DELETE error: %s", e)
            return False

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


# Global Redis client instance
redis_client = RedisClient()
