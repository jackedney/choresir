"""Deletion service for seconded chore deletion workflow.

Implements a two-step deletion process where one member requests deletion
and another member must approve (second) the request.
"""

import logging
from datetime import datetime
from typing import Any

from src.core import db_client
from src.core.logging import span
from src.domain.chore import ChoreState
from src.services import user_service, workflow_service


logger = logging.getLogger(__name__)


async def get_pending_deletion_workflow(*, chore_id: str) -> dict[str, Any] | None:
    """Get the pending deletion workflow for a chore if one exists.

    Args:
        chore_id: Chore ID to check for pending deletion workflow

    Returns:
        The pending deletion workflow record, or None if no pending workflow
    """
    with span("deletion_service.get_pending_deletion_workflow"):
        filter_query = (
            f'type = "{workflow_service.WorkflowType.DELETION_APPROVAL.value}" && '
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


async def request_chore_deletion(
    *,
    chore_id: str,
    requester_user_id: str,
    reason: str = "",
) -> dict[str, Any]:
    """Request deletion of a chore (first step of seconded deletion).

    Creates a workflow for the deletion request and log entry for audit trail.

    Args:
        chore_id: Chore ID to request deletion for
        requester_user_id: User ID of the member requesting deletion
        reason: Optional reason for deletion request

    Returns:
        Created workflow record

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

        # Check for existing pending deletion workflow
        existing_workflow = await get_pending_deletion_workflow(chore_id=chore_id)
        if existing_workflow:
            msg = f"Chore {chore_id} already has a pending deletion request"
            raise ValueError(msg)

        # Get requester name for workflow
        requester = await user_service.get_user_by_id(user_id=requester_user_id)

        # Create deletion workflow
        workflow = await workflow_service.create_workflow(
            params=workflow_service.WorkflowCreateParams(
                workflow_type=workflow_service.WorkflowType.DELETION_APPROVAL,
                requester_user_id=requester_user_id,
                requester_name=requester.get("name", "Unknown"),
                target_id=chore_id,
                target_title=chore.get("title", "Unknown"),
            )
        )

        # Create log entry for audit trail
        log_data = {
            "chore_id": chore_id,
            "user_id": requester_user_id,
            "action": "deletion_requested",
            "notes": reason,
            "timestamp": datetime.now().isoformat(),
        }

        await db_client.create_record(collection="logs", data=log_data)

        logger.info(
            "User %s requested deletion of chore %s",
            requester_user_id,
            chore_id,
        )

        return workflow


async def approve_chore_deletion(
    *,
    chore_id: str,
    approver_user_id: str,
    reason: str = "",
) -> dict[str, Any]:
    """Approve a pending deletion request (second step - the 'seconding').

    Archives the chore and resolves workflow.

    Args:
        chore_id: Chore ID to approve deletion for
        approver_user_id: User ID of the member approving deletion
        reason: Optional reason for approval

    Returns:
        Updated chore record

    Raises:
        ValueError: If no pending deletion workflow exists
        PermissionError: If approver is the original requester (self-approval)
        KeyError: If chore not found
    """
    with span("deletion_service.approve_chore_deletion"):
        # Get pending deletion workflow
        pending_workflow = await get_pending_deletion_workflow(chore_id=chore_id)
        if not pending_workflow:
            msg = f"No pending deletion request for chore {chore_id}"
            raise ValueError(msg)

        # Get approver name for workflow resolution
        approver = await user_service.get_user_by_id(user_id=approver_user_id)

        # Resolve workflow (self-approval check is handled by workflow_service)
        await workflow_service.resolve_workflow(
            workflow_id=pending_workflow["id"],
            resolver_user_id=approver_user_id,
            resolver_name=approver.get("name", "Unknown"),
            decision=workflow_service.WorkflowStatus.APPROVED,
            reason=reason,
        )

        # Create log entry for audit trail
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
            "User %s approved deletion of chore %s",
            approver_user_id,
            chore_id,
        )

        return updated_chore


async def reject_chore_deletion(
    *,
    chore_id: str,
    rejecter_user_id: str,
    reason: str = "",
) -> dict[str, Any]:
    """Reject a pending deletion request.

    Cancels deletion request without archiving the chore.

    Args:
        chore_id: Chore ID to reject deletion for
        rejecter_user_id: User ID of the member rejecting deletion
        reason: Optional reason for rejection

    Returns:
        The rejection log record

    Raises:
        ValueError: If no pending deletion workflow exists
        KeyError: If chore not found
    """
    with span("deletion_service.reject_chore_deletion"):
        # Verify chore exists
        await db_client.get_record(collection="chores", record_id=chore_id)

        # Get pending deletion workflow
        pending_workflow = await get_pending_deletion_workflow(chore_id=chore_id)
        if not pending_workflow:
            msg = f"No pending deletion request for chore {chore_id}"
            raise ValueError(msg)

        # Get rejecter name for workflow resolution
        rejecter = await user_service.get_user_by_id(user_id=rejecter_user_id)

        # Resolve workflow as REJECTED
        try:
            await workflow_service.resolve_workflow(
                workflow_id=pending_workflow["id"],
                resolver_user_id=rejecter_user_id,
                resolver_name=rejecter.get("name", "Unknown"),
                decision=workflow_service.WorkflowStatus.REJECTED,
                reason=reason,
            )
        except ValueError as e:
            # Allow requester to reject (cancel) their own request
            if "Cannot approve own workflow" in str(e):
                pass
            else:
                raise

        # Create log entry for audit trail
        log_data = {
            "chore_id": chore_id,
            "user_id": rejecter_user_id,
            "action": "deletion_rejected",
            "notes": reason,
            "timestamp": datetime.now().isoformat(),
        }
        log_record = await db_client.create_record(collection="logs", data=log_data)

        logger.info(
            "User %s rejected deletion of chore %s",
            rejecter_user_id,
            chore_id,
        )

        return log_record
