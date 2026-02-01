"""Session service for managing join session state."""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from src.core import db_client
from src.core.db_client import sanitize_param
from src.core.logging import span


logger = logging.getLogger(__name__)


# Session expiry timeout (5 minutes)
SESSION_EXPIRY_MINUTES = 5

# Rate limit delay after failed attempt (5 seconds)
RATE_LIMIT_SECONDS = 5


async def create_session(
    *,
    phone: str,
    house_name: str,
    step: str = "awaiting_password",
) -> dict[str, Any]:
    """Create a new join session. Replaces any existing session for this phone.

    Args:
        phone: User's phone number in E.164 format
        house_name: Name of house user is trying to join
        step: Current step in join flow (default: "awaiting_password")

    Returns:
        Created session document

    Raises:
        RuntimeError: If database operation fails
    """
    with span("session_service.create_session"):
        # Delete any existing session for this phone (latest command wins)
        existing_session = await db_client.get_first_record(
            collection="join_sessions",
            filter_query=f'phone = "{sanitize_param(phone)}"',
        )
        if existing_session:
            await db_client.delete_record(
                collection="join_sessions",
                record_id=existing_session["id"],
            )
            logger.info("Deleted existing session", extra={"operation": "delete_existing_session"})

        # Create new session
        now = datetime.now(UTC)
        expires_at = now + timedelta(minutes=SESSION_EXPIRY_MINUTES)

        session_data = {
            "phone": phone,
            "house_name": house_name,
            "step": step,
            "password_attempts_count": 0,
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
        }

        record = await db_client.create_record(
            collection="join_sessions",
            data=session_data,
        )
        logger.info(
            "Created join session", extra={"operation": "create_join_session", "expires_at": expires_at.isoformat()}
        )

        return record


async def get_session(*, phone: str) -> dict[str, Any] | None:
    """Get active session for phone. Returns None if expired or not found.

    Args:
        phone: User's phone number in E.164 format

    Returns:
        Session document or None if not found or expired

    Raises:
        RuntimeError: If database operation fails
    """
    with span("session_service.get_session"):
        session = await db_client.get_first_record(
            collection="join_sessions",
            filter_query=f'phone = "{sanitize_param(phone)}"',
        )

        if not session:
            return None

        # Check if session has expired
        if is_expired(session):
            await db_client.delete_record(
                collection="join_sessions",
                record_id=session["id"],
            )
            logger.info("Deleted expired session", extra={"operation": "delete_expired_session"})
            return None

        return session


async def update_session(*, phone: str, updates: dict[str, Any]) -> bool:
    """Update session fields. Returns True if successful.

    Args:
        phone: User's phone number in E.164 format
        updates: Dictionary of fields to update

    Returns:
        True if session was found and updated, False otherwise

    Raises:
        RuntimeError: If database operation fails
    """
    with span("session_service.update_session"):
        session = await db_client.get_first_record(
            collection="join_sessions",
            filter_query=f'phone = "{sanitize_param(phone)}"',
        )

        if not session:
            logger.warning("Session not found", extra={"operation": "update_session", "status": "not_found"})
            return False

        await db_client.update_record(
            collection="join_sessions",
            record_id=session["id"],
            data=updates,
        )
        logger.info("Updated session", extra={"operation": "update_session", "updates": list(updates.keys())})

        return True


async def delete_session(*, phone: str) -> bool:
    """Delete session. Returns True if session existed.

    Args:
        phone: User's phone number in E.164 format

    Returns:
        True if session existed and was deleted, False otherwise

    Raises:
        RuntimeError: If database operation fails
    """
    with span("session_service.delete_session"):
        session = await db_client.get_first_record(
            collection="join_sessions",
            filter_query=f'phone = "{sanitize_param(phone)}"',
        )

        if not session:
            return False

        await db_client.delete_record(
            collection="join_sessions",
            record_id=session["id"],
        )
        logger.info("Deleted session", extra={"operation": "delete_session"})

        return True


def is_rate_limited(*, session: dict[str, Any]) -> bool:
    """Check if session is rate limited (5 second delay after failed attempt).

    Args:
        session: Session document

    Returns:
        True if rate limited, False otherwise
    """
    last_attempt_at = session.get("last_attempt_at")
    if not last_attempt_at:
        return False

    # Parse the last_attempt_at timestamp
    last_attempt = datetime.fromisoformat(last_attempt_at.replace("Z", "+00:00"))
    now = datetime.now(UTC)

    # Check if less than 5 seconds have elapsed
    elapsed = (now - last_attempt).total_seconds()
    return elapsed < RATE_LIMIT_SECONDS


async def increment_password_attempts(*, phone: str) -> None:
    """Increment password attempt counter and update last_attempt_at.

    Args:
        phone: User's phone number in E.164 format

    Raises:
        RuntimeError: If database operation fails
    """
    with span("session_service.increment_password_attempts"):
        session = await db_client.get_first_record(
            collection="join_sessions",
            filter_query=f'phone = "{sanitize_param(phone)}"',
        )

        if not session:
            logger.warning(
                "Session not found, cannot increment attempts",
                extra={"operation": "increment_attempts", "status": "not_found"},
            )
            return

        current_count = session.get("password_attempts_count", 0)
        updates = {
            "password_attempts_count": current_count + 1,
            "last_attempt_at": datetime.now(UTC).isoformat(),
        }

        await db_client.update_record(
            collection="join_sessions",
            record_id=session["id"],
            data=updates,
        )
        logger.info(
            "Incremented password attempts for %s: %d -> %d",
            phone,
            current_count,
            current_count + 1,
        )


def is_expired(session: dict[str, Any]) -> bool:
    """Check if session has expired.

    Args:
        session: Session document

    Returns:
        True if expired, False otherwise
    """
    expires_at = session.get("expires_at")
    if not expires_at:
        return True

    # Parse the expires_at timestamp
    expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    now = datetime.now(UTC)

    return now > expiry
