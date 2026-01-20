"""Unit tests for handle_join_password_step function."""

from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from src.agents.choresir_agent import handle_join_password_step


@pytest.mark.asyncio
async def test_password_step_validates_password_with_constant_time() -> None:
    """Test that password validation uses constant-time comparison."""
    with (
        patch("src.agents.choresir_agent.settings") as mock_settings,
        patch("src.agents.choresir_agent.session_service") as mock_session_service,
        patch("secrets.compare_digest") as mock_compare_digest,
    ):
        mock_settings.house_password = "correct_password"
        mock_session_service.get_session = AsyncMock(
            return_value={
                "id": "session123",
                "phone": "+1234567890",
                "house_name": "TestHouse",
                "step": "awaiting_password",
                "password_attempts_count": 0,
            }
        )
        mock_session_service.is_rate_limited = lambda session: False
        mock_session_service.update_session = AsyncMock()
        mock_compare_digest.return_value = True

        await handle_join_password_step("+1234567890", "test_password")

        # Verify secrets.compare_digest was called with encoded strings
        mock_compare_digest.assert_called_once()
        call_args = mock_compare_digest.call_args[0]
        assert call_args[0] == b"test_password"
        assert call_args[1] == b"correct_password"


@pytest.mark.asyncio
async def test_password_step_checks_rate_limiting() -> None:
    """Test that rate limiting is checked before password validation."""
    with (
        patch("src.agents.choresir_agent.settings") as mock_settings,
        patch("src.agents.choresir_agent.session_service") as mock_session_service,
    ):
        mock_settings.house_password = "correct_password"
        session = {
            "id": "session123",
            "phone": "+1234567890",
            "house_name": "TestHouse",
            "step": "awaiting_password",
            "password_attempts_count": 1,
            "last_attempt_at": datetime.now().isoformat(),
        }
        mock_session_service.get_session = AsyncMock(return_value=session)
        mock_session_service.is_rate_limited = lambda session: True
        mock_session_service.increment_password_attempts = AsyncMock()

        response = await handle_join_password_step("+1234567890", "correct_password")

        # Verify rate limit message
        assert "wait a few seconds" in response.lower()

        # Verify increment_password_attempts was NOT called
        mock_session_service.increment_password_attempts.assert_not_called()


@pytest.mark.asyncio
async def test_password_step_increments_attempts_on_failure() -> None:
    """Test that failed attempts increment the counter."""
    with (
        patch("src.agents.choresir_agent.settings") as mock_settings,
        patch("src.agents.choresir_agent.session_service") as mock_session_service,
    ):
        mock_settings.house_password = "correct_password"
        mock_session_service.get_session = AsyncMock(
            return_value={
                "id": "session123",
                "phone": "+1234567890",
                "house_name": "TestHouse",
                "step": "awaiting_password",
                "password_attempts_count": 0,
            }
        )
        mock_session_service.is_rate_limited = lambda session: False
        mock_session_service.increment_password_attempts = AsyncMock()

        response = await handle_join_password_step("+1234567890", "wrong_password")

        # Verify error message
        assert "invalid password" in response.lower()
        assert "try again" in response.lower()

        # Verify increment was called
        mock_session_service.increment_password_attempts.assert_called_once_with(phone="+1234567890")


@pytest.mark.asyncio
async def test_password_step_updates_session_on_success() -> None:
    """Test that successful password validation updates session to awaiting_name."""
    with (
        patch("src.agents.choresir_agent.settings") as mock_settings,
        patch("src.agents.choresir_agent.session_service") as mock_session_service,
    ):
        mock_settings.house_password = "correct_password"
        mock_session_service.get_session = AsyncMock(
            return_value={
                "id": "session123",
                "phone": "+1234567890",
                "house_name": "TestHouse",
                "step": "awaiting_password",
                "password_attempts_count": 0,
            }
        )
        mock_session_service.is_rate_limited = lambda session: False
        mock_session_service.update_session = AsyncMock()

        response = await handle_join_password_step("+1234567890", "correct_password")

        # Verify success message
        assert "delete your previous message" in response.lower()
        assert "name would you like" in response.lower()

        # Verify session update
        mock_session_service.update_session.assert_called_once_with(
            phone="+1234567890",
            updates={"step": "awaiting_name"},
        )


@pytest.mark.asyncio
async def test_password_step_handles_expired_session() -> None:
    """Test that expired sessions return appropriate error."""
    with (
        patch("src.agents.choresir_agent.settings") as mock_settings,
        patch("src.agents.choresir_agent.session_service") as mock_session_service,
    ):
        mock_settings.house_password = "correct_password"
        mock_session_service.get_session = AsyncMock(return_value=None)

        response = await handle_join_password_step("+1234567890", "correct_password")

        # Verify expired session message
        assert "session has expired" in response.lower()
        assert "/house join" in response.lower()


@pytest.mark.asyncio
async def test_password_step_handles_missing_config() -> None:
    """Test that missing password config returns error."""
    with (
        patch("src.agents.choresir_agent.settings") as mock_settings,
        patch("src.agents.choresir_agent.session_service") as mock_session_service,
    ):
        mock_settings.house_password = None
        mock_session_service.get_session = AsyncMock(
            return_value={
                "id": "session123",
                "phone": "+1234567890",
                "house_name": "TestHouse",
                "step": "awaiting_password",
                "password_attempts_count": 0,
            }
        )
        mock_session_service.is_rate_limited = lambda session: False

        response = await handle_join_password_step("+1234567890", "any_password")

        # Verify error message
        assert "not available" in response.lower() or "administrator" in response.lower()


@pytest.mark.asyncio
async def test_password_step_includes_house_name_in_error() -> None:
    """Test that error message includes house name for context."""
    with (
        patch("src.agents.choresir_agent.settings") as mock_settings,
        patch("src.agents.choresir_agent.session_service") as mock_session_service,
    ):
        mock_settings.house_password = "correct_password"
        mock_session_service.get_session = AsyncMock(
            return_value={
                "id": "session123",
                "phone": "+1234567890",
                "house_name": "MyTestHouse",
                "step": "awaiting_password",
                "password_attempts_count": 0,
            }
        )
        mock_session_service.is_rate_limited = lambda session: False
        mock_session_service.increment_password_attempts = AsyncMock()

        response = await handle_join_password_step("+1234567890", "wrong_password")

        # Verify house name is in error message
        assert "MyTestHouse" in response
