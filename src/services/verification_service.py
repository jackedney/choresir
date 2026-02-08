"""Verification service for chore completion verification."""

import logging
from datetime import datetime
from enum import StrEnum
from typing import Any

from src.core import db_client
from src.core.logging import span
from src.domain.chore import ChoreState
from src.services import (
    analytics_service,
    chore_service,
    conflict_service,
    notification_service,
    user_service,
    workflow_service,
)


logger = logging.getLogger(__name__)

# Constants
LOGS_PAGE_SIZE = 500
CHORE_ID_BATCH_SIZE = 100  # PocketBase limits: 200 filter expressions, 3500 char filter strings


class VerificationDecision(StrEnum):
    """Verification decision enum."""

    APPROVE = "APPROVE"
    REJECT = "REJECT"


async def get_pending_verification_workflow(*, chore_id: str) -> dict[str, Any] | None:
    """Get the pending verification workflow for a chore if one exists.

    Args:
        chore_id: Chore ID to check for pending verification workflow

    Returns:
        The pending verification workflow record, or None if no pending workflow
    """
    with span("verification_service.get_pending_verification_workflow"):
        filter_query = (
            f'type = "{workflow_service.WorkflowType.CHORE_VERIFICATION.value}" && '
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


async def request_verification(
    *,
    chore_id: str,
    claimer_user_id: str,
    notes: str = "",
    is_swap: bool = False,
) -> dict[str, Any]:
    """Request verification for a chore claim.

    Transitions chore to PENDING_VERIFICATION state and creates log entry.
    Supports Robin Hood Protocol swaps where one user takes over another's chore.

    Args:
        chore_id: Chore ID
        claimer_user_id: ID of user claiming completion
        notes: Optional notes about completion
        is_swap: True if this is a Robin Hood swap (one user doing another's chore)

    Returns:
        Created workflow record

    Raises:
        chore_service.InvalidStateTransitionError: If chore is not in TODO state
        db_client.RecordNotFoundError: If chore not found
    """
    with span("verification_service.request_verification"):
        # Get chore details to determine original assignee
        chore = await db_client.get_record(collection="chores", record_id=chore_id)
        original_assignee_id = chore["assigned_to"]

        # Get claimer name for workflow
        claimer = await user_service.get_user_by_id(user_id=claimer_user_id)

        # Transition chore to pending verification
        await chore_service.mark_pending_verification(chore_id=chore_id)

        # Create verification workflow with metadata
        metadata = {
            "is_swap": is_swap,
            "notes": notes,
        }

        workflow = await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.CHORE_VERIFICATION,
                requester_user_id=claimer_user_id,
                requester_name=claimer.get("name", "Unknown"),
                target_id=chore_id,
                target_title=chore.get("title", "Unknown"),
                metadata=metadata,
            )
        )

        # Create log entry with Robin Hood tracking (audit trail)
        log_data = {
            "chore_id": chore_id,
            "user_id": claimer_user_id,
            "action": "claimed_completion",
            "notes": notes,
            "timestamp": datetime.now().isoformat(),
            "is_swap": is_swap,
            "original_assignee_id": original_assignee_id,
            "actual_completer_id": claimer_user_id,
        }

        log_record = await db_client.create_record(collection="logs", data=log_data)

        logger.info(
            "User %s requested verification for chore %s (is_swap=%s)",
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
                "Failed to send verification notifications for chore %s",
                chore_id,
            )

        return workflow


async def verify_chore(
    *,
    chore_id: str,
    verifier_user_id: str,
    decision: VerificationDecision,
    reason: str = "",
) -> dict[str, Any]:
    """Verify or reject a chore completion claim.

    Business rule: Verifier cannot be the original claimer (enforced by workflow_service).

    If APPROVE: Transitions chore to COMPLETED and updates deadline.
    If REJECT: Transitions chore to CONFLICT and initiates voting.

    Args:
        chore_id: Chore ID
        verifier_user_id: ID of user performing verification
        decision: APPROVE or REJECT
        reason: Optional reason for the decision

    Returns:
        Updated chore record

    Raises:
        ValueError: If no pending verification workflow exists or self-verification attempted
        KeyError: If chore not found
    """
    with span("verification_service.verify_chore"):
        # Get pending verification workflow
        pending_workflow = await get_pending_verification_workflow(chore_id=chore_id)
        if not pending_workflow:
            msg = f"No pending verification request for chore {chore_id}"
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
            # Convert workflow self-approval error to PermissionError
            if "Cannot approve own workflow" in str(e):
                msg = "User cannot verify their own chore claim"
                raise PermissionError(msg) from e
            raise

        # Create verification log
        action = f"{decision.lower()}_verification"
        log_data = {
            "chore_id": chore_id,
            "user_id": verifier_user_id,
            "action": action,
            "notes": reason,
            "timestamp": datetime.now().isoformat(),
        }
        await db_client.create_record(collection="logs", data=log_data)

        # Process decision
        if decision == VerificationDecision.APPROVE:
            updated_chore = await chore_service.complete_chore(chore_id=chore_id)
            logger.info(
                "User %s approved chore %s",
                verifier_user_id,
                chore_id,
            )
            # Invalidate leaderboard cache since completion counts changed
            await analytics_service.invalidate_leaderboard_cache()
        else:  # REJECT
            updated_chore = await chore_service.move_to_conflict(chore_id=chore_id)
            logger.info(
                "User %s rejected chore %s - moving to conflict",
                verifier_user_id,
                chore_id,
            )
            # Initiate voting process
            await conflict_service.initiate_vote(chore_id=chore_id)
            # Invalidate leaderboard cache in case rejection affects counts
            await analytics_service.invalidate_leaderboard_cache()

        return updated_chore


async def get_pending_verifications(*, user_id: str | None = None) -> list[dict[str, Any]]:
    """Get chores pending verification.

    Args:
        user_id: Optional filter to exclude chores claimed by this user

    Returns:
        List of chores in PENDING_VERIFICATION state
    """
    with span("verification_service.get_pending_verifications"):
        # Get all pending verification chores
        chores = await chore_service.get_chores(state=ChoreState.PENDING_VERIFICATION)

        # If user_id provided, filter out chores they claimed
        if user_id:
            if not chores:
                return []

            # Build filter query for logs (action="claimed_completion" && chore_id in [...])
            # Batch chore_ids to stay within PocketBase limits (200 filter expressions, 3500 char filter strings)
            chore_ids = [c["id"] for c in chores]
            sanitized_user_id = db_client.sanitize_param(user_id)

            # Fetch logs in batches to avoid exceeding PocketBase filter limits
            user_claimed_chore_ids: set[str] = set()
            for batch_start in range(0, len(chore_ids), CHORE_ID_BATCH_SIZE):
                batch_ids = chore_ids[batch_start : batch_start + CHORE_ID_BATCH_SIZE]
                chore_id_conditions = " || ".join(
                    [f'chore_id = "{db_client.sanitize_param(cid)}"' for cid in batch_ids]
                )
                filter_query = (
                    f'action = "claimed_completion" && user_id = "{sanitized_user_id}" && ({chore_id_conditions})'
                )

                # Paginate within each batch to get all matching logs
                page = 1
                while True:
                    logs = await db_client.list_records(
                        collection="logs",
                        filter_query=filter_query,
                        sort="-timestamp",
                        per_page=LOGS_PAGE_SIZE,
                        page=page,
                    )
                    # Accumulate chore IDs from this page
                    for log in logs:
                        if chore_id := log.get("chore_id"):
                            user_claimed_chore_ids.add(chore_id)
                    # Stop if we got fewer than a full page (no more results)
                    if len(logs) < LOGS_PAGE_SIZE:
                        break
                    page += 1

            filtered_chores = []
            for chore in chores:
                # Exclude if this user claimed it
                if chore["id"] not in user_claimed_chore_ids:
                    filtered_chores.append(chore)
            return filtered_chores

        return chores
