"""Tests for webhook rate limiting integration."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import BackgroundTasks, HTTPException, Request

from src.interface import whatsapp_parser
from src.interface.webhook import _handle_user_status, receive_webhook


@pytest.mark.asyncio
async def test_webhook_rate_limit_enforced():
    """Test that webhook endpoint enforces rate limits."""
    mock_request = MagicMock(spec=Request)
    mock_request.json = AsyncMock(return_value={"payload": {"body": "test"}})

    mock_bg_tasks = MagicMock(spec=BackgroundTasks)

    with patch("src.interface.webhook.rate_limiter") as mock_limiter:
        mock_limiter.check_webhook_rate_limit = AsyncMock(
            side_effect=HTTPException(
                status_code=429,
                detail="Too many requests",
                headers={
                    "Retry-After": "30",
                    "X-RateLimit-Limit": "60",
                },
            )
        )

        with pytest.raises(HTTPException) as exc_info:
            await receive_webhook(mock_request, mock_bg_tasks)

        exc = exc_info.value
        assert isinstance(exc, HTTPException)
        assert exc.status_code == 429
        assert exc.detail == "Too many requests"
        assert exc.headers is not None
        assert "Retry-After" in exc.headers
        assert exc.headers["Retry-After"] == "30"
        assert exc.headers["X-RateLimit-Limit"] == "60"


@pytest.mark.asyncio
async def test_webhook_rate_limit_passes_when_under_limit():
    """Test that webhook processes normally when under rate limit."""
    mock_request = MagicMock(spec=Request)
    mock_request.json = AsyncMock(
        return_value={
            "event": "message",
            "payload": {
                "id": "123",
                "from": "1234567890@c.us",
                "body": "test message",
                "timestamp": 1234567890,
            },
        }
    )

    mock_bg_tasks = MagicMock(spec=BackgroundTasks)
    mock_bg_tasks.add_task = MagicMock()

    with (
        patch("src.interface.webhook.rate_limiter") as mock_limiter,
        patch("src.interface.webhook.whatsapp_parser.parse_waha_webhook") as mock_parse,
        patch("src.interface.webhook.webhook_security") as mock_security,
    ):
        mock_limiter.check_webhook_rate_limit = AsyncMock(return_value=None)

        mock_message = MagicMock()
        mock_message.message_id = "test123"
        mock_message.timestamp = "2024-01-01T00:00:00Z"
        mock_message.from_phone = "+1234567890"
        mock_parse.return_value = mock_message

        mock_security_result = MagicMock()
        mock_security_result.is_valid = True
        mock_security.verify_webhook_security = AsyncMock(return_value=mock_security_result)

        result = await receive_webhook(mock_request, mock_bg_tasks)

        assert result == {"status": "received"}
        mock_limiter.check_webhook_rate_limit.assert_called_once()


@pytest.mark.asyncio
async def test_agent_rate_limit_enforced_per_user():
    """Test that agent calls enforce per-user rate limits."""
    mock_message = MagicMock(spec=whatsapp_parser.ParsedMessage)
    mock_message.from_phone = "+1234567890"
    mock_message.text = "test message"
    mock_message.is_group_message = False
    mock_message.group_id = None
    mock_message.actual_sender_phone = None

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
        mock_limiter.check_agent_rate_limit = AsyncMock(
            side_effect=HTTPException(
                status_code=429,
                detail="Too many requests",
                headers={
                    "Retry-After": "1800",
                    "X-RateLimit-Limit": "50",
                },
            )
        )

        mock_result = MagicMock()
        mock_result.success = True
        mock_result.error = None
        mock_sender.send_text_message = AsyncMock(return_value=mock_result)

        success, _error = await _handle_user_status(
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
    mock_message = MagicMock(spec=whatsapp_parser.ParsedMessage)
    mock_message.from_phone = "+1234567890"
    mock_message.text = "test message"
    mock_message.is_group_message = False
    mock_message.group_id = None
    mock_message.actual_sender_phone = None

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

        success, _error = await _handle_user_status(
            user_record=mock_user_record,
            message=mock_message,
            db=mock_db,
            deps=mock_deps,
        )

        assert success is True
        mock_limiter.check_agent_rate_limit.assert_called_once_with("+1234567890")
        mock_agent.run_agent.assert_called_once()
