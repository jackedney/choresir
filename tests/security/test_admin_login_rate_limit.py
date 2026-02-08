from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException, Request, status

from src.interface.admin_router import check_login_rate_limit


@pytest.mark.asyncio
async def test_check_login_rate_limit_success():
    """Test rate limit check passes when under limit."""
    with patch("src.interface.admin_router.redis_client") as mock_redis:
        mock_redis.is_available = True
        mock_redis.increment = AsyncMock(return_value=1)
        mock_redis.expire = AsyncMock()

        request = AsyncMock(spec=Request)
        request.client.host = "127.0.0.1"

        await check_login_rate_limit(request)

        mock_redis.increment.assert_called_once()
        mock_redis.expire.assert_called_once()


@pytest.mark.asyncio
async def test_check_login_rate_limit_exceeded():
    """Test rate limit check raises 429 when limit exceeded."""
    with patch("src.interface.admin_router.redis_client") as mock_redis:
        mock_redis.is_available = True
        mock_redis.increment = AsyncMock(return_value=6)

        request = AsyncMock(spec=Request)
        request.client.host = "127.0.0.1"

        with pytest.raises(HTTPException) as exc:
            await check_login_rate_limit(request)

        assert exc.value.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert "Too many login attempts" in exc.value.detail


@pytest.mark.asyncio
async def test_check_login_rate_limit_redis_unavailable():
    """Test rate limit check passes when Redis is unavailable."""
    with patch("src.interface.admin_router.redis_client") as mock_redis:
        mock_redis.is_available = False

        request = AsyncMock(spec=Request)

        # Should not raise exception
        await check_login_rate_limit(request)

        mock_redis.increment.assert_not_called()


def test_login_endpoint_rate_limit_integration(test_client):
    """Test the login endpoint returns 429 when rate limit is hit."""
    with patch("src.interface.admin_router.redis_client") as mock_redis:
        mock_redis.is_available = True
        # Mock increment to return 6 (exceeded)
        mock_redis.increment = AsyncMock(return_value=6)

        response = test_client.post(
            "/admin/login",
            data={"password": "wrongpassword"},
        )

        assert response.status_code == status.HTTP_429_TOO_MANY_REQUESTS
        assert "Too many login attempts" in response.json()["detail"]
