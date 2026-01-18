"""Chore service for CRUD operations and state machine."""

import logging
import re
from datetime import datetime, timedelta
from typing import Any

from croniter import croniter

from src.core import db_client
from src.core.logging import span
from src.domain.chore import ChoreState
from src.services import chore_state_machine


logger = logging.getLogger(__name__)


def _parse_recurrence_to_cron(recurrence: str) -> str:
    """Parse recurrence string to CRON expression.

    Supports:
    - Direct CRON expressions (e.g., "0 20 * * *")
    - Interval format (e.g., "every 3 days")

    Args:
        recurrence: Recurrence string

    Returns:
        CRON expression

    Raises:
        ValueError: If recurrence format is invalid
    """
    # Check if already a valid CRON expression
    if croniter.is_valid(recurrence):
        return recurrence

    # Parse "every X days" format
    match = re.match(r"^every\s+(\d+)\s+days?$", recurrence.lower())
    if match:
        days = int(match.group(1))
        # Encode interval in CRON string: INTERVAL:N:cron_expression
        # This allows us to add N days programmatically instead of using invalid CRON syntax
        return f"INTERVAL:{days}:0 0 * * *"

    msg = f"Invalid recurrence format: {recurrence}. Use CRON expression or 'every X days'"
    raise ValueError(msg)


def _parse_recurrence_for_personal_chore(recurrence: str) -> tuple[str | None, datetime | None]:
    """Parse recurrence string for personal chores.

    Supports:
    - Direct CRON expressions (e.g., "0 20 * * *")
    - "every X days" format (e.g., "every 3 days")
    - "every morning" → 0 8 * * * (daily at 8 AM)
    - "every Friday" → 0 8 * * 5 (weekly on Friday at 8 AM)
    - "by Friday" → one-time task with due date (no recurrence)

    Args:
        recurrence: Recurrence string from user input

    Returns:
        Tuple of (cron_expression, due_date)
        - If recurring: (cron_string, None)
        - If one-time: (None, due_date)

    Raises:
        ValueError: If recurrence format is invalid
    """
    recurrence_lower = recurrence.lower().strip()

    # Check if already a valid CRON expression
    if croniter.is_valid(recurrence):
        return (recurrence, None)

    # Parse "every X days" format
    match = re.match(r"^every\s+(\d+)\s+days?$", recurrence_lower)
    if match:
        days = int(match.group(1))
        return (f"INTERVAL:{days}:0 0 * * *", None)

    # Parse "every morning"
    if recurrence_lower == "every morning":
        return ("0 8 * * *", None)

    # Parse "every [weekday]" (e.g., "every friday")
    weekday_match = re.match(r"^every\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)$", recurrence_lower)
    if weekday_match:
        weekday_map = {
            "monday": 1,
            "tuesday": 2,
            "wednesday": 3,
            "thursday": 4,
            "friday": 5,
            "saturday": 6,
            "sunday": 0,
        }
        day_num = weekday_map[weekday_match.group(1)]
        return (f"0 8 * * {day_num}", None)

    # Parse "by [weekday]" (e.g., "by friday") - one-time task
    by_match = re.match(r"^by\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)$", recurrence_lower)
    if by_match:
        # Calculate next occurrence of this weekday
        today = datetime.now().date()
        target_weekday_map = {
            "monday": 0,
            "tuesday": 1,
            "wednesday": 2,
            "thursday": 3,
            "friday": 4,
            "saturday": 5,
            "sunday": 6,
        }
        target_weekday = target_weekday_map[by_match.group(1)]
        current_weekday = today.weekday()

        # Calculate days until target weekday
        days_ahead = target_weekday - current_weekday
        if days_ahead <= 0:  # Target day already happened this week
            days_ahead += 7

        due_date = datetime.combine(today + timedelta(days=days_ahead), datetime.min.time().replace(hour=8, minute=0))
        return (None, due_date)

    # Invalid format
    msg = (
        f"Invalid recurrence format: {recurrence}. "
        f"Use CRON expression, 'every X days', 'every morning', "
        f"'every [weekday]', or 'by [weekday]'"
    )
    raise ValueError(msg)


async def create_chore(
    *,
    title: str,
    description: str = "",
    recurrence: str,
    assigned_to: str | None = None,
) -> dict[str, Any]:
    """Create a new chore.

    Args:
        title: Chore title (e.g., "Wash Dishes")
        description: Detailed description
        recurrence: Recurrence string (CRON or "every X days")
        assigned_to: User ID to assign chore to (None for unassigned)

    Returns:
        Created chore record

    Raises:
        ValueError: If recurrence format is invalid
        db_client.DatabaseError: If database operation fails
    """
    with span("chore_service.create_chore"):
        # Parse and validate recurrence
        schedule_cron = _parse_recurrence_to_cron(recurrence)

        # Calculate initial deadline
        deadline = chore_state_machine._calculate_next_deadline(schedule_cron=schedule_cron)

        # Create chore record
        chore_data = {
            "title": title,
            "description": description,
            "schedule_cron": schedule_cron,
            "assigned_to": assigned_to or "",  # Empty string for unassigned
            "current_state": ChoreState.TODO,
            "deadline": deadline.isoformat(),
        }

        record = await db_client.create_record(collection="chores", data=chore_data)
        logger.info("Created chore: %s (assigned to: %s)", title, assigned_to or "unassigned")

        return record


async def get_chores(
    *,
    user_id: str | None = None,
    state: ChoreState | None = None,
    time_range_start: datetime | None = None,
    time_range_end: datetime | None = None,
) -> list[dict[str, Any]]:
    """Get chores with optional filters.

    Args:
        user_id: Filter by assigned user ID
        state: Filter by chore state
        time_range_start: Filter by deadline >= this time
        time_range_end: Filter by deadline <= this time

    Returns:
        List of chore records matching filters
    """
    with span("chore_service.get_chores"):
        # Build filter query
        filters = []

        if user_id:
            filters.append(f'assigned_to = "{user_id}"')

        if state:
            filters.append(f'current_state = "{state}"')

        if time_range_start:
            filters.append(f'deadline >= "{time_range_start.isoformat()}"')

        if time_range_end:
            filters.append(f'deadline <= "{time_range_end.isoformat()}"')

        filter_query = " && ".join(filters) if filters else ""

        records = await db_client.list_records(
            collection="chores",
            filter_query=filter_query,
            sort="+deadline",  # Sort by deadline ascending
        )

        logger.debug("Retrieved %d chores with filters: %s", len(records), filter_query)

        return records


async def mark_pending_verification(*, chore_id: str) -> dict[str, Any]:
    """Transition chore to PENDING_VERIFICATION state.

    Args:
        chore_id: Chore ID

    Returns:
        Updated chore record

    Raises:
        InvalidStateTransitionError: If chore is not in TODO state
        db_client.RecordNotFoundError: If chore not found
    """
    return await chore_state_machine.transition_to_pending_verification(chore_id=chore_id)


async def complete_chore(*, chore_id: str) -> dict[str, Any]:
    """Complete a chore and calculate next deadline (floating schedule).

    Args:
        chore_id: Chore ID

    Returns:
        Updated chore record

    Raises:
        InvalidStateTransitionError: If chore is not in PENDING_VERIFICATION state
        db_client.RecordNotFoundError: If chore not found
    """
    return await chore_state_machine.transition_to_completed(chore_id=chore_id)


async def move_to_conflict(*, chore_id: str) -> dict[str, Any]:
    """Transition chore to CONFLICT state.

    Args:
        chore_id: Chore ID

    Returns:
        Updated chore record

    Raises:
        InvalidStateTransitionError: If chore is not in PENDING_VERIFICATION state
        db_client.RecordNotFoundError: If chore not found
    """
    return await chore_state_machine.transition_to_conflict(chore_id=chore_id)


async def reset_chore_to_todo(*, chore_id: str) -> dict[str, Any]:
    """Reset chore back to TODO state (useful after conflict resolution).

    Args:
        chore_id: Chore ID

    Returns:
        Updated chore record
    """
    return await chore_state_machine.transition_to_todo(chore_id=chore_id)


async def get_chore_by_id(*, chore_id: str) -> dict[str, Any]:
    """Get chore by ID.

    Args:
        chore_id: Chore ID

    Returns:
        Chore record

    Raises:
        db_client.RecordNotFoundError: If chore not found
    """
    return await db_client.get_record(collection="chores", record_id=chore_id)
