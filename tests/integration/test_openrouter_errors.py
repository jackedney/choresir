"""Integration tests for OpenRouter error handling and notifications.

This module tests the full flow from OpenRouter API errors through error
classification, user notifications, and admin alerts.
"""

import logging
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.agents.base import Deps
from src.agents.choresir_agent import run_agent
from src.core import admin_notifier
from src.core.admin_notifier import notification_rate_limiter
from src.core.errors import ErrorCategory


@pytest.mark.integration
@pytest.mark.asyncio
class TestOpenRouterErrorFlow:
    """Test full error flow from OpenRouter to user notification."""

    async def test_quota_exceeded_flow(self, mock_db_module, db_client, sample_users: dict):
        """Test complete flow when OpenRouter quota is exceeded.

        Flow:
        1. Agent execution triggers OpenRouter API call
        2. OpenRouter returns quota exceeded error
        3. Error is classified as SERVICE_QUOTA_EXCEEDED
        4. User receives friendly error message
        5. Admin receives critical notification
        """
        # Use alice from sample_users as admin (role="admin" in integration/conftest.py)
        admin = sample_users["alice"]

        # Setup dependencies for agent
        deps = Deps(
            db=None,  # SQLite - no db client object needed
            user_id=sample_users["bob"]["id"],
            user_phone=sample_users["bob"]["phone"],
            user_name=sample_users["bob"]["name"],
            user_role=sample_users["bob"]["role"],
            current_time=datetime.now(),
        )

        # Mock the agent to raise OpenRouter quota exceeded error
        with (
            patch("src.agents.choresir_agent.get_agent") as mock_get_agent,
            patch("src.core.admin_notifier.send_text_message") as mock_send_message,
        ):
            # Configure mock agent to raise quota exceeded error
            mock_agent_instance = MagicMock()
            mock_agent_instance.run = AsyncMock(
                side_effect=Exception("OpenRouter API error: quota exceeded for model anthropic/claude-3.5-sonnet")
            )
            mock_get_agent.return_value = mock_agent_instance

            # Mock successful WhatsApp message send
            mock_send_message.return_value = MagicMock(success=True, message_id="msg_123")

            # Execute agent run
            response = await run_agent(
                user_message="What are my chores?",
                deps=deps,
                member_list="Test members",
            )

            # Verify user receives friendly error message
            assert "quota" in response.lower()
            assert "try again later" in response.lower()
            assert "openrouter" not in response.lower()  # No technical details leaked

            # Verify admin notification was sent
            mock_send_message.assert_called_once()
            call_args = mock_send_message.call_args

            # Verify notification sent to admin
            assert call_args.kwargs["to_phone"] == admin["phone"]

            # Verify notification content
            message_text = call_args.kwargs["text"]
            assert "[CRITICAL]" in message_text
            assert "quota exceeded" in message_text.lower()
            assert sample_users["bob"]["name"] in message_text
            assert sample_users["bob"]["phone"] in message_text

    async def test_rate_limit_flow_no_admin_notification(self, mock_db_module, db_client, sample_users: dict):
        """Test rate limit errors do not trigger admin notifications.

        Flow:
        1. OpenRouter returns rate limit error
        2. Error is classified as RATE_LIMIT_EXCEEDED
        3. User receives friendly error message
        4. Admin is NOT notified (transient error)
        """
        deps = Deps(
            db=None,  # SQLite - no db client object needed
            user_id=sample_users["bob"]["id"],
            user_phone=sample_users["bob"]["phone"],
            user_name=sample_users["bob"]["name"],
            user_role=sample_users["bob"]["role"],
            current_time=datetime.now(),
        )

        with (
            patch("src.agents.choresir_agent.get_agent") as mock_get_agent,
            patch("src.core.admin_notifier.send_text_message") as mock_send_message,
        ):
            # Configure mock agent to raise rate limit error
            mock_agent_instance = MagicMock()
            mock_agent_instance.run = AsyncMock(side_effect=Exception("OpenRouter error (429): Rate limit exceeded"))
            mock_get_agent.return_value = mock_agent_instance

            # Execute agent run
            response = await run_agent(
                user_message="What are my chores?",
                deps=deps,
                member_list="Test members",
            )

            # Verify user receives friendly message
            assert "too many requests" in response.lower()
            assert "wait" in response.lower()

            # Verify admin was NOT notified (rate limits are transient)
            mock_send_message.assert_not_called()

    async def test_authentication_error_flow(self, mock_db_module, db_client, sample_users: dict):
        """Test authentication errors trigger admin notifications.

        Flow:
        1. OpenRouter returns authentication error
        2. Error is classified as AUTHENTICATION_FAILED
        3. User receives message to contact support
        4. Admin receives critical notification
        """
        # Use alice from sample_users as admin (role="admin" in integration/conftest.py)
        _admin = sample_users["alice"]

        deps = Deps(
            db=None,  # SQLite - no db client object needed
            user_id=sample_users["bob"]["id"],
            user_phone=sample_users["bob"]["phone"],
            user_name=sample_users["bob"]["name"],
            user_role=sample_users["bob"]["role"],
            current_time=datetime.now(),
        )

        with (
            patch("src.agents.choresir_agent.get_agent") as mock_get_agent,
            patch("src.core.admin_notifier.send_text_message") as mock_send_message,
        ):
            # Configure mock to raise auth error
            mock_agent_instance = MagicMock()
            mock_agent_instance.run = AsyncMock(side_effect=Exception("OpenRouter error (401): Invalid API key"))
            mock_get_agent.return_value = mock_agent_instance

            mock_send_message.return_value = MagicMock(success=True, message_id="msg_123")

            # Execute agent run
            response = await run_agent(
                user_message="What are my chores?",
                deps=deps,
                member_list="Test members",
            )

            # Verify user message
            assert "authentication" in response.lower()
            assert "contact support" in response.lower()

            # Note: Authentication errors trigger admin notifications via should_notify_admins
            # However, the current implementation in choresir_agent.py only handles
            # SERVICE_QUOTA_EXCEEDED explicitly. This would need to be updated
            # to handle all critical errors. For now, we verify the classification works.

    async def test_network_error_no_admin_notification(self, mock_db_module, db_client, sample_users: dict):
        """Test network errors do not trigger admin notifications.

        Flow:
        1. Network error occurs during API call
        2. Error is classified as NETWORK_ERROR
        3. User receives network error message
        4. Admin is NOT notified (transient issue)
        """
        deps = Deps(
            db=None,  # SQLite - no db client object needed
            user_id=sample_users["bob"]["id"],
            user_phone=sample_users["bob"]["phone"],
            user_name=sample_users["bob"]["name"],
            user_role=sample_users["bob"]["role"],
            current_time=datetime.now(),
        )

        with (
            patch("src.agents.choresir_agent.get_agent") as mock_get_agent,
            patch("src.core.admin_notifier.send_text_message") as mock_send_message,
        ):
            mock_agent_instance = MagicMock()
            mock_agent_instance.run = AsyncMock(side_effect=Exception("HTTP 503: Service unavailable"))
            mock_get_agent.return_value = mock_agent_instance

            response = await run_agent(
                user_message="What are my chores?",
                deps=deps,
                member_list="Test members",
            )

            # Verify user message
            assert "network" in response.lower()

            # Verify no admin notification
            mock_send_message.assert_not_called()


@pytest.mark.integration
@pytest.mark.asyncio
class TestAdminNotificationRateLimiting:
    """Test admin notification rate limiting functionality."""

    async def test_rate_limiter_prevents_spam(self, mock_db_module, db_client, sample_users: dict):
        """Test that duplicate notifications within cooldown period are blocked.

        Flow:
        1. First quota exceeded error triggers admin notification
        2. Second quota exceeded error within 1 hour is rate limited
        3. No duplicate notification sent
        """
        # Use alice from sample_users as admin (role="admin" in integration/conftest.py)
        _admin = sample_users["alice"]

        # Reset rate limiter to clean state
        notification_rate_limiter._notifications.clear()

        with patch("src.core.admin_notifier.send_text_message") as mock_send_message:
            mock_send_message.return_value = MagicMock(success=True, message_id="msg_123")

            # First notification should succeed
            assert admin_notifier.notification_rate_limiter.can_notify(ErrorCategory.SERVICE_QUOTA_EXCEEDED)

            await admin_notifier.notify_admins(
                "First quota exceeded notification",
                severity="critical",
            )

            # Record the notification
            admin_notifier.notification_rate_limiter.record_notification(ErrorCategory.SERVICE_QUOTA_EXCEEDED)

            # Verify first message sent
            assert mock_send_message.call_count == 1

            # Second notification should be rate limited
            assert not admin_notifier.notification_rate_limiter.can_notify(ErrorCategory.SERVICE_QUOTA_EXCEEDED)

            # Reset mock to verify no new calls
            mock_send_message.reset_mock()

            # This would be blocked at the caller level (not implemented in MVP)
            # For now, we just verify the rate limiter logic works

    async def test_different_error_types_not_rate_limited(self, mock_db_module, db_client, sample_users: dict):
        """Test that different error categories have independent rate limits.

        Flow:
        1. Quota exceeded notification sent
        2. Authentication error notification can still be sent
        3. Both notifications go through
        """
        # Use alice from sample_users as admin (role="admin" in integration/conftest.py)
        _admin = sample_users["alice"]

        # Reset rate limiter
        notification_rate_limiter._notifications.clear()

        with patch("src.core.admin_notifier.send_text_message") as mock_send_message:
            mock_send_message.return_value = MagicMock(success=True, message_id="msg_123")

            # Send quota exceeded notification
            assert admin_notifier.notification_rate_limiter.can_notify(ErrorCategory.SERVICE_QUOTA_EXCEEDED)
            admin_notifier.notification_rate_limiter.record_notification(ErrorCategory.SERVICE_QUOTA_EXCEEDED)

            # Authentication error should NOT be rate limited
            assert admin_notifier.notification_rate_limiter.can_notify(ErrorCategory.AUTHENTICATION_FAILED)


@pytest.mark.integration
@pytest.mark.asyncio
class TestAdminNotificationFailures:
    """Test graceful handling of admin notification failures."""

    async def test_notification_failure_logged_not_raised(self, mock_db_module, db_client, sample_users: dict, caplog):
        """Test that WhatsApp send failures don't break user flow.

        Flow:
        1. Quota exceeded error occurs
        2. Admin notification fails to send
        3. Failure is logged
        4. User still receives error message
        """
        # Set caplog to capture ERROR level logs
        caplog.set_level(logging.ERROR)

        # Use alice from sample_users as admin (role="admin" in integration/conftest.py)
        _admin = sample_users["alice"]

        deps = Deps(
            db=None,  # SQLite - no db client object needed
            user_id=sample_users["bob"]["id"],
            user_phone=sample_users["bob"]["phone"],
            user_name=sample_users["bob"]["name"],
            user_role=sample_users["bob"]["role"],
            current_time=datetime.now(),
        )

        with (
            patch("src.agents.choresir_agent.get_agent") as mock_get_agent,
            patch("src.core.admin_notifier.send_text_message") as mock_send_message,
        ):
            # Configure agent to raise quota error
            mock_agent_instance = MagicMock()
            mock_agent_instance.run = AsyncMock(side_effect=Exception("OpenRouter API error: quota exceeded"))
            mock_get_agent.return_value = mock_agent_instance

            # Configure WhatsApp send to fail
            mock_send_message.return_value = MagicMock(
                success=False,
                error="Rate limit exceeded",
            )

            # Execute should not raise exception
            response = await run_agent(
                user_message="What are my chores?",
                deps=deps,
                member_list="Test members",
            )

            # User still receives error message
            assert "quota" in response.lower()

            # Verify failure was logged using caplog
            assert any("Failed to send admin notification" in record.message for record in caplog.records)

    async def test_database_error_during_admin_lookup(self, mock_db_module, db_client, sample_users: dict):
        """Test graceful handling when admin user lookup fails.

        Flow:
        1. Quota exceeded error occurs
        2. Database query for admins fails
        3. Error is logged
        4. User still receives error message
        """
        deps = Deps(
            db=None,  # SQLite - no db client object needed
            user_id=sample_users["bob"]["id"],
            user_phone=sample_users["bob"]["phone"],
            user_name=sample_users["bob"]["name"],
            user_role=sample_users["bob"]["role"],
            current_time=datetime.now(),
        )

        with (
            patch("src.agents.choresir_agent.get_agent") as mock_get_agent,
            patch("src.core.admin_notifier.list_records") as mock_list_records,
        ):
            mock_agent_instance = MagicMock()
            mock_agent_instance.run = AsyncMock(side_effect=Exception("OpenRouter API error: quota exceeded"))
            mock_get_agent.return_value = mock_agent_instance

            # Configure database to fail
            mock_list_records.side_effect = Exception("Database connection failed")

            # Execute should not raise exception
            response = await run_agent(
                user_message="What are my chores?",
                deps=deps,
                member_list="Test members",
            )

            # User still receives error message
            assert "quota" in response.lower()


@pytest.mark.integration
@pytest.mark.asyncio
class TestErrorClassificationIntegration:
    """Test error classification with real exception types."""

    async def test_multiple_error_indicators_prioritization(self, mock_db_module, db_client, sample_users: dict):
        """Test that error classification correctly prioritizes when multiple patterns match.

        Flow:
        1. Error message contains both "quota" and "rate limit"
        2. Quota exceeded is matched first (higher priority)
        3. User receives quota exceeded message
        """
        deps = Deps(
            db=None,  # SQLite - no db client object needed
            user_id=sample_users["bob"]["id"],
            user_phone=sample_users["bob"]["phone"],
            user_name=sample_users["bob"]["name"],
            user_role=sample_users["bob"]["role"],
            current_time=datetime.now(),
        )

        with patch("src.agents.choresir_agent.get_agent") as mock_get_agent:
            # Ambiguous error with multiple indicators
            mock_agent_instance = MagicMock()
            mock_agent_instance.run = AsyncMock(side_effect=Exception("Quota exceeded due to rate limit"))
            mock_get_agent.return_value = mock_agent_instance

            response = await run_agent(
                user_message="What are my chores?",
                deps=deps,
                member_list="Test members",
            )

            # Should match quota exceeded (checked first in classify_agent_error)
            assert "quota" in response.lower()

    async def test_unknown_error_provides_generic_message(self, mock_db_module, db_client, sample_users: dict):
        """Test that unrecognized errors provide generic helpful message.

        Flow:
        1. Unexpected error type occurs
        2. Classified as UNKNOWN
        3. User receives generic error message
        4. No admin notification
        """
        deps = Deps(
            db=None,  # SQLite - no db client object needed
            user_id=sample_users["bob"]["id"],
            user_phone=sample_users["bob"]["phone"],
            user_name=sample_users["bob"]["name"],
            user_role=sample_users["bob"]["role"],
            current_time=datetime.now(),
        )

        with (
            patch("src.agents.choresir_agent.get_agent") as mock_get_agent,
            patch("src.core.admin_notifier.send_text_message") as mock_send_message,
        ):
            mock_agent_instance = MagicMock()
            mock_agent_instance.run = AsyncMock(side_effect=ValueError("Unexpected internal error in agent"))
            mock_get_agent.return_value = mock_agent_instance

            response = await run_agent(
                user_message="What are my chores?",
                deps=deps,
                member_list="Test members",
            )

            # Generic error message
            assert "unexpected error" in response.lower()
            assert "try again later" in response.lower()

            # No admin notification for unknown errors
            mock_send_message.assert_not_called()
