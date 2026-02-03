"""Tests for WhatsApp webhook endpoints."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from src.interface.webhook import (
    _handle_button_payload,
    process_webhook_message,
    receive_webhook,
)
from src.interface.webhook_security import WebhookSecurityResult
from src.services.verification_service import VerificationDecision


class TestReceiveWebhook:
    """Test webhook endpoint."""

    @pytest.mark.asyncio
    @patch("src.interface.webhook.webhook_security.verify_webhook_security")
    @patch("src.interface.webhook.process_webhook_message")
    @patch("src.interface.webhook.whatsapp_parser.parse_waha_webhook")
    async def test_receive_webhook_valid(self, mock_parse, mock_process, mock_security):
        """Test webhook receives and validates valid requests."""
        mock_security.return_value = WebhookSecurityResult(is_valid=True, error_message=None, http_status_code=None)

        mock_msg = MagicMock()
        mock_msg.message_id = "123"
        mock_msg.timestamp = "123456"
        mock_msg.from_phone = "1234567890"
        mock_parse.return_value = mock_msg

        # Create mock request with JSON data
        mock_request = MagicMock()
        mock_request.json = AsyncMock(return_value={"event": "message", "payload": {}})

        mock_background_tasks = MagicMock()

        result = await receive_webhook(mock_request, mock_background_tasks)

        # Should return success
        assert result == {"status": "received"}

        # Should verify security
        mock_security.assert_called_once()

        # Should queue background task
        mock_background_tasks.add_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_receive_webhook_invalid_json(self):
        """Test webhook rejects invalid JSON."""
        mock_request = MagicMock()
        mock_request.json = AsyncMock(side_effect=Exception("Invalid JSON"))
        mock_background_tasks = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await receive_webhook(mock_request, mock_background_tasks)

        assert isinstance(exc_info.value, HTTPException)
        assert exc_info.value.status_code == 400

    @pytest.mark.asyncio
    @patch("src.interface.webhook.whatsapp_parser.parse_waha_webhook")
    async def test_receive_webhook_ignored_event(self, mock_parse):
        """Test webhook ignores non-message events."""
        mock_parse.return_value = None

        mock_request = MagicMock()
        mock_request.json = AsyncMock(return_value={"event": "status"})
        mock_background_tasks = MagicMock()

        result = await receive_webhook(mock_request, mock_background_tasks)

        assert result == {"status": "ignored"}
        mock_background_tasks.add_task.assert_not_called()

    @pytest.mark.asyncio
    @patch("src.interface.webhook.webhook_security.verify_webhook_security")
    @patch("src.interface.webhook.whatsapp_parser.parse_waha_webhook")
    async def test_receive_webhook_security_failure(self, mock_parse, mock_security):
        """Test webhook fails on security check."""
        mock_msg = MagicMock()
        mock_msg.message_id = "123"
        mock_msg.timestamp = "123456"
        mock_msg.from_phone = "1234567890"
        mock_parse.return_value = mock_msg

        mock_security.return_value = WebhookSecurityResult(
            is_valid=False, error_message="Security failed", http_status_code=400
        )

        mock_request = MagicMock()
        mock_request.json = AsyncMock(return_value={})
        mock_background_tasks = MagicMock()

        with pytest.raises(HTTPException) as exc_info:
            await receive_webhook(mock_request, mock_background_tasks)

        assert isinstance(exc_info.value, HTTPException)
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail == "Security failed"


class TestProcessWebhookMessage:
    """Test background webhook message processing."""

    @pytest.mark.asyncio
    @patch("src.interface.webhook.whatsapp_parser.parse_waha_webhook")
    @patch("src.interface.webhook.db_client")
    async def test_process_webhook_message_no_text(self, mock_db, mock_parser):
        """Test processing skips messages without text."""
        # Parser returns message without text
        mock_parser.return_value = MagicMock(text=None, message_type="unknown", button_payload=None)

        params = {"payload": {}}

        await process_webhook_message(params)

        # Should parse but not create any records (skip)
        mock_parser.assert_called_once_with(params)
        mock_db.create_record.assert_not_called()

    @pytest.mark.asyncio
    @patch("src.interface.webhook.whatsapp_parser.parse_waha_webhook")
    @patch("src.interface.webhook.db_client")
    async def test_process_webhook_message_duplicate(self, mock_db, mock_parser):
        """Test processing skips duplicate messages."""
        mock_message = MagicMock()
        mock_message.message_id = "123"
        mock_message.text = "Hello"
        mock_message.button_payload = None
        mock_message.message_type = "text"
        mock_parser.return_value = mock_message

        # Simulate existing message log
        mock_db.get_first_record = AsyncMock(return_value={"id": "existing"})

        params = {}

        await process_webhook_message(params)

        # Should check for duplicate
        mock_db.get_first_record.assert_called_once()
        # Should not create new record
        mock_db.create_record.assert_not_called()

    @pytest.mark.asyncio
    @patch("src.interface.webhook.whatsapp_parser.parse_waha_webhook")
    @patch("src.interface.webhook.db_client")
    @patch("src.interface.webhook.choresir_agent")
    @patch("src.interface.webhook.whatsapp_sender")
    async def test_process_webhook_message_unknown_user(self, mock_sender, mock_agent, mock_db, mock_parser):
        """Test processing message from unknown user."""
        mock_message = MagicMock()
        mock_message.message_id = "123"
        mock_message.from_phone = "1234567890"
        mock_message.text = "Hello"
        mock_message.button_payload = None
        mock_message.message_type = "text"
        mock_parser.return_value = mock_message

        # No existing message log
        mock_db.get_first_record = AsyncMock(
            side_effect=[
                None,  # check duplicate
                None,  # user lookup
                None,  # update message status
            ]
        )
        mock_db.create_record = AsyncMock(return_value={"id": "msg123"})

        # build_deps returns None for unknown user
        mock_agent.build_deps = AsyncMock(return_value=None)
        mock_agent.handle_unknown_user = AsyncMock(return_value="Welcome! Please join.")

        mock_sender.send_text_message = AsyncMock(return_value=MagicMock(success=True, error=None))

        params = {}

        await process_webhook_message(params)

        # Should send onboarding message
        mock_agent.handle_unknown_user.assert_called_once()
        mock_sender.send_text_message.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.interface.webhook.whatsapp_parser.parse_waha_webhook")
    @patch("src.interface.webhook.db_client")
    @patch("src.interface.webhook.whatsapp_sender")
    async def test_process_webhook_message_handles_errors(self, mock_sender, mock_db, mock_parser):
        """Test error handling in webhook processing."""
        mock_message = MagicMock()
        mock_message.message_id = "123"
        mock_message.from_phone = "1234567890"
        mock_message.text = "Hello"
        mock_message.button_payload = None
        mock_message.message_type = "text"
        mock_parser.return_value = mock_message

        # Simulate database error during duplicate check or logging
        mock_db.get_first_record = AsyncMock(side_effect=Exception("DB error"))

        # Should send error message to user
        mock_sender.send_text_message = AsyncMock(return_value=MagicMock(success=True, error=None))

        params = {}

        # Should not raise exception
        await process_webhook_message(params)

        # Should attempt to send error message
        mock_sender.send_text_message.assert_called()
        call_args = mock_sender.send_text_message.call_args
        assert "error" in call_args.kwargs["text"].lower()


class TestHandleButtonPayload:
    """Test button payload handling."""

    @pytest.mark.asyncio
    @patch("src.interface.webhook.whatsapp_sender")
    @patch("src.interface.webhook.db_client")
    @patch("src.services.verification_service")
    async def test_approve_button_success(self, mock_verification, mock_db, mock_sender):
        """Test successful approval via button."""
        # Create mock message with button payload
        mock_message = MagicMock()
        mock_message.from_phone = "+1234567890"
        mock_message.button_payload = "VERIFY:APPROVE:log123"

        # Mock user record
        user_record = {"id": "user123", "name": "Alice"}

        # Mock database responses
        mock_db.get_record = AsyncMock(
            side_effect=[
                {"id": "log123", "chore_id": "chore456"},  # log record
                {"id": "chore456", "title": "Wash dishes"},  # chore record
            ]
        )

        # Mock verification service
        mock_verification.verify_chore = AsyncMock()
        mock_verification.VerificationDecision = VerificationDecision

        # Mock sender
        mock_sender.send_text_message = AsyncMock(return_value=MagicMock(success=True, error=None))

        # Execute
        success, error = await _handle_button_payload(message=mock_message, user_record=user_record)

        # Assertions
        assert success is True
        assert error is None
        mock_verification.verify_chore.assert_called_once()
        mock_sender.send_text_message.assert_called_once()
        call_args = mock_sender.send_text_message.call_args
        assert "Approved" in call_args.kwargs["text"]
