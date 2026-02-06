"""Tests for handle_unknown_user function."""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest

from src.agents import choresir_agent


@pytest.mark.asyncio
async def test_pending_invite_confirmation_success():
    """Test confirming a pending invite with YES."""
    user_phone = "+1234567890"
    message_text = "YES"

    with (
        patch("src.agents.choresir_agent.db_client") as mock_db_client,
        patch("src.agents.choresir_agent.user_service") as mock_user_service,
        patch("src.agents.choresir_agent.get_house_config") as mock_get_config,
    ):
        # Setup mocks
        mock_db_client.get_first_record = AsyncMock(
            return_value={
                "id": "invite123",
                "phone": "+1234567890",
            }
        )
        mock_db_client.update_record = AsyncMock()
        mock_db_client.delete_record = AsyncMock()
        mock_user_service.get_user_by_phone = AsyncMock(
            return_value={
                "id": "user123",
                "phone": "+1234567890",
                "name": "Test User",
                "status": "pending",
            }
        )
        mock_get_config.return_value = {"name": "MyHouse"}

        result = await choresir_agent.handle_unknown_user(
            user_phone=user_phone,
            message_text=message_text,
        )

        # Should confirm invite and return welcome message
        assert "Welcome to MyHouse" in result
        assert "Your membership is now active" in result
        mock_db_client.update_record.assert_called_once()
        mock_db_client.delete_record.assert_called_once()


@pytest.mark.asyncio
async def test_pending_invite_confirmation_case_insensitive():
    """Test confirming a pending invite with various case variations of YES."""
    user_phone = "+1234567890"
    test_cases = ["yes", "Yes", "YES", "yEs"]

    with (
        patch("src.agents.choresir_agent.db_client") as mock_db_client,
        patch("src.agents.choresir_agent.user_service") as mock_user_service,
        patch("src.agents.choresir_agent.get_house_config") as mock_get_config,
    ):
        for message_text in test_cases:
            # Setup mocks
            mock_db_client.get_first_record = AsyncMock(
                return_value={
                    "id": "invite123",
                    "phone": "+1234567890",
                }
            )
            mock_db_client.update_record = AsyncMock()
            mock_db_client.delete_record = AsyncMock()
            mock_user_service.get_user_by_phone = AsyncMock(
                return_value={
                    "id": "user123",
                    "phone": "+1234567890",
                    "name": "Test User",
                    "status": "pending",
                }
            )
            mock_get_config.return_value = {"name": "MyHouse"}

            result = await choresir_agent.handle_unknown_user(
                user_phone=user_phone,
                message_text=message_text,
            )

            # Should confirm invite
            assert "Welcome to MyHouse" in result
            mock_db_client.update_record.assert_called_once()
            mock_db_client.delete_record.assert_called_once()


@pytest.mark.asyncio
async def test_pending_invite_confirmation_user_not_found():
    """Test confirming a pending invite when user is not found."""
    user_phone = "+1234567890"
    message_text = "YES"

    with (
        patch("src.agents.choresir_agent.db_client") as mock_db_client,
        patch("src.agents.choresir_agent.user_service") as mock_user_service,
    ):
        mock_db_client.get_first_record = AsyncMock(
            return_value={
                "id": "invite123",
                "phone": "+1234567890",
                "invited_at": datetime.now(UTC).isoformat(),
            }
        )
        mock_user_service.get_user_by_phone = AsyncMock(return_value=None)

        result = await choresir_agent.handle_unknown_user(
            user_phone=user_phone,
            message_text=message_text,
        )

        # Should return error message
        assert "Sorry, there was an error processing your invite" in result
        assert "Please contact an admin" in result


@pytest.mark.asyncio
async def test_pending_invite_non_yes_message():
    """Test that non-YES message prompts user to reply YES."""
    user_phone = "+1234567890"
    message_text = "Hello"

    with patch("src.agents.choresir_agent.db_client") as mock_db_client:
        mock_db_client.get_first_record = AsyncMock(
            return_value={
                "id": "invite123",
                "phone": "+1234567890",
                "invited_at": datetime.now(UTC).isoformat(),
            }
        )

        result = await choresir_agent.handle_unknown_user(
            user_phone=user_phone,
            message_text=message_text,
        )

        # Should instruct user to reply YES
        assert "To confirm your invitation, please reply YES" in result


@pytest.mark.asyncio
async def test_no_pending_invite_returns_not_a_member():
    """Test that unknown user without pending invite gets not a member message."""
    user_phone = "+1234567890"
    message_text = "Hello"

    with patch("src.agents.choresir_agent.db_client") as mock_db_client:
        mock_db_client.get_first_record = AsyncMock(return_value=None)

        result = await choresir_agent.handle_unknown_user(
            user_phone=user_phone,
            message_text=message_text,
        )

        # Should return not a member message
        assert "You are not a member of this household" in result
        assert "Please contact an admin to request an invite" in result


@pytest.mark.asyncio
async def test_house_join_command_returns_not_a_member():
    """Test that /house join command returns not a member message."""
    user_phone = "+1234567890"
    message_text = "/house join MyHouse"

    with patch("src.agents.choresir_agent.db_client") as mock_db_client:
        mock_db_client.get_first_record = AsyncMock(return_value=None)

        result = await choresir_agent.handle_unknown_user(
            user_phone=user_phone,
            message_text=message_text,
        )

        # Should return not a member message
        assert "You are not a member of this household" in result
        assert "Please contact an admin to request an invite" in result
