"""Verification service for chore completion verification."""

import logging
from datetime import datetime
from enum import StrEnum
from typing import Any

from src.core import db_client
from src.core.logging import span
from src.domain.chore import ChoreState
from src.services import analytics_service, chore_service, conflict_service, notification_service


logger = logging.getLogger(__name__)

# Constants
LOGS_PAGE_SIZE = 500


class VerificationDecision(StrEnum):
    """Verification decision enum."""

    APPROVE = "APPROVE"
    REJECT = "REJECT"


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
        Created log record

    Raises:
        chore_service.InvalidStateTransitionError: If chore is not in TODO state
        db_client.RecordNotFoundError: If chore not found
    """
    with span("verification_service.request_verification"):
        # Get chore details to determine original assignee
        chore = await db_client.get_record(collection="chores", record_id=chore_id)
        original_assignee_id = chore["assigned_to"]

        # Transition chore to pending verification
        await chore_service.mark_pending_verification(chore_id=chore_id)

        # Create log entry with Robin Hood tracking
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

        return log_record


async def verify_chore(
    *,
    chore_id: str,
    verifier_user_id: str,
    decision: VerificationDecision,
    reason: str = "",
) -> dict[str, Any]:
    """Verify or reject a chore completion claim.

    Business rule: Verifier cannot be the original claimer.

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
        PermissionError: If verifier is the claimer
        db_client.RecordNotFoundError: If chore or log not found
    """
    with span("verification_service.verify_chore"):
        # Guard: Get the latest claim log to find the claimer (sorted by timestamp for determinism)
        # Use a specific filter query instead of fetching all logs (DoS prevention)
        filter_query = f'chore_id = "{db_client.sanitize_param(chore_id)}" && action = "claimed_completion"'
        claim_logs = await db_client.list_records(
            collection="logs",
            filter_query=filter_query,
            sort="-timestamp",
            per_page=1,
        )

        if not claim_logs:
            msg = f"No claim log found for chore {chore_id}"
            raise KeyError(msg)

        latest_claim = claim_logs[0]
        claimer_user_id = latest_claim["user_id"]

        # Guard: Prevent self-verification
        if verifier_user_id == claimer_user_id:
            msg = f"User {verifier_user_id} cannot verify their own chore claim"
            logger.warning(msg)
            raise PermissionError(msg)

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
                "User %s approved chore %s (claimed by %s)",
                verifier_user_id,
                chore_id,
                claimer_user_id,
            )
            # Invalidate leaderboard cache since completion counts changed
            await analytics_service.invalidate_leaderboard_cache()
        else:  # REJECT
            updated_chore = await chore_service.move_to_conflict(chore_id=chore_id)
            logger.info(
                "User %s rejected chore %s (claimed by %s) - moving to conflict",
                verifier_user_id,
                chore_id,
                claimer_user_id,
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
            chore_ids = [c["id"] for c in chores]
            chore_id_conditions = " || ".join([f'chore_id = "{db_client.sanitize_param(cid)}"' for cid in chore_ids])
            # Optimization: Filter by user_id as well to only find claims by THIS user
            # This ensures we don't miss self-claims due to pagination if there are many other claims
            sanitized_user_id = db_client.sanitize_param(user_id)
            filter_query = (
                f'action = "claimed_completion" && user_id = "{sanitized_user_id}" && ({chore_id_conditions})'
            )

            # Fetch all logs matching these chores AND this user (paginate to get all)
            user_claimed_chore_ids: set[str] = set()
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
