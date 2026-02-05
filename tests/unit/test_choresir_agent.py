"""Unit tests for choresir_agent error handling."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.base import Deps
from src.agents.choresir_agent import handle_unknown_user, run_agent
from src.core.errors import ErrorCategory


@pytest.fixture(autouse=True)
def mock_admin_notifier():
    """Mock admin notifier to avoid WhatsApp API calls with retry delays."""
    with patch("src.agents.choresir_agent.admin_notifier") as mock_notifier:
        mock_notifier.should_notify_admins.return_value = False
        mock_notifier.notify_admins = AsyncMock()
        yield mock_notifier


@pytest.mark.unit
class TestChoresirAgentErrorHandling:
    """Tests for choresir agent error handling with error classification."""

    @pytest.fixture
    def mock_deps(self):
        """Create mock dependencies for agent execution."""
        return Deps(
            db=MagicMock(),
            user_id="test_user_123",
            user_phone="+1234567890",
            user_name="Test User",
            user_role="member",
            current_time=datetime(2024, 1, 1, 12, 0, 0),
        )

    @pytest.fixture
    def mock_member_list(self):
        """Create mock member list."""
        return "- Test User (+1234567890)\n- Admin User (+9876543210) (admin)"

    def _mock_agent_with_error(self, exception):
        """Helper to mock agent and retry handler with an error."""
        mock_agent = AsyncMock()
        mock_agent.run.side_effect = exception

        mock_retry_handler = AsyncMock()
        mock_retry_handler.execute_with_retry.side_effect = exception

        return mock_agent, mock_retry_handler

    @pytest.mark.asyncio
    async def test_quota_exceeded_error_returns_user_friendly_message(self, mock_deps, mock_member_list):
        """Test that quota exceeded errors return appropriate user message."""
        with (
            patch("src.agents.choresir_agent.get_agent") as mock_get_agent,
            patch("src.agents.choresir_agent.get_retry_handler") as mock_get_retry_handler,
        ):
            # Mock agent to raise quota exceeded error
            mock_agent = AsyncMock()
            mock_agent.run.side_effect = Exception("OpenRouter API error: quota exceeded")
            mock_get_agent.return_value = mock_agent

            # Mock retry handler to pass through the error
            mock_retry_handler = AsyncMock()
            mock_retry_handler.execute_with_retry.side_effect = Exception("OpenRouter API error: quota exceeded")
            mock_get_retry_handler.return_value = mock_retry_handler

            # Run agent
            result = await run_agent(
                user_message="What chores do I have?",
                deps=mock_deps,
                member_list=mock_member_list,
            )

            # Verify user-friendly message
            assert "quota" in result.lower()
            assert "try again later" in result.lower()
            assert "contact support" in result.lower()
            # Ensure message is concise (WhatsApp-friendly)
            assert len(result.split(".")) <= 3  # Max 2-3 sentences

    @pytest.mark.asyncio
    async def test_rate_limit_error_returns_user_friendly_message(self, mock_deps, mock_member_list):
        """Test that rate limit errors return appropriate user message."""
        exception = Exception("Rate limit exceeded. Try again in 60s")
        with (
            patch("src.agents.choresir_agent.get_agent") as mock_get_agent,
            patch("src.agents.choresir_agent.get_retry_handler") as mock_get_retry_handler,
        ):
            mock_agent, mock_retry_handler = self._mock_agent_with_error(exception)
            mock_get_agent.return_value = mock_agent
            mock_get_retry_handler.return_value = mock_retry_handler

            # Run agent
            result = await run_agent(
                user_message="Show me the leaderboard",
                deps=mock_deps,
                member_list=mock_member_list,
            )

            # Verify user-friendly message
            assert "too many requests" in result.lower()
            assert "wait" in result.lower()
            # Ensure message is concise
            assert len(result.split(".")) <= 3

    @pytest.mark.asyncio
    async def test_authentication_error_returns_user_friendly_message(self, mock_deps, mock_member_list):
        """Test that authentication errors return appropriate user message."""
        exception = Exception("Invalid API key provided")
        with (
            patch("src.agents.choresir_agent.get_agent") as mock_get_agent,
            patch("src.agents.choresir_agent.get_retry_handler") as mock_get_retry_handler,
        ):
            mock_agent, mock_retry_handler = self._mock_agent_with_error(exception)
            mock_get_agent.return_value = mock_agent
            mock_get_retry_handler.return_value = mock_retry_handler

            # Run agent
            result = await run_agent(
                user_message="What's my score?",
                deps=mock_deps,
                member_list=mock_member_list,
            )

            # Verify user-friendly message
            assert "authentication" in result.lower()
            assert "contact support" in result.lower()
            # Ensure message is concise
            assert len(result.split(".")) <= 3

    @pytest.mark.asyncio
    async def test_network_error_returns_user_friendly_message(self, mock_deps, mock_member_list):
        """Test that network errors return appropriate user message."""
        exception = ConnectionError("Connection failed")
        with (
            patch("src.agents.choresir_agent.get_agent") as mock_get_agent,
            patch("src.agents.choresir_agent.get_retry_handler") as mock_get_retry_handler,
        ):
            mock_agent, mock_retry_handler = self._mock_agent_with_error(exception)
            mock_get_agent.return_value = mock_agent
            mock_get_retry_handler.return_value = mock_retry_handler

            # Run agent
            result = await run_agent(
                user_message="Add a chore",
                deps=mock_deps,
                member_list=mock_member_list,
            )

            # Verify user-friendly message
            assert "network" in result.lower()
            assert "connection" in result.lower()
            # Ensure message is concise
            assert len(result.split(".")) <= 3

    @pytest.mark.asyncio
    async def test_unknown_error_returns_generic_message(self, mock_deps, mock_member_list):
        """Test that unknown errors return generic user message."""
        exception = ValueError("Something went wrong")
        with (
            patch("src.agents.choresir_agent.get_agent") as mock_get_agent,
            patch("src.agents.choresir_agent.get_retry_handler") as mock_get_retry_handler,
        ):
            mock_agent, mock_retry_handler = self._mock_agent_with_error(exception)
            mock_get_agent.return_value = mock_agent
            mock_get_retry_handler.return_value = mock_retry_handler

            # Run agent
            result = await run_agent(
                user_message="Do something",
                deps=mock_deps,
                member_list=mock_member_list,
            )

            # Verify generic error message
            assert "unexpected error" in result.lower()
            assert "try again later" in result.lower()
            # Ensure message is concise
            assert len(result.split(".")) <= 3

    @pytest.mark.asyncio
    async def test_error_logging_includes_category(self, mock_deps, mock_member_list):
        """Test that error logging includes the error category."""
        exception = Exception("quota exceeded")
        with (
            patch("src.agents.choresir_agent.get_agent") as mock_get_agent,
            patch("src.agents.choresir_agent.get_retry_handler") as mock_get_retry_handler,
            patch("src.agents.choresir_agent.logfire") as mock_logfire,
        ):
            mock_agent, mock_retry_handler = self._mock_agent_with_error(exception)
            mock_get_agent.return_value = mock_agent
            mock_get_retry_handler.return_value = mock_retry_handler

            # Run agent
            await run_agent(
                user_message="Test message",
                deps=mock_deps,
                member_list=mock_member_list,
            )

            # Verify logfire.error was called with error_category
            mock_logfire.error.assert_called_once()
            call_args = mock_logfire.error.call_args
            assert "error_category" in call_args.kwargs
            assert call_args.kwargs["error_category"] == ErrorCategory.SERVICE_QUOTA_EXCEEDED.value

    @pytest.mark.asyncio
    async def test_different_error_types_log_different_categories(self, mock_deps, mock_member_list):
        """Test that different error types log with their respective categories."""
        test_cases = [
            (Exception("rate limit exceeded"), ErrorCategory.RATE_LIMIT_EXCEEDED.value),
            (Exception("authentication failed"), ErrorCategory.AUTHENTICATION_FAILED.value),
            (ConnectionError("network error"), ErrorCategory.NETWORK_ERROR.value),
            (ValueError("random error"), ErrorCategory.UNKNOWN.value),
        ]

        for exception, expected_category in test_cases:
            with (
                patch("src.agents.choresir_agent.get_agent") as mock_get_agent,
                patch("src.agents.choresir_agent.get_retry_handler") as mock_get_retry_handler,
                patch("src.agents.choresir_agent.logfire") as mock_logfire,
            ):
                mock_agent, mock_retry_handler = self._mock_agent_with_error(exception)
                mock_get_agent.return_value = mock_agent
                mock_get_retry_handler.return_value = mock_retry_handler

                # Run agent
                await run_agent(
                    user_message="Test",
                    deps=mock_deps,
                    member_list=mock_member_list,
                )

                # Verify correct category was logged
                call_args = mock_logfire.error.call_args
                assert call_args.kwargs["error_category"] == expected_category

    @pytest.mark.asyncio
    async def test_whatsapp_friendly_message_format(self, mock_deps, mock_member_list):
        """Test that all error messages are WhatsApp-friendly (concise)."""
        # Test various error types
        error_exceptions = [
            Exception("quota exceeded"),
            Exception("rate limit exceeded"),
            Exception("authentication failed"),
            ConnectionError("network error"),
            ValueError("unknown error"),
        ]

        for exception in error_exceptions:
            with (
                patch("src.agents.choresir_agent.get_agent") as mock_get_agent,
                patch("src.agents.choresir_agent.get_retry_handler") as mock_get_retry_handler,
            ):
                mock_agent, mock_retry_handler = self._mock_agent_with_error(exception)
                mock_get_agent.return_value = mock_agent
                mock_get_retry_handler.return_value = mock_retry_handler

                result = await run_agent(
                    user_message="Test",
                    deps=mock_deps,
                    member_list=mock_member_list,
                )

                # Verify message is concise (max 2-3 sentences)
                sentence_count = len([s for s in result.split(".") if s.strip()])
                assert sentence_count <= 3, f"Message has {sentence_count} sentences: {result}"

                # Verify message is not too long (reasonable for WhatsApp)
                assert len(result) < 200, f"Message too long ({len(result)} chars): {result}"


@pytest.mark.unit
class TestHandleUnknownUserInviteConfirmation:
    """Tests for handle_unknown_user with invite confirmation flow."""

    @pytest.fixture
    def mock_pending_invite(self):
        """Create mock pending invite record."""
        return {
            "id": "invite_id_123",
            "phone": "+1234567890",
            "invited_at": "2024-01-01T00:00:00Z",
            "invite_message_id": "msg_id_123",
        }

    @pytest.fixture
    def mock_pending_user(self):
        """Create mock pending user record."""
        return {
            "id": "user_id_123",
            "phone": "+1234567890",
            "name": "Pending User",
            "status": "pending",
            "role": "member",
        }

    @pytest.mark.asyncio
    async def test_yes_confirms_invite_and_welcomes_user(self, mock_pending_invite, mock_pending_user):
        """Test that YES confirms invite, updates user status, deletes invite, and welcomes user."""
        with (
            patch("src.agents.choresir_agent.db_client.get_first_record") as mock_get_first,
            patch("src.agents.choresir_agent.db_client.update_record") as mock_update,
            patch("src.agents.choresir_agent.db_client.delete_record") as mock_delete,
            patch("src.agents.choresir_agent.user_service.get_user_by_phone") as mock_get_user,
            patch("src.agents.choresir_agent.get_house_config") as mock_get_house_config,
        ):
            # Mock pending invite and user lookup
            mock_get_first.return_value = mock_pending_invite
            mock_get_user.return_value = mock_pending_user

            # Mock house config
            mock_get_house_config.return_value = {"name": "Test House", "password": "pass", "code": "CODE"}

            # Handle message
            result = await handle_unknown_user(user_phone="+1234567890", message_text="YES")

            # Verify user status was updated to active
            mock_update.assert_called_once_with(
                collection="users",
                record_id="user_id_123",
                data={"status": "active"},
            )

            # Verify pending invite was deleted
            mock_delete.assert_called_once_with(
                collection="pending_invites",
                record_id="invite_id_123",
            )

            # Verify welcome message includes house name
            assert "Welcome to Test House" in result
            assert "membership is now active" in result

    @pytest.mark.asyncio
    async def test_yes_case_insensitive_confirms_invite(self, mock_pending_invite, mock_pending_user):
        """Test that 'yes', 'Yes', and 'YES' all confirm the invite."""
        test_messages = ["yes", "Yes", "YES", "YeS", " yEs "]

        for message in test_messages:
            with (
                patch("src.agents.choresir_agent.db_client.get_first_record") as mock_get_first,
                patch("src.agents.choresir_agent.db_client.update_record") as mock_update,
                patch("src.agents.choresir_agent.db_client.delete_record") as mock_delete,
                patch("src.agents.choresir_agent.user_service.get_user_by_phone") as mock_get_user,
                patch("src.agents.choresir_agent.get_house_config") as mock_get_house_config,
            ):
                # Mock pending invite and user lookup
                mock_get_first.return_value = mock_pending_invite
                mock_get_user.return_value = mock_pending_user
                mock_get_house_config.return_value = {"name": "Test House", "password": "pass", "code": "CODE"}

                # Handle message
                result = await handle_unknown_user(user_phone="+1234567890", message_text=message)

                # Verify invite was confirmed
                mock_update.assert_called_once()
                mock_delete.assert_called_once()
                assert "Welcome to Test House" in result

    @pytest.mark.asyncio
    async def test_non_yes_message_returns_instruction(self, mock_pending_invite):
        """Test that non-YES messages instruct user to reply YES."""
        test_messages = ["hello", "maybe", "no", "what?", ""]

        for message in test_messages:
            with (
                patch("src.agents.choresir_agent.db_client.get_first_record") as mock_get_first,
                patch("src.agents.choresir_agent.db_client.update_record") as mock_update,
                patch("src.agents.choresir_agent.db_client.delete_record") as mock_delete,
            ):
                # Mock pending invite exists but no user update/deletion
                mock_get_first.return_value = mock_pending_invite

                # Handle message
                result = await handle_unknown_user(user_phone="+1234567890", message_text=message)

                # Verify no user update or delete
                mock_update.assert_not_called()
                mock_delete.assert_not_called()

                # Verify instruction message
                assert result == "To confirm your invitation, please reply YES"

    @pytest.mark.asyncio
    async def test_no_pending_invite_returns_not_member_message(self):
        """Test that users without pending invite get 'not a member' message."""
        with (
            patch("src.agents.choresir_agent.db_client.get_first_record") as mock_get_first,
            patch("src.agents.choresir_agent.session_service.get_session") as mock_get_session,
        ):
            # Mock no pending invite and no join session
            mock_get_first.return_value = None
            mock_get_session.return_value = None

            # Handle message
            result = await handle_unknown_user(user_phone="+1234567890", message_text="hello")

            # Verify 'not a member' message
            assert "not a member of this household" in result
            assert "contact an admin to request an invite" in result

    @pytest.mark.asyncio
    async def test_pending_invite_but_no_user_record_returns_error(self, mock_pending_invite):
        """Test that missing user record after pending invite returns error message."""
        with (
            patch("src.agents.choresir_agent.db_client.get_first_record") as mock_get_first,
            patch("src.agents.choresir_agent.db_client.update_record") as mock_update,
            patch("src.agents.choresir_agent.db_client.delete_record") as mock_delete,
            patch("src.agents.choresir_agent.user_service.get_user_by_phone") as mock_get_user,
        ):
            # Mock pending invite exists but user not found
            mock_get_first.return_value = mock_pending_invite
            mock_get_user.return_value = None

            # Handle message
            result = await handle_unknown_user(user_phone="+1234567890", message_text="YES")

            # Verify error message
            assert "error processing your invite" in result
            assert "contact an admin" in result

            # Verify no update or delete was attempted
            mock_update.assert_not_called()
            mock_delete.assert_not_called()
