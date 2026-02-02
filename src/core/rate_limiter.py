"""Rate limiting middleware using Redis sliding window algorithm."""

import logging
from datetime import UTC, datetime

from fastapi import HTTPException

from src.core.config import Constants
from src.core.redis_client import redis_client


logger = logging.getLogger(__name__)


class RateLimiter:
    """Rate limiter using Redis sliding window algorithm."""

    async def check_rate_limit(
        self,
        scope: str,
        identifier: str,
        limit: int,
        window_seconds: int,
    ) -> None:
        """Check if request is within rate limit.

        Uses Redis sliding window algorithm:
        - Increment counter for the current window
        - Set expiry on first increment
        - Raise exception if limit exceeded

        Args:
            scope: Rate limit scope (e.g., 'webhook', 'agent')
            identifier: Unique identifier (e.g., user_id, 'global')
            limit: Maximum requests allowed
            window_seconds: Time window in seconds

        Raises:
            RateLimitExceeded: If rate limit is exceeded
        """
        if not redis_client.is_available:
            logger.debug("rate_limit_check_skipped", extra={"reason": "redis_unavailable"})
            return

        # Generate key for current window
        now = datetime.now(UTC)
        window_start = int(now.timestamp()) // window_seconds
        key = f"ratelimit:{scope}:{identifier}:{window_start}"

        try:
            # Increment counter
            count = await redis_client.increment(key)

            if count is None:
                logger.warning("rate_limit_check_failed", extra={"reason": "redis_increment_failed"})
                return

            # Set expiry on first increment
            if count == 1:
                await redis_client.expire(key, window_seconds)

            # Check if limit exceeded
            if count > limit:
                retry_after = window_seconds - (int(now.timestamp()) % window_seconds)
                logger.warning(
                    "rate_limit_exceeded",
                    extra={
                        "scope": scope,
                        "identifier": identifier,
                        "count": count,
                        "limit": limit,
                        "retry_after": retry_after,
                    },
                )
                raise HTTPException(
                    status_code=429,
                    detail="Too many requests",
                    headers={
                        "Retry-After": str(retry_after),
                        "X-RateLimit-Limit": str(limit),
                    },
                )

            logger.debug(
                "rate_limit_check_passed",
                extra={
                    "scope": scope,
                    "identifier": identifier,
                    "count": count,
                    "limit": limit,
                },
            )

        except HTTPException:
            raise
        except (RuntimeError, ConnectionError, OSError):
            logger.exception("rate_limit_check_error")
            # Fail open - don't block requests if rate limiting fails
            return

    async def check_webhook_rate_limit(self) -> None:
        """Check global webhook rate limit."""
        await self.check_rate_limit(
            scope="webhook",
            identifier="global",
            limit=Constants.MAX_REQUESTS_PER_MINUTE,
            window_seconds=60,
        )

    async def check_agent_rate_limit(self, user_id: str) -> None:
        """Check per-user agent call rate limit.

        Args:
            user_id: User identifier (phone number or user ID)
        """
        await self.check_rate_limit(
            scope="agent",
            identifier=user_id,
            limit=Constants.MAX_AGENT_CALLS_PER_USER_PER_HOUR,
            window_seconds=3600,
        )


# Global rate limiter instance
rate_limiter = RateLimiter()
