"""Tests for webhook rate limiting integration."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from src.core.rate_limiter import RateLimitExceeded


@pytest.mark.asyncio
async def test_webhook_rate_limit_enforced():
    """Test that webhook endpoint enforces rate limits."""
    from fastapi import BackgroundTasks, Request

    from src.interface.webhook import receive_webhook

    mock_request = MagicMock(spec=Request)
    mock_request.form = AsyncMock(
        return_value={
            "Body": "test message",
            "From": "whatsapp:+1234567890",
            "MessageSid": "test123",
        }
    )
    mock_request.headers.get.return_value = "valid_signature"
    mock_request.url = "https://example.com/webhook"

    mock_bg_tasks = MagicMock(spec=BackgroundTasks)

    with patch("src.interface.webhook.rate_limiter") as mock_limiter:
        mock_limiter.check_webhook_rate_limit = AsyncMock(side_effect=RateLimitExceeded(retry_after=30, limit=60))

        with pytest.raises(HTTPException) as exc_info:
            await receive_webhook(mock_request, mock_bg_tasks)

        assert exc_info.value.status_code == 429
        assert exc_info.value.detail == "Too many requests"
        assert "Retry-After" in exc_info.value.headers
        assert exc_info.value.headers["Retry-After"] == "30"
        assert exc_info.value.headers["X-RateLimit-Limit"] == "60"


@pytest.mark.asyncio
async def test_webhook_rate_limit_passes_when_under_limit():
    """Test that webhook processes normally when under rate limit."""
    from fastapi import BackgroundTasks, Request

    from src.interface.webhook import receive_webhook

    mock_request = MagicMock(spec=Request)
    mock_request.form = AsyncMock(
        return_value={
            "Body": "test message",
            "From": "whatsapp:+1234567890",
            "To": "whatsapp:+0987654321",
            "MessageSid": "test123",
        }
    )
    mock_request.headers.get.return_value = "valid_signature"
    mock_request.url = "https://example.com/webhook"

    mock_bg_tasks = MagicMock(spec=BackgroundTasks)
    mock_bg_tasks.add_task = MagicMock()

    with (
        patch("src.interface.webhook.rate_limiter") as mock_limiter,
        patch("src.interface.webhook.verify_twilio_signature") as mock_verify,
        patch("src.interface.webhook.whatsapp_parser") as mock_parser,
        patch("src.interface.webhook.webhook_security") as mock_security,
    ):
        mock_limiter.check_webhook_rate_limit = AsyncMock(return_value=None)
        mock_verify.return_value = True

        mock_message = MagicMock()
        mock_message.message_id = "test123"
        mock_message.timestamp = "2024-01-01T00:00:00Z"
        mock_message.from_phone = "+1234567890"
        mock_parser.parse_twilio_webhook.return_value = mock_message

        mock_security_result = MagicMock()
        mock_security_result.is_valid = True
        mock_security.verify_webhook_security = AsyncMock(return_value=mock_security_result)

        result = await receive_webhook(mock_request, mock_bg_tasks)

        assert result == {"status": "received"}
        mock_limiter.check_webhook_rate_limit.assert_called_once()


@pytest.mark.asyncio
async def test_agent_rate_limit_enforced_per_user():
    """Test that agent calls enforce per-user rate limits."""
    from src.interface import whatsapp_parser
    from src.interface.webhook import _handle_user_status

    mock_message = MagicMock(spec=whatsapp_parser.ParsedMessage)
    mock_message.from_phone = "+1234567890"
    mock_message.text = "test message"

    mock_user_record = {
        "status": "active",
        "name": "Test User",
    }

    mock_db = MagicMock()
    mock_deps = MagicMock()

    with (
        patch("src.interface.webhook.rate_limiter") as mock_limiter,
        patch("src.interface.webhook.whatsapp_sender") as mock_sender,
    ):
        mock_limiter.check_agent_rate_limit = AsyncMock(side_effect=RateLimitExceeded(retry_after=1800, limit=50))

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.error = None
        mock_sender.send_text_message = AsyncMock(return_value=mock_result)

        success, error = await _handle_user_status(
            user_record=mock_user_record,
            message=mock_message,
            db=mock_db,
            deps=mock_deps,
        )

        assert success is True
        mock_limiter.check_agent_rate_limit.assert_called_once_with("+1234567890")

        # Verify rate limit message was sent
        mock_sender.send_text_message.assert_called_once()
        call_args = mock_sender.send_text_message.call_args[1]
        assert "limit" in call_args["text"].lower()
        assert "50" in call_args["text"]


@pytest.mark.asyncio
async def test_agent_rate_limit_allows_processing_when_under_limit():
    """Test that agent processes normally when under rate limit."""
    from src.interface import whatsapp_parser
    from src.interface.webhook import _handle_user_status

    mock_message = MagicMock(spec=whatsapp_parser.ParsedMessage)
    mock_message.from_phone = "+1234567890"
    mock_message.text = "test message"

    mock_user_record = {
        "status": "active",
        "name": "Test User",
    }

    mock_db = MagicMock()
    mock_deps = MagicMock()

    with (
        patch("src.interface.webhook.rate_limiter") as mock_limiter,
        patch("src.interface.webhook.choresir_agent") as mock_agent,
        patch("src.interface.webhook.whatsapp_sender") as mock_sender,
    ):
        mock_limiter.check_agent_rate_limit = AsyncMock(return_value=None)
        mock_agent.get_member_list = AsyncMock(return_value=[])
        mock_agent.run_agent = AsyncMock(return_value="Agent response")

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.error = None
        mock_sender.send_text_message = AsyncMock(return_value=mock_result)

        success, error = await _handle_user_status(
            user_record=mock_user_record,
            message=mock_message,
            db=mock_db,
            deps=mock_deps,
        )

        assert success is True
        mock_limiter.check_agent_rate_limit.assert_called_once_with("+1234567890")
        mock_agent.run_agent.assert_called_once()
