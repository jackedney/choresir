"""Tests for rate limiting functionality."""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from src.core.rate_limiter import RateLimiter


@pytest.fixture
def rate_limiter():
    """Create a RateLimiter instance."""
    return RateLimiter()


@pytest.mark.asyncio
async def test_check_rate_limit_within_limit(rate_limiter):
    """Test rate limit check passes when within limit."""
    with patch("src.core.rate_limiter.redis_client") as mock_redis:
        mock_redis.is_available = True
        mock_redis.increment = AsyncMock(return_value=5)
        mock_redis.expire = AsyncMock(return_value=True)

        # Should not raise
        await rate_limiter.check_rate_limit(
            scope="test",
            identifier="user1",
            limit=10,
            window_seconds=60,
        )

        mock_redis.increment.assert_called_once()
        mock_redis.expire.assert_not_called()  # Not first request


@pytest.mark.asyncio
async def test_check_rate_limit_first_request_sets_expiry(rate_limiter):
    """Test that first request sets TTL on key."""
    with patch("src.core.rate_limiter.redis_client") as mock_redis:
        mock_redis.is_available = True
        mock_redis.increment = AsyncMock(return_value=1)
        mock_redis.expire = AsyncMock(return_value=True)

        await rate_limiter.check_rate_limit(
            scope="test",
            identifier="user1",
            limit=10,
            window_seconds=60,
        )

        mock_redis.increment.assert_called_once()
        mock_redis.expire.assert_called_once()
        call_args = mock_redis.expire.call_args
        assert call_args[0][1] == 60  # TTL should be window_seconds


@pytest.mark.asyncio
async def test_check_rate_limit_exceeds_limit(rate_limiter):
    """Test rate limit check raises exception when limit exceeded."""
    with patch("src.core.rate_limiter.redis_client") as mock_redis:
        mock_redis.is_available = True
        mock_redis.increment = AsyncMock(return_value=11)

        with pytest.raises(HTTPException) as exc_info:
            await rate_limiter.check_rate_limit(
                scope="test",
                identifier="user1",
                limit=10,
                window_seconds=60,
            )

        exc = exc_info.value
        assert isinstance(exc, HTTPException)
        assert exc.status_code == 429
        assert exc.detail == "Too many requests"
        assert exc.headers is not None
        assert exc.headers.get("X-RateLimit-Limit") == "10"
        retry_after = int(exc.headers.get("Retry-After", "0"))
        assert 0 < retry_after <= 60


@pytest.mark.asyncio
async def test_check_rate_limit_redis_unavailable(rate_limiter):
    """Test rate limit check passes when Redis is unavailable."""
    with patch("src.core.rate_limiter.redis_client") as mock_redis:
        mock_redis.is_available = False

        # Should not raise - fail open
        await rate_limiter.check_rate_limit(
            scope="test",
            identifier="user1",
            limit=10,
            window_seconds=60,
        )


@pytest.mark.asyncio
async def test_check_rate_limit_redis_error(rate_limiter):
    """Test rate limit check handles Redis errors gracefully."""
    with patch("src.core.rate_limiter.redis_client") as mock_redis:
        mock_redis.is_available = True
        mock_redis.increment = AsyncMock(side_effect=Exception("Redis error"))

        # Should not raise - fail open
        await rate_limiter.check_rate_limit(
            scope="test",
            identifier="user1",
            limit=10,
            window_seconds=60,
        )


@pytest.mark.asyncio
async def test_check_rate_limit_increment_returns_none(rate_limiter):
    """Test rate limit check handles None return from increment."""
    with patch("src.core.rate_limiter.redis_client") as mock_redis:
        mock_redis.is_available = True
        mock_redis.increment = AsyncMock(return_value=None)

        # Should not raise - fail open
        await rate_limiter.check_rate_limit(
            scope="test",
            identifier="user1",
            limit=10,
            window_seconds=60,
        )


@pytest.mark.asyncio
async def test_check_webhook_rate_limit(rate_limiter):
    """Test webhook rate limit uses correct parameters."""
    with patch.object(rate_limiter, "check_rate_limit") as mock_check:
        mock_check.return_value = None

        await rate_limiter.check_webhook_rate_limit()

        mock_check.assert_called_once()
        call_args = mock_check.call_args[1]
        assert call_args["scope"] == "webhook"
        assert call_args["identifier"] == "global"
        assert call_args["window_seconds"] == 60


@pytest.mark.asyncio
async def test_check_agent_rate_limit(rate_limiter):
    """Test agent rate limit uses correct parameters."""
    with patch.object(rate_limiter, "check_rate_limit") as mock_check:
        mock_check.return_value = None

        await rate_limiter.check_agent_rate_limit("user123")

        mock_check.assert_called_once()
        call_args = mock_check.call_args[1]
        assert call_args["scope"] == "agent"
        assert call_args["identifier"] == "user123"
        assert call_args["window_seconds"] == 3600


@pytest.mark.asyncio
async def test_rate_limit_sliding_window_key_format(rate_limiter):
    """Test that rate limit keys use correct sliding window format."""
    with patch("src.core.rate_limiter.redis_client") as mock_redis:
        mock_redis.is_available = True
        mock_redis.increment = AsyncMock(return_value=1)
        mock_redis.expire = AsyncMock(return_value=True)

        await rate_limiter.check_rate_limit(
            scope="test",
            identifier="user1",
            limit=10,
            window_seconds=60,
        )

        # Verify key format: ratelimit:scope:identifier:window_start
        call_args = mock_redis.increment.call_args[0][0]
        assert call_args.startswith("ratelimit:test:user1:")
        assert call_args.count(":") == 3


def test_rate_limit_exceeded_exception():
    """Test HTTPException with rate limit headers."""
    exc = HTTPException(
        status_code=429,
        detail="Too many requests",
        headers={
            "Retry-After": "30",
            "X-RateLimit-Limit": "50",
        },
    )

    assert exc.status_code == 429
    assert exc.detail == "Too many requests"
    assert exc.headers is not None
    assert exc.headers.get("Retry-After") == "30"
    assert exc.headers.get("X-RateLimit-Limit") == "50"
