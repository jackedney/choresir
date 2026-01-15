"""Chore service for CRUD operations and state machine."""

import logging
import re
from datetime import datetime, timedelta
from typing import Any

from croniter import croniter

from src.core import db_client
from src.domain.chore import ChoreState


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


def _calculate_next_deadline(*, schedule_cron: str, from_time: datetime | None = None) -> datetime:
    """Calculate next deadline from CRON schedule.

    Uses floating schedule logic: if from_time is provided, calculates next occurrence
    from that time (useful for deadlines that shift based on completion time).

    Args:
        schedule_cron: CRON expression or INTERVAL:N:cron format
        from_time: Starting time for calculation (defaults to now)

    Returns:
        Next deadline datetime
    """
    base_time = from_time or datetime.now()

    # Handle interval-based scheduling (e.g., "INTERVAL:3:0 0 * * *")
    if schedule_cron.startswith("INTERVAL:"):
        parts = schedule_cron.split(":", 2)
        days = int(parts[1])
        # Add X days to base time
        next_time = base_time + timedelta(days=days)
        # Set to midnight of that day
        return next_time.replace(hour=0, minute=0, second=0, microsecond=0)

    # Standard CRON expression
    cron = croniter(schedule_cron, base_time)
    return cron.get_next(datetime)


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
    # Parse and validate recurrence
    schedule_cron = _parse_recurrence_to_cron(recurrence)

    # Calculate initial deadline
    deadline = _calculate_next_deadline(schedule_cron=schedule_cron)

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
    # Guard: Verify chore exists and is in TODO state
    chore = await db_client.get_record(collection="chores", record_id=chore_id)
    if chore["current_state"] != ChoreState.TODO:
        msg = f"Cannot mark pending: chore {chore_id} is in {chore['current_state']} state"
        raise ValueError(msg)

    # Update state
    updated_record = await db_client.update_record(
        collection="chores",
        record_id=chore_id,
        data={"current_state": ChoreState.PENDING_VERIFICATION},
    )

    logger.info("Marked chore %s as pending verification", chore_id)

    return updated_record


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
    # Guard: Verify chore exists and is pending verification
    chore = await db_client.get_record(collection="chores", record_id=chore_id)
    if chore["current_state"] != ChoreState.PENDING_VERIFICATION:
        msg = f"Cannot complete: chore {chore_id} is in {chore['current_state']} state"
        raise ValueError(msg)

    # Calculate next deadline from now (floating schedule)
    next_deadline = _calculate_next_deadline(
        schedule_cron=chore["schedule_cron"],
        from_time=datetime.now(),
    )

    # Update state and deadline
    updated_record = await db_client.update_record(
        collection="chores",
        record_id=chore_id,
        data={
            "current_state": ChoreState.COMPLETED,
            "deadline": next_deadline.isoformat(),
        },
    )

    logger.info("Completed chore %s, next deadline: %s", chore_id, next_deadline)

    return updated_record


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
    # Guard: Verify chore exists and is pending verification
    chore = await db_client.get_record(collection="chores", record_id=chore_id)
    if chore["current_state"] != ChoreState.PENDING_VERIFICATION:
        msg = f"Cannot move to conflict: chore {chore_id} is in {chore['current_state']} state"
        raise ValueError(msg)

    # Update state
    updated_record = await db_client.update_record(
        collection="chores",
        record_id=chore_id,
        data={"current_state": ChoreState.CONFLICT},
    )

    logger.info("Moved chore %s to conflict state", chore_id)

    return updated_record


async def reset_chore_to_todo(*, chore_id: str) -> dict[str, Any]:
    """Reset chore back to TODO state (useful after conflict resolution).

    Args:
        chore_id: Chore ID

    Returns:
        Updated chore record
    """
    updated_record = await db_client.update_record(
        collection="chores",
        record_id=chore_id,
        data={"current_state": ChoreState.TODO},
    )

    logger.info("Reset chore %s to TODO state", chore_id)

    return updated_record


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
