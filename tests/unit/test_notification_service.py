"""Unit tests for notification_service module."""

from unittest.mock import AsyncMock

import pytest

from src.domain.user import UserStatus
from src.interface.whatsapp_sender import SendMessageResult
from src.services import notification_service


@pytest.fixture
def patched_notification_db(monkeypatch, in_memory_db):
    """Patches src.core.db_client functions to use InMemoryDBClient."""
    # Patch all db_client functions used by notification service
    monkeypatch.setattr("src.services.notification_service.db_client.get_record", in_memory_db.get_record)
    monkeypatch.setattr("src.services.notification_service.db_client.list_records", in_memory_db.list_records)
    return in_memory_db


@pytest.fixture
def mock_whatsapp_sender(monkeypatch):
    """Mock the whatsapp_sender.send_text_message function."""
    mock_send = AsyncMock(return_value=SendMessageResult(success=True, message_id="msg_456"))
    monkeypatch.setattr("src.services.notification_service.whatsapp_sender.send_text_message", mock_send)
    return mock_send


@pytest.fixture
def sample_chore():
    """Sample chore data (without id - will be generated)."""
    return {
        "title": "Dishes",
        "description": "Wash all the dishes",
    }


@pytest.fixture
def sample_users():
    """Sample user data (without ids - will be generated)."""
    return [
        {"name": "Alice", "phone": "+11111111111", "status": UserStatus.ACTIVE},
        {"name": "Bob", "phone": "+12222222222", "status": UserStatus.ACTIVE},
        {"name": "Charlie", "phone": "+13333333333", "status": UserStatus.ACTIVE},
    ]


class TestSendVerificationRequest:
    """Test verification request notifications."""

    @pytest.mark.asyncio
    async def test_excludes_claimer(
        self,
        patched_notification_db,
        mock_whatsapp_sender,
        sample_chore,
        sample_users,
    ):
        """Notifications go to all active users except claimer."""
        # Populate in-memory database
        chore = await patched_notification_db.create_record(collection="chores", data=sample_chore)
        created_users = []
        for user in sample_users:
            created_user = await patched_notification_db.create_record(collection="users", data=user)
            created_users.append(created_user)

        # Send verification request (first user is claimer)
        results = await notification_service.send_verification_request(
            log_id="log123",
            chore_id=chore["id"],
            claimer_user_id=created_users[0]["id"],
        )

        # Should send to user2 and user3 only (not user1/claimer)
        assert len(results) == 2
        phones = {r.phone for r in results}
        assert "+11111111111" not in phones  # user1 (claimer) excluded
        assert "+12222222222" in phones  # user2 included
        assert "+13333333333" in phones  # user3 included

        # All should be successful
        assert all(r.success for r in results)

        # Message should be sent twice
        assert mock_whatsapp_sender.call_count == 2

    @pytest.mark.asyncio
    async def test_sends_verification_request_text(
        self,
        patched_notification_db,
        mock_whatsapp_sender,
        sample_chore,
        sample_users,
    ):
        """Uses text message with instructions."""
        # Populate in-memory database
        chore = await patched_notification_db.create_record(collection="chores", data=sample_chore)
        created_users = []
        for user in sample_users:
            created_user = await patched_notification_db.create_record(collection="users", data=user)
            created_users.append(created_user)

        # Send verification request
        await notification_service.send_verification_request(
            log_id="log123",
            chore_id=chore["id"],
            claimer_user_id=created_users[0]["id"],
        )

        # Verify text message was called
        assert mock_whatsapp_sender.call_count == 2

        # Check first call arguments
        first_call = mock_whatsapp_sender.call_args_list[0]
        assert first_call.kwargs["to_phone"] in ["+12222222222", "+13333333333"]
        assert "Alice" in first_call.kwargs["text"]  # claimer name
        assert "Dishes" in first_call.kwargs["text"]  # chore title
        assert "log123" in first_call.kwargs["text"]  # log_id
        assert "approve log123" in first_call.kwargs["text"]
        assert "reject log123" in first_call.kwargs["text"]

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_chore_not_found(
        self,
        patched_notification_db,
        sample_users,
    ):
        """Returns empty list when chore doesn't exist."""
        # Only add users, no chore
        for user in sample_users:
            await patched_notification_db.create_record(collection="users", data=user)

        # Send verification request with non-existent chore
        results = await notification_service.send_verification_request(
            log_id="log123",
            chore_id="nonexistent",
            claimer_user_id="user1",
        )

        # Should return empty list
        assert results == []

    @pytest.mark.asyncio
    async def test_handles_claimer_not_found(
        self,
        patched_notification_db,
        mock_whatsapp_sender,
        sample_chore,
        sample_users,
    ):
        """Uses 'Someone' as claimer name when claimer not found."""
        # Populate in-memory database (only chore and users, but claimer doesn't exist)
        chore = await patched_notification_db.create_record(collection="chores", data=sample_chore)
        for user in sample_users:
            await patched_notification_db.create_record(collection="users", data=user)

        # Send verification request with non-existent claimer
        results = await notification_service.send_verification_request(
            log_id="log123",
            chore_id=chore["id"],
            claimer_user_id="nonexistent_user",
        )

        # Should still send to all users
        assert len(results) == 3

        # Check that "Someone" is used as claimer name in text
        first_call = mock_whatsapp_sender.call_args_list[0]
        assert "Someone" in first_call.kwargs["text"]

    @pytest.mark.asyncio
    async def test_only_sends_to_active_users(
        self,
        patched_notification_db,
        mock_whatsapp_sender,
        sample_chore,
    ):
        """Only sends notifications to active users."""
        # Populate with users of different statuses
        users = [
            {"name": "Alice", "phone": "+11111111111", "status": UserStatus.ACTIVE},
            {"name": "Bob", "phone": "+12222222222", "status": UserStatus.ACTIVE},
            {"name": "Charlie", "phone": "+13333333333", "status": UserStatus.PENDING_NAME},
        ]

        chore = await patched_notification_db.create_record(collection="chores", data=sample_chore)
        created_users = []
        for user in users:
            created_user = await patched_notification_db.create_record(collection="users", data=user)
            created_users.append(created_user)

        # Send verification request (first user is claimer)
        results = await notification_service.send_verification_request(
            log_id="log123",
            chore_id=chore["id"],
            claimer_user_id=created_users[0]["id"],
        )

        # Should only send to user2 (active, not claimer)
        # user3 is pending, user1 is claimer
        assert len(results) == 1
        assert results[0].phone == "+12222222222"
        assert results[0].user_id == created_users[1]["id"]

    @pytest.mark.asyncio
    async def test_handles_send_failures(
        self,
        patched_notification_db,
        sample_chore,
        sample_users,
        monkeypatch,
    ):
        """Handles send failures gracefully."""

        # Mock send to fail for specific phone
        async def mock_send_text(**kwargs):
            if kwargs["to_phone"] == "+12222222222":
                return SendMessageResult(success=False, error="Rate limit exceeded")
            return SendMessageResult(success=True, message_id="msg_123")

        monkeypatch.setattr(
            "src.services.notification_service.whatsapp_sender.send_text_message",
            mock_send_text,
        )

        # Populate in-memory database
        chore = await patched_notification_db.create_record(collection="chores", data=sample_chore)
        created_users = []
        for user in sample_users:
            created_user = await patched_notification_db.create_record(collection="users", data=user)
            created_users.append(created_user)

        # Send verification request
        results = await notification_service.send_verification_request(
            log_id="log123",
            chore_id=chore["id"],
            claimer_user_id=created_users[0]["id"],
        )

        # Should have results for both users
        assert len(results) == 2

        # Find the failed one
        failed_results = [r for r in results if not r.success]
        assert len(failed_results) == 1
        assert failed_results[0].phone == "+12222222222"
        assert failed_results[0].error == "Rate limit exceeded"

        # Find the successful one
        success_results = [r for r in results if r.success]
        assert len(success_results) == 1
        assert success_results[0].phone == "+13333333333"

    @pytest.mark.asyncio
    async def test_returns_empty_list_when_no_other_users(
        self,
        patched_notification_db,
        sample_chore,
    ):
        """Returns empty list when only the claimer exists."""
        # Only add the chore and the claimer
        chore = await patched_notification_db.create_record(collection="chores", data=sample_chore)
        claimer = await patched_notification_db.create_record(
            collection="users",
            data={"name": "Alice", "phone": "+11111111111", "status": UserStatus.ACTIVE},
        )

        # Send verification request
        results = await notification_service.send_verification_request(
            log_id="log123",
            chore_id=chore["id"],
            claimer_user_id=claimer["id"],
        )

        # Should return empty list (no one to notify)
        assert results == []
