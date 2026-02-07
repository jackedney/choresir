"""Workflow service for managing multi-step approval workflows.

This service provides centralized CRUD operations for tracking workflow state
across different workflow types (deletion approval, chore verification, personal verification).
"""

import logging
from datetime import datetime, timedelta
from enum import Enum
from typing import Any

from src.core import db_client
from src.core.logging import span


logger = logging.getLogger(__name__)


class WorkflowType(str, Enum):
    """Types of workflows supported in the system."""

    DELETION_APPROVAL = "deletion_approval"
    CHORE_VERIFICATION = "chore_verification"
    PERSONAL_VERIFICATION = "personal_verification"


class WorkflowStatus(str, Enum):
    """Status states for workflows."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


async def create_workflow(
    *,
    workflow_type: WorkflowType,
    requester_user_id: str,
    requester_name: str,
    target_id: str,
    target_title: str,
    expires_hours: int = 48,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create a new workflow.

    Args:
        workflow_type: Type of workflow to create
        requester_user_id: ID of user requesting the workflow
        requester_name: Name of user requesting the workflow (denormalized)
        target_id: ID of target (chore_id or personal_chore_id)
        target_title: Title of target (denormalized for display)
        expires_hours: Hours until workflow expires (default 48)
        metadata: Optional JSON metadata for workflow-specific data

    Returns:
        Created workflow record as dict
    """
    with span("workflow.create_workflow"):
        created_at = datetime.now()
        expires_at = created_at + timedelta(hours=expires_hours)

        workflow_data = {
            "type": workflow_type.value,
            "status": WorkflowStatus.PENDING.value,
            "requester_user_id": requester_user_id,
            "requester_name": requester_name,
            "target_id": target_id,
            "target_title": target_title,
            "created_at": created_at.isoformat(),
            "expires_at": expires_at.isoformat(),
        }

        if metadata:
            workflow_data["metadata"] = metadata

        return await db_client.create_record(collection="workflows", data=workflow_data)


async def get_workflow(*, workflow_id: str) -> dict[str, Any] | None:
    """Get a workflow by ID.

    Args:
        workflow_id: ID of workflow to retrieve

    Returns:
        Workflow record as dict, or None if not found
    """
    with span("workflow.get_workflow"):
        try:
            return await db_client.get_record(collection="workflows", record_id=workflow_id)
        except KeyError:
            return None


async def get_pending_workflows(*, workflow_type: WorkflowType | None = None) -> list[dict[str, Any]]:
    """Get all pending workflows, optionally filtered by type.

    Args:
        workflow_type: Optional filter by workflow type

    Returns:
        List of pending workflow records as dicts
    """
    with span("workflow.get_pending_workflows"):
        filter_query = f'status = "{WorkflowStatus.PENDING.value}"'

        if workflow_type:
            filter_query += f' && type = "{db_client.sanitize_param(workflow_type.value)}"'

        return await db_client.list_records(collection="workflows", filter_query=filter_query)


async def get_user_pending_workflows(*, user_id: str) -> list[dict[str, Any]]:
    """Get pending workflows initiated by the specified user.

    Args:
        user_id: ID of the user who requested the workflows

    Returns:
        List of pending workflow records as dicts initiated by the user
    """
    with span("workflow.get_user_pending_workflows"):
        filter_query = (
            f'requester_user_id = "{db_client.sanitize_param(user_id)}" && status = "{WorkflowStatus.PENDING.value}"'
        )

        return await db_client.list_records(collection="workflows", filter_query=filter_query)


async def get_actionable_workflows(*, user_id: str) -> list[dict[str, Any]]:
    """Get pending workflows the user can approve/reject (not initiated by them).

    Args:
        user_id: ID of the user who can action the workflows

    Returns:
        List of pending workflow records as dicts initiated by others
    """
    with span("workflow.get_actionable_workflows"):
        filter_query = (
            f'requester_user_id != "{db_client.sanitize_param(user_id)}" && status = "{WorkflowStatus.PENDING.value}"'
        )

        return await db_client.list_records(collection="workflows", filter_query=filter_query)


async def resolve_workflow(
    *,
    workflow_id: str,
    resolver_user_id: str,
    resolver_name: str,
    decision: WorkflowStatus,
    reason: str = "",
) -> dict[str, Any]:
    """Resolve a workflow by approving or rejecting it.

    Args:
        workflow_id: ID of workflow to resolve
        resolver_user_id: ID of user resolving the workflow
        resolver_name: Name of user resolving the workflow (denormalized)
        decision: Resolution decision (APPROVED or REJECTED)
        reason: Optional reason for rejection

    Returns:
        Updated workflow record as dict

    Raises:
        ValueError: If workflow not found, resolver is requester, workflow not pending, or decision invalid
    """
    with span("workflow.resolve_workflow"):
        workflow = await get_workflow(workflow_id=workflow_id)

        if workflow is None:
            msg = f"Workflow not found: {workflow_id}"
            raise ValueError(msg)

        if workflow["status"] != WorkflowStatus.PENDING.value:
            msg = f"Cannot resolve workflow with status '{workflow['status']}': {workflow_id}"
            raise ValueError(msg)

        if workflow["requester_user_id"] == resolver_user_id:
            msg = f"Cannot approve own workflow: {workflow_id}"
            raise ValueError(msg)

        if decision not in (WorkflowStatus.APPROVED, WorkflowStatus.REJECTED):
            msg = f"Invalid decision '{decision}', must be APPROVED or REJECTED"
            raise ValueError(msg)

        resolved_at = datetime.now().isoformat()
        update_data = {
            "status": decision.value,
            "resolved_at": resolved_at,
            "resolver_user_id": resolver_user_id,
            "resolver_name": resolver_name,
        }

        if reason:
            update_data["reason"] = reason

        updated_workflow = await db_client.update_record(
            collection="workflows", record_id=workflow_id, data=update_data
        )

        logger.info(
            "Workflow resolved",
            extra={
                "workflow_id": workflow_id,
                "resolver_user_id": resolver_user_id,
                "decision": decision.value,
            },
        )

        return updated_workflow
