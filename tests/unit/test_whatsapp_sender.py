"""Tests for WhatsApp message sender with mocked Twilio client."""

from unittest.mock import MagicMock, patch

import pytest
from twilio.base.exceptions import TwilioRestException

import src.interface.whatsapp_sender as sender_module
from src.interface.whatsapp_sender import (
    RateLimiter,
    get_twilio_client,
    send_text_message,
)


class TestRateLimiter:
    """Test rate limiting functionality."""

    def test_can_send_when_under_limit(self):
        """Test that sending is allowed when under rate limit."""
        limiter = RateLimiter()
        phone = "+1234567890"

        # Should allow sending when no requests recorded
        assert limiter.can_send(phone) is True

        # Record some requests (under limit)
        for _ in range(5):
            limiter.record_request(phone)

        # Should still allow
        assert limiter.can_send(phone) is True

    def test_cannot_send_when_at_limit(self):
        """Test that sending is blocked when at rate limit."""
        limiter = RateLimiter()
        phone = "+1234567890"

        # Record max requests (60 per minute based on constants.MAX_REQUESTS_PER_MINUTE)
        # Assuming default limit is 60
        for _ in range(60):
            limiter.record_request(phone)

        # Should block
        assert limiter.can_send(phone) is False

    def test_rate_limit_per_phone(self):
        """Test that rate limits are tracked per phone number."""
        limiter = RateLimiter()
        phone1 = "+1234567890"
        phone2 = "+9876543210"

        # Max out phone1
        for _ in range(60):
            limiter.record_request(phone1)

        # phone1 should be blocked
        assert limiter.can_send(phone1) is False

        # phone2 should be allowed
        assert limiter.can_send(phone2) is True


class TestSendTextMessage:
    """Test sending text messages via Twilio."""

    @pytest.mark.asyncio
    @patch("src.interface.whatsapp_sender.get_twilio_client")
    async def test_send_text_message_success(self, mock_get_client):
        """Test successful message sending."""
        # Setup mock
        mock_client = MagicMock()
        mock_message = MagicMock()
        mock_message.sid = "SM123abc"
        mock_client.messages.create.return_value = mock_message
        mock_get_client.return_value = mock_client

        # Send message
        result = await send_text_message(
            to_phone="+1234567890",
            text="Hello, test message",
        )

        # Verify result
        assert result.success is True
        assert result.message_id == "SM123abc"
        assert result.error is None

        # Verify Twilio API was called correctly
        mock_client.messages.create.assert_called_once()
        call_args = mock_client.messages.create.call_args
        assert call_args.kwargs["to"] == "whatsapp:+1234567890"
        assert call_args.kwargs["body"] == "Hello, test message"

    @pytest.mark.asyncio
    @patch("src.interface.whatsapp_sender.get_twilio_client")
    async def test_send_text_message_handles_whatsapp_prefix(self, mock_get_client):
        """Test that whatsapp: prefix is added if missing."""
        mock_client = MagicMock()
        mock_message = MagicMock()
        mock_message.sid = "SM456"
        mock_client.messages.create.return_value = mock_message
        mock_get_client.return_value = mock_client

        # Send with phone number (no prefix)
        await send_text_message(to_phone="+1234567890", text="Test")

        # Verify prefix was added
        call_args = mock_client.messages.create.call_args
        assert call_args.kwargs["to"] == "whatsapp:+1234567890"

    @pytest.mark.asyncio
    @patch("src.interface.whatsapp_sender.get_twilio_client")
    async def test_send_text_message_preserves_whatsapp_prefix(self, mock_get_client):
        """Test that existing whatsapp: prefix is preserved."""
        mock_client = MagicMock()
        mock_message = MagicMock()
        mock_message.sid = "SM789"
        mock_client.messages.create.return_value = mock_message
        mock_get_client.return_value = mock_client

        # Send with whatsapp: prefix already present
        await send_text_message(to_phone="whatsapp:+1234567890", text="Test")

        # Verify prefix not duplicated
        call_args = mock_client.messages.create.call_args
        assert call_args.kwargs["to"] == "whatsapp:+1234567890"
        assert "whatsapp:whatsapp:" not in call_args.kwargs["to"]

    @pytest.mark.asyncio
    @patch("src.interface.whatsapp_sender.get_twilio_client")
    async def test_send_text_message_client_error(self, mock_get_client):
        """Test handling of 4xx client errors (no retry)."""
        mock_client = MagicMock()
        # Simulate a 400 Bad Request error
        error = TwilioRestException(
            status=400,
            uri="/Messages.json",
            msg="Invalid phone number",
            code=21211,
        )
        mock_client.messages.create.side_effect = error
        mock_get_client.return_value = mock_client

        result = await send_text_message(to_phone="+1234567890", text="Test")

        # Should fail without retry
        assert result.success is False
        assert result.error is not None
        assert "Client error" in result.error
        assert "Invalid phone number" in result.error

        # Should only try once (no retries on 4xx)
        assert mock_client.messages.create.call_count == 1

    @pytest.mark.asyncio
    @patch("src.interface.whatsapp_sender.get_twilio_client")
    async def test_send_text_message_server_error_with_retry(self, mock_get_client):
        """Test retry logic on 5xx server errors."""
        mock_client = MagicMock()
        # Simulate a 500 server error
        error = TwilioRestException(
            status=500,
            uri="/Messages.json",
            msg="Internal server error",
            code=20500,
        )
        mock_client.messages.create.side_effect = error
        mock_get_client.return_value = mock_client

        result = await send_text_message(
            to_phone="+1234567890",
            text="Test",
            max_retries=3,
            retry_delay=0.01,  # Fast retry for testing
        )

        # Should fail after retries
        assert result.success is False
        assert result.error == "Max retries exceeded"

        # Should retry 3 times
        assert mock_client.messages.create.call_count == 3

    @pytest.mark.asyncio
    @patch("src.interface.whatsapp_sender.get_twilio_client")
    async def test_send_text_message_retry_then_success(self, mock_get_client):
        """Test successful send after initial failures."""
        mock_client = MagicMock()
        mock_message = MagicMock()
        mock_message.sid = "SM999"

        # First two calls fail, third succeeds
        error = TwilioRestException(status=500, uri="/Messages.json", msg="Error", code=20500)
        mock_client.messages.create.side_effect = [error, error, mock_message]
        mock_get_client.return_value = mock_client

        result = await send_text_message(
            to_phone="+1234567890",
            text="Test",
            max_retries=3,
            retry_delay=0.01,
        )

        # Should eventually succeed
        assert result.success is True
        assert result.message_id == "SM999"

        # Should have tried 3 times
        assert mock_client.messages.create.call_count == 3

    @pytest.mark.asyncio
    @patch("src.interface.whatsapp_sender.rate_limiter")
    async def test_send_text_message_rate_limited(self, mock_rate_limiter):
        """Test that rate limiting blocks message sending."""
        # Mock rate limiter to deny request
        mock_rate_limiter.can_send.return_value = False

        result = await send_text_message(to_phone="+1234567890", text="Test")

        # Should fail due to rate limit
        assert result.success is False
        assert result.error is not None
        assert "Rate limit exceeded" in result.error

    @pytest.mark.asyncio
    @patch("src.interface.whatsapp_sender.get_twilio_client")
    @patch("src.interface.whatsapp_sender.rate_limiter")
    async def test_rate_limiter_records_request(self, mock_rate_limiter, mock_get_client):
        """Test that rate limiter records successful requests."""
        mock_rate_limiter.can_send.return_value = True

        mock_client = MagicMock()
        mock_message = MagicMock()
        mock_message.sid = "SM111"
        mock_client.messages.create.return_value = mock_message
        mock_get_client.return_value = mock_client

        phone = "+1234567890"
        await send_text_message(to_phone=phone, text="Test")

        # Verify rate limiter was checked and request was recorded
        mock_rate_limiter.can_send.assert_called_once_with(phone)
        mock_rate_limiter.record_request.assert_called_once_with(phone)

    @pytest.mark.asyncio
    @patch("src.interface.whatsapp_sender.get_twilio_client")
    async def test_send_text_message_unexpected_error(self, mock_get_client):
        """Test handling of unexpected errors."""
        mock_client = MagicMock()
        # Simulate unexpected exception
        mock_client.messages.create.side_effect = Exception("Unexpected error")
        mock_get_client.return_value = mock_client

        result = await send_text_message(
            to_phone="+1234567890",
            text="Test",
            max_retries=2,
            retry_delay=0.01,
        )

        # Should fail after retries
        assert result.success is False
        assert result.error == "Max retries exceeded"

        # Should retry
        assert mock_client.messages.create.call_count == 2


class TestGetTwilioClient:
    """Test Twilio client singleton."""

    @patch("src.interface.whatsapp_sender.Client")
    @patch("src.interface.whatsapp_sender.settings")
    def test_get_twilio_client_creates_client(self, mock_settings, mock_client_class):
        """Test that get_twilio_client creates a Twilio client."""
        # Reset singleton state
        sender_module._TwilioClientSingleton._instance = None

        # Mock require_credential to return appropriate values
        def require_credential_side_effect(key, _description):
            if key == "twilio_account_sid":
                return "ACtest123"
            if key == "twilio_auth_token":
                return "test_token"
            raise ValueError(f"Unknown credential: {key}")

        mock_settings.require_credential.side_effect = require_credential_side_effect
        mock_client_instance = MagicMock()
        mock_client_class.return_value = mock_client_instance

        client = get_twilio_client()

        # Verify client was created with correct credentials
        mock_client_class.assert_called_once_with("ACtest123", "test_token")
        assert client == mock_client_instance

    @patch("src.interface.whatsapp_sender.Client")
    @patch("src.interface.whatsapp_sender.settings")
    def test_get_twilio_client_singleton(self, mock_settings, mock_client_class):
        """Test that get_twilio_client returns same instance."""
        # Reset singleton state
        sender_module._TwilioClientSingleton._instance = None

        # Mock require_credential to return appropriate values
        def require_credential_side_effect(key, _description):
            if key == "twilio_account_sid":
                return "ACtest123"
            if key == "twilio_auth_token":
                return "test_token"
            raise ValueError(f"Unknown credential: {key}")

        mock_settings.require_credential.side_effect = require_credential_side_effect

        # Create a client
        mock_client_instance = MagicMock()
        mock_client_class.return_value = mock_client_instance

        client1 = get_twilio_client()
        client2 = get_twilio_client()

        # Should be same instance
        assert client1 is client2

        # Should only create once
        assert mock_client_class.call_count == 1
