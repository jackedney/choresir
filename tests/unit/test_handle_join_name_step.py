"""Unit tests for handle_join_name_step function."""

from unittest.mock import AsyncMock, patch

import pytest

from src.agents.choresir_agent import handle_join_name_step


@pytest.mark.asyncio
async def test_name_step_validates_name_with_user_model() -> None:
    """Test that name validation uses User model validator."""
    with (
        patch("src.agents.choresir_agent.settings") as mock_settings,
        patch("src.agents.choresir_agent.session_service") as mock_session_service,
        patch("src.agents.choresir_agent.user_service") as mock_user_service,
        patch("src.agents.choresir_agent.User") as mock_user_class,
    ):
        mock_settings.house_password = "correct_password"
        mock_session_service.get_session = AsyncMock(
            return_value={
                "id": "session123",
                "phone": "+1234567890",
                "house_name": "TestHouse",
                "step": "awaiting_name",
            }
        )
        mock_user_service.request_join = AsyncMock()
        mock_session_service.delete_session = AsyncMock()

        # Mock User constructor to validate name
        mock_user_class.return_value = None  # Success

        await handle_join_name_step("+1234567890", "John Doe")

        # Verify User constructor was called with the name
        mock_user_class.assert_called_once()
        call_kwargs = mock_user_class.call_args[1]
        assert call_kwargs["name"] == "John Doe"
        assert call_kwargs["phone"] == "+1234567890"
        assert call_kwargs["id"] == "temp"


@pytest.mark.asyncio
async def test_name_step_handles_invalid_name() -> None:
    """Test that invalid names return error without deleting session."""
    with (
        patch("src.agents.choresir_agent.settings") as mock_settings,
        patch("src.agents.choresir_agent.session_service") as mock_session_service,
        patch("src.agents.choresir_agent.user_service") as mock_user_service,
        patch("src.agents.choresir_agent.User") as mock_user_class,
    ):
        mock_settings.house_password = "correct_password"
        mock_session_service.get_session = AsyncMock(
            return_value={
                "id": "session123",
                "phone": "+1234567890",
                "house_name": "TestHouse",
                "step": "awaiting_name",
            }
        )
        mock_user_service.request_join = AsyncMock()
        mock_session_service.delete_session = AsyncMock()

        # Mock User constructor to raise ValueError
        mock_user_class.side_effect = ValueError("Name can only contain letters, spaces, hyphens, and apostrophes")

        response = await handle_join_name_step("+1234567890", "🎉emoji")

        # Verify error message
        assert "name isn't usable" in response.lower()
        assert "letters, spaces, hyphens, and apostrophes" in response.lower()

        # Verify session was NOT deleted
        mock_session_service.delete_session.assert_not_called()

        # Verify join request was NOT created
        mock_user_service.request_join.assert_not_called()


@pytest.mark.asyncio
async def test_name_step_deletes_session_after_success() -> None:
    """Test that session is deleted after successful join."""
    with (
        patch("src.agents.choresir_agent.settings") as mock_settings,
        patch("src.agents.choresir_agent.session_service") as mock_session_service,
        patch("src.agents.choresir_agent.user_service") as mock_user_service,
        patch("src.agents.choresir_agent.User") as mock_user_class,
    ):
        mock_settings.house_password = "correct_password"
        mock_session_service.get_session = AsyncMock(
            return_value={
                "id": "session123",
                "phone": "+1234567890",
                "house_name": "TestHouse",
                "step": "awaiting_name",
            }
        )
        mock_user_service.request_join = AsyncMock()
        mock_session_service.delete_session = AsyncMock()
        mock_user_class.return_value = None  # Success

        response = await handle_join_name_step("+1234567890", "John Doe")

        # Verify session was deleted
        mock_session_service.delete_session.assert_called_once_with(phone="+1234567890")

        # Verify welcome message
        assert "welcome" in response.lower()
        assert "John Doe" in response


@pytest.mark.asyncio
async def test_name_step_calls_request_join_with_correct_params() -> None:
    """Test that request_join is called with correct parameters."""
    with (
        patch("src.agents.choresir_agent.settings") as mock_settings,
        patch("src.agents.choresir_agent.session_service") as mock_session_service,
        patch("src.agents.choresir_agent.user_service") as mock_user_service,
        patch("src.agents.choresir_agent.User") as mock_user_class,
    ):
        mock_settings.house_password = "correct_password"
        mock_settings.house_code = "TestHouse"
        mock_session_service.get_session = AsyncMock(
            return_value={
                "id": "session123",
                "phone": "+1234567890",
                "house_name": "TestHouse",
                "step": "awaiting_name",
            }
        )
        mock_user_service.request_join = AsyncMock()
        mock_session_service.delete_session = AsyncMock()
        mock_user_class.return_value = None  # Success

        await handle_join_name_step("+1234567890", "John Doe")

        # Verify request_join was called with correct params (house_code now comes from settings)
        mock_user_service.request_join.assert_called_once_with(
            phone="+1234567890",
            name="John Doe",
            house_code="TestHouse",
            password="correct_password",
        )


@pytest.mark.asyncio
async def test_name_step_handles_expired_session() -> None:
    """Test that expired session returns appropriate error."""
    with patch("src.agents.choresir_agent.session_service") as mock_session_service:
        mock_session_service.get_session = AsyncMock(return_value=None)

        response = await handle_join_name_step("+1234567890", "John Doe")

        # Verify error message
        assert "session has expired" in response.lower()
        assert "/house join" in response.lower()


@pytest.mark.asyncio
async def test_name_step_handles_wrong_session_step() -> None:
    """Test that session in wrong step returns error."""
    with patch("src.agents.choresir_agent.session_service") as mock_session_service:
        mock_session_service.get_session = AsyncMock(
            return_value={
                "id": "session123",
                "phone": "+1234567890",
                "house_name": "TestHouse",
                "step": "awaiting_password",  # Wrong step
            }
        )

        response = await handle_join_name_step("+1234567890", "John Doe")

        # Verify error message
        assert "something went wrong" in response.lower()
        assert "/house join" in response.lower()


@pytest.mark.asyncio
async def test_name_step_deletes_session_even_if_join_fails() -> None:
    """Test that session is deleted even if join request fails."""
    with (
        patch("src.agents.choresir_agent.settings") as mock_settings,
        patch("src.agents.choresir_agent.session_service") as mock_session_service,
        patch("src.agents.choresir_agent.user_service") as mock_user_service,
        patch("src.agents.choresir_agent.User") as mock_user_class,
    ):
        mock_settings.house_password = "correct_password"
        mock_session_service.get_session = AsyncMock(
            return_value={
                "id": "session123",
                "phone": "+1234567890",
                "house_name": "TestHouse",
                "step": "awaiting_name",
            }
        )
        # Simulate join failure
        mock_user_service.request_join = AsyncMock(side_effect=Exception("Database error"))
        mock_session_service.delete_session = AsyncMock()
        mock_user_class.return_value = None  # Name validation succeeds

        response = await handle_join_name_step("+1234567890", "John Doe")

        # Verify session was deleted even though join failed
        mock_session_service.delete_session.assert_called_once_with(phone="+1234567890")

        # Verify error message
        assert "something went wrong" in response.lower()


@pytest.mark.asyncio
async def test_name_step_handles_missing_house_password() -> None:
    """Test that missing house password returns error."""
    with (
        patch("src.agents.choresir_agent.settings") as mock_settings,
        patch("src.agents.choresir_agent.session_service") as mock_session_service,
        patch("src.agents.choresir_agent.user_service") as mock_user_service,
        patch("src.agents.choresir_agent.User") as mock_user_class,
    ):
        mock_settings.house_password = None  # Not configured
        mock_session_service.get_session = AsyncMock(
            return_value={
                "id": "session123",
                "phone": "+1234567890",
                "house_name": "TestHouse",
                "step": "awaiting_name",
            }
        )
        mock_session_service.delete_session = AsyncMock()
        mock_user_service.request_join = AsyncMock()
        mock_user_class.return_value = None  # Name validation succeeds

        response = await handle_join_name_step("+1234567890", "John Doe")

        # Verify error message
        assert "not available" in response.lower()
        assert "contact an administrator" in response.lower()

        # Verify session was deleted
        mock_session_service.delete_session.assert_called_once_with(phone="+1234567890")

        # Verify join request was NOT created
        mock_user_service.request_join.assert_not_called()
