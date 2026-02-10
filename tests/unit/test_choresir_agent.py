"""Unit tests for choresir_agent error handling."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.base import Deps
from src.agents.choresir_agent import _build_workflow_context, run_agent
from src.core.errors import ErrorCategory


@pytest.fixture(autouse=True)
def mock_admin_notifier():
    """Mock admin notifier to avoid WhatsApp API calls with retry delays."""
    with patch("src.agents.choresir_agent.admin_notifier") as mock_notifier:
        mock_notifier.should_notify_admins.return_value = False
        mock_notifier.notify_admins = AsyncMock()
        yield mock_notifier


@pytest.fixture(autouse=True)
def mock_workflow_service():
    """Mock workflow service to avoid database queries in error handling tests."""
    with (
        patch("src.agents.choresir_agent.workflow_service.get_user_pending_workflows") as mock_user_wfs,
        patch("src.agents.choresir_agent.workflow_service.get_actionable_workflows") as mock_actionable_wfs,
    ):
        mock_user_wfs.return_value = []
        mock_actionable_wfs.return_value = []
        yield mock_user_wfs, mock_actionable_wfs


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

    @pytest.mark.asyncio
    async def test_group_id_fetches_group_context(self, mock_deps, mock_member_list):
        """Test that group_id parameter triggers group context fetching."""
        group_id = "group_123"

        mock_group_context = [
            {"sender_name": "Alice", "content": "I'll do the dishes"},
            {"sender_name": "Bob", "content": "I'll take out trash"},
        ]

        with (
            patch("src.agents.choresir_agent.get_agent") as mock_get_agent,
            patch("src.agents.choresir_agent.get_retry_handler") as mock_get_retry_handler,
            patch("src.agents.choresir_agent.get_group_context") as mock_get_group_context,
        ):
            # Mock group context fetching
            mock_get_group_context.return_value = mock_group_context

            # Mock agent execution
            mock_agent = AsyncMock()
            mock_agent.run.return_value = MagicMock(output="Response")
            mock_get_agent.return_value = mock_agent
            mock_retry_handler = AsyncMock()
            mock_retry_handler.execute_with_retry.return_value = "Response"
            mock_get_retry_handler.return_value = mock_retry_handler

            # Run agent with group_id
            await run_agent(
                user_message="What's happening?",
                deps=mock_deps,
                member_list=mock_member_list,
                group_id=group_id,
            )

            # Verify group context was fetched
            mock_get_group_context.assert_called_once_with(group_id=group_id)

    @pytest.mark.asyncio
    async def test_none_group_id_uses_per_user_context(self, mock_deps, mock_member_list):
        """Test that None group_id uses per-user conversation context."""
        with (
            patch("src.agents.choresir_agent.get_agent") as mock_get_agent,
            patch("src.agents.choresir_agent.get_retry_handler") as mock_get_retry_handler,
            patch("src.agents.choresir_agent.get_recent_context") as mock_get_recent_context,
            patch("src.agents.choresir_agent.format_context_for_prompt") as mock_format_context,
            patch("src.agents.choresir_agent.get_group_context") as mock_get_group_context,
        ):
            # Mock per-user context fetching
            mock_get_recent_context.return_value = []
            mock_format_context.return_value = "## RECENT CONVERSATION\n..."

            # Mock agent execution
            mock_agent = AsyncMock()
            mock_agent.run.return_value = MagicMock(output="Response")
            mock_get_agent.return_value = mock_agent
            mock_retry_handler = AsyncMock()
            mock_retry_handler.execute_with_retry.return_value = "Response"
            mock_get_retry_handler.return_value = mock_retry_handler

            # Run agent without group_id
            await run_agent(
                user_message="What's happening?",
                deps=mock_deps,
                member_list=mock_member_list,
                group_id=None,
            )

            # Verify per-user context was fetched
            mock_get_recent_context.assert_called_once_with(user_phone=mock_deps.user_phone)
            # Verify group context was NOT fetched
            mock_get_group_context.assert_not_called()

    @pytest.mark.asyncio
    async def test_group_context_formatted_with_sender_names(self, mock_deps, mock_member_list):
        """Test that group context is formatted with sender names in [Name]: message format."""
        group_id = "group_123"

        mock_group_context = [
            {"sender_name": "Alice", "content": "I'll do dishes"},
            {"sender_name": "Bob", "content": "I'll do laundry"},
            {"sender_name": "Charlie", "content": "I'll cook"},
        ]

        with (
            patch("src.agents.choresir_agent.get_agent") as mock_get_agent,
            patch("src.agents.choresir_agent.get_retry_handler") as mock_get_retry_handler,
            patch("src.agents.choresir_agent.get_group_context") as mock_get_group_context,
        ):
            mock_get_group_context.return_value = mock_group_context

            # Mock agent to capture instructions
            mock_agent = AsyncMock()
            mock_result = MagicMock()
            mock_result.output = "Agent response"
            mock_agent.run.return_value = mock_result
            mock_get_agent.return_value = mock_agent

            # Mock retry handler to actually call the function
            async def mock_execute(func):
                return await func()

            mock_retry_handler = AsyncMock()
            mock_retry_handler.execute_with_retry.side_effect = mock_execute
            mock_get_retry_handler.return_value = mock_retry_handler

            # Run agent with group_id
            await run_agent(
                user_message="What's happening?",
                deps=mock_deps,
                member_list=mock_member_list,
                group_id=group_id,
            )

            # Verify agent.run was called and get the instructions
            mock_agent.run.assert_called_once()
            call_kwargs = mock_agent.run.call_args.kwargs
            instructions = call_kwargs.get("instructions", "")

            # Verify instructions include formatted group context with sender names
            assert "## RECENT GROUP CONVERSATION" in instructions
            assert "[Alice]: I'll do dishes" in instructions
            assert "[Bob]: I'll do laundry" in instructions
            assert "[Charlie]: I'll cook" in instructions


@pytest.mark.unit
class TestBuildWorkflowContext:
    """Tests for _build_workflow_context function."""

    @pytest.mark.asyncio
    async def test_empty_context_when_no_pending_workflows(self):
        """Test that empty string is returned when there are no pending workflows."""
        with (
            patch("src.services.workflow_service.get_user_pending_workflows") as mock_user_wfs,
            patch("src.services.workflow_service.get_actionable_workflows") as mock_actionable_wfs,
        ):
            mock_user_wfs.return_value = []
            mock_actionable_wfs.return_value = []

            result = await _build_workflow_context(user_id="user_123")

            assert result == ""

    @pytest.mark.asyncio
    async def test_user_pending_requests_section(self):
        """Test that user's pending requests are shown correctly."""
        user_workflows = [
            {
                "id": "wf1",
                "type": "deletion_approval",
                "target_title": "Clean kitchen",
                "requester_name": "Alice",
            },
            {
                "id": "wf2",
                "type": "task_verification",
                "target_title": "Take out trash",
                "requester_name": "Alice",
            },
        ]

        with (
            patch("src.services.workflow_service.get_user_pending_workflows") as mock_user_wfs,
            patch("src.services.workflow_service.get_actionable_workflows") as mock_actionable_wfs,
        ):
            mock_user_wfs.return_value = user_workflows
            mock_actionable_wfs.return_value = []

            result = await _build_workflow_context(user_id="user_123")

        assert "## YOUR PENDING REQUESTS" in result
        assert "Deletion Approval: Clean kitchen" in result
        assert "Task Verification: Take out trash" in result

    @pytest.mark.asyncio
    async def test_actionable_workflows_section_with_numbering(self):
        """Test that actionable workflows are shown with numbering."""
        actionable_workflows = [
            {
                "id": "wf3",
                "type": "deletion_approval",
                "target_title": "Do dishes",
                "requester_name": "Bob",
            },
            {
                "id": "wf4",
                "type": "task_verification",
                "target_title": "Gym workout",
                "requester_name": "Charlie",
            },
        ]

        with (
            patch("src.services.workflow_service.get_user_pending_workflows") as mock_user_wfs,
            patch("src.services.workflow_service.get_actionable_workflows") as mock_actionable_wfs,
        ):
            mock_user_wfs.return_value = []
            mock_actionable_wfs.return_value = actionable_workflows

            result = await _build_workflow_context(user_id="user_123")

        assert "## REQUESTS YOU CAN ACTION" in result
        assert "1. Deletion Approval: Do dishes (from Bob)" in result
        assert "2. Task Verification: Gym workout (from Charlie)" in result

    @pytest.mark.asyncio
    async def test_both_sections_shown(self):
        """Test that both sections are shown when user has both pending and actionable workflows."""
        user_workflows = [
            {
                "id": "wf1",
                "type": "deletion_approval",
                "target_title": "My chore",
                "requester_name": "Alice",
            }
        ]

        actionable_workflows = [
            {
                "id": "wf2",
                "type": "task_verification",
                "target_title": "Other chore",
                "requester_name": "Bob",
            }
        ]

        with (
            patch("src.services.workflow_service.get_user_pending_workflows") as mock_user_wfs,
            patch("src.services.workflow_service.get_actionable_workflows") as mock_actionable_wfs,
        ):
            mock_user_wfs.return_value = user_workflows
            mock_actionable_wfs.return_value = actionable_workflows

            result = await _build_workflow_context(user_id="user_123")

        assert "## YOUR PENDING REQUESTS" in result
        assert "## REQUESTS YOU CAN ACTION" in result
        assert "Deletion Approval: My chore" in result
        assert "1. Task Verification: Other chore (from Bob)" in result

    @pytest.mark.asyncio
    async def test_hint_message_for_batch_operations(self):
        """Test that hint message is shown when there are actionable workflows."""
        actionable_workflows = [
            {
                "id": "wf1",
                "type": "deletion_approval",
                "target_title": "Some chore",
                "requester_name": "Bob",
            }
        ]

        with (
            patch("src.services.workflow_service.get_user_pending_workflows") as mock_user_wfs,
            patch("src.services.workflow_service.get_actionable_workflows") as mock_actionable_wfs,
        ):
            mock_user_wfs.return_value = []
            mock_actionable_wfs.return_value = actionable_workflows

            result = await _build_workflow_context(user_id="user_123")

            assert "User can say: approve 1, reject both, approve all" in result

    @pytest.mark.asyncio
    async def test_no_hint_when_only_user_pending_workflows(self):
        """Test that hint is not shown when there are no actionable workflows."""
        user_workflows = [
            {
                "id": "wf1",
                "type": "deletion_approval",
                "target_title": "My chore",
                "requester_name": "Alice",
            }
        ]

        with (
            patch("src.services.workflow_service.get_user_pending_workflows") as mock_user_wfs,
            patch("src.services.workflow_service.get_actionable_workflows") as mock_actionable_wfs,
        ):
            mock_user_wfs.return_value = user_workflows
            mock_actionable_wfs.return_value = []

            result = await _build_workflow_context(user_id="user_123")

            assert "User can say:" not in result
            assert "## YOUR PENDING REQUESTS" in result
            assert "Deletion Approval: My chore" in result
