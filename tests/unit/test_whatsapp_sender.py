"""Tests for WhatsApp message sender using WAHA via httpx."""

from collections.abc import Generator
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from src.interface.whatsapp_sender import (
    RateLimiter,
    format_phone_for_waha,
    send_text_message,
)


@pytest.fixture(autouse=True)
def mock_asyncio_sleep() -> Generator[AsyncMock, None, None]:
    """Mock asyncio.sleep to avoid actual delays in retry tests."""
    with patch("src.interface.whatsapp_sender.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        yield mock_sleep


class TestRateLimiter:
    """Test rate limiting functionality."""

    def test_can_send_when_under_limit(self) -> None:
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

    def test_cannot_send_when_at_limit(self) -> None:
        """Test that sending is blocked when at rate limit."""
        limiter = RateLimiter()
        phone = "+1234567890"

        # Record max requests (60 per minute based on constants.MAX_REQUESTS_PER_MINUTE)
        # Assuming default limit is 60
        for _ in range(60):
            limiter.record_request(phone)

        # Should block
        assert limiter.can_send(phone) is False

    def test_rate_limit_per_phone(self) -> None:
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


class TestFormatPhoneForWaha:
    """Test phone number formatting for WAHA."""

    def test_format_clean_number(self) -> None:
        assert format_phone_for_waha("1234567890") == "1234567890@c.us"

    def test_format_with_plus(self) -> None:
        assert format_phone_for_waha("+1234567890") == "1234567890@c.us"

    def test_format_with_whatsapp_prefix(self) -> None:
        assert format_phone_for_waha("whatsapp:+1234567890") == "1234567890@c.us"

    def test_format_already_formatted(self) -> None:
        assert format_phone_for_waha("1234567890@c.us") == "1234567890@c.us"


class TestSendTextMessage:
    """Test sending text messages via WAHA."""

    @pytest.mark.asyncio
    async def test_send_text_message_success(self) -> None:
        """Test successful message sending."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.is_success = True
        mock_response.json.return_value = {"id": "true_123@c.us_ABC"}

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            # Send message
            result = await send_text_message(
                to_phone="+1234567890",
                text="Hello, test message",
            )

            # Verify result
            assert result.success is True
            assert result.message_id == "true_123@c.us_ABC"
            assert result.error is None

            # Verify WAHA API was called correctly
            mock_post.assert_called_once()
            call_kwargs = mock_post.call_args.kwargs
            assert "json" in call_kwargs
            payload = call_kwargs["json"]
            assert payload["chatId"] == "1234567890@c.us"
            assert payload["text"] == "Hello, test message"
            assert payload["session"] == "default"

    @pytest.mark.asyncio
    async def test_send_text_message_client_error(self) -> None:
        """Test handling of 4xx client errors (no retry)."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 400
        mock_response.is_success = False
        mock_response.text = "Bad Request"

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            result = await send_text_message(to_phone="+1234567890", text="Test")

            # Should fail without retry
            assert result.success is False
            assert result.error is not None
            assert "Client error" in result.error
            assert "Bad Request" in result.error

            # Should only try once (no retries on 4xx)
            assert mock_post.call_count == 1

    @pytest.mark.asyncio
    async def test_send_text_message_server_error_with_retry(self) -> None:
        """Test retry logic on 5xx server errors."""
        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 500
        mock_response.is_success = False
        mock_response.request = MagicMock()

        # httpx raises HTTPStatusError when raise_for_status called or manually raised
        # In our code we check status and raise HTTPStatusError

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            result = await send_text_message(
                to_phone="+1234567890",
                text="Test",
                max_retries=3,
                retry_delay=0.01,  # Fast retry for testing
            )

            # Should fail after retries
            assert result.success is False
            assert result.error == "Failed after retries: Server error: 500"

            # Should retry 3 times
            assert mock_post.call_count == 3

    @pytest.mark.asyncio
    @patch("src.interface.whatsapp_sender.rate_limiter")
    async def test_send_text_message_rate_limited(self, mock_rate_limiter: MagicMock) -> None:
        """Test that rate limiting blocks message sending."""
        # Mock rate limiter to deny request
        mock_rate_limiter.can_send.return_value = False

        result = await send_text_message(to_phone="+1234567890", text="Test")

        # Should fail due to rate limit
        assert result.success is False
        assert result.error is not None
        assert "Rate limit exceeded" in result.error

    @pytest.mark.asyncio
    @patch("src.interface.whatsapp_sender.rate_limiter")
    async def test_rate_limiter_records_request(self, mock_rate_limiter: MagicMock) -> None:
        """Test that rate limiter records successful requests."""
        mock_rate_limiter.can_send.return_value = True

        mock_response = MagicMock(spec=httpx.Response)
        mock_response.status_code = 200
        mock_response.is_success = True
        mock_response.json.return_value = {"id": "1"}

        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.return_value = mock_response

            phone = "+1234567890"
            await send_text_message(to_phone=phone, text="Test")

            # Verify rate limiter was checked and request was recorded
            mock_rate_limiter.can_send.assert_called_once_with(phone)
            mock_rate_limiter.record_request.assert_called_once_with(phone)

    @pytest.mark.asyncio
    async def test_send_text_message_unexpected_error(self) -> None:
        """Test handling of unexpected errors."""
        with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
            mock_post.side_effect = httpx.HTTPError("Unexpected error")

            result = await send_text_message(
                to_phone="+1234567890",
                text="Test",
                max_retries=2,
                retry_delay=0.01,
            )

            # Should fail after retries
            assert result.success is False
            # Check for error in return
            assert result.error is not None
            assert "Failed after retries" in result.error or result.error == "Max retries exceeded"
            # In code: return SendMessageResult(success=False, error=f"Failed after retries: {str(e)}")

            # Should retry
            assert mock_post.call_count == 2
