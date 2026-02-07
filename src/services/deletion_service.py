"""Deletion service for seconded chore deletion workflow.

Implements a two-step deletion process where one member requests deletion
and another member must approve (second) the request.
"""

import logging
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from src.core import db_client
from src.core.logging import span
from src.domain.chore import ChoreState


logger = logging.getLogger(__name__)

# Constants
DELETION_REQUEST_EXPIRY_HOURS = 48


class DeletionDecision(StrEnum):
    """Deletion response decision enum."""

    APPROVE = "APPROVE"
    REJECT = "REJECT"


async def get_pending_deletion_request(*, chore_id: str) -> dict[str, Any] | None:
    """Get the pending deletion request for a chore if one exists.

    Args:
        chore_id: Chore ID to check for pending deletion request

    Returns:
        The pending deletion request log record, or None if no pending request
    """
    with span("deletion_service.get_pending_deletion_request"):
        filter_query = f'chore_id = "{db_client.sanitize_param(chore_id)}" && action = "deletion_requested"'

        logs = await db_client.list_records(
            collection="logs",
            filter_query=filter_query,
            sort="-timestamp",
            per_page=1,
        )

        if not logs:
            return None

        request_log = logs[0]

        # Check if this request has been resolved (approved/rejected)
        request_timestamp = request_log.get("timestamp", "")
        if not request_timestamp:
            return None

        # Look for a resolution log after this request
        resolution_filter = (
            f'chore_id = "{db_client.sanitize_param(chore_id)}" && '
            f'(action = "deletion_approved" || action = "deletion_rejected") && '
            f'timestamp >= "{request_timestamp}"'
        )

        resolution_logs = await db_client.list_records(
            collection="logs",
            filter_query=resolution_filter,
            per_page=1,
        )

        if resolution_logs:
            # Request has been resolved
            return None

        # Check if request has expired (48 hours)
        try:
            request_time = datetime.fromisoformat(request_timestamp)
            expiry_time = request_time + timedelta(hours=DELETION_REQUEST_EXPIRY_HOURS)
            if datetime.now() > expiry_time:
                # Request has expired
                return None
        except (ValueError, TypeError):
            logger.warning("Invalid timestamp in deletion request log: %s", request_log.get("id"))
            return None

        return request_log


async def request_chore_deletion(
    *,
    chore_id: str,
    requester_user_id: str,
    reason: str = "",
) -> dict[str, Any]:
    """Request deletion of a chore (first step of seconded deletion).

    Creates a log entry for the deletion request and triggers notifications
    to other household members.

    Args:
        chore_id: Chore ID to request deletion for
        requester_user_id: User ID of the member requesting deletion
        reason: Optional reason for deletion request

    Returns:
        Created log record

    Raises:
        ValueError: If chore already has a pending deletion request
        KeyError: If chore not found
    """
    with span("deletion_service.request_chore_deletion"):
        # Verify chore exists
        chore = await db_client.get_record(collection="chores", record_id=chore_id)

        # Check chore is not already archived
        if chore["current_state"] == ChoreState.ARCHIVED:
            msg = f"Cannot request deletion: chore {chore_id} is already archived"
            raise ValueError(msg)

        # Check for existing pending deletion request
        existing_request = await get_pending_deletion_request(chore_id=chore_id)
        if existing_request:
            msg = f"Chore {chore_id} already has a pending deletion request"
            raise ValueError(msg)

        # Create deletion request log
        log_data = {
            "chore_id": chore_id,
            "user_id": requester_user_id,
            "action": "deletion_requested",
            "notes": reason,
            "timestamp": datetime.now().isoformat(),
        }

        log_record = await db_client.create_record(collection="logs", data=log_data)

        logger.info(
            "User %s requested deletion of chore %s",
            requester_user_id,
            chore_id,
        )

        return log_record


async def approve_chore_deletion(
    *,
    chore_id: str,
    approver_user_id: str,
    reason: str = "",
) -> dict[str, Any]:
    """Approve a pending deletion request (second step - the 'seconding').

    Archives the chore and creates approval log.

    Args:
        chore_id: Chore ID to approve deletion for
        approver_user_id: User ID of the member approving deletion
        reason: Optional reason for approval

    Returns:
        Updated chore record

    Raises:
        ValueError: If no pending deletion request exists
        PermissionError: If approver is the original requester (self-approval)
        KeyError: If chore not found
    """
    with span("deletion_service.approve_chore_deletion"):
        # Get pending deletion request
        pending_request = await get_pending_deletion_request(chore_id=chore_id)
        if not pending_request:
            msg = f"No pending deletion request for chore {chore_id}"
            raise ValueError(msg)

        requester_user_id = pending_request["user_id"]

        # Prevent self-approval
        if approver_user_id == requester_user_id:
            msg = f"User {approver_user_id} cannot approve their own deletion request"
            logger.warning(msg)
            raise PermissionError(msg)

        # Create approval log
        log_data = {
            "chore_id": chore_id,
            "user_id": approver_user_id,
            "action": "deletion_approved",
            "notes": reason,
            "timestamp": datetime.now().isoformat(),
        }
        await db_client.create_record(collection="logs", data=log_data)

        # Archive the chore (soft delete)
        updated_chore = await db_client.update_record(
            collection="chores",
            record_id=chore_id,
            data={"current_state": ChoreState.ARCHIVED},
        )

        logger.info(
            "User %s approved deletion of chore %s (requested by %s)",
            approver_user_id,
            chore_id,
            requester_user_id,
        )

        return updated_chore


async def reject_chore_deletion(
    *,
    chore_id: str,
    rejecter_user_id: str,
    reason: str = "",
) -> dict[str, Any]:
    """Reject a pending deletion request.

    Cancels the deletion request without archiving the chore.

    Args:
        chore_id: Chore ID to reject deletion for
        rejecter_user_id: User ID of the member rejecting deletion
        reason: Optional reason for rejection

    Returns:
        The rejection log record

    Raises:
        ValueError: If no pending deletion request exists
        KeyError: If chore not found
    """
    with span("deletion_service.reject_chore_deletion"):
        # Verify chore exists
        await db_client.get_record(collection="chores", record_id=chore_id)

        # Get pending deletion request
        pending_request = await get_pending_deletion_request(chore_id=chore_id)
        if not pending_request:
            msg = f"No pending deletion request for chore {chore_id}"
            raise ValueError(msg)

        requester_user_id = pending_request["user_id"]

        # Create rejection log
        log_data = {
            "chore_id": chore_id,
            "user_id": rejecter_user_id,
            "action": "deletion_rejected",
            "notes": reason,
            "timestamp": datetime.now().isoformat(),
        }
        log_record = await db_client.create_record(collection="logs", data=log_data)

        logger.info(
            "User %s rejected deletion of chore %s (requested by %s)",
            rejecter_user_id,
            chore_id,
            requester_user_id,
        )

        return log_record


async def _is_deletion_request_resolved(*, chore_id: str, request_timestamp: str) -> bool:
    """Check if a deletion request has been resolved (approved or rejected).

    Args:
        chore_id: Chore ID
        request_timestamp: Timestamp of the deletion request

    Returns:
        True if the request has been resolved, False if still pending
    """
    resolution_filter = (
        f'chore_id = "{db_client.sanitize_param(chore_id)}" && '
        f'(action = "deletion_approved" || action = "deletion_rejected") && '
        f'timestamp >= "{request_timestamp}"'
    )

    resolution_logs = await db_client.list_records(
        collection="logs",
        filter_query=resolution_filter,
        per_page=1,
    )

    return len(resolution_logs) > 0


async def expire_old_deletion_requests() -> int:
    """Expire deletion requests that have been pending for > 48 hours.

    This function is called by the scheduler job.
    Unlike verification, expired deletion requests are cancelled (not auto-approved)
    for safety.

    Returns:
        Number of requests expired
    """
    with span("deletion_service.expire_old_deletion_requests"):
        cutoff_time = datetime.now() - timedelta(hours=DELETION_REQUEST_EXPIRY_HOURS)

        # Find all deletion_requested logs older than cutoff
        filter_query = f'action = "deletion_requested" && timestamp < "{cutoff_time.isoformat()}"'

        old_requests = await db_client.list_records(
            collection="logs",
            filter_query=filter_query,
        )

        expired_count = 0
        for request_log in old_requests:
            chore_id = request_log.get("chore_id")
            request_timestamp = request_log.get("timestamp")
            if not chore_id or not request_timestamp:
                continue

            # Check if this request has already been resolved
            is_resolved = await _is_deletion_request_resolved(
                chore_id=chore_id,
                request_timestamp=request_timestamp,
            )

            if not is_resolved:
                # This old request is still pending - expire it
                try:
                    # Create expiry log
                    expiry_log_data = {
                        "chore_id": chore_id,
                        "user_id": request_log.get("user_id"),
                        "action": "deletion_rejected",
                        "notes": "Auto-expired (no response within 48 hours)",
                        "timestamp": datetime.now().isoformat(),
                    }
                    await db_client.create_record(collection="logs", data=expiry_log_data)
                    expired_count += 1

                    logger.info(
                        "Auto-expired deletion request for chore %s (48h timeout)",
                        chore_id,
                    )
                except Exception as e:
                    logger.error("Failed to expire deletion request %s: %s", request_log.get("id"), e)
                    continue

        logger.info("Expired %d deletion requests", expired_count)
        return expired_count


async def get_all_pending_deletion_requests() -> list[dict[str, Any]]:
    """Get all pending deletion requests across all chores.

    Returns:
        List of pending deletion request log records with chore details
    """
    with span("deletion_service.get_all_pending_deletion_requests"):
        cutoff_time = datetime.now() - timedelta(hours=DELETION_REQUEST_EXPIRY_HOURS)

        # Find all deletion_requested logs within expiry window
        filter_query = f'action = "deletion_requested" && timestamp >= "{cutoff_time.isoformat()}"'

        request_logs = await db_client.list_records(
            collection="logs",
            filter_query=filter_query,
            sort="-timestamp",
        )

        pending_requests = []
        for request_log in request_logs:
            chore_id = request_log.get("chore_id")
            if not chore_id:
                continue

            # Verify this is actually pending (not resolved)
            pending = await get_pending_deletion_request(chore_id=chore_id)
            if pending and pending.get("id") == request_log.get("id"):
                # Enrich with chore details
                try:
                    chore = await db_client.get_record(collection="chores", record_id=chore_id)
                    enriched = dict(request_log)
                    enriched["chore_title"] = chore.get("title", "Unknown")
                    pending_requests.append(enriched)
                except KeyError:
                    # Chore was deleted
                    continue

        return pending_requests


async def get_user_pending_deletion_requests(*, user_id: str) -> list[dict[str, Any]]:
    """Get pending deletion requests made by a specific user.

    Args:
        user_id: User ID to get pending deletions for

    Returns:
        List of pending deletion request records with chore details
    """
    with span("deletion_service.get_user_pending_deletion_requests"):
        cutoff_time = datetime.now() - timedelta(hours=DELETION_REQUEST_EXPIRY_HOURS)

        # Find deletion_requested logs by this user within expiry window
        filter_query = (
            f'action = "deletion_requested" && '
            f'user_id = "{db_client.sanitize_param(user_id)}" && '
            f'timestamp >= "{cutoff_time.isoformat()}"'
        )

        request_logs = await db_client.list_records(
            collection="logs",
            filter_query=filter_query,
            sort="-timestamp",
        )

        pending_requests = []
        for request_log in request_logs:
            chore_id = request_log.get("chore_id")
            if not chore_id:
                continue

            # Verify this is actually pending (not resolved)
            pending = await get_pending_deletion_request(chore_id=chore_id)
            if pending and pending.get("id") == request_log.get("id"):
                # Enrich with chore details
                try:
                    chore = await db_client.get_record(collection="chores", record_id=chore_id)
                    enriched = dict(request_log)
                    enriched["chore_title"] = chore.get("title", "Unknown")
                    pending_requests.append(enriched)
                except KeyError:
                    # Chore was deleted
                    continue

        return pending_requests
