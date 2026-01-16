"""Verification service for chore completion verification."""

import logging
from datetime import datetime
from enum import StrEnum
from typing import Any

from src.core import db_client
from src.core.logging import span
from src.domain.chore import ChoreState
from src.services import chore_service


logger = logging.getLogger(__name__)


class VerificationDecision(StrEnum):
    """Verification decision enum."""

    APPROVE = "APPROVE"
    REJECT = "REJECT"


async def request_verification(
    *,
    chore_id: str,
    claimer_user_id: str,
    notes: str = "",
) -> dict[str, Any]:
    """Request verification for a chore claim.

    Transitions chore to PENDING_VERIFICATION state and creates log entry.

    Args:
        chore_id: Chore ID
        claimer_user_id: ID of user claiming completion
        notes: Optional notes about completion

    Returns:
        Created log record

    Raises:
        chore_service.InvalidStateTransitionError: If chore is not in TODO state
        db_client.RecordNotFoundError: If chore not found
    """
    with span("verification_service.request_verification"):
        # Transition chore to pending verification
        await chore_service.mark_pending_verification(chore_id=chore_id)

        # Create log entry
        log_data = {
            "chore_id": chore_id,
            "user_id": claimer_user_id,
            "action": f"claimed_completion: {notes}" if notes else "claimed_completion",
            "timestamp": datetime.now().isoformat(),
        }

        log_record = await db_client.create_record(collection="logs", data=log_data)

        logger.info(
            "User %s requested verification for chore %s",
            claimer_user_id,
            chore_id,
        )

        # Note: Notification system not yet implemented

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
        # Guard: Get the original claim log to find the claimer
        claim_logs = await db_client.list_records(
            collection="logs",
            filter_query=f'chore_id = "{chore_id}" && action ~ "claimed_completion"',
            sort="-created",  # Most recent first
            per_page=1,
        )

        if not claim_logs:
            msg = f"No claim log found for chore {chore_id}"
            raise db_client.RecordNotFoundError(msg)

        claimer_user_id = claim_logs[0]["user_id"]

        # Guard: Prevent self-verification
        if verifier_user_id == claimer_user_id:
            msg = f"User {verifier_user_id} cannot verify their own chore claim"
            logger.warning(msg)
            raise PermissionError(msg)

        # Create verification log
        action = f"{decision.lower()}_verification: {reason}" if reason else f"{decision.lower()}_verification"
        log_data = {
            "chore_id": chore_id,
            "user_id": verifier_user_id,
            "action": action,
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
        else:  # REJECT
            updated_chore = await chore_service.move_to_conflict(chore_id=chore_id)
            logger.info(
                "User %s rejected chore %s (claimed by %s) - moving to conflict",
                verifier_user_id,
                chore_id,
                claimer_user_id,
            )
            # Note: Voting process not yet implemented

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
            filtered_chores = []
            for chore in chores:
                # Get claim logs for this chore
                claim_logs = await db_client.list_records(
                    collection="logs",
                    filter_query=f'chore_id = "{chore["id"]}" && action ~ "claimed_completion"',
                    sort="-created",
                    per_page=1,
                )
                # Exclude if this user claimed it
                if not claim_logs or claim_logs[0]["user_id"] != user_id:
                    filtered_chores.append(chore)
            return filtered_chores

        return chores
