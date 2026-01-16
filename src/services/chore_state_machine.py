"""Pure state transition functions for chore lifecycle management."""

import logging
from datetime import datetime, timedelta
from typing import Any

from croniter import croniter

from src.core import db_client
from src.domain.chore import ChoreState


logger = logging.getLogger(__name__)


def _calculate_next_deadline(*, schedule_cron: str, from_time: datetime | None = None) -> datetime:
    """Calculate next deadline from CRON schedule using floating schedule logic."""
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


async def transition_to_completed(*, chore_id: str) -> dict[str, Any]:
    """Transition chore to COMPLETED state and recalculate deadline."""
    # Guard: Verify chore exists and is in valid state
    chore = await db_client.get_record(collection="chores", record_id=chore_id)

    valid_states = {ChoreState.PENDING_VERIFICATION, ChoreState.CONFLICT}
    if chore["current_state"] not in valid_states:
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

    logger.info("Transitioned chore %s to COMPLETED, next deadline: %s", chore_id, next_deadline)

    return updated_record


async def transition_to_todo(*, chore_id: str) -> dict[str, Any]:
    """Transition chore to TODO state."""
    updated_record = await db_client.update_record(
        collection="chores",
        record_id=chore_id,
        data={"current_state": ChoreState.TODO},
    )

    logger.info("Transitioned chore %s to TODO", chore_id)

    return updated_record


async def transition_to_pending_verification(*, chore_id: str) -> dict[str, Any]:
    """Transition chore to PENDING_VERIFICATION state."""
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

    logger.info("Transitioned chore %s to PENDING_VERIFICATION", chore_id)

    return updated_record


async def transition_to_conflict(*, chore_id: str) -> dict[str, Any]:
    """Transition chore to CONFLICT state."""
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

    logger.info("Transitioned chore %s to CONFLICT", chore_id)

    return updated_record


async def transition_to_deadlock(*, chore_id: str) -> dict[str, Any]:
    """Transition chore to DEADLOCK state."""
    # Guard: Verify chore exists and is in conflict
    chore = await db_client.get_record(collection="chores", record_id=chore_id)
    if chore["current_state"] != ChoreState.CONFLICT:
        msg = f"Cannot move to deadlock: chore {chore_id} is in {chore['current_state']} state"
        raise ValueError(msg)

    # Update state
    updated_record = await db_client.update_record(
        collection="chores",
        record_id=chore_id,
        data={"current_state": ChoreState.DEADLOCK},
    )

    logger.warning("Transitioned chore %s to DEADLOCK", chore_id)

    return updated_record
