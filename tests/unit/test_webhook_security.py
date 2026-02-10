"""Tests for webhook security module."""

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from src.interface.webhook_security import (
    validate_webhook_nonce,
    validate_webhook_rate_limit,
    validate_webhook_timestamp,
    verify_webhook_security,
)


class TestValidateWebhookTimestamp:
    """Test webhook timestamp validation."""

    @pytest.mark.asyncio
    async def test_valid_timestamp(self):
        """Test validation passes for recent timestamp."""
        current_timestamp = str(int(datetime.now().timestamp()))
        result = await validate_webhook_timestamp(current_timestamp)

        assert result.is_valid is True
        assert result.error_message is None
        assert result.http_status_code is None

    @pytest.mark.asyncio
    async def test_expired_timestamp(self):
        """Test validation fails for expired timestamp."""
        old_timestamp = str(int(datetime.now().timestamp()) - 400)
        result = await validate_webhook_timestamp(old_timestamp)

        assert result.is_valid is False
        assert result.error_message is not None
        assert "expired" in result.error_message.lower()
        assert result.http_status_code == 400

    @pytest.mark.asyncio
    async def test_future_timestamp(self):
        """Test validation fails for future timestamp."""
        future_timestamp = str(int(datetime.now().timestamp()) + 100)
        result = await validate_webhook_timestamp(future_timestamp)

        assert result.is_valid is False
        assert result.error_message is not None
        assert "future" in result.error_message.lower()
        assert result.http_status_code == 400

    @pytest.mark.asyncio
    async def test_invalid_timestamp_format(self):
        """Test validation fails for invalid timestamp format."""
        result = await validate_webhook_timestamp("not_a_number")

        assert result.is_valid is False
        assert result.error_message is not None
        assert "format" in result.error_message.lower()
        assert result.http_status_code == 400


class TestValidateWebhookNonce:
    """Test webhook nonce validation."""

    @pytest.mark.asyncio
    @patch("src.interface.webhook_security.cache_client")
    async def test_first_webhook_accepted(self, mock_cache):
        """Test first webhook with message ID is accepted."""
        mock_cache.is_available = True
        mock_cache.set_if_not_exists = AsyncMock(return_value=True)

        result = await validate_webhook_nonce("MSG123")

        assert result.is_valid is True
        assert result.error_message is None

    @pytest.mark.asyncio
    @patch("src.interface.webhook_security.cache_client")
    async def test_duplicate_webhook_rejected(self, mock_cache):
        """Test duplicate webhook is rejected with 200 status to prevent retries."""
        mock_cache.is_available = True
        mock_cache.set_if_not_exists = AsyncMock(return_value=False)

        result = await validate_webhook_nonce("MSG123")

        assert result.is_valid is False
        assert result.error_message is not None
        assert "duplicate" in result.error_message.lower()
        # Returns 200 to prevent WhatsApp from retrying duplicate messages
        assert result.http_status_code == 200

    @pytest.mark.asyncio
    @patch("src.interface.webhook_security.cache_client")
    async def test_cache_unavailable_allows_webhook(self, mock_cache):
        """Test webhook allowed when cache unavailable."""
        mock_cache.is_available = False

        result = await validate_webhook_nonce("MSG123")

        assert result.is_valid is True


class TestValidateWebhookRateLimit:
    """Test webhook rate limiting."""

    @pytest.mark.asyncio
    @patch("src.interface.webhook_security.cache_client")
    async def test_within_rate_limit(self, mock_cache):
        """Test webhook accepted within rate limit."""
        mock_cache.is_available = True
        mock_cache.increment = AsyncMock(return_value=5)
        mock_cache.expire = AsyncMock(return_value=True)

        result = await validate_webhook_rate_limit("+1234567890")

        assert result.is_valid is True
        assert result.error_message is None

    @pytest.mark.asyncio
    @patch("src.interface.webhook_security.cache_client")
    async def test_exceeds_rate_limit(self, mock_cache):
        """Test webhook rejected when rate limit exceeded."""
        mock_cache.is_available = True
        mock_cache.increment = AsyncMock(return_value=25)

        result = await validate_webhook_rate_limit("+1234567890")

        assert result.is_valid is False
        assert result.error_message is not None
        assert "rate limit" in result.error_message.lower()
        assert result.http_status_code == 429

    @pytest.mark.asyncio
    @patch("src.interface.webhook_security.cache_client")
    async def test_first_request_sets_ttl(self, mock_cache):
        """Test TTL set on first request."""
        mock_cache.is_available = True
        mock_cache.increment = AsyncMock(return_value=1)
        mock_cache.expire = AsyncMock(return_value=True)

        await validate_webhook_rate_limit("+1234567890")

        mock_cache.expire.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.interface.webhook_security.cache_client")
    async def test_cache_unavailable_allows_webhook(self, mock_cache):
        """Test webhook allowed when cache unavailable."""
        mock_cache.is_available = False

        result = await validate_webhook_rate_limit("+1234567890")

        assert result.is_valid is True


class TestVerifyWebhookSecurity:
    """Test complete webhook security validation."""

    @pytest.mark.asyncio
    @patch("src.interface.webhook_security.cache_client")
    async def test_all_checks_pass(self, mock_cache):
        """Test webhook accepted when all checks pass."""
        mock_cache.is_available = True
        mock_cache.set_if_not_exists = AsyncMock(return_value=True)
        mock_cache.increment = AsyncMock(return_value=5)
        mock_cache.expire = AsyncMock(return_value=True)

        current_timestamp = str(int(datetime.now().timestamp()))
        result = await verify_webhook_security("MSG123", current_timestamp, "+1234567890")

        assert result.is_valid is True
        assert result.error_message is None

    @pytest.mark.asyncio
    @patch("src.interface.webhook_security.cache_client")
    async def test_timestamp_failure_stops_further_checks(self, mock_cache):
        """Test that timestamp failure prevents further checks."""
        mock_cache.is_available = True

        old_timestamp = str(int(datetime.now().timestamp()) - 400)
        result = await verify_webhook_security("MSG123", old_timestamp, "+1234567890")

        assert result.is_valid is False
        assert result.error_message is not None
        assert "expired" in result.error_message.lower()
        mock_cache.set_if_not_exists.assert_not_called()

    @pytest.mark.asyncio
    @patch("src.interface.webhook_security.cache_client")
    async def test_nonce_failure_stops_rate_limit_check(self, mock_cache):
        """Test that nonce failure prevents rate limit check."""
        mock_cache.is_available = True
        mock_cache.set_if_not_exists = AsyncMock(return_value=False)

        current_timestamp = str(int(datetime.now().timestamp()))
        result = await verify_webhook_security("MSG123", current_timestamp, "+1234567890")

        assert result.is_valid is False
        assert result.error_message is not None
        assert "duplicate" in result.error_message.lower()
        mock_cache.increment.assert_not_called()
