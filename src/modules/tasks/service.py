"""Task service for CRUD operations and state machine."""

import logging
from datetime import datetime
from typing import Any

from src.core import db_client
from src.core.db_client import sanitize_param
from src.core.fuzzy_match import fuzzy_match
from src.core.logging import span
from src.core.recurrence_parser import parse_recurrence_for_personal_chore, parse_recurrence_to_cron
from src.domain.task import TaskScope, TaskState, VerificationType
from src.modules.tasks import state_machine


logger = logging.getLogger(__name__)


async def create_chore(
    *,
    title: str,
    description: str = "",
    recurrence: str,
    assigned_to: str | None = None,
) -> dict[str, Any]:
    """Create a new shared chore.

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
    with span("task_service.create_chore"):
        # Parse and validate recurrence
        schedule_cron = parse_recurrence_to_cron(recurrence)

        # Calculate initial deadline
        deadline = state_machine._calculate_next_deadline(schedule_cron=schedule_cron)

        # Create chore record
        chore_data: dict[str, Any] = {
            "title": title,
            "description": description,
            "schedule_cron": schedule_cron,
            "current_state": TaskState.TODO,
            "deadline": deadline.isoformat(),
            "scope": TaskScope.SHARED,
            "verification": VerificationType.PEER,
        }
        # Only set assigned_to if we have a valid ID (relations can't be empty string)
        if assigned_to:
            chore_data["assigned_to"] = assigned_to

        record = await db_client.create_record(collection="tasks", data=chore_data)
        logger.info("Created chore: %s (assigned to: %s)", title, assigned_to or "unassigned")

        return record


async def create_personal_chore(
    *,
    owner_id: str,
    title: str,
    recurrence: str | None = None,
    accountability_partner_id: str | None = None,
) -> dict[str, Any]:
    """Create a new personal chore.

    Args:
        owner_id: Member ID of chore owner
        title: Chore title (e.g., "Go to gym")
        recurrence: Recurrence string (CRON, "every X days", "every morning", etc.)
        accountability_partner_id: Optional partner member ID for verification

    Returns:
        Created personal chore record

    Raises:
        ValueError: If recurrence format is invalid
        db_client.DatabaseError: If database operation fails
    """
    with span("task_service.create_personal_chore"):
        # Parse recurrence if provided
        cron_expression = None
        due_date = None

        if recurrence:
            cron_expression, due_date = parse_recurrence_for_personal_chore(recurrence)

        # Determine verification type
        verification = VerificationType.PARTNER if accountability_partner_id else VerificationType.NONE

        # Create chore record using unified tasks schema
        chore_data: dict[str, Any] = {
            "title": title,
            "scope": TaskScope.PERSONAL,
            "verification": verification,
            "current_state": TaskState.TODO,
            "owner_id": owner_id,
        }

        if cron_expression:
            chore_data["schedule_cron"] = cron_expression

        if due_date:
            chore_data["deadline"] = due_date.isoformat()

        if accountability_partner_id:
            chore_data["accountability_partner_id"] = accountability_partner_id

        record = await db_client.create_record(collection="tasks", data=chore_data)

        logger.info(
            "Created personal chore '%s' for owner_id=%s (partner: %s)",
            title,
            owner_id,
            accountability_partner_id or "none",
        )

        return record


async def get_chores(
    *,
    user_id: str | None = None,
    state: TaskState | None = None,
    time_range_start: datetime | None = None,
    time_range_end: datetime | None = None,
    scope: TaskScope | None = None,
) -> list[dict[str, Any]]:
    """Get tasks with optional filters.

    Args:
        user_id: Filter by assigned user ID (shared) or owner ID (personal)
        state: Filter by task state
        time_range_start: Filter by deadline >= this time
        time_range_end: Filter by deadline <= this time
        scope: Filter by scope (shared or personal)

    Returns:
        List of task records matching filters
    """
    with span("task_service.get_tasks"):
        # Build filter query
        filters = []

        if scope:
            filters.append(f'scope = "{db_client.sanitize_param(scope)}"')

        if user_id:
            if scope == TaskScope.PERSONAL:
                filters.append(f'owner_id = "{db_client.sanitize_param(user_id)}"')
            else:
                filters.append(f'assigned_to = "{db_client.sanitize_param(user_id)}"')

        if state:
            filters.append(f'current_state = "{db_client.sanitize_param(state)}"')

        if time_range_start:
            filters.append(f'deadline >= "{time_range_start.isoformat()}"')

        if time_range_end:
            filters.append(f'deadline <= "{time_range_end.isoformat()}"')

        filter_query = " && ".join(filters) if filters else ""

        records = await db_client.list_records(
            collection="tasks",
            filter_query=filter_query,
            sort="+deadline",  # Sort by deadline ascending
        )

        logger.debug("Retrieved %d tasks with filters: %s", len(records), filter_query)

        return records


async def get_personal_chores(
    *,
    owner_id: str,
    include_archived: bool = False,
) -> list[dict[str, Any]]:
    """Get all personal chores for a user.

    Args:
        owner_id: Member ID of chore owner
        include_archived: Whether to include archived chores (default: False)

    Returns:
        List of personal chore records
    """
    with span("task_service.get_personal_chores"):
        filters = [
            f'owner_id = "{sanitize_param(owner_id)}"',
            f'scope = "{TaskScope.PERSONAL}"',
        ]

        if not include_archived:
            filters.append(f'current_state != "{TaskState.ARCHIVED}"')

        filter_query = " && ".join(filters)

        return await db_client.list_records(
            collection="tasks",
            filter_query=filter_query,
            sort="+created",
        )


async def get_task_by_id(*, task_id: str) -> dict[str, Any]:
    """Get task by ID.

    Args:
        task_id: Task ID

    Returns:
        Task record

    Raises:
        db_client.RecordNotFoundError: If task not found
    """
    return await db_client.get_record(collection="tasks", record_id=task_id)


async def get_personal_chore_by_id(
    *,
    chore_id: str,
    owner_id: str,
) -> dict[str, Any]:
    """Get a personal chore by ID with ownership validation.

    Args:
        chore_id: Personal chore ID
        owner_id: Expected owner member ID (for validation)

    Returns:
        Personal chore record

    Raises:
        KeyError: If chore not found
        PermissionError: If chore doesn't belong to owner
    """
    with span("task_service.get_personal_chore_by_id"):
        record = await db_client.get_record(
            collection="tasks",
            record_id=chore_id,
        )

        # Validate ownership
        if str(record.get("owner_id")) != str(owner_id):
            raise PermissionError(f"Personal chore {chore_id} does not belong to {owner_id}")

        return record


async def delete_personal_chore(
    *,
    chore_id: str,
    owner_id: str,
) -> None:
    """Archive a personal chore (soft delete).

    Args:
        chore_id: Personal chore ID
        owner_id: Owner member ID (for validation)

    Raises:
        KeyError: If chore not found
        PermissionError: If chore doesn't belong to owner
    """
    with span("task_service.delete_personal_chore"):
        # Validate ownership
        chore = await get_personal_chore_by_id(
            chore_id=chore_id,
            owner_id=owner_id,
        )

        # Soft delete by transitioning to ARCHIVED
        await db_client.update_record(
            collection="tasks",
            record_id=chore_id,
            data={"current_state": TaskState.ARCHIVED},
        )

        logger.info("Archived personal chore '%s' for owner_id=%s", chore["title"], owner_id)


def fuzzy_match_task(tasks: list[dict], title_query: str) -> dict | None:
    """Fuzzy match a task by title.

    Delegates to the shared fuzzy_match utility.

    Args:
        tasks: List of task records
        title_query: User's search query

    Returns:
        Best matching task or None
    """
    return fuzzy_match(tasks, title_query)


async def complete_task(*, task_id: str) -> dict[str, Any]:
    """Complete a task and calculate next deadline (floating schedule).

    Args:
        task_id: Task ID

    Returns:
        Updated task record

    Raises:
        ValueError: If task is not in PENDING_VERIFICATION state
        db_client.RecordNotFoundError: If task not found
    """
    return await state_machine.transition_to_completed(task_id=task_id)


async def complete_task_no_verification(*, task_id: str) -> dict[str, Any]:
    """Directly complete a task that has verification=none.

    Args:
        task_id: Task ID

    Returns:
        Updated task record

    Raises:
        ValueError: If task is not in TODO state
        db_client.RecordNotFoundError: If task not found
    """
    return await state_machine.transition_to_completed_no_verification(task_id=task_id)


async def reset_task_to_todo(*, task_id: str) -> dict[str, Any]:
    """Reset task back to TODO state (e.g. after rejection or recurring reset).

    Args:
        task_id: Task ID

    Returns:
        Updated task record
    """
    return await state_machine.transition_to_todo(task_id=task_id)


async def archive_task(*, task_id: str) -> dict[str, Any]:
    """Archive a task (soft delete).

    Args:
        task_id: Task ID

    Returns:
        Updated task record
    """
    return await state_machine.transition_to_archived(task_id=task_id)


# Backwards compatibility aliases for chore_service
async def complete_chore(*, chore_id: str) -> dict[str, Any]:
    """Complete a chore (backwards compatibility wrapper)."""
    return await complete_task(task_id=chore_id)


async def mark_pending_verification(*, chore_id: str) -> dict[str, Any]:
    """Transition chore to pending verification (backwards compatibility wrapper)."""
    return await state_machine.transition_to_pending_verification(task_id=chore_id)


async def reset_chore_to_todo(*, chore_id: str) -> dict[str, Any]:
    """Reset chore to TODO (backwards compatibility wrapper)."""
    return await state_machine.transition_to_todo(task_id=chore_id)


async def get_chore_by_id(*, chore_id: str) -> dict[str, Any]:
    """Get chore by ID (backwards compatibility wrapper)."""
    return await db_client.get_record(collection="tasks", record_id=chore_id)


# Backwards compatibility for personal_chore_service
fuzzy_match_personal_chore = fuzzy_match_task
