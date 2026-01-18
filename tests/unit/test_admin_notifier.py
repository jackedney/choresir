"""Unit tests for admin notification system."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from src.core.admin_notifier import (
    NotificationRateLimiter,
    notify_admins,
    should_notify_admins,
)
from src.core.errors import ErrorCategory


@pytest.mark.unit
class TestShouldNotifyAdmins:
    """Tests for should_notify_admins function."""

    def test_returns_true_for_quota_exceeded(self):
        """Test that quota exceeded errors trigger admin notifications."""
        assert should_notify_admins(ErrorCategory.SERVICE_QUOTA_EXCEEDED) is True

    def test_returns_true_for_authentication_failed(self):
        """Test that authentication failures trigger admin notifications."""
        assert should_notify_admins(ErrorCategory.AUTHENTICATION_FAILED) is True

    def test_returns_false_for_rate_limit(self):
        """Test that rate limit errors do not trigger admin notifications."""
        assert should_notify_admins(ErrorCategory.RATE_LIMIT_EXCEEDED) is False

    def test_returns_false_for_network_error(self):
        """Test that network errors do not trigger admin notifications."""
        assert should_notify_admins(ErrorCategory.NETWORK_ERROR) is False

    def test_returns_false_for_unknown_error(self):
        """Test that unknown errors do not trigger admin notifications."""
        assert should_notify_admins(ErrorCategory.UNKNOWN) is False


@pytest.mark.unit
class TestNotificationRateLimiter:
    """Tests for NotificationRateLimiter class."""

    def test_allows_first_notification(self):
        """Test that first notification for an error category is allowed."""
        limiter = NotificationRateLimiter()
        assert limiter.can_notify(ErrorCategory.SERVICE_QUOTA_EXCEEDED) is True

    def test_blocks_duplicate_notification_within_hour(self):
        """Test that duplicate notifications within one hour are blocked."""
        limiter = NotificationRateLimiter()

        # First notification allowed
        assert limiter.can_notify(ErrorCategory.SERVICE_QUOTA_EXCEEDED) is True
        limiter.record_notification(ErrorCategory.SERVICE_QUOTA_EXCEEDED)

        # Second notification within hour blocked
        assert limiter.can_notify(ErrorCategory.SERVICE_QUOTA_EXCEEDED) is False

    def test_allows_notification_after_hour_passes(self):
        """Test that notifications are allowed after one hour passes."""
        limiter = NotificationRateLimiter()

        # Record notification with timestamp 2 hours ago
        past_time = datetime.now() - timedelta(hours=2)
        limiter._notifications[ErrorCategory.SERVICE_QUOTA_EXCEEDED.value] = past_time

        # Should allow notification now
        assert limiter.can_notify(ErrorCategory.SERVICE_QUOTA_EXCEEDED) is True

    def test_different_error_categories_tracked_independently(self):
        """Test that different error categories have independent rate limits."""
        limiter = NotificationRateLimiter()

        # Record notification for quota exceeded
        limiter.record_notification(ErrorCategory.SERVICE_QUOTA_EXCEEDED)

        # Authentication errors should still be allowed
        assert limiter.can_notify(ErrorCategory.AUTHENTICATION_FAILED) is True


@pytest.mark.unit
class TestNotifyAdmins:
    """Tests for notify_admins function."""

    @pytest.fixture
    def mock_admin_users(self):
        """Create mock admin user records."""
        return [
            {
                "id": "admin1",
                "phone": "+1234567890",
                "name": "Admin One",
                "role": "admin",
                "status": "active",
            },
            {
                "id": "admin2",
                "phone": "+9876543210",
                "name": "Admin Two",
                "role": "admin",
                "status": "active",
            },
        ]

    @pytest.mark.asyncio
    async def test_looks_up_admin_users_from_database(self, mock_admin_users):
        """Test that notify_admins queries database for admin users."""
        with (
            patch("src.core.admin_notifier.list_records") as mock_list_records,
            patch("src.core.admin_notifier.send_text_message") as mock_send,
        ):
            mock_list_records.return_value = mock_admin_users
            mock_send.return_value = MagicMock(success=True, message_id="msg_123")

            await notify_admins("Test notification")

            # Verify database query for admins
            mock_list_records.assert_called_once()
            call_args = mock_list_records.call_args
            assert call_args.kwargs["collection"] == "users"
            assert "role = 'admin'" in call_args.kwargs["filter_query"]
            assert "status = 'active'" in call_args.kwargs["filter_query"]

    @pytest.mark.asyncio
    async def test_sends_message_to_each_admin(self, mock_admin_users):
        """Test that messages are sent to all admin users."""
        with (
            patch("src.core.admin_notifier.list_records") as mock_list_records,
            patch("src.core.admin_notifier.send_text_message") as mock_send,
        ):
            mock_list_records.return_value = mock_admin_users
            mock_send.return_value = MagicMock(success=True, message_id="msg_123")

            await notify_admins("Critical error occurred")

            # Verify send_text_message called for each admin
            assert mock_send.call_count == 2

            # Verify correct phone numbers used
            call_phones = [call.kwargs["to_phone"] for call in mock_send.call_args_list]
            assert "+1234567890" in call_phones
            assert "+9876543210" in call_phones

    @pytest.mark.asyncio
    async def test_includes_severity_in_message(self, mock_admin_users):
        """Test that severity level is included in notification message."""
        with (
            patch("src.core.admin_notifier.list_records") as mock_list_records,
            patch("src.core.admin_notifier.send_text_message") as mock_send,
        ):
            mock_list_records.return_value = mock_admin_users
            mock_send.return_value = MagicMock(success=True, message_id="msg_123")

            await notify_admins("Test message", severity="critical")

            # Verify message contains severity
            call_args = mock_send.call_args_list[0]
            message_text = call_args.kwargs["text"]
            assert "[CRITICAL]" in message_text
            assert "Test message" in message_text

    @pytest.mark.asyncio
    async def test_logs_notification_attempts_to_logfire(self, mock_admin_users):
        """Test that notification attempts are logged to Logfire."""
        with (
            patch("src.core.admin_notifier.list_records") as mock_list_records,
            patch("src.core.admin_notifier.send_text_message") as mock_send,
            patch("src.core.admin_notifier.logfire") as mock_logfire,
        ):
            mock_list_records.return_value = mock_admin_users
            mock_send.return_value = MagicMock(success=True, message_id="msg_123")

            await notify_admins("Test notification", severity="warning")

            # Verify logfire span created
            mock_logfire.span.assert_called_once()
            span_args = mock_logfire.span.call_args
            assert span_args.args[0] == "admin_notifier.notify_admins"
            assert span_args.kwargs["severity"] == "warning"

            # Verify success logging
            info_calls = [call for call in mock_logfire.info.call_args_list]
            assert len(info_calls) >= 2  # At least one per admin

    @pytest.mark.asyncio
    async def test_handles_send_failures_gracefully(self, mock_admin_users):
        """Test that send failures are logged but don't stop other notifications."""
        with (
            patch("src.core.admin_notifier.list_records") as mock_list_records,
            patch("src.core.admin_notifier.send_text_message") as mock_send,
            patch("src.core.admin_notifier.logfire") as mock_logfire,
        ):
            mock_list_records.return_value = mock_admin_users

            # First admin succeeds, second fails
            mock_send.side_effect = [
                MagicMock(success=True, message_id="msg_123"),
                MagicMock(success=False, error="Rate limit exceeded"),
            ]

            await notify_admins("Test notification")

            # Verify both sends were attempted
            assert mock_send.call_count == 2

            # Verify failure was logged
            error_calls = [call for call in mock_logfire.error.call_args_list]
            assert any("Failed to send admin notification" in str(call) for call in error_calls)

    @pytest.mark.asyncio
    async def test_handles_no_admins_gracefully(self):
        """Test that function handles case with no admin users."""
        with (
            patch("src.core.admin_notifier.list_records") as mock_list_records,
            patch("src.core.admin_notifier.send_text_message") as mock_send,
            patch("src.core.admin_notifier.logfire") as mock_logfire,
        ):
            mock_list_records.return_value = []

            await notify_admins("Test notification")

            # Verify no messages sent
            mock_send.assert_not_called()

            # Verify warning logged
            warn_calls = [call for call in mock_logfire.warn.call_args_list]
            assert any("No active admin users" in str(call) for call in warn_calls)

    @pytest.mark.asyncio
    async def test_handles_database_errors_gracefully(self):
        """Test that database errors are caught and logged."""
        with (
            patch("src.core.admin_notifier.list_records") as mock_list_records,
            patch("src.core.admin_notifier.logfire") as mock_logfire,
        ):
            mock_list_records.side_effect = Exception("Database connection failed")

            # Should not raise exception
            await notify_admins("Test notification")

            # Verify error was logged
            error_calls = [call for call in mock_logfire.error.call_args_list]
            assert any("Failed to notify admins" in str(call) for call in error_calls)

    @pytest.mark.asyncio
    async def test_filters_only_active_admins(self):
        """Test that only active admin users receive notifications."""
        mixed_users = [
            {
                "id": "admin1",
                "phone": "+1234567890",
                "name": "Active Admin",
                "role": "admin",
                "status": "active",
            },
            {
                "id": "admin2",
                "phone": "+9876543210",
                "name": "Pending Admin",
                "role": "admin",
                "status": "pending",  # Should not receive notification
            },
        ]

        with (
            patch("src.core.admin_notifier.list_records") as mock_list_records,
            patch("src.core.admin_notifier.send_text_message") as mock_send,
        ):
            # Database query should filter out non-active users
            mock_list_records.return_value = [mixed_users[0]]
            mock_send.return_value = MagicMock(success=True, message_id="msg_123")

            await notify_admins("Test notification")

            # Verify only one message sent (to active admin)
            assert mock_send.call_count == 1
            call_args = mock_send.call_args
            assert call_args.kwargs["to_phone"] == "+1234567890"

    @pytest.mark.asyncio
    async def test_logs_success_and_failure_counts(self, mock_admin_users):
        """Test that success/failure counts are logged."""
        with (
            patch("src.core.admin_notifier.list_records") as mock_list_records,
            patch("src.core.admin_notifier.send_text_message") as mock_send,
            patch("src.core.admin_notifier.logfire") as mock_logfire,
        ):
            mock_list_records.return_value = mock_admin_users

            # One success, one failure
            mock_send.side_effect = [
                MagicMock(success=True, message_id="msg_123"),
                MagicMock(success=False, error="Error"),
            ]

            await notify_admins("Test notification")

            # Verify final summary log
            info_calls = [call for call in mock_logfire.info.call_args_list]
            summary_call = next(
                (call for call in info_calls if "notification batch complete" in str(call)),
                None,
            )
            assert summary_call is not None
            assert summary_call.kwargs["success_count"] == 1
            assert summary_call.kwargs["failure_count"] == 1
            assert summary_call.kwargs["total_admins"] == 2
