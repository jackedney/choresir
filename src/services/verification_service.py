"""Unified verification service for task completion verification.

Handles both peer verification (scope=shared) and partner verification (scope=personal).
Works against task_logs table.
"""

import logging
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from pydantic import ValidationError

from src.core import db_client
from src.core.db_client import sanitize_param
from src.core.logging import span
from src.domain.task import TaskState
from src.models.service_models import PersonalChoreLog, PersonalChoreStatistics
from src.services import (
    analytics_service,
    chore_service,
    notification_service,
    user_service,
    workflow_service,
)


logger = logging.getLogger(__name__)

# Constants
LOGS_PAGE_SIZE = 500
CHORE_ID_BATCH_SIZE = 100  # Batch size for filter queries to avoid issues


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
    with span("verification_service.get_pending_verification_workflow"):
        filter_query = (
            f'type = "{workflow_service.WorkflowType.TASK_VERIFICATION.value}" && '
            f'target_id = "{db_client.sanitize_param(chore_id)}" && '
            f'status = "{workflow_service.WorkflowStatus.PENDING.value}"'
        )

        workflows = await db_client.list_records(
            collection="workflows",
            filter_query=filter_query,
            sort="-created_at",
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
    with span("verification_service.get_pending_personal_verification_workflow"):
        filter_query = (
            f'type = "{workflow_service.WorkflowType.TASK_VERIFICATION.value}" && '
            f'target_id = "{sanitize_param(log_id)}" && '
            f'status = "{workflow_service.WorkflowStatus.PENDING.value}"'
        )

        workflows = await db_client.list_records(
            collection="workflows",
            filter_query=filter_query,
            sort="-created_at",
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
        chore_service.InvalidStateTransitionError: If task is not in TODO state
        db_client.RecordNotFoundError: If task not found
    """
    with span("verification_service.request_verification"):
        # Get task details to determine original assignee
        task = await db_client.get_record(collection="tasks", record_id=chore_id)
        original_assignee_id = task["assigned_to"]

        # Get claimer name for workflow
        claimer = await user_service.get_user_by_id(user_id=claimer_user_id)

        # Transition task to pending verification
        await chore_service.mark_pending_verification(chore_id=chore_id)

        # Create verification workflow with metadata
        metadata = {
            "is_swap": is_swap,
            "notes": notes,
        }

        workflow = await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.TASK_VERIFICATION,
                requester_user_id=claimer_user_id,
                requester_name=claimer.get("name", "Unknown"),
                target_id=chore_id,
                target_title=task.get("title", "Unknown"),
                metadata=metadata,
            )
        )

        # Create log entry with Robin Hood tracking (audit trail)
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

        # Send verification request notifications to household members
        try:
            await notification_service.send_verification_request(
                log_id=log_record["id"],
                chore_id=chore_id,
                claimer_user_id=claimer_user_id,
            )
        except Exception:
            # Log with full traceback for debugging
            # Note: Notification failure doesn't fail the claim itself
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
    with span("verification_service.verify_chore"):
        # Get pending verification workflow
        pending_workflow = await get_pending_verification_workflow(chore_id=task_id)
        if not pending_workflow:
            msg = f"No pending verification request for task {task_id}"
            raise ValueError(msg)

        # Get verifier name for workflow resolution
        verifier = await user_service.get_user_by_id(user_id=verifier_user_id)

        # Resolve workflow (self-verification check is handled by workflow_service)
        workflow_decision = (
            workflow_service.WorkflowStatus.APPROVED
            if decision == VerificationDecision.APPROVE
            else workflow_service.WorkflowStatus.REJECTED
        )

        try:
            await workflow_service.resolve_workflow(
                workflow_id=pending_workflow["id"],
                resolver_user_id=verifier_user_id,
                resolver_name=verifier.get("name", "Unknown"),
                decision=workflow_decision,
                reason=reason,
            )
        except ValueError as e:
            if "Cannot approve own workflow" in str(e):
                msg = "User cannot verify their own task claim"
                raise PermissionError(msg) from e
            raise

        # Find the claim log entry for verification details
        claim_logs = await db_client.list_records(
            collection="task_logs",
            filter_query=f'task_id = "{db_client.sanitize_param(task_id)}" && action = "claimed_completion"',
            sort="-timestamp",
            per_page=1,
        )

        # Update claim log with verification details
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

        # Process decision
        if decision == VerificationDecision.APPROVE:
            updated_task = await chore_service.complete_chore(chore_id=task_id)
            logger.info(
                "User %s approved task %s",
                verifier_user_id,
                task_id,
            )
            await analytics_service.invalidate_leaderboard_cache()
        else:
            updated_task = await chore_service.reset_chore_to_todo(chore_id=task_id)
            logger.info(
                "User %s rejected task %s - returning to TODO",
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
    with span("verification_service.get_pending_verifications"):
        # Get all pending verification tasks
        tasks = await chore_service.get_chores(state=TaskState.PENDING_VERIFICATION)

        # If user_id provided, filter out tasks they claimed
        if user_id:
            if not tasks:
                return []

            # Build filter query for logs (action="claimed_completion" && task_id in [...])
            task_ids = [t["id"] for t in tasks]
            sanitized_user_id = db_client.sanitize_param(user_id)

            # Fetch logs in batches to avoid issues with large filter queries
            user_claimed_task_ids: set[str] = set()
            for batch_start in range(0, len(task_ids), CHORE_ID_BATCH_SIZE):
                batch_ids = task_ids[batch_start : batch_start + CHORE_ID_BATCH_SIZE]
                task_id_conditions = " || ".join([f'task_id = "{db_client.sanitize_param(tid)}"' for tid in batch_ids])
                filter_query = (
                    f'action = "claimed_completion" && user_id = "{sanitized_user_id}" && ({task_id_conditions})'
                )

                # Paginate within each batch to get all matching logs
                page = 1
                while True:
                    logs = await db_client.list_records(
                        collection="task_logs",
                        filter_query=filter_query,
                        sort="-timestamp",
                        per_page=LOGS_PAGE_SIZE,
                        page=page,
                    )
                    # Accumulate task IDs from this page
                    for log in logs:
                        if task_id := log.get("task_id"):
                            user_claimed_task_ids.add(task_id)
                    # Stop if we got fewer than a full page (no more results)
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
) -> PersonalChoreLog:
    """Log completion of a personal task.

    If task has accountability partner, creates PENDING log.
    If self-verified, creates SELF_VERIFIED log.

    Args:
        task_id: Personal task ID
        owner_id: Owner ID (for validation)
        notes: Optional notes about completion

    Returns:
        Created PersonalChoreLog object

    Raises:
        KeyError: If task not found
        PermissionError: If task doesn't belong to owner
    """
    with span("verification_service.log_personal_task"):
        # Get task and validate ownership
        task = await db_client.get_record(collection="tasks", record_id=task_id)

        # Validate ownership
        if task.get("owner_id") != owner_id:
            raise PermissionError(f"Task does not belong to owner {owner_id}")

        # Determine verification status
        partner_id = task.get("accountability_partner_id")
        verification_status = "PENDING" if partner_id else "SELF_VERIFIED"

        # Create log entry
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
            "Logged personal task '%s' for %s (status: %s)",
            task["title"],
            owner_id,
            verification_status,
        )

        # Send verification request notification if pending
        if verification_status == "PENDING" and partner_id:
            try:
                # Get owner details for notification and workflow
                owner = await user_service.get_user_by_id(user_id=owner_id)
                owner_name = owner.get("name", "Unknown")

                # Create workflow for personal verification
                workflow = await workflow_service.create_workflow(
                    params=workflow_service.WorkflowCreateParams(
                        workflow_type=workflow_service.WorkflowType.TASK_VERIFICATION,
                        requester_user_id=owner_id,
                        requester_name=owner_name,
                        target_id=log_record["id"],
                        target_title=task["title"],
                    )
                )

                # Get partner details
                partner = await user_service.get_user_by_id(user_id=partner_id)
                partner_phone = partner.get("phone", "") if partner else ""

                await notification_service.send_personal_verification_request(
                    log_id=log_record["id"],
                    chore_title=task["title"],
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

        # Build PersonalChoreLog response (enriched with task details)
        owner = await user_service.get_user_by_id(user_id=owner_id)
        owner_phone = owner.get("phone", "") if owner else ""
        partner_phone = ""
        if partner_id:
            partner = await user_service.get_user_by_id(user_id=partner_id)
            partner_phone = partner.get("phone", "") if partner else ""

        return PersonalChoreLog(
            id=log_record["id"],
            personal_chore_id=task_id,
            owner_phone=owner_phone,
            completed_at=log_record["timestamp"],
            verification_status=verification_status,
            accountability_partner_phone=partner_phone,
            partner_feedback="",
            notes=notes,
            created=log_record["created"],
            updated=log_record["updated"],
            chore_title=task["title"],
            owner_phone_display=owner_phone,
        )


async def verify_personal_task(
    *,
    log_id: str,
    verifier_id: str,
    approved: bool,
    feedback: str = "",
) -> PersonalChoreLog:
    """Verify or reject a personal task completion.

    Args:
        log_id: Personal task log ID
        verifier_id: Accountability partner ID
        approved: True to approve, False to reject
        feedback: Optional feedback message

    Returns:
        Updated PersonalChoreLog object

    Raises:
        KeyError: If log not found
        PermissionError: If verifier is not accountability partner
        ValueError: If log not in pending state or self-verification attempted
    """
    with span("verification_service.verify_personal_task"):
        # Get log record
        log_record = await db_client.get_record(
            collection="task_logs",
            record_id=log_id,
        )

        # Validate log is in PENDING state
        if log_record.get("verification_status") != "PENDING":
            raise ValueError(f"Cannot verify log in state {log_record.get('verification_status')}")

        # Get pending workflow
        pending_workflow = await get_pending_personal_verification_workflow(log_id=log_id)
        if not pending_workflow:
            msg = f"No pending verification workflow for log {log_id}"
            raise ValueError(msg)

        # Get task to get partner_id
        task = await db_client.get_record(
            collection="tasks",
            record_id=log_record["task_id"],
        )

        # Get verifier details
        verifier = await user_service.get_user_by_id(user_id=verifier_id)
        verifier_name = verifier.get("name", "Unknown") if verifier else "Unknown"
        verifier_phone = verifier.get("phone", "") if verifier else ""

        # Validate verifier is the accountability partner
        expected_partner_id = task.get("accountability_partner_id")
        if verifier_id != expected_partner_id:
            raise PermissionError("Only accountability partner can verify this task")

        # Resolve workflow
        workflow_decision = (
            workflow_service.WorkflowStatus.APPROVED if approved else workflow_service.WorkflowStatus.REJECTED
        )

        await workflow_service.resolve_workflow(
            workflow_id=pending_workflow["id"],
            resolver_user_id=verifier_id,
            resolver_name=verifier_name,
            decision=workflow_decision,
            reason=feedback,
        )

        # Update verification status
        new_status = "VERIFIED" if approved else "REJECTED"
        updated_log = await db_client.update_record(
            collection="task_logs",
            record_id=log_id,
            data={
                "verification_status": new_status,
                "verifier_id": verifier_id,
                "verifier_feedback": feedback,
            },
        )

        logger.info(
            "Personal task log %s %s by %s",
            log_id,
            "approved" if approved else "rejected",
            verifier_id,
        )

        # Send result notification to owner
        try:
            owner = await user_service.get_user_by_id(user_id=log_record["user_id"])
            owner_phone = owner.get("phone", "") if owner else ""

            await notification_service.send_personal_verification_result(
                chore_title=task["title"],
                owner_phone=owner_phone,
                verifier_name=verifier_name,
                approved=approved,
                feedback=feedback,
            )
        except Exception:
            logger.exception(
                "Failed to send verification result notification for log %s",
                log_id,
            )

        # Build PersonalChoreLog response
        owner = await user_service.get_user_by_id(user_id=updated_log["user_id"])
        owner_phone = owner.get("phone", "") if owner else ""
        partner_phone = verifier_phone

        return PersonalChoreLog(
            id=updated_log["id"],
            personal_chore_id=updated_log["task_id"],
            owner_phone=owner_phone,
            completed_at=updated_log.get("timestamp", ""),
            verification_status=new_status,
            accountability_partner_phone=partner_phone,
            partner_feedback=feedback,
            notes=updated_log.get("notes", ""),
            created=updated_log["created"],
            updated=updated_log["updated"],
            chore_title=task["title"],
            owner_phone_display=owner_phone,
        )


async def get_pending_partner_verifications(
    *,
    partner_id: str,
) -> list[PersonalChoreLog]:
    """Get all pending verifications for an accountability partner.

    Args:
        partner_id: Accountability partner user ID

    Returns:
        List of PersonalChoreLog objects with enriched task details
    """
    with span("verification_service.get_pending_partner_verifications"):
        # Get partner details to get phone
        partner = await user_service.get_user_by_id(user_id=partner_id)
        if not partner:
            return []

        # Get tasks where this user is the accountability partner
        tasks = await db_client.list_records(
            collection="tasks",
            filter_query=f'accountability_partner_id = "{db_client.sanitize_param(partner_id)}" && scope = "personal"',
        )

        # Get pending logs for these tasks
        task_ids = [t["id"] for t in tasks]
        if not task_ids:
            return []

        # Build filter query for task_logs
        task_id_conditions = " || ".join([f'task_id = "{db_client.sanitize_param(tid)}"' for tid in task_ids])
        filter_query = f'action = "claimed_completion" && verification_status = "PENDING" && ({task_id_conditions})'

        logs = await db_client.list_records(
            collection="task_logs",
            filter_query=filter_query,
            sort="-timestamp",
        )

        # Enrich with task details and convert to models
        enriched_logs = []
        for log in logs:
            try:
                task = await db_client.get_record(
                    collection="tasks",
                    record_id=log["task_id"],
                )
                # Get owner details
                owner = await user_service.get_user_by_id(user_id=log["user_id"])
                owner_phone = owner.get("phone", "") if owner else ""
                partner_phone = partner.get("phone", "")

                enriched_log = PersonalChoreLog(
                    id=log["id"],
                    personal_chore_id=log["task_id"],
                    owner_phone=owner_phone,
                    completed_at=log.get("timestamp", ""),
                    verification_status=log.get("verification_status", "PENDING"),
                    accountability_partner_phone=partner_phone,
                    partner_feedback=log.get("verifier_feedback", ""),
                    notes=log.get("notes", ""),
                    created=log["created"],
                    updated=log["updated"],
                    chore_title=task.get("title", ""),
                    owner_phone_display=owner_phone,
                )
                enriched_logs.append(enriched_log)
            except (KeyError, ValidationError) as e:
                logger.warning("Failed to process log %s: %s", log.get("id"), e)
                continue

        return enriched_logs


async def get_personal_stats(
    *,
    owner_id: str,
    period_days: int = 30,
) -> PersonalChoreStatistics:
    """Get personal task statistics for a user.

    Args:
        owner_id: Owner user ID
        period_days: Number of days to include (default: 30)

    Returns:
        PersonalChoreStatistics object with user's personal task metrics
    """
    with span("verification_service.get_personal_stats"):
        # Get all active personal tasks
        active_tasks = await db_client.list_records(
            collection="tasks",
            filter_query=(
                f'owner_id = "{db_client.sanitize_param(owner_id)}" && '
                f'scope = "personal" && current_state != "ARCHIVED"'
            ),
        )

        # Get completions in period
        cutoff_time = datetime.now() - timedelta(days=period_days)
        completions_filter = (
            f'user_id = "{db_client.sanitize_param(owner_id)}" '
            f'&& timestamp >= "{cutoff_time.isoformat()}" '
            f'&& (verification_status = "SELF_VERIFIED" || verification_status = "VERIFIED")'
        )

        completions = await db_client.list_records(
            collection="task_logs",
            filter_query=completions_filter,
        )

        # Get pending verifications
        pending_filter = f'user_id = "{db_client.sanitize_param(owner_id)}" && verification_status = "PENDING"'

        pending = await db_client.list_records(
            collection="task_logs",
            filter_query=pending_filter,
        )

        # Calculate completion rate
        total_tasks = len(active_tasks)
        completions_count = len(completions)
        completion_rate = (completions_count / total_tasks * 100) if total_tasks > 0 else 0

        return PersonalChoreStatistics(
            total_chores=total_tasks,
            completions_this_period=completions_count,
            pending_verifications=len(pending),
            completion_rate=round(completion_rate, 1),
            period_days=period_days,
        )


# Backwards compatibility aliases for personal verification functions
async def log_personal_chore(
    *,
    chore_id: str,
    owner_phone: str,
    notes: str = "",
) -> PersonalChoreLog:
    """Log a personal task completion (backwards compatibility wrapper)."""
    user = await user_service.get_user_by_phone(phone=owner_phone)
    if not user:
        raise KeyError(f"User with phone {owner_phone} not found")
    return await log_personal_task(
        task_id=chore_id,
        owner_id=user["id"],
        notes=notes,
    )


async def verify_personal_chore(
    *,
    log_id: str,
    verifier_phone: str,
    approved: bool,
    feedback: str = "",
) -> PersonalChoreLog:
    """Verify a personal task (backwards compatibility wrapper)."""
    user = await user_service.get_user_by_phone(phone=verifier_phone)
    if not user:
        raise KeyError(f"User with phone {verifier_phone} not found")
    return await verify_personal_task(
        log_id=log_id,
        verifier_id=user["id"],
        approved=approved,
        feedback=feedback,
    )


async def get_pending_partner_verifications_phone(
    *,
    partner_phone: str,
) -> list[PersonalChoreLog]:
    """Get pending partner verifications by phone (backwards compatibility wrapper)."""
    user = await user_service.get_user_by_phone(phone=partner_phone)
    if not user:
        return []
    return await get_pending_partner_verifications(partner_id=user["id"])


async def get_personal_stats_by_phone(
    *,
    owner_phone: str,
    period_days: int = 30,
) -> PersonalChoreStatistics:
    """Get personal stats by owner phone (backwards compatibility wrapper)."""
    user = await user_service.get_user_by_phone(phone=owner_phone)
    if not user:
        return PersonalChoreStatistics(
            total_chores=0,
            completions_this_period=0,
            pending_verifications=0,
            completion_rate=0.0,
            period_days=period_days,
        )
    return await get_personal_stats(
        owner_id=user["id"],
        period_days=period_days,
    )
