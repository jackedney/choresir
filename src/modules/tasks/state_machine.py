"""Pure state transition functions for task lifecycle management."""

import logging
from datetime import datetime, timedelta
from typing import Any

from croniter import croniter

from src.core import db_client
from src.core.logging import span
from src.domain.task import TaskState, VerificationType


logger = logging.getLogger(__name__)


# Allowed transitions by verification type
VERIFIED_TRANSITIONS: dict[TaskState, set[TaskState]] = {
    TaskState.TODO: {TaskState.PENDING_VERIFICATION, TaskState.ARCHIVED},
    TaskState.PENDING_VERIFICATION: {TaskState.COMPLETED, TaskState.TODO},
    TaskState.COMPLETED: {TaskState.TODO},  # Reset for recurring
    TaskState.ARCHIVED: set(),
}

SIMPLE_TRANSITIONS: dict[TaskState, set[TaskState]] = {
    TaskState.TODO: {TaskState.COMPLETED, TaskState.ARCHIVED},
    TaskState.COMPLETED: {TaskState.TODO},  # Reset for recurring
    TaskState.ARCHIVED: set(),
}


def get_transitions(*, verification: VerificationType) -> dict[TaskState, set[TaskState]]:
    """Get allowed state transitions based on verification type."""
    if verification == VerificationType.NONE:
        return SIMPLE_TRANSITIONS
    return VERIFIED_TRANSITIONS


def calculate_next_deadline(*, schedule_cron: str, from_time: datetime | None = None) -> datetime:
    """Calculate next deadline from CRON schedule using floating schedule logic."""
    base_time = from_time or datetime.now()

    # Handle interval-based scheduling (e.g., "INTERVAL:3:0 0 * * *")
    if schedule_cron.startswith("INTERVAL:"):
        parts = schedule_cron.split(":", 2)
        days = int(parts[1])
        next_time = base_time + timedelta(days=days)
        return next_time.replace(hour=0, minute=0, second=0, microsecond=0)

    # Standard CRON expression
    cron = croniter(schedule_cron, base_time)
    return cron.get_next(datetime)


async def transition_to_completed(*, task_id: str) -> dict[str, Any]:
    """Transition task to COMPLETED state and recalculate deadline for recurring tasks."""
    with span("task_state_machine.transition_to_completed"):
        task = await db_client.get_record(collection="tasks", record_id=task_id)

        if task["current_state"] != TaskState.PENDING_VERIFICATION:
            msg = f"Cannot complete: task {task_id} is in {task['current_state']} state"
            raise ValueError(msg)

        update_data: dict[str, Any] = {"current_state": TaskState.COMPLETED}

        # Calculate next deadline from now for recurring tasks (floating schedule)
        if task.get("schedule_cron"):
            next_deadline = calculate_next_deadline(
                schedule_cron=task["schedule_cron"],
                from_time=datetime.now(),
            )
            update_data["deadline"] = next_deadline.isoformat()

        updated_record = await db_client.update_record(
            collection="tasks",
            record_id=task_id,
            data=update_data,
        )

        logger.info("Transitioned task %s to COMPLETED", task_id)
        return updated_record


async def transition_to_completed_no_verification(*, task_id: str) -> dict[str, Any]:
    """Directly complete a task that has verification=none."""
    with span("task_state_machine.transition_to_completed_no_verification"):
        task = await db_client.get_record(collection="tasks", record_id=task_id)

        if task["current_state"] != TaskState.TODO:
            msg = f"Cannot complete: task {task_id} is in {task['current_state']} state"
            raise ValueError(msg)

        update_data: dict[str, Any] = {"current_state": TaskState.COMPLETED}

        if task.get("schedule_cron"):
            next_deadline = calculate_next_deadline(
                schedule_cron=task["schedule_cron"],
                from_time=datetime.now(),
            )
            update_data["deadline"] = next_deadline.isoformat()

        updated_record = await db_client.update_record(
            collection="tasks",
            record_id=task_id,
            data=update_data,
        )

        logger.info("Transitioned task %s to COMPLETED (no verification)", task_id)
        return updated_record


async def transition_to_todo(*, task_id: str) -> dict[str, Any]:
    """Transition task to TODO state (e.g. after rejection or recurring reset)."""
    with span("task_state_machine.transition_to_todo"):
        task = await db_client.get_record(collection="tasks", record_id=task_id)
        if task["current_state"] == TaskState.ARCHIVED:
            msg = f"Cannot transition to TODO: task {task_id} is ARCHIVED"
            raise ValueError(msg)

        updated_record = await db_client.update_record(
            collection="tasks",
            record_id=task_id,
            data={"current_state": TaskState.TODO},
        )

        logger.info("Transitioned task %s to TODO", task_id)
        return updated_record


async def transition_to_pending_verification(*, task_id: str) -> dict[str, Any]:
    """Transition task to PENDING_VERIFICATION state."""
    with span("task_state_machine.transition_to_pending_verification"):
        task = await db_client.get_record(collection="tasks", record_id=task_id)
        if task["current_state"] != TaskState.TODO:
            msg = f"Cannot mark pending: task {task_id} is in {task['current_state']} state"
            raise ValueError(msg)

        updated_record = await db_client.update_record(
            collection="tasks",
            record_id=task_id,
            data={"current_state": TaskState.PENDING_VERIFICATION},
        )

        logger.info("Transitioned task %s to PENDING_VERIFICATION", task_id)
        return updated_record


async def transition_to_archived(*, task_id: str) -> dict[str, Any]:
    """Transition task to ARCHIVED state (soft delete)."""
    with span("task_state_machine.transition_to_archived"):
        task = await db_client.get_record(collection="tasks", record_id=task_id)
        if task["current_state"] != TaskState.TODO:
            msg = f"Cannot archive: task {task_id} is in {task['current_state']} state, must be TODO"
            raise ValueError(msg)

        updated_record = await db_client.update_record(
            collection="tasks",
            record_id=task_id,
            data={"current_state": TaskState.ARCHIVED},
        )

        logger.info("Transitioned task %s to ARCHIVED", task_id)
        return updated_record
