"""Unit tests for conversational join flow."""

from unittest.mock import AsyncMock, patch

import pytest

from src.agents.choresir_agent import handle_unknown_user


@pytest.mark.asyncio
async def test_happy_path_join_flow() -> None:
    """Test the complete happy path for joining a house via conversation."""
    phone = "+1234567890"

    with (
        patch("src.agents.choresir_agent.settings") as mock_settings,
        patch("src.agents.choresir_agent.session_service") as mock_session_service,
        patch("src.agents.choresir_agent.user_service") as mock_user_service,
    ):
        # Configure mocks
        mock_settings.house_name = "TestHouse"
        mock_settings.house_password = "secret123"
        mock_settings.house_code = "TEST123"

        mock_session_service.create_session = AsyncMock()
        mock_session_service.update_session = AsyncMock()
        mock_session_service.delete_session = AsyncMock()
        mock_session_service.is_rate_limited = lambda session: False

        mock_user_service.get_user_by_phone = AsyncMock(return_value=None)
        mock_user_service.request_join = AsyncMock(return_value={"id": "user123"})

        # Step 1: User sends /house join TestHouse → returns password prompt
        mock_session_service.get_session = AsyncMock(return_value=None)

        response1 = await handle_unknown_user(user_phone=phone, message_text="/house join TestHouse")

        assert "password" in response1.lower()
        mock_session_service.create_session.assert_called_once_with(
            phone=phone,
            house_name="testhouse",
            step="awaiting_password",
        )

        # Step 2: User sends password → returns name prompt with security reminder
        mock_session_service.get_session = AsyncMock(
            return_value={"step": "awaiting_password", "house_name": "testhouse"}
        )

        response2 = await handle_unknown_user(user_phone=phone, message_text="secret123")

        assert "name" in response2.lower()
        assert "delete" in response2.lower() or "security" in response2.lower()
        mock_session_service.update_session.assert_called_once_with(
            phone=phone,
            updates={"step": "awaiting_name"},
        )

        # Step 3: User sends name → returns welcome message
        mock_session_service.get_session = AsyncMock(return_value={"step": "awaiting_name", "house_name": "testhouse"})

        response3 = await handle_unknown_user(user_phone=phone, message_text="Alice")

        assert "welcome" in response3.lower()
        assert "alice" in response3.lower()
        mock_user_service.request_join.assert_called_once_with(
            phone=phone,
            name="Alice",
            house_code="TEST123",
            password="secret123",
        )
        mock_session_service.delete_session.assert_called_once_with(phone=phone)


@pytest.mark.asyncio
async def test_invalid_house_name_rejected() -> None:
    """Test that invalid house name returns error and creates no session."""
    phone = "+1234567890"

    with (
        patch("src.agents.choresir_agent.settings") as mock_settings,
        patch("src.agents.choresir_agent.session_service") as mock_session_service,
    ):
        mock_settings.house_name = "TestHouse"
        mock_session_service.get_session = AsyncMock(return_value=None)
        mock_session_service.create_session = AsyncMock()

        response = await handle_unknown_user(user_phone=phone, message_text="/house join WrongHouse")

        assert "invalid house name" in response.lower()
        mock_session_service.create_session.assert_not_called()


@pytest.mark.asyncio
async def test_invalid_password_rejected() -> None:
    """Test that invalid password returns error and increments attempt counter."""
    phone = "+1234567890"

    with (
        patch("src.agents.choresir_agent.settings") as mock_settings,
        patch("src.agents.choresir_agent.session_service") as mock_session_service,
    ):
        mock_settings.house_password = "correctpassword"
        mock_session_service.get_session = AsyncMock(
            return_value={"step": "awaiting_password", "house_name": "testhouse"}
        )
        mock_session_service.is_rate_limited = lambda session: False
        mock_session_service.increment_password_attempts = AsyncMock()

        response = await handle_unknown_user(user_phone=phone, message_text="wrongpassword")

        assert "invalid password" in response.lower()
        mock_session_service.increment_password_attempts.assert_called_once_with(phone=phone)


@pytest.mark.asyncio
async def test_password_rate_limiting() -> None:
    """Test that rate-limited users get wait message without password validation."""
    phone = "+1234567890"

    with patch("src.agents.choresir_agent.session_service") as mock_session_service:
        mock_session_service.get_session = AsyncMock(
            return_value={"step": "awaiting_password", "house_name": "testhouse"}
        )
        mock_session_service.is_rate_limited = lambda session: True

        response = await handle_unknown_user(user_phone=phone, message_text="anypassword")

        assert "wait" in response.lower() or "seconds" in response.lower()


@pytest.mark.asyncio
async def test_expired_session_prompts_restart() -> None:
    """Test that expired/deleted session returns onboarding prompt."""
    phone = "+1234567890"

    with patch("src.agents.choresir_agent.session_service") as mock_session_service:
        mock_session_service.get_session = AsyncMock(return_value=None)

        response = await handle_unknown_user(user_phone=phone, message_text="mypassword")

        assert "house join" in response.lower() or "/house" in response.lower()


@pytest.mark.asyncio
async def test_invalid_name_rejected() -> None:
    """Test that invalid name returns error and allows retry."""
    phone = "+1234567890"

    with (
        patch("src.agents.choresir_agent.session_service") as mock_session_service,
        patch("src.agents.choresir_agent.user_service") as mock_user_service,
    ):
        mock_session_service.get_session = AsyncMock(return_value={"step": "awaiting_name", "house_name": "testhouse"})
        mock_session_service.delete_session = AsyncMock()
        mock_user_service.request_join = AsyncMock(side_effect=ValueError("Invalid name"))

        response = await handle_unknown_user(user_phone=phone, message_text="!!!invalid!!!")

        assert "name" in response.lower()
        mock_session_service.delete_session.assert_not_called()


@pytest.mark.asyncio
async def test_cancel_with_active_session() -> None:
    """Test that /cancel deletes active session and returns confirmation."""
    phone = "+1234567890"

    with patch("src.agents.choresir_agent.session_service") as mock_session_service:
        mock_session_service.get_session = AsyncMock(return_value={"step": "awaiting_name"})
        mock_session_service.delete_session = AsyncMock()

        response = await handle_unknown_user(user_phone=phone, message_text="/cancel")

        assert "cancel" in response.lower()
        mock_session_service.delete_session.assert_called_once_with(phone=phone)


@pytest.mark.asyncio
async def test_cancel_without_session() -> None:
    """Test that /cancel without active session returns nothing to cancel."""
    phone = "+1234567890"

    with patch("src.agents.choresir_agent.session_service") as mock_session_service:
        mock_session_service.get_session = AsyncMock(return_value=None)
        mock_session_service.delete_session = AsyncMock()

        response = await handle_unknown_user(user_phone=phone, message_text="/cancel")

        assert "nothing to cancel" in response.lower()
        mock_session_service.delete_session.assert_not_called()


@pytest.mark.asyncio
async def test_house_join_uppercase_command() -> None:
    """Test that /HOUSE JOIN (uppercase) works correctly."""
    phone = "+1234567890"

    with (
        patch("src.agents.choresir_agent.settings") as mock_settings,
        patch("src.agents.choresir_agent.session_service") as mock_session_service,
    ):
        mock_settings.house_name = "TestHouse"
        mock_session_service.get_session = AsyncMock(return_value=None)
        mock_session_service.create_session = AsyncMock()

        response = await handle_unknown_user(user_phone=phone, message_text="/HOUSE JOIN TestHouse")

        assert "password" in response.lower()
        mock_session_service.create_session.assert_called_once()


@pytest.mark.asyncio
async def test_cancel_uppercase_command() -> None:
    """Test that /CANCEL (uppercase) works correctly."""
    phone = "+1234567890"

    with patch("src.agents.choresir_agent.session_service") as mock_session_service:
        mock_session_service.get_session = AsyncMock(return_value={"step": "awaiting_password"})
        mock_session_service.delete_session = AsyncMock()

        response = await handle_unknown_user(user_phone=phone, message_text="/CANCEL")

        assert "cancel" in response.lower()
        mock_session_service.delete_session.assert_called_once()
