"""Unit tests for choresir_agent error handling."""

from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.base import Deps
from src.agents.choresir_agent import run_agent
from src.core.errors import ErrorCategory


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

    @pytest.mark.asyncio
    async def test_quota_exceeded_error_returns_user_friendly_message(self, mock_deps, mock_member_list):
        """Test that quota exceeded errors return appropriate user message."""
        with patch("src.agents.choresir_agent.get_agent") as mock_get_agent:
            # Mock agent to raise quota exceeded error
            mock_agent = AsyncMock()
            mock_agent.run.side_effect = Exception("OpenRouter API error: quota exceeded")
            mock_get_agent.return_value = mock_agent

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
        with patch("src.agents.choresir_agent.get_agent") as mock_get_agent:
            # Mock agent to raise rate limit error
            mock_agent = AsyncMock()
            mock_agent.run.side_effect = Exception("Rate limit exceeded. Try again in 60s")
            mock_get_agent.return_value = mock_agent

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
        with patch("src.agents.choresir_agent.get_agent") as mock_get_agent:
            # Mock agent to raise authentication error
            mock_agent = AsyncMock()
            mock_agent.run.side_effect = Exception("Invalid API key provided")
            mock_get_agent.return_value = mock_agent

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
        with patch("src.agents.choresir_agent.get_agent") as mock_get_agent:
            # Mock agent to raise network error
            mock_agent = AsyncMock()
            mock_agent.run.side_effect = ConnectionError("Connection failed")
            mock_get_agent.return_value = mock_agent

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
        with patch("src.agents.choresir_agent.get_agent") as mock_get_agent:
            # Mock agent to raise unknown error
            mock_agent = AsyncMock()
            mock_agent.run.side_effect = ValueError("Something went wrong")
            mock_get_agent.return_value = mock_agent

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
        with (
            patch("src.agents.choresir_agent.get_agent") as mock_get_agent,
            patch("src.agents.choresir_agent.logfire") as mock_logfire,
        ):
            # Mock agent to raise quota exceeded error
            mock_agent = AsyncMock()
            mock_agent.run.side_effect = Exception("quota exceeded")
            mock_get_agent.return_value = mock_agent

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
                patch("src.agents.choresir_agent.logfire") as mock_logfire,
            ):
                # Mock agent to raise the exception
                mock_agent = AsyncMock()
                mock_agent.run.side_effect = exception
                mock_get_agent.return_value = mock_agent

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
            with patch("src.agents.choresir_agent.get_agent") as mock_get_agent:
                mock_agent = AsyncMock()
                mock_agent.run.side_effect = exception
                mock_get_agent.return_value = mock_agent

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
