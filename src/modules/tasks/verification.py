"""Unified verification service for task completion verification.

Handles both peer verification (scope=shared) and partner verification (scope=personal).
Works against task_logs table.
"""

import logging
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from src.core import db_client
from src.core.db_client import sanitize_param
from src.core.logging import span
from src.domain.task import TaskState


logger = logging.getLogger(__name__)

# Constants
LOGS_PAGE_SIZE = 500
CHORE_ID_BATCH_SIZE = 100


class VerificationDecision(StrEnum):
    """Verification decision enum."""

    APPROVE = "APPROVE"
    REJECT = "REJECT"


async def get_pending_verification_workflow(*, chore_id: str) -> dict[str, Any] | None:
    """Get pending verification workflow for a chore if one exists.

    Args:
        chore_id: Chore ID to check for pending verification workflow

    Returns:
        The pending verification workflow record, or None if no pending workflow
    """
    import src.services.workflow_service

    workflow_type = src.services.workflow_service.WorkflowType.TASK_VERIFICATION.value
    workflow_status = src.services.workflow_service.WorkflowStatus.PENDING.value

    with span("verification_service.get_pending_verification_workflow"):
        filter_query = (
            f'type = "{workflow_type}" && target_id = "{sanitize_param(chore_id)}" && status = "{workflow_status}"'
        )

        workflows = await db_client.list_records(
            collection="workflows",
            filter_query=filter_query,
            sort="created_at DESC",
            per_page=1,
        )

        return workflows[0] if workflows else None


async def get_pending_personal_verification_workflow(*, log_id: str) -> dict[str, Any] | None:
    """Get pending verification workflow for a personal chore log if one exists.

    Args:
        log_id: Personal chore log ID to check for pending verification workflow

    Returns:
        The pending verification workflow record, or None if no pending workflow
    """
    import src.services.workflow_service

    workflow_type = src.services.workflow_service.WorkflowType.TASK_VERIFICATION.value
    workflow_status = src.services.workflow_service.WorkflowStatus.PENDING.value

    with span("verification_service.get_pending_personal_verification_workflow"):
        filter_query = (
            f'type = "{workflow_type}" && target_id = "{sanitize_param(log_id)}" && status = "{workflow_status}"'
        )

        workflows = await db_client.list_records(
            collection="workflows",
            filter_query=filter_query,
            sort="created_at DESC",
            per_page=1,
        )

        return workflows[0] if workflows else None


async def request_verification(
    *,
    chore_id: str,
    claimer_user_id: str,
    notes: str = "",
    is_swap: bool = False,
) -> dict[str, Any]:
    """Request verification for a shared task claim.

    Transitions task to PENDING_VERIFICATION state and creates log entry.
    Supports Robin Hood Protocol swaps where one user takes over another's task.

    Args:
        chore_id: Task ID
        claimer_user_id: ID of user claiming completion
        notes: Optional notes about completion
        is_swap: True if this is a Robin Hood swap (one user doing another's task)

    Returns:
        Created workflow record

    Raises:
        ValueError: If task is not in TODO state
        db_client.RecordNotFoundError: If task not found
    """
    import src.services.notification_service
    import src.services.user_service
    import src.services.workflow_service
    from src.modules.tasks import service as task_service

    task = await db_client.get_record(collection="tasks", record_id=chore_id)
    original_assignee_id = task["assigned_to"]

    claimer = await src.services.user_service.get_user_by_id(user_id=claimer_user_id)

    await task_service.mark_pending_verification(chore_id=chore_id)

    metadata = {
        "is_swap": is_swap,
        "notes": notes,
    }

    workflow = await src.services.workflow_service.create_workflow(
        params=src.services.workflow_service.WorkflowCreateParams(
            workflow_type=src.services.workflow_service.WorkflowType.TASK_VERIFICATION,
            requester_user_id=claimer_user_id,
            requester_name=claimer.get("name", "Unknown"),
            target_id=chore_id,
            target_title=task.get("title", "Unknown"),
            metadata=metadata,
        )
    )

    log_data = {
        "task_id": chore_id,
        "user_id": claimer_user_id,
        "action": "claimed_completion",
        "notes": notes,
        "timestamp": datetime.now().isoformat(),
        "is_swap": is_swap,
        "original_assignee_id": original_assignee_id,
        "actual_completer_id": claimer_user_id,
    }

    log_record = await db_client.create_record(collection="task_logs", data=log_data)

    logger.info(
        "User %s requested verification for task %s (is_swap=%s)",
        claimer_user_id,
        chore_id,
        is_swap,
    )

    try:
        await src.services.notification_service.send_verification_request(
            log_id=log_record["id"],
            task_id=chore_id,
            claimer_user_id=claimer_user_id,
        )
    except Exception:
        logger.exception(
            "Failed to send verification notifications for task %s",
            chore_id,
        )

    return workflow


async def verify_chore(
    *,
    task_id: str,
    verifier_user_id: str,
    decision: VerificationDecision,
    reason: str = "",
) -> dict[str, Any]:
    """Verify or reject a task completion claim.

    Business rule: Verifier cannot be original claimer (enforced by workflow_service).

    If APPROVE: Transitions task to COMPLETED and updates deadline.
    If REJECT: Transitions task to TODO.

    Args:
        task_id: Task ID
        verifier_user_id: ID of user performing verification
        decision: APPROVE or REJECT
        reason: Optional reason for decision

    Returns:
        Updated task record

    Raises:
        ValueError: If no pending verification workflow exists or self-verification attempted
        KeyError: If task not found
    """
    import src.modules.tasks.analytics as analytics_service
    import src.services.user_service
    import src.services.workflow_service
    from src.modules.tasks import service as task_service

    pending_workflow = await get_pending_verification_workflow(chore_id=task_id)
    if not pending_workflow:
        msg = f"No pending verification request for task {task_id}"
        raise ValueError(msg)

    verifier = await src.services.user_service.get_user_by_id(user_id=verifier_user_id)

    workflow_decision = (
        src.services.workflow_service.WorkflowStatus.APPROVED
        if decision == VerificationDecision.APPROVE
        else src.services.workflow_service.WorkflowStatus.REJECTED
    )

    await src.services.workflow_service.resolve_workflow(
        workflow_id=pending_workflow["id"],
        resolver_user_id=verifier_user_id,
        resolver_name=verifier.get("name", "Unknown"),
        decision=workflow_decision,
        reason=reason,
    )

    claim_logs = await db_client.list_records(
        collection="task_logs",
        filter_query=f'task_id = "{sanitize_param(task_id)}" && action = "claimed_completion"',
        sort="timestamp DESC",
        per_page=1,
    )

    if claim_logs:
        claim_log = claim_logs[0]

        await db_client.update_record(
            collection="task_logs",
            record_id=claim_log["id"],
            data={
                "verification_status": "VERIFIED" if decision == VerificationDecision.APPROVE else "REJECTED",
                "verifier_id": verifier_user_id,
                "verifier_feedback": reason,
            },
        )

    if decision == VerificationDecision.APPROVE:
        updated_task = await task_service.complete_chore(chore_id=task_id)
        logger.info(
            "User %s approved task %s",
            verifier_user_id,
            task_id,
        )
        await analytics_service.invalidate_leaderboard_cache()
    else:
        updated_task = await task_service.reset_chore_to_todo(chore_id=task_id)
        logger.info(
            "User %s rejected task %s",
            verifier_user_id,
            task_id,
        )
        await analytics_service.invalidate_leaderboard_cache()

    return updated_task


async def get_pending_verifications(*, user_id: str | None = None) -> list[dict[str, Any]]:
    """Get tasks pending verification.

    Args:
        user_id: Optional filter to exclude tasks claimed by this user

    Returns:
        List of tasks in PENDING_VERIFICATION state
    """
    from src.modules.tasks import service as task_service

    with span("verification_service.get_pending_verifications"):
        tasks = await task_service.get_chores(state=TaskState.PENDING_VERIFICATION)

        if user_id:
            user_claimed_task_ids: set[str] = set()
            for batch_start in range(0, len(tasks), CHORE_ID_BATCH_SIZE):
                batch_ids = tasks[batch_start : batch_start + CHORE_ID_BATCH_SIZE]
                task_id_conditions = " || ".join([f'task_id = "{sanitize_param(task["id"])}"' for task in batch_ids])

                page = 1
                while True:
                    logs = await db_client.list_records(
                        collection="task_logs",
                        filter_query=(
                            f'action = "claimed_completion" && user_id = "{sanitize_param(user_id)}" && ({task_id_conditions})'  # noqa: E501
                        ),
                        sort="timestamp DESC",
                        per_page=LOGS_PAGE_SIZE,
                        page=page,
                    )

                    for log in logs:
                        if (task_id := log.get("task_id")) and task_id not in user_claimed_task_ids:
                            user_claimed_task_ids.add(task_id)

                    if len(logs) < LOGS_PAGE_SIZE:
                        break

                    page += 1

            filtered_tasks = []
            for task in tasks:
                if task["id"] not in user_claimed_task_ids:
                    filtered_tasks.append(task)

            return filtered_tasks

        return tasks


async def log_personal_task(
    *,
    task_id: str,
    owner_id: str,
    notes: str = "",
) -> dict[str, Any]:
    """Log completion of a personal task.

    If task has accountability partner, creates PENDING log.
    If self-verified, creates SELF_VERIFIED log.

    Args:
        task_id: Personal task ID
        owner_id: Owner ID (for validation)
        notes: Optional notes about completion

    Returns:
        Created log record
    """
    import src.services.notification_service
    import src.services.user_service
    import src.services.workflow_service

    task = await db_client.get_record(collection="tasks", record_id=task_id)

    if task.get("owner_id") != owner_id:
        raise PermissionError(f"Task does not belong to owner {owner_id}")

    partner_id = task.get("accountability_partner_id")
    verification_status = "PENDING" if partner_id else "SELF_VERIFIED"

    log_data = {
        "task_id": task_id,
        "user_id": owner_id,
        "action": "claimed_completion",
        "notes": notes,
        "timestamp": datetime.now().isoformat(),
        "verification_status": verification_status,
        "actual_completer_id": owner_id,
    }

    log_record = await db_client.create_record(collection="task_logs", data=log_data)

    logger.info(
        "Logged personal task '%s' for %s",
        task["title"],
        owner_id,
    )

    if verification_status == "PENDING" and partner_id:
        try:
            await src.services.user_service.get_user_by_id(user_id=partner_id)

            owner = await src.services.user_service.get_user_by_id(user_id=owner_id)
            owner_name = owner.get("name", "Unknown")

            workflow = await src.services.workflow_service.create_workflow(
                params=src.services.workflow_service.WorkflowCreateParams(
                    workflow_type=src.services.workflow_service.WorkflowType.TASK_VERIFICATION,
                    requester_user_id=owner_id,
                    requester_name=owner_name,
                    target_id=log_record["id"],
                    target_title=task["title"],
                )
            )

            partner = await src.services.user_service.get_user_by_id(user_id=partner_id)
            partner_phone = partner.get("phone", "") if partner else ""

            await src.services.notification_service.send_personal_verification_request(
                log_id=log_record["id"],
                task_title=task["title"],
                owner_name=owner_name,
                partner_phone=partner_phone,
            )

            logger.info(
                "Created personal verification workflow %s for log %s",
                workflow["id"],
                log_record["id"],
            )

        except Exception:
            logger.exception(
                "Failed to send verification request notification for task %s",
                task_id,
            )

    return log_record


async def verify_personal_task(
    *,
    log_id: str,
    verifier_id: str,
    approved: bool,
    feedback: str = "",
) -> dict[str, Any]:
    """Verify or reject a personal task completion.

    Args:
        log_id: Personal task log ID
        verifier_id: Accountability partner ID
        approved: True to approve, False to reject
        feedback: Optional feedback message

    Returns:
        Updated log record
    """
    import src.modules.tasks.analytics as analytics_service
    import src.services.user_service
    import src.services.workflow_service
    from src.modules.tasks import service as task_service

    log = await db_client.get_record(collection="task_logs", record_id=log_id)
    task_id = log["task_id"]

    task = await db_client.get_record(collection="tasks", record_id=task_id)

    if task.get("owner_id") == verifier_id:
        raise PermissionError("Only accountability partner can verify this task")

    pending_workflow = await get_pending_personal_verification_workflow(log_id=log_id)
    if not pending_workflow:
        msg = f"No pending verification request for log {log_id}"
        raise ValueError(msg)

    verifier = await src.services.user_service.get_user_by_id(user_id=verifier_id)
    verifier_name = verifier.get("name", "Unknown") if verifier else "Unknown"

    await src.services.workflow_service.resolve_workflow(
        workflow_id=pending_workflow["id"],
        resolver_user_id=verifier_id,
        resolver_name=verifier_name,
        decision=src.services.workflow_service.WorkflowStatus.APPROVED
        if approved
        else src.services.workflow_service.WorkflowStatus.REJECTED,
        reason=feedback,
    )

    updated_log = await db_client.update_record(
        collection="task_logs",
        record_id=log_id,
        data={
            "verification_status": "VERIFIED" if approved else "REJECTED",
            "verifier_id": verifier_id,
            "verifier_feedback": feedback,
        },
    )

    if approved:
        await task_service.complete_chore(chore_id=task_id)
        logger.info(
            "User %s verified personal task %s",
            verifier_id,
            task_id,
        )
        await analytics_service.invalidate_leaderboard_cache()
    else:
        await task_service.reset_chore_to_todo(chore_id=task_id)
        logger.info(
            "User %s rejected personal task %s",
            verifier_id,
            task_id,
        )
        await analytics_service.invalidate_leaderboard_cache()

    return updated_log


async def get_pending_partner_verifications(
    *,
    partner_id: str,
) -> list[dict[str, Any]]:
    """Get all pending verifications for an accountability partner.

    Args:
        partner_id: Accountability partner user ID

    Returns:
        List of enriched log records with task details
    """
    import src.services.user_service

    with span("verification_service.get_pending_partner_verifications"):
        partner = await src.services.user_service.get_user_by_id(user_id=partner_id)
        if not partner:
            return []

        logs = await db_client.list_records(
            collection="task_logs",
            filter_query='action = "claimed_completion" && verification_status = "PENDING"',
            sort="timestamp DESC",
        )

        partner_user = await src.services.user_service.get_user_by_id(user_id=partner_id)

        enriched_logs = []
        for log in logs:
            task = await db_client.get_record(
                collection="tasks",
                record_id=log["task_id"],
            )

            enriched_log = {
                "id": log["id"],
                "task_id": log["task_id"],
                "owner_phone": partner_user.get("phone", "") if partner_user else "",
                "completed_at": log.get("timestamp", ""),
                "verification_status": log.get("verification_status", "PENDING"),
                "accountability_partner_phone": partner_user.get("phone", "") if partner_user else "",
                "partner_feedback": log.get("verifier_feedback", ""),
                "notes": log.get("notes", ""),
                "chore_title": task.get("title", ""),
                "owner_phone_display": partner_user.get("phone", "") if partner_user else "",
            }

            enriched_logs.append(enriched_log)

        return enriched_logs


async def get_personal_stats(
    *,
    owner_id: str,
    period_days: int = 30,
) -> dict[str, Any]:
    """Get personal task statistics for a user.

    Args:
        owner_id: Owner user ID
        period_days: Number of days to look back (default: 30)

    Returns:
        Personal task statistics dictionary
    """

    cutoff_date = datetime.now() - timedelta(days=period_days)

    active_tasks = await db_client.list_records(
        collection="tasks",
        filter_query=(f'owner_id = "{sanitize_param(owner_id)}" && scope = "personal" && current_state != "ARCHIVED"'),
    )

    completions_filter = (
        f'user_id = "{sanitize_param(owner_id)}" '
        f'&& timestamp >= "{cutoff_date.isoformat()}" '
        f'&& (verification_status = "SELF_VERIFIED" || verification_status = "VERIFIED")'
    )

    pending_filter = f'user_id = "{sanitize_param(owner_id)}" && verification_status = "PENDING"'

    completions = await db_client.list_records(
        collection="task_logs",
        filter_query=completions_filter,
    )

    pending = await db_client.list_records(
        collection="task_logs",
        filter_query=pending_filter,
    )

    total_tasks = len(active_tasks)
    completions_count = len(completions)
    completion_rate = (completions_count / total_tasks * 100) if total_tasks > 0 else 0.0

    return {
        "total_chores": total_tasks,
        "completions_this_period": completions_count,
        "pending_verifications": len(pending),
        "completion_rate": completion_rate,
        "period_days": period_days,
    }
