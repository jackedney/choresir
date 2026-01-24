"""Unit tests for handle_house_join function."""

from unittest.mock import AsyncMock, patch

import pytest

from src.agents.choresir_agent import handle_house_join
from src.domain.user import UserStatus


@pytest.mark.asyncio
async def test_handle_house_join_validates_house_name() -> None:
    """Test that handle_house_join validates the house name."""
    # Mock settings and services
    with (
        patch("src.agents.choresir_agent.settings") as mock_settings,
        patch("src.agents.choresir_agent.user_service") as mock_user_service,
        patch("src.agents.choresir_agent.session_service") as mock_session_service,
    ):
        mock_settings.house_name = "TestHouse"
        mock_user_service.get_user_by_phone = AsyncMock(return_value=None)
        mock_session_service.create_session = AsyncMock()

        # Test valid house name (case-insensitive)
        response = await handle_house_join("+1234567890", "testhouse")
        assert "password" in response.lower()
        mock_session_service.create_session.assert_called_once()

        # Reset mock
        mock_session_service.create_session.reset_mock()

        # Test invalid house name
        response = await handle_house_join("+1234567890", "WrongHouse")
        assert "invalid house name" in response.lower()
        mock_session_service.create_session.assert_not_called()


@pytest.mark.asyncio
async def test_handle_house_join_checks_existing_member() -> None:
    """Test that handle_house_join checks if user is already a member."""
    with (
        patch("src.agents.choresir_agent.settings") as mock_settings,
        patch("src.agents.choresir_agent.user_service") as mock_user_service,
        patch("src.agents.choresir_agent.session_service") as mock_session_service,
    ):
        mock_settings.house_name = "TestHouse"
        mock_user_service.get_user_by_phone = AsyncMock(
            return_value={
                "id": "user123",
                "phone": "+1234567890",
                "name": "Test User",
                "status": UserStatus.ACTIVE,
            }
        )
        mock_session_service.create_session = AsyncMock()

        response = await handle_house_join("+1234567890", "TestHouse")
        assert "already a member" in response.lower()
        mock_session_service.create_session.assert_not_called()


@pytest.mark.asyncio
async def test_handle_house_join_creates_session_on_success() -> None:
    """Test that handle_house_join creates session on successful validation."""
    with (
        patch("src.agents.choresir_agent.settings") as mock_settings,
        patch("src.agents.choresir_agent.user_service") as mock_user_service,
        patch("src.agents.choresir_agent.session_service") as mock_session_service,
    ):
        mock_settings.house_name = "TestHouse"
        mock_user_service.get_user_by_phone = AsyncMock(return_value=None)
        mock_session_service.create_session = AsyncMock()

        response = await handle_house_join("+1234567890", "TestHouse")

        # Verify password prompt
        assert "password" in response.lower()

        # Verify session creation (house_name preserves original case)
        mock_session_service.create_session.assert_called_once_with(
            phone="+1234567890",
            house_name="TestHouse",
            step="awaiting_password",
        )


@pytest.mark.asyncio
async def test_handle_house_join_handles_missing_config() -> None:
    """Test that handle_house_join handles missing house_name config."""
    with (
        patch("src.agents.choresir_agent.settings") as mock_settings,
        patch("src.agents.choresir_agent.user_service") as mock_user_service,
        patch("src.agents.choresir_agent.session_service") as mock_session_service,
    ):
        mock_settings.house_name = None
        mock_user_service.get_user_by_phone = AsyncMock()
        mock_session_service.create_session = AsyncMock()

        response = await handle_house_join("+1234567890", "AnyHouse")

        # Should return error about service not available
        assert "not available" in response.lower() or "administrator" in response.lower()
        mock_session_service.create_session.assert_not_called()


@pytest.mark.asyncio
async def test_handle_house_join_case_insensitive() -> None:
    """Test that house name matching is case-insensitive."""
    with (
        patch("src.agents.choresir_agent.settings") as mock_settings,
        patch("src.agents.choresir_agent.user_service") as mock_user_service,
        patch("src.agents.choresir_agent.session_service") as mock_session_service,
    ):
        mock_settings.house_name = "MyHouse"
        mock_user_service.get_user_by_phone = AsyncMock(return_value=None)
        mock_session_service.create_session = AsyncMock()

        # Test various cases
        test_cases = ["myhouse", "MYHOUSE", "MyHoUsE", "MyHouse"]

        for house_name in test_cases:
            mock_session_service.create_session.reset_mock()
            response = await handle_house_join("+1234567890", house_name)
            assert "password" in response.lower()
            mock_session_service.create_session.assert_called_once()


@pytest.mark.asyncio
async def test_handle_house_join_ignores_pending_users() -> None:
    """Test that handle_house_join allows pending users to restart join flow."""
    with (
        patch("src.agents.choresir_agent.settings") as mock_settings,
        patch("src.agents.choresir_agent.user_service") as mock_user_service,
        patch("src.agents.choresir_agent.session_service") as mock_session_service,
    ):
        mock_settings.house_name = "TestHouse"
        mock_user_service.get_user_by_phone = AsyncMock(
            return_value={
                "id": "user123",
                "phone": "+1234567890",
                "name": "Test User",
                "status": UserStatus.PENDING,  # Not ACTIVE
            }
        )
        mock_session_service.create_session = AsyncMock()

        response = await handle_house_join("+1234567890", "TestHouse")

        # Should allow pending users to restart (they're not "active members")
        assert "password" in response.lower()
        mock_session_service.create_session.assert_called_once()
