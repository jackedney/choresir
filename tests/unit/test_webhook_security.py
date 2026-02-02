"""Tests for webhook security module."""

import hashlib
import hmac
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from src.interface.webhook_security import (
    validate_webhook_hmac,
    validate_webhook_nonce,
    validate_webhook_rate_limit,
    validate_webhook_timestamp,
    verify_webhook_security,
)


class TestValidateWebhookTimestamp:
    """Test webhook timestamp validation."""

    @pytest.mark.asyncio
    async def test_valid_timestamp(self) -> None:
        """Test validation passes for recent timestamp."""
        current_timestamp = str(int(datetime.now().timestamp()))
        result = await validate_webhook_timestamp(current_timestamp)

        assert result.is_valid is True
        assert result.error_message is None
        assert result.http_status_code is None

    @pytest.mark.asyncio
    async def test_expired_timestamp(self) -> None:
        """Test validation fails for expired timestamp."""
        old_timestamp = str(int(datetime.now().timestamp()) - 400)
        result = await validate_webhook_timestamp(old_timestamp)

        assert result.is_valid is False
        assert result.error_message is not None
        assert "expired" in result.error_message.lower()
        assert result.http_status_code == 400

    @pytest.mark.asyncio
    async def test_future_timestamp(self) -> None:
        """Test validation fails for future timestamp."""
        future_timestamp = str(int(datetime.now().timestamp()) + 100)
        result = await validate_webhook_timestamp(future_timestamp)

        assert result.is_valid is False
        assert result.error_message is not None
        assert "future" in result.error_message.lower()
        assert result.http_status_code == 400

    @pytest.mark.asyncio
    async def test_invalid_timestamp_format(self) -> None:
        """Test validation fails for invalid timestamp format."""
        result = await validate_webhook_timestamp("not_a_number")

        assert result.is_valid is False
        assert result.error_message is not None
        assert "format" in result.error_message.lower()
        assert result.http_status_code == 400


class TestValidateWebhookHmac:
    """Test webhook HMAC validation."""

    def test_valid_hmac_signature(self) -> None:
        """Test validation passes for valid HMAC signature."""
        secret = "test_secret_key_123"
        body = b'{"message": "test"}'
        signature = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

        result = validate_webhook_hmac(raw_body=body, signature=signature, secret=secret)

        assert result.is_valid is True
        assert result.error_message is None
        assert result.http_status_code is None

    def test_missing_hmac_header(self) -> None:
        """Test validation fails with 401 when header is missing."""
        secret = "test_secret_key_123"
        body = b'{"message": "test"}'

        result = validate_webhook_hmac(raw_body=body, signature=None, secret=secret)

        assert result.is_valid is False
        assert result.error_message == "Missing webhook signature"
        assert result.http_status_code == 401

    def test_invalid_hmac_signature(self) -> None:
        """Test validation fails with 401 for invalid signature."""
        secret = "test_secret_key_123"
        body = b'{"message": "test"}'
        wrong_signature = "invalid_signature_1234567890"

        result = validate_webhook_hmac(raw_body=body, signature=wrong_signature, secret=secret)

        assert result.is_valid is False
        assert result.error_message == "Invalid webhook signature"
        assert result.http_status_code == 401


class TestValidateWebhookNonce:
    """Test webhook nonce validation."""

    @pytest.mark.asyncio
    @patch("src.interface.webhook_security.redis_client")
    async def test_first_webhook_accepted(self, mock_redis) -> None:
        """Test first webhook with message ID is accepted."""
        mock_redis.is_available = True
        mock_redis.set_if_not_exists = AsyncMock(return_value=True)

        result = await validate_webhook_nonce("MSG123")

        assert result.is_valid is True
        assert result.error_message is None

    @pytest.mark.asyncio
    @patch("src.interface.webhook_security.redis_client")
    async def test_duplicate_webhook_rejected(self, mock_redis) -> None:
        """Test duplicate webhook is rejected."""
        mock_redis.is_available = True
        mock_redis.set_if_not_exists = AsyncMock(return_value=False)

        result = await validate_webhook_nonce("MSG123")

        assert result.is_valid is False
        assert result.error_message is not None
        assert "duplicate" in result.error_message.lower()
        assert result.http_status_code == 400

    @pytest.mark.asyncio
    @patch("src.interface.webhook_security.redis_client")
    async def test_redis_unavailable_allows_webhook(self, mock_redis) -> None:
        """Test webhook allowed when Redis unavailable."""
        mock_redis.is_available = False

        result = await validate_webhook_nonce("MSG123")

        assert result.is_valid is True


class TestValidateWebhookRateLimit:
    """Test webhook rate limiting."""

    @pytest.mark.asyncio
    @patch("src.interface.webhook_security.redis_client")
    async def test_within_rate_limit(self, mock_redis) -> None:
        """Test webhook accepted within rate limit."""
        mock_redis.is_available = True
        mock_redis.increment = AsyncMock(return_value=5)
        mock_redis.expire = AsyncMock(return_value=True)

        result = await validate_webhook_rate_limit("+1234567890")

        assert result.is_valid is True
        assert result.error_message is None

    @pytest.mark.asyncio
    @patch("src.interface.webhook_security.redis_client")
    async def test_exceeds_rate_limit(self, mock_redis) -> None:
        """Test webhook rejected when rate limit exceeded."""
        mock_redis.is_available = True
        mock_redis.increment = AsyncMock(return_value=25)

        result = await validate_webhook_rate_limit("+1234567890")

        assert result.is_valid is False
        assert result.error_message is not None
        assert "rate limit" in result.error_message.lower()
        assert result.http_status_code == 429

    @pytest.mark.asyncio
    @patch("src.interface.webhook_security.redis_client")
    async def test_first_request_sets_ttl(self, mock_redis) -> None:
        """Test TTL set on first request."""
        mock_redis.is_available = True
        mock_redis.increment = AsyncMock(return_value=1)
        mock_redis.expire = AsyncMock(return_value=True)

        await validate_webhook_rate_limit("+1234567890")

        mock_redis.expire.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.interface.webhook_security.redis_client")
    async def test_redis_unavailable_allows_webhook(self, mock_redis) -> None:
        """Test webhook allowed when Redis unavailable."""
        mock_redis.is_available = False

        result = await validate_webhook_rate_limit("+1234567890")

        assert result.is_valid is True


class TestVerifyWebhookSecurity:
    """Test complete webhook security validation."""

    @pytest.mark.asyncio
    @patch("src.interface.webhook_security.redis_client")
    async def test_all_checks_pass(self, mock_redis) -> None:
        """Test webhook accepted when all checks pass."""
        mock_redis.is_available = True
        mock_redis.set_if_not_exists = AsyncMock(return_value=True)
        mock_redis.increment = AsyncMock(return_value=5)
        mock_redis.expire = AsyncMock(return_value=True)

        current_timestamp = str(int(datetime.now().timestamp()))
        result = await verify_webhook_security("MSG123", current_timestamp, "+1234567890")

        assert result.is_valid is True
        assert result.error_message is None

    @pytest.mark.asyncio
    @patch("src.interface.webhook_security.redis_client")
    async def test_timestamp_failure_stops_further_checks(self, mock_redis) -> None:
        """Test that timestamp failure prevents further checks."""
        mock_redis.is_available = True

        old_timestamp = str(int(datetime.now().timestamp()) - 400)
        result = await verify_webhook_security("MSG123", old_timestamp, "+1234567890")

        assert result.is_valid is False
        assert result.error_message is not None
        assert "expired" in result.error_message.lower()
        mock_redis.set_if_not_exists.assert_not_called()

    @pytest.mark.asyncio
    @patch("src.interface.webhook_security.redis_client")
    async def test_nonce_failure_stops_rate_limit_check(self, mock_redis) -> None:
        """Test that nonce failure prevents rate limit check."""
        mock_redis.is_available = True
        mock_redis.set_if_not_exists = AsyncMock(return_value=False)

        current_timestamp = str(int(datetime.now().timestamp()))
        result = await verify_webhook_security("MSG123", current_timestamp, "+1234567890")

        assert result.is_valid is False
        assert result.error_message is not None
        assert "duplicate" in result.error_message.lower()
        mock_redis.increment.assert_not_called()
