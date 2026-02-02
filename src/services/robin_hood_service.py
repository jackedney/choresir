"""Robin Hood Protocol service for chore takeover management.

This module implements the Robin Hood Protocol (ADR-016) which allows
household members to take over each other's chores with weekly limits.

Key Features:
- Track weekly takeover counts per user
- Enforce 3 takeovers per week limit
- Reset counters every Monday at 00:00 household timezone
- Support for point attribution based on completion timing
"""

import logging
from datetime import UTC, datetime, timedelta

from src.core import db_client
from src.core.config import settings


logger = logging.getLogger(__name__)


def get_week_start_date(dt: datetime | None = None) -> datetime:
    """Get the start of the week (Monday 00:00) for a given datetime.

    Args:
        dt: Datetime to get week start for. If None, uses current time.

    Returns:
        Datetime representing Monday 00:00 of the week in UTC
    """
    if dt is None:
        dt = datetime.now(UTC)

    # Get days since Monday (0 = Monday, 6 = Sunday)
    days_since_monday = dt.weekday()

    # Calculate Monday of this week at 00:00
    monday = dt - timedelta(days=days_since_monday)
    return monday.replace(hour=0, minute=0, second=0, microsecond=0)


async def get_weekly_takeover_count(user_id: str) -> int:
    """Get the number of takeovers a user has performed this week.

    Args:
        user_id: User ID to check

    Returns:
        Number of takeovers performed this week (0-3)
    """
    week_start = get_week_start_date()

    try:
        # Query for this user's record for the current week
        records = await db_client.list_records(
            collection="robin_hood_swaps",
            filter_query=f'user_id = "{user_id}" && week_start_date = "{week_start.isoformat()}"',
        )

        if records:
            return records[0].get("takeover_count", 0)
        return 0

    except Exception:
        logger.exception("Failed to get weekly takeover count for user %s", user_id)
        # Fail safe: return 0 to allow operation if DB query fails
        return 0


async def increment_weekly_takeover_count(user_id: str) -> int:
    """Increment the weekly takeover count for a user.

    Creates a new record if one doesn't exist for this week.

    Args:
        user_id: User ID to increment count for

    Returns:
        New takeover count after increment

    Raises:
        RuntimeError: If database operation fails
    """
    week_start = get_week_start_date()

    try:
        # Try to get existing record for this week
        records = await db_client.list_records(
            collection="robin_hood_swaps",
            filter_query=f'user_id = "{user_id}" && week_start_date = "{week_start.isoformat()}"',
        )

        if records:
            # Update existing record
            record = records[0]
            new_count = record.get("takeover_count", 0) + 1
            await db_client.update_record(
                collection="robin_hood_swaps",
                record_id=record["id"],
                data={"takeover_count": new_count},
            )
            logger.info(f"Incremented takeover count for user {user_id} to {new_count}")
            return new_count
        # Create new record for this week
        await db_client.create_record(
            collection="robin_hood_swaps",
            data={
                "user_id": user_id,
                "week_start_date": week_start.isoformat(),
                "takeover_count": 1,
            },
        )
        logger.info(f"Created new takeover record for user {user_id}")
        return 1

    except Exception as e:
        error_msg = f"Failed to increment weekly takeover count for user {user_id}: {e}"
        logger.error(error_msg)
        raise RuntimeError(error_msg) from e


async def can_perform_takeover(user_id: str) -> tuple[bool, str | None]:
    """Check if a user can perform a Robin Hood takeover.

    Args:
        user_id: User ID to check

    Returns:
        Tuple of (can_takeover, error_message)
        - can_takeover: True if user hasn't reached weekly limit
        - error_message: None if allowed, error string if not
    """
    current_count = await get_weekly_takeover_count(user_id)

    if current_count >= settings.robin_hood_weekly_limit:
        return False, (
            f"You've reached your weekly takeover limit ({settings.robin_hood_weekly_limit} takeovers). "
            f"This limit resets every Monday at midnight."
        )

    return True, None
