"""Unit tests for notification_service module."""

from unittest.mock import AsyncMock

import pytest

from src.domain.user import UserStatus
from src.interface.whatsapp_sender import SendMessageResult
from src.services import notification_service
from tests.unit.conftest import DatabaseClient


@pytest.fixture
def patched_notification_db(mock_db_module_for_unit_tests, db_client):
    """Patches settings and database for notification service tests.

    Uses real SQLite database via db_client fixture from tests/conftest.py.
    Settings are patched by mock_db_module_for_unit_tests fixture.
    """
    return DatabaseClient()


@pytest.fixture
def mock_whatsapp_sender(monkeypatch):
    """Mock whatsapp_sender.send_group_message function."""
    mock_send = AsyncMock(return_value=SendMessageResult(success=True, message_id="msg_456", error=None))
    monkeypatch.setattr("src.services.notification_service.whatsapp_sender.send_group_message", mock_send)
    return mock_send


@pytest.fixture
def sample_chore():
    """Sample chore data (without id - will be generated)."""
    return {
        "title": "Dishes",
        "description": "Wash all the dishes",
        "scope": "shared",
        "current_state": "TODO",
    }


@pytest.fixture
def sample_users():
    """Sample user data (without ids - will be generated)."""
    return [
        {"name": "Alice", "phone": "+11111111111", "role": "member", "status": UserStatus.ACTIVE},
        {"name": "Bob", "phone": "+12222222222", "role": "member", "status": UserStatus.ACTIVE},
        {"name": "Charlie", "phone": "+13333333333", "role": "member", "status": UserStatus.ACTIVE},
    ]


class TestSendVerificationRequest:
    """Test verification request notifications to group chat."""

    @pytest.mark.asyncio
    async def test_sends_to_group_chat(
        self,
        patched_notification_db,
        mock_whatsapp_sender,
        sample_chore,
        sample_users,
    ):
        """Sends verification request to configured group chat."""
        # Populate in-memory database
        chore = await patched_notification_db.create_record(collection="tasks", data=sample_chore)
        claimer = await patched_notification_db.create_record(collection="members", data=sample_users[0])

        # Set up house config with group chat ID
        await patched_notification_db.create_record(
            collection="house_config",
            data={"name": "Test House", "group_chat_id": "group123@g.us"},
        )

        # Send verification request
        results = await notification_service.send_verification_request(
            log_id="log123",
            task_id=chore["id"],
            claimer_user_id=claimer["id"],
        )

        # Should have one result for the group message
        assert (
            len(results) == 0
        )  # Returns empty list since we're not creating NotificationResult objects for group messages

        # Verify group message was sent once
        assert mock_whatsapp_sender.call_count == 1

        # Check call arguments
        call_args = mock_whatsapp_sender.call_args
        assert call_args.kwargs["to_group_id"] == "group123@g.us"
        text = call_args.kwargs["text"]

        # Verify message content
        assert "Alice" in text  # claimer name
        assert "Dishes" in text  # chore title
        assert "log123" in text  # log_id
        assert "approve log123" in text
        assert "reject log123" in text

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_chore_not_found(
        self,
        patched_notification_db,
        sample_users,
    ):
        """Returns empty list when chore doesn't exist."""
        # Only add users, no chore
        for user in sample_users:
            await patched_notification_db.create_record(collection="members", data=user)

        # Send verification request with non-existent chore ID
        results = await notification_service.send_verification_request(
            log_id="log123",
            task_id="99999",
            claimer_user_id="1",
        )

        # Should return empty list
        assert results == []

    @pytest.mark.asyncio
    async def test_uses_someone_when_claimer_not_found(
        self,
        patched_notification_db,
        mock_whatsapp_sender,
        sample_chore,
        sample_users,
    ):
        """Uses 'Someone' as claimer name when claimer not found."""
        # Populate in-memory database (only chore and users, but claimer doesn't exist)
        chore = await patched_notification_db.create_record(collection="tasks", data=sample_chore)

        # Set up house config with group chat ID
        await patched_notification_db.create_record(
            collection="house_config",
            data={"name": "Test House", "group_chat_id": "group123@g.us"},
        )

        # Send verification request with non-existent claimer ID
        await notification_service.send_verification_request(
            log_id="log123",
            task_id=chore["id"],
            claimer_user_id="99999",
        )

        # Verify group message was sent
        assert mock_whatsapp_sender.call_count == 1

        # Check that "Someone" is used as claimer name in text
        call_args = mock_whatsapp_sender.call_args
        text = call_args.kwargs["text"]
        assert "Someone" in text

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_group_configured(
        self,
        patched_notification_db,
        sample_chore,
        sample_users,
    ):
        """Returns empty list when no group chat ID is configured."""
        # Populate in-memory database (no house_config)
        chore = await patched_notification_db.create_record(collection="tasks", data=sample_chore)
        claimer = await patched_notification_db.create_record(collection="members", data=sample_users[0])

        # Send verification request
        results = await notification_service.send_verification_request(
            log_id="log123",
            task_id=chore["id"],
            claimer_user_id=claimer["id"],
        )

        # Should return empty list
        assert results == []

    @pytest.mark.asyncio
    async def test_handles_send_failure(
        self,
        patched_notification_db,
        sample_chore,
        sample_users,
        monkeypatch,
    ):
        """Handles send failure gracefully."""
        # Mock send to fail
        mock_send = AsyncMock(
            return_value=SendMessageResult(success=False, message_id=None, error="Rate limit exceeded")
        )
        monkeypatch.setattr(
            "src.services.notification_service.whatsapp_sender.send_group_message",
            mock_send,
        )

        # Populate in-memory database
        chore = await patched_notification_db.create_record(collection="tasks", data=sample_chore)
        claimer = await patched_notification_db.create_record(collection="members", data=sample_users[0])

        # Set up house config with group chat ID
        await patched_notification_db.create_record(
            collection="house_config",
            data={"name": "Test House", "group_chat_id": "group123@g.us"},
        )

        # Send verification request
        results = await notification_service.send_verification_request(
            log_id="log123",
            task_id=chore["id"],
            claimer_user_id=claimer["id"],
        )

        # Should return empty list (no NotificationResult objects for group messages)
        assert len(results) == 0

        # Verify send was attempted
        assert mock_send.call_count == 1


class TestSendDeletionRequestNotification:
    """Test deletion request notifications to group chat."""

    @pytest.mark.asyncio
    async def test_sends_to_group_chat(
        self,
        patched_notification_db,
        monkeypatch,
        sample_chore,
        sample_users,
    ):
        """Sends deletion request to configured group chat."""
        # Mock send_group_message
        mock_send = AsyncMock(return_value=SendMessageResult(success=True, message_id="msg_789", error=None))
        monkeypatch.setattr(
            "src.services.notification_service.whatsapp_sender.send_group_message",
            mock_send,
        )

        # Populate in-memory database
        chore = await patched_notification_db.create_record(collection="tasks", data=sample_chore)
        requester = await patched_notification_db.create_record(collection="members", data=sample_users[0])

        # Set up house config with group chat ID
        await patched_notification_db.create_record(
            collection="house_config",
            data={"name": "Test House", "group_chat_id": "group123@g.us"},
        )

        # Send deletion request notification
        results = await notification_service.send_deletion_request_notification(
            log_id="log456",
            task_id=chore["id"],
            task_title="Dishes",
            requester_user_id=requester["id"],
        )

        # Should return empty list (no NotificationResult objects for group messages)
        assert results == []
