"""Tests for WhatsApp webhook endpoints."""

import json
from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from src.core import db_client as db_module
from src.interface.webhook import (
    _handle_button_payload,
    process_webhook_message,
    receive_webhook,
)
from src.interface.webhook_security import WebhookSecurityResult
from src.services.verification_service import VerificationDecision


@pytest.fixture
def mock_hmac_validation() -> Generator[MagicMock, None, None]:
    """Provides mock for HMAC webhook validation."""
    with (
        patch("src.interface.webhook.settings.waha_webhook_hmac_key", "test_secret"),
        patch("src.interface.webhook.webhook_security.validate_webhook_hmac") as mock,
    ):
        mock.return_value = WebhookSecurityResult(is_valid=True, error_message=None, http_status_code=None)
        yield mock


@pytest.fixture
def mock_security_validation() -> Generator[MagicMock, None, None]:
    """Provides mock for security validation."""
    with patch("src.interface.webhook.webhook_security.verify_webhook_security") as mock:
        mock.return_value = WebhookSecurityResult(is_valid=True, error_message=None, http_status_code=None)
        yield mock


@pytest.fixture
def mock_webhook_parser() -> Generator[MagicMock, None, None]:
    """Provides mock for webhook parser."""
    with patch("src.interface.webhook.whatsapp_parser.parse_waha_webhook") as mock:
        yield mock


@pytest.fixture
def mock_process_webhook() -> Generator[MagicMock, None, None]:
    """Provides mock for process_webhook_message."""
    with patch("src.interface.webhook.process_webhook_message") as mock:
        yield mock


@pytest.fixture
def mock_rate_limiter() -> Generator[AsyncMock, None, None]:
    """Provides mock for rate limiter."""
    with patch(
        "src.interface.webhook.rate_limiter.check_webhook_rate_limit", new_callable=AsyncMock, return_value=None
    ) as mock:
        yield mock


@pytest.fixture
def mock_webhook_message() -> MagicMock:
    """Provides a mock webhook message object."""
    mock_msg = MagicMock()
    mock_msg.message_id = "123"
    mock_msg.timestamp = "123456"
    mock_msg.from_phone = "1234567890"
    mock_msg.text = "Hello"
    mock_msg.button_payload = None
    mock_msg.message_type = "text"
    return mock_msg


@pytest.fixture
def mock_webhook_request() -> MagicMock:
    """Provides a mock webhook request object."""
    mock_request = MagicMock()
    mock_request.body = AsyncMock(return_value=b'{"event": "message"}')
    mock_request.headers = {"X-Hub-Signature-256": "valid_signature"}
    mock_request.json = AsyncMock(return_value={"event": "message", "payload": {}})
    return mock_request


@pytest.fixture
def mock_background_tasks() -> MagicMock:
    """Provides mock for FastAPI background tasks."""
    return MagicMock()


@pytest.fixture
def mock_choresir_agent() -> Generator[MagicMock, None, None]:
    """Provides mock for choresir agent."""
    with patch("src.interface.webhook.choresir_agent") as mock:
        yield mock


@pytest.fixture
def mock_whatsapp_sender() -> Generator[MagicMock, None, None]:
    """Provides mock for WhatsApp sender."""
    with patch("src.interface.webhook.whatsapp_sender") as mock:
        yield mock


@pytest.fixture
def mock_verification_service() -> Generator[MagicMock, None, None]:
    """Provides mock for verification service."""
    with patch("src.services.verification_service") as mock:
        mock.verify_chore = AsyncMock()
        mock.VerificationDecision = VerificationDecision
        yield mock


class TestReceiveWebhook:
    """Test webhook endpoint."""

    @pytest.mark.asyncio
    async def test_receive_webhook_valid(  # noqa: PLR0913
        self,
        *,
        mock_webhook_parser: MagicMock,
        mock_process_webhook: MagicMock,
        mock_security_validation: MagicMock,
        mock_hmac_validation: MagicMock,
        mock_webhook_message: MagicMock,
        mock_webhook_request: MagicMock,
        mock_background_tasks: MagicMock,
    ) -> None:
        """Test webhook receives and validates valid requests."""
        mock_webhook_parser.return_value = mock_webhook_message

        result = await receive_webhook(mock_webhook_request, mock_background_tasks)

        # Should return success
        assert result == {"status": "received"}

        # Should validate HMAC
        mock_hmac_validation.assert_called_once()

        # Should verify security
        mock_security_validation.assert_called_once()

        # Should queue background task
        mock_background_tasks.add_task.assert_called_once()

    @pytest.mark.asyncio
    async def test_receive_webhook_missing_hmac_header(
        self,
        *,
        mock_hmac_validation: MagicMock,
        mock_background_tasks: MagicMock,
    ) -> None:
        """Test webhook rejects requests without HMAC header."""
        # Mock HMAC validation failure (missing header)
        mock_hmac_validation.return_value = WebhookSecurityResult(
            is_valid=False, error_message="Missing webhook signature", http_status_code=401
        )

        mock_request = MagicMock()
        mock_request.body = AsyncMock(return_value=b'{"event": "message"}')
        mock_request.headers = {}

        with pytest.raises(HTTPException) as exc_info:
            await receive_webhook(mock_request, mock_background_tasks)

        assert exc_info.value.status_code == 401  # type: ignore[attr-defined]
        assert exc_info.value.detail == "Missing webhook signature"  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_receive_webhook_invalid_hmac_signature(
        self,
        *,
        mock_hmac_validation: MagicMock,
        mock_background_tasks: MagicMock,
    ) -> None:
        """Test webhook rejects requests with invalid HMAC signature."""
        # Mock HMAC validation failure (invalid signature)
        mock_hmac_validation.return_value = WebhookSecurityResult(
            is_valid=False, error_message="Invalid webhook signature", http_status_code=401
        )

        mock_request = MagicMock()
        mock_request.body = AsyncMock(return_value=b'{"event": "message"}')
        mock_request.headers = {"X-Hub-Signature-256": "invalid_signature"}

        with pytest.raises(HTTPException) as exc_info:
            await receive_webhook(mock_request, mock_background_tasks)

        assert exc_info.value.status_code == 401  # type: ignore[attr-defined]
        assert exc_info.value.detail == "Invalid webhook signature"  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_receive_webhook_valid_hmac_proceeds(  # noqa: PLR0913
        self,
        *,
        mock_webhook_parser: MagicMock,
        mock_process_webhook: MagicMock,
        mock_rate_limiter: AsyncMock,
        mock_security_validation: MagicMock,
        mock_hmac_validation: MagicMock,
        mock_webhook_message: MagicMock,
        mock_background_tasks: MagicMock,
    ) -> None:
        """Test webhook with valid HMAC proceeds to normal processing."""
        mock_webhook_parser.return_value = mock_webhook_message

        mock_request = MagicMock()
        body = b'{"event": "message", "payload": {"from": "1234567890"}}'
        mock_request.body = AsyncMock(return_value=body)
        mock_request.headers = {"X-Hub-Signature-256": "valid_signature"}
        mock_request.json = AsyncMock(return_value={"event": "message", "payload": {}})

        result = await receive_webhook(mock_request, mock_background_tasks)

        assert result == {"status": "received"}
        mock_hmac_validation.assert_called_once_with(raw_body=body, signature="valid_signature", secret="test_secret")

    @pytest.mark.asyncio
    async def test_receive_webhook_invalid_json(
        self,
        *,
        mock_hmac_validation: MagicMock,
        mock_background_tasks: MagicMock,
    ) -> None:
        """Test webhook rejects invalid JSON."""
        mock_hmac_validation.return_value = WebhookSecurityResult(
            is_valid=True, error_message=None, http_status_code=None
        )

        mock_request = MagicMock()
        mock_request.body = AsyncMock(return_value=b'{"invalid": json}')
        mock_request.headers = {"X-Hub-Signature-256": "valid_signature"}
        mock_request.json = AsyncMock(side_effect=json.JSONDecodeError("Invalid JSON", "", 0))

        with pytest.raises(HTTPException) as exc_info:
            await receive_webhook(mock_request, mock_background_tasks)

        assert exc_info.value.status_code == 400  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_receive_webhook_ignored_event(
        self,
        *,
        mock_webhook_parser: MagicMock,
        mock_hmac_validation: MagicMock,
        mock_background_tasks: MagicMock,
    ) -> None:
        """Test webhook ignores non-message events."""
        mock_hmac_validation.return_value = WebhookSecurityResult(
            is_valid=True, error_message=None, http_status_code=None
        )
        mock_webhook_parser.return_value = None

        mock_request = MagicMock()
        mock_request.body = AsyncMock(return_value=b'{"event": "status"}')
        mock_request.headers = {"X-Hub-Signature-256": "valid_signature"}
        mock_request.json = AsyncMock(return_value={"event": "status"})

        result = await receive_webhook(mock_request, mock_background_tasks)

        assert result == {"status": "ignored"}
        mock_background_tasks.add_task.assert_not_called()

    @pytest.mark.asyncio
    async def test_receive_webhook_security_failure(
        self,
        *,
        mock_webhook_parser: MagicMock,
        mock_security_validation: MagicMock,
        mock_hmac_validation: MagicMock,
        mock_webhook_message: MagicMock,
        mock_background_tasks: MagicMock,
    ) -> None:
        """Test webhook fails on security check."""
        mock_webhook_parser.return_value = mock_webhook_message

        mock_security_validation.return_value = WebhookSecurityResult(
            is_valid=False, error_message="Security failed", http_status_code=400
        )

        mock_request = MagicMock()
        mock_request.body = AsyncMock(return_value=b'{"event": "message"}')
        mock_request.headers = {"X-Hub-Signature-256": "valid_signature"}
        mock_request.json = AsyncMock(return_value={})

        with pytest.raises(HTTPException) as exc_info:
            await receive_webhook(mock_request, mock_background_tasks)

        assert exc_info.value.status_code == 400  # type: ignore[attr-defined]
        assert exc_info.value.detail == "Security failed"  # type: ignore[attr-defined]


@pytest.mark.usefixtures("mock_db_module", "db_client")
class TestProcessWebhookMessage:
    """Test background webhook message processing."""

    @pytest.mark.asyncio
    async def test_process_webhook_message_no_text(
        self,
        *,
        mock_webhook_parser: MagicMock,
    ) -> None:
        """Test processing skips messages without text."""
        mock_webhook_parser.return_value = MagicMock(text=None, message_type="unknown", button_payload=None)

        params = {"payload": {}}

        await process_webhook_message(params)

        # Should parse but not create any records (skip)
        mock_webhook_parser.assert_called_once_with(params)
        # Verify no records were created in processed_messages collection
        records = await db_module.list_records(collection="processed_messages")
        assert len(records) == 0

    @pytest.mark.asyncio
    async def test_process_webhook_message_duplicate(
        self,
        *,
        mock_webhook_parser: MagicMock,
    ) -> None:
        """Test processing skips duplicate messages."""
        mock_webhook_message = MagicMock()
        mock_webhook_message.button_payload = None
        mock_webhook_message.message_id = "msg123"
        mock_webhook_message.from_phone = "+1234567890"
        mock_webhook_message.text = "Hello"
        mock_webhook_message.message_type = "text"
        mock_webhook_parser.return_value = mock_webhook_message

        # Create existing processed message record to simulate duplicate
        await db_module.create_record(
            collection="processed_messages",
            data={
                "message_id": "msg123",
                "from_phone": "+1234567890",
                "processed_at": datetime.now(UTC).isoformat(),
                "success": True,
            },
        )

        params = {}

        await process_webhook_message(params)

        # Should not create new record (still just the original)
        records = await db_module.list_records(collection="processed_messages")
        assert len(records) == 1
        assert records[0]["message_id"] == "msg123"

    @pytest.mark.asyncio
    async def test_process_webhook_message_unknown_user(
        self,
        *,
        mock_whatsapp_sender: MagicMock,
        mock_choresir_agent: MagicMock,
        mock_webhook_parser: MagicMock,
    ) -> None:
        """Test processing message from unknown user."""
        mock_webhook_message = MagicMock()
        mock_webhook_message.message_id = "msg456"
        mock_webhook_message.from_phone = "+15551234567"
        mock_webhook_message.text = "Hello"
        mock_webhook_message.message_type = "text"
        mock_webhook_message.button_payload = None
        mock_webhook_parser.return_value = mock_webhook_message

        # build_deps returns None for unknown user
        mock_choresir_agent.build_deps = AsyncMock(return_value=None)
        mock_choresir_agent.handle_unknown_user = AsyncMock(return_value="Welcome! Please join.")

        mock_whatsapp_sender.send_text_message = AsyncMock(return_value=MagicMock(success=True, error=None))

        params = {}

        await process_webhook_message(params)

        # Verify processed message record was created
        records = await db_module.list_records(collection="processed_messages")
        assert len(records) == 1
        assert records[0]["message_id"] == "msg456"

        # Should send onboarding message
        mock_choresir_agent.handle_unknown_user.assert_called_once()
        mock_whatsapp_sender.send_text_message.assert_called_once()

    @pytest.mark.asyncio
    async def test_process_webhook_message_handles_errors(
        self,
        *,
        mock_whatsapp_sender: MagicMock,
        mock_webhook_parser: MagicMock,
    ) -> None:
        """Test error handling in webhook processing."""
        mock_webhook_message = MagicMock()
        mock_webhook_message.message_id = "msg789"
        mock_webhook_message.from_phone = "+15551234567"
        mock_webhook_message.text = "Hello"
        mock_webhook_message.message_type = "text"
        mock_webhook_message.button_payload = None
        mock_webhook_parser.return_value = mock_webhook_message

        # Simulate database error during duplicate check
        with patch("src.core.db_client.get_first_record", side_effect=Exception("DB error")):
            # Should send error message to user
            mock_whatsapp_sender.send_text_message = AsyncMock(return_value=MagicMock(success=True, error=None))

            params = {}

            # Should not raise exception
            await process_webhook_message(params)

            # Should attempt to send error message
            mock_whatsapp_sender.send_text_message.assert_called()
            call_args = mock_whatsapp_sender.send_text_message.call_args
            assert "error" in call_args.kwargs["text"].lower()


@pytest.mark.usefixtures("mock_db_module", "db_client")
class TestHandleButtonPayload:
    """Test button payload handling."""

    @pytest.mark.asyncio
    async def test_approve_button_success(
        self,
        *,
        mock_verification_service: MagicMock,
        mock_whatsapp_sender: MagicMock,
    ) -> None:
        """Test successful approval via button."""
        # Create user record
        user_record = await db_module.create_record(
            collection="users",
            data={
                "phone": "+1234567890",
                "name": "Alice",
                "email": "alice@test.local",
                "role": "member",
                "status": "active",
                "password": "test_password",
                "passwordConfirm": "test_password",
            },
        )

        # Create chore record
        chore_record = await db_module.create_record(
            collection="chores",
            data={
                "title": "Wash dishes",
                "description": "Clean all dishes",
                "schedule_cron": "0 20 * * *",
                "assigned_to": user_record["id"],
                "current_state": "PENDING_VERIFICATION",
                "deadline": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
            },
        )

        # Create log record
        log_record = await db_module.create_record(
            collection="logs",
            data={
                "chore_id": chore_record["id"],
                "user_id": user_record["id"],
                "action": "completed",
                "notes": "Task done",
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )

        # Create mock message with button payload
        mock_message = MagicMock()
        mock_message.from_phone = "+1234567890"
        mock_message.button_payload = f"VERIFY:APPROVE:{log_record['id']}"

        # Mock sender
        mock_whatsapp_sender.send_text_message = AsyncMock(return_value=MagicMock(success=True, error=None))

        # Execute
        success, error = await _handle_button_payload(message=mock_message, user_record=user_record)

        # Assertions
        assert success is True
        assert error is None
        mock_verification_service.verify_chore.assert_called_once()
        mock_whatsapp_sender.send_text_message.assert_called_once()
        call_args = mock_whatsapp_sender.send_text_message.call_args
        assert "Approved" in call_args.kwargs["text"]
