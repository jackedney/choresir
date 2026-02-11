"""Admin notification system for critical errors and events."""

import logging
from collections import defaultdict
from datetime import datetime, timedelta

from src.core.config import Constants, settings
from src.core.db_client import list_records
from src.core.errors import ErrorCategory
from src.domain.user import User, UserRole, UserStatus
from src.interface.whatsapp_sender import send_text_message


logger = logging.getLogger(__name__)


class NotificationRateLimiter:
    """Rate limiter for admin notifications to prevent spam.

    Tracks notifications per error category per hour to ensure admins
    are not overwhelmed with duplicate alerts.
    """

    def __init__(self) -> None:
        """Initialize notification rate limiter."""
        self._notifications: dict[str, datetime] = defaultdict()

    def can_notify(self, error_category: ErrorCategory) -> bool:
        """Check if a notification can be sent for the given error category.

        Args:
            error_category: The category of error to check

        Returns:
            True if notification is allowed, False if rate limited
        """
        key = error_category.value
        now = datetime.now()

        # Check if we've notified about this error category within the cooldown period
        if key in self._notifications:
            last_notification = self._notifications[key]
            cooldown = timedelta(minutes=settings.admin_notification_cooldown_minutes)
            if now - last_notification < cooldown:
                return False

        return True

    def record_notification(self, error_category: ErrorCategory) -> None:
        """Record a notification for rate limiting.

        Args:
            error_category: The category of error that was notified
        """
        self._notifications[error_category.value] = datetime.now()


# Global rate limiter instance (in-memory for MVP)
notification_rate_limiter = NotificationRateLimiter()


def should_notify_admins(error_category: ErrorCategory) -> bool:
    """Determine if admins should be notified for a given error category.

    Critical errors that require immediate admin attention return True.
    Transient errors that are expected to resolve themselves return False.

    Args:
        error_category: The category of error to evaluate

    Returns:
        True if admins should be notified, False otherwise
    """
    critical_errors = {
        ErrorCategory.SERVICE_QUOTA_EXCEEDED,
        ErrorCategory.AUTHENTICATION_FAILED,
    }

    return error_category in critical_errors


async def notify_admins(message: str, severity: str = "warning") -> None:
    """Send WhatsApp notification to all admin users.

    Looks up all active admin users from the database and sends them
    a WhatsApp message. Includes rate limiting to prevent spam.

    Args:
        message: The notification message to send
        severity: Severity level (e.g., "warning", "critical", "info")
    """
    # Check if admin notifications are enabled
    if not settings.enable_admin_notifications:
        logger.debug(
            "Admin notifications disabled, skipping notification",
            extra={"message": message, "severity": severity},
        )
        return

    logger.info("admin_notifier.notify_admins", extra={"severity": severity})
    try:
        # Look up all admin users from database
        admin_records = await list_records(
            collection="members",
            filter_query=f"role = '{UserRole.ADMIN}' && status = '{UserStatus.ACTIVE}'",
            per_page=Constants.DEFAULT_PER_PAGE_LIMIT,
        )

        if not admin_records:
            logger.warning("No active admin users found to notify")
            return

        # Parse admin users into User objects
        admins = [User(**record) for record in admin_records]

        # Format message with severity prefix
        formatted_message = f"[{severity.upper()}] {message}"

        # Send notification to each admin
        success_count = 0
        failure_count = 0

        for admin in admins:
            logger.info(
                "Sending admin notification",
                extra={"admin_id": admin.id, "admin_name": admin.name, "severity": severity},
            )

            result = await send_text_message(
                to_phone=admin.phone,
                text=formatted_message,
            )

            if result.success:
                success_count += 1
                logger.info(
                    "Admin notification sent successfully",
                    extra={"admin_id": admin.id, "message_id": result.message_id},
                )
            else:
                failure_count += 1
                logger.error(
                    "Failed to send admin notification",
                    extra={"admin_id": admin.id, "error": result.error},
                )

        logger.info(
            "Admin notification batch complete",
            extra={"total_admins": len(admins), "success_count": success_count, "failure_count": failure_count},
        )

    except Exception as e:
        logger.error("Failed to notify admins", extra={"error": str(e)})
