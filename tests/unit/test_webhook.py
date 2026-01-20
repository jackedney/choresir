"""Tests for WhatsApp webhook endpoints with Twilio signature validation."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from src.interface.webhook import (
    _handle_button_payload,
    process_webhook_message,
    receive_webhook,
    verify_twilio_signature,
)
from src.interface.webhook_security import WebhookSecurityResult
from src.services.verification_service import VerificationDecision


class TestVerifyTwilioSignature:
    """Test Twilio signature verification."""

    @patch("src.interface.webhook.RequestValidator")
    @patch("src.interface.webhook.settings")
    def test_verify_twilio_signature_valid(self, mock_settings, mock_validator_class):
        """Test signature verification with valid signature."""
        mock_settings.require_credential.return_value = "test_auth_token"
        mock_validator = MagicMock()
        mock_validator.validate.return_value = True
        mock_validator_class.return_value = mock_validator

        url = "https://example.com/webhook"
        params = {"MessageSid": "SM123", "From": "whatsapp:+1234567890"}
        signature = "valid_signature"

        result = verify_twilio_signature(url, params, signature)

        assert result is True
        mock_validator.validate.assert_called_once_with(url, params, signature)

    @patch("src.interface.webhook.RequestValidator")
    @patch("src.interface.webhook.settings")
    def test_verify_twilio_signature_invalid(self, mock_settings, mock_validator_class):
        """Test signature verification with invalid signature."""
        mock_settings.require_credential.return_value = "test_auth_token"
        mock_validator = MagicMock()
        mock_validator.validate.return_value = False
        mock_validator_class.return_value = mock_validator

        url = "https://example.com/webhook"
        params = {"MessageSid": "SM123", "From": "whatsapp:+1234567890"}
        signature = "invalid_signature"

        result = verify_twilio_signature(url, params, signature)

        assert result is False

    @patch("src.interface.webhook.RequestValidator")
    @patch("src.interface.webhook.settings")
    def test_verify_twilio_signature_uses_auth_token(self, mock_settings, mock_validator_class):
        """Test that signature verification uses auth token from settings."""
        mock_settings.require_credential.return_value = "test_auth_token"
        mock_validator = MagicMock()
        mock_validator.validate.return_value = True
        mock_validator_class.return_value = mock_validator

        url = "https://example.com/webhook"
        params = {}
        signature = "sig"

        verify_twilio_signature(url, params, signature)

        # Verify require_credential was called and RequestValidator was initialized with the token
        mock_settings.require_credential.assert_called_once_with("twilio_auth_token", "Twilio Auth Token")
        mock_validator_class.assert_called_once_with("test_auth_token")


class TestReceiveWebhook:
    """Test webhook endpoint."""

    @pytest.mark.asyncio
    @patch("src.interface.webhook.webhook_security.verify_webhook_security")
    @patch("src.interface.webhook.verify_twilio_signature")
    @patch("src.interface.webhook.process_webhook_message")
    async def test_receive_webhook_valid_signature(self, mock_process, mock_verify, mock_security):
        """Test webhook receives and validates valid requests."""
        mock_verify.return_value = True
        mock_security.return_value = WebhookSecurityResult(is_valid=True, error_message=None, http_status_code=None)

        # Create mock request with form data
        mock_request = MagicMock()
        mock_form = MagicMock()
        mock_form.items.return_value = [
            ("MessageSid", "SM123"),
            ("From", "whatsapp:+1234567890"),
            ("Body", "Test message"),
        ]
        mock_request.form = AsyncMock(return_value=mock_form)
        mock_request.headers.get.return_value = "valid_signature"
        mock_request.url = "https://example.com/webhook"

        mock_background_tasks = MagicMock()

        result = await receive_webhook(mock_request, mock_background_tasks)

        # Should return success
        assert result == {"status": "received"}

        # Should verify signature
        mock_verify.assert_called_once()

        # Should verify security
        mock_security.assert_called_once()

        # Should queue background task
        mock_background_tasks.add_task.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.interface.webhook.verify_twilio_signature")
    async def test_receive_webhook_invalid_signature(self, mock_verify):
        """Test webhook rejects invalid signatures."""
        mock_verify.return_value = False

        mock_request = MagicMock()
        mock_form = MagicMock()
        mock_form.items.return_value = [("MessageSid", "SM123")]
        mock_request.form = AsyncMock(return_value=mock_form)
        mock_request.headers.get.return_value = "invalid_signature"
        mock_request.url = "https://example.com/webhook"

        mock_background_tasks = MagicMock()

        # Should raise HTTPException with 401
        with pytest.raises(HTTPException) as exc_info:
            await receive_webhook(mock_request, mock_background_tasks)

        exc = exc_info.value
        assert isinstance(exc, HTTPException)
        assert exc.status_code == 401
        assert exc.detail == "Invalid signature"

        # Should not queue background task
        mock_background_tasks.add_task.assert_not_called()

    @pytest.mark.asyncio
    async def test_receive_webhook_missing_signature(self):
        """Test webhook rejects requests without signature."""
        mock_request = MagicMock()
        mock_form = MagicMock()
        mock_form.items.return_value = []
        mock_request.form = AsyncMock(return_value=mock_form)
        mock_request.headers.get.return_value = ""  # Missing signature

        mock_background_tasks = MagicMock()

        # Should raise HTTPException with 401
        with pytest.raises(HTTPException) as exc_info:
            await receive_webhook(mock_request, mock_background_tasks)

        exc = exc_info.value
        assert isinstance(exc, HTTPException)
        assert exc.status_code == 401
        assert exc.detail == "Missing signature"

        # Should not queue background task
        mock_background_tasks.add_task.assert_not_called()

    @pytest.mark.asyncio
    @patch("src.interface.webhook.webhook_security.verify_webhook_security")
    @patch("src.interface.webhook.verify_twilio_signature")
    async def test_receive_webhook_form_data_conversion(self, mock_verify, mock_security):
        """Test that form data is correctly converted to dict."""
        mock_verify.return_value = True
        mock_security.return_value = WebhookSecurityResult(is_valid=True, error_message=None, http_status_code=None)

        mock_request = MagicMock()
        mock_form = MagicMock()
        # Simulate form data with various types
        mock_form.items.return_value = [
            ("MessageSid", "SM123"),
            ("From", "whatsapp:+1234567890"),
            ("NumMedia", 0),  # Integer value
            ("Body", "test message"),  # Required for webhook parsing
        ]
        mock_request.form = AsyncMock(return_value=mock_form)
        mock_request.headers.get.return_value = "valid_sig"
        mock_request.url = "https://example.com/webhook"

        mock_background_tasks = MagicMock()

        await receive_webhook(mock_request, mock_background_tasks)

        # Verify signature was called with string-converted params
        call_args = mock_verify.call_args
        params = call_args[0][1]  # Second argument is params
        assert all(isinstance(v, str) for v in params.values())


class TestProcessWebhookMessage:
    """Test background webhook message processing."""

    @pytest.mark.asyncio
    @patch("src.interface.webhook.whatsapp_parser.parse_twilio_webhook")
    @patch("src.interface.webhook.db_client")
    async def test_process_webhook_message_no_text(self, mock_db, mock_parser):
        """Test processing skips messages without text."""
        # Parser returns message without text
        mock_parser.return_value = MagicMock(text=None)

        params = {"MessageSid": "SM123", "From": "whatsapp:+1234567890"}

        await process_webhook_message(params)

        # Should parse but not create any records
        mock_parser.assert_called_once_with(params)
        mock_db.create_record.assert_not_called()

    @pytest.mark.asyncio
    @patch("src.interface.webhook.whatsapp_parser.parse_twilio_webhook")
    @patch("src.interface.webhook.db_client")
    async def test_process_webhook_message_duplicate(self, mock_db, mock_parser):
        """Test processing skips duplicate messages."""
        mock_message = MagicMock()
        mock_message.message_id = "SM123"
        mock_message.text = "Hello"
        mock_parser.return_value = mock_message

        # Simulate existing message log
        mock_db.get_first_record = AsyncMock(return_value={"id": "existing"})

        params = {"MessageSid": "SM123", "From": "whatsapp:+1234567890"}

        await process_webhook_message(params)

        # Should check for duplicate
        mock_db.get_first_record.assert_called_once()
        # Should not create new record
        mock_db.create_record.assert_not_called()

    @pytest.mark.asyncio
    @patch("src.interface.webhook.whatsapp_parser.parse_twilio_webhook")
    @patch("src.interface.webhook.db_client")
    @patch("src.interface.webhook.choresir_agent")
    @patch("src.interface.webhook.whatsapp_sender")
    async def test_process_webhook_message_unknown_user(self, mock_sender, mock_agent, mock_db, mock_parser):
        """Test processing message from unknown user."""
        mock_message = MagicMock()
        mock_message.message_id = "SM123"
        mock_message.from_phone = "+1234567890"
        mock_message.text = "Hello"
        mock_parser.return_value = mock_message

        # No existing message log
        mock_db.get_first_record = AsyncMock(return_value=None)
        mock_db.create_record = AsyncMock(return_value={"id": "msg123"})

        # build_deps returns None for unknown user
        mock_agent.build_deps = AsyncMock(return_value=None)
        mock_agent.handle_unknown_user = AsyncMock(return_value="Welcome! Please join.")

        mock_sender.send_text_message = AsyncMock(return_value=MagicMock(success=True, error=None))

        params = {"MessageSid": "SM123", "From": "whatsapp:+1234567890"}

        await process_webhook_message(params)

        # Should send onboarding message
        mock_agent.handle_unknown_user.assert_called_once()
        mock_sender.send_text_message.assert_called_once()

    @pytest.mark.asyncio
    @patch("src.interface.webhook.whatsapp_parser.parse_twilio_webhook")
    async def test_process_webhook_message_parse_failure(self, mock_parser):
        """Test handling of parse failures."""
        # Parser returns None
        mock_parser.return_value = None

        params = {"invalid": "data"}

        # Should not raise exception
        await process_webhook_message(params)

    @pytest.mark.asyncio
    @patch("src.interface.webhook.whatsapp_parser.parse_twilio_webhook")
    @patch("src.interface.webhook.db_client")
    @patch("src.interface.webhook.whatsapp_sender")
    async def test_process_webhook_message_handles_errors(self, mock_sender, mock_db, mock_parser):
        """Test error handling in webhook processing."""
        mock_message = MagicMock()
        mock_message.message_id = "SM123"
        mock_message.from_phone = "+1234567890"
        mock_message.text = "Hello"
        mock_parser.return_value = mock_message

        # Simulate database error
        mock_db.get_first_record = AsyncMock(side_effect=Exception("DB error"))

        # Should send error message to user
        mock_sender.send_text_message = AsyncMock(return_value=MagicMock(success=True, error=None))

        params = {"MessageSid": "SM123", "From": "whatsapp:+1234567890"}

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

    @pytest.mark.asyncio
    @patch("src.interface.webhook.whatsapp_sender")
    @patch("src.interface.webhook.db_client")
    @patch("src.services.verification_service")
    async def test_reject_button_success(self, mock_verification, mock_db, mock_sender):
        """Test successful rejection via button."""
        mock_message = MagicMock()
        mock_message.from_phone = "+1234567890"
        mock_message.button_payload = "VERIFY:REJECT:log123"

        user_record = {"id": "user123", "name": "Alice"}

        mock_db.get_record = AsyncMock(
            side_effect=[
                {"id": "log123", "chore_id": "chore456"},
                {"id": "chore456", "title": "Wash dishes"},
            ]
        )

        mock_verification.verify_chore = AsyncMock()
        mock_verification.VerificationDecision = VerificationDecision

        mock_sender.send_text_message = AsyncMock(return_value=MagicMock(success=True, error=None))

        success, error = await _handle_button_payload(message=mock_message, user_record=user_record)

        assert success is True
        assert error is None
        call_args = mock_sender.send_text_message.call_args
        assert "Rejected" in call_args.kwargs["text"]

    @pytest.mark.asyncio
    @patch("src.interface.webhook.whatsapp_sender")
    @patch("src.interface.webhook.db_client")
    @patch("src.services.verification_service")
    async def test_self_verification_blocked(self, mock_verification, mock_db, mock_sender):
        """Test error when user tries to verify own claim."""
        mock_message = MagicMock()
        mock_message.from_phone = "+1234567890"
        mock_message.button_payload = "VERIFY:APPROVE:log123"

        user_record = {"id": "user123", "name": "Alice"}

        mock_db.get_record = AsyncMock(
            side_effect=[
                {"id": "log123", "chore_id": "chore456"},
                {"id": "chore456", "title": "Wash dishes"},
            ]
        )

        # Simulate self-verification error
        mock_verification.verify_chore = AsyncMock(side_effect=PermissionError("Cannot verify own claim"))
        mock_verification.VerificationDecision = VerificationDecision

        mock_sender.send_text_message = AsyncMock(return_value=MagicMock(success=True, error=None))

        success, error = await _handle_button_payload(message=mock_message, user_record=user_record)

        assert success is False
        assert error == "Self-verification attempted"
        call_args = mock_sender.send_text_message.call_args
        assert "cannot verify your own" in call_args.kwargs["text"].lower()

    @pytest.mark.asyncio
    @patch("src.interface.webhook.whatsapp_sender")
    async def test_invalid_payload_format(self, mock_sender):
        """Test handling of malformed payload."""
        mock_message = MagicMock()
        mock_message.from_phone = "+1234567890"
        mock_message.button_payload = "INVALID:FORMAT"

        user_record = {"id": "user123", "name": "Alice"}

        mock_sender.send_text_message = AsyncMock(return_value=MagicMock(success=True, error=None))

        success, error = await _handle_button_payload(message=mock_message, user_record=user_record)

        assert success is False
        assert error is not None
        assert "Invalid payload format" in error
        call_args = mock_sender.send_text_message.call_args
        assert "couldn't process" in call_args.kwargs["text"].lower()

    @pytest.mark.asyncio
    @patch("src.interface.webhook.whatsapp_sender")
    @patch("src.interface.webhook.db_client")
    async def test_expired_log_id(self, mock_db, mock_sender):
        """Test handling when log_id not found."""
        mock_message = MagicMock()
        mock_message.from_phone = "+1234567890"
        mock_message.button_payload = "VERIFY:APPROVE:nonexistent"

        user_record = {"id": "user123", "name": "Alice"}

        # Simulate KeyError
        mock_db.get_record = AsyncMock(side_effect=KeyError("Record not found"))

        mock_sender.send_text_message = AsyncMock(return_value=MagicMock(success=True, error=None))

        success, error = await _handle_button_payload(message=mock_message, user_record=user_record)

        assert success is False
        assert error is not None
        assert "Record not found" in error
        call_args = mock_sender.send_text_message.call_args
        assert "expired" in call_args.kwargs["text"].lower()

    @pytest.mark.asyncio
    @patch("src.interface.webhook.whatsapp_sender")
    async def test_invalid_decision_type(self, mock_sender):
        """Test handling when decision is not APPROVE or REJECT."""
        mock_message = MagicMock()
        mock_message.from_phone = "+1234567890"
        mock_message.button_payload = "VERIFY:INVALID:log123"

        user_record = {"id": "user123", "name": "Alice"}

        mock_sender.send_text_message = AsyncMock(return_value=MagicMock(success=True, error=None))

        success, error = await _handle_button_payload(message=mock_message, user_record=user_record)

        assert success is False
        assert error is not None
        assert "Invalid decision" in error
        call_args = mock_sender.send_text_message.call_args
        assert "couldn't process that button click" in call_args.kwargs["text"].lower()

    @pytest.mark.asyncio
    @patch("src.interface.webhook.whatsapp_sender")
    @patch("src.interface.webhook.db_client")
    @patch("src.interface.webhook.logger")
    async def test_unexpected_exception_logging(self, mock_logger, mock_db, mock_sender):
        """Test that unexpected exceptions are logged with detailed information."""
        mock_message = MagicMock()
        mock_message.from_phone = "+1234567890"
        mock_message.button_payload = "VERIFY:APPROVE:log123"

        user_record = {"id": "user123", "name": "Alice"}

        # Create a custom KeyError class that won't catch AttributeError
        class KeyError(Exception):
            pass

        mock_db.KeyError = KeyError

        # Simulate unexpected AttributeError
        mock_db.get_record = AsyncMock(side_effect=AttributeError("'NoneType' object has no attribute 'get'"))

        mock_sender.send_text_message = AsyncMock(return_value=MagicMock(success=True, error=None))

        success, error = await _handle_button_payload(message=mock_message, user_record=user_record)

        # Verify the function handles the error gracefully
        assert success is False
        assert error is not None
        assert "Unexpected error:" in error
        assert "AttributeError" in error

        # Verify detailed logging with exception type and stack trace
        mock_logger.error.assert_called()
        log_call = mock_logger.error.call_args
        # With lazy formatting, exception type is in args[1], not the format string
        assert "Unexpected button handler error" in log_call[0][0]
        assert log_call[0][1] == "AttributeError"  # Exception type in first arg
        assert log_call[1]["exc_info"] is True  # Stack trace included

        # Verify user-friendly error message was sent
        call_args = mock_sender.send_text_message.call_args
        assert "error occurred" in call_args.kwargs["text"].lower()
