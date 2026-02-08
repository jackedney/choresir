"""Workflow service for managing multi-step approval workflows.

This service provides centralized CRUD operations for tracking workflow state
across different workflow types (deletion approval, chore verification, personal verification).
"""

import logging
from dataclasses import dataclass, field
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


@dataclass
class WorkflowCreateParams:
    """Parameters for creating a workflow."""

    workflow_type: WorkflowType
    requester_user_id: str
    requester_name: str
    target_id: str
    target_title: str
    expires_hours: int = 48
    metadata: dict[str, Any] = field(default_factory=dict)


async def create_workflow(*, params: WorkflowCreateParams) -> dict[str, Any]:
    """Create a new workflow.

    Args:
        params: WorkflowCreateParams dataclass containing all workflow parameters

    Returns:
        Created workflow record as dict
    """
    with span("workflow.create_workflow"):
        created_at = datetime.now()
        expires_at = created_at + timedelta(hours=params.expires_hours)

        workflow_data = {
            "type": params.workflow_type.value,
            "status": WorkflowStatus.PENDING.value,
            "requester_user_id": params.requester_user_id,
            "requester_name": params.requester_name,
            "target_id": params.target_id,
            "target_title": params.target_title,
            "created_at": created_at.isoformat(),
            "expires_at": expires_at.isoformat(),
        }

        if params.metadata:
            workflow_data["metadata"] = params.metadata

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


async def batch_resolve_workflows(
    *,
    workflow_ids: list[str],
    resolver_user_id: str,
    resolver_name: str,
    decision: WorkflowStatus,
    reason: str = "",
) -> list[dict[str, Any]]:
    """Resolve multiple workflows by approving or rejecting them.

    Args:
        workflow_ids: List of workflow IDs to resolve
        resolver_user_id: ID of user resolving the workflows
        resolver_name: Name of user resolving the workflows (denormalized)
        decision: Resolution decision (APPROVED or REJECTED)
        reason: Optional reason for rejection

    Returns:
        List of resolved workflow records as dicts (skipped workflows not included)

    Raises:
        ValueError: If decision is not APPROVED or REJECTED
    """
    with span("workflow.batch_resolve_workflows"):
        if decision not in (WorkflowStatus.APPROVED, WorkflowStatus.REJECTED):
            msg = f"Invalid decision '{decision}', must be APPROVED or REJECTED"
            raise ValueError(msg)

        resolved_workflows: list[dict[str, Any]] = []

        for workflow_id in workflow_ids:
            workflow = await get_workflow(workflow_id=workflow_id)

            if workflow is None:
                logger.warning(
                    "Skipping workflow not found",
                    extra={
                        "workflow_id": workflow_id,
                        "resolver_user_id": resolver_user_id,
                    },
                )
                continue

            if workflow["status"] != WorkflowStatus.PENDING.value:
                logger.warning(
                    "Skipping workflow not in PENDING status",
                    extra={
                        "workflow_id": workflow_id,
                        "status": workflow["status"],
                        "resolver_user_id": resolver_user_id,
                    },
                )
                continue

            if workflow["requester_user_id"] == resolver_user_id:
                logger.warning(
                    "Skipping workflow where resolver is requester",
                    extra={
                        "workflow_id": workflow_id,
                        "requester_user_id": workflow["requester_user_id"],
                        "resolver_user_id": resolver_user_id,
                    },
                )
                continue

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

            resolved_workflows.append(updated_workflow)

            logger.info(
                "Workflow batch resolved",
                extra={
                    "workflow_id": workflow_id,
                    "resolver_user_id": resolver_user_id,
                    "decision": decision.value,
                },
            )

        return resolved_workflows


async def expire_old_workflows() -> int:
    """Expire workflows that have passed their expiration time.

    Updates status to EXPIRED for all workflows where expires_at < now and status = PENDING.

    Returns:
        Count of expired workflows
    """
    with span("workflow.expire_old_workflows"):
        now = datetime.now().isoformat()

        # Find all pending workflows that have expired
        expired_workflows = await db_client.list_records(
            collection="workflows",
            filter_query=f'status = "{WorkflowStatus.PENDING.value}" && expires_at < "{db_client.sanitize_param(now)}"',
        )

        expired_count = 0

        for workflow in expired_workflows:
            try:
                await db_client.update_record(
                    collection="workflows",
                    record_id=workflow["id"],
                    data={"status": WorkflowStatus.EXPIRED.value},
                )

                expired_count += 1

                logger.info(
                    "Workflow expired",
                    extra={
                        "workflow_id": workflow["id"],
                        "workflow_type": workflow["type"],
                        "requester_user_id": workflow["requester_user_id"],
                    },
                )
            except Exception as e:
                logger.error(
                    "Error expiring workflow",
                    extra={"workflow_id": workflow["id"], "error": str(e)},
                    exc_info=True,
                )

        logger.info("Completed workflow expiry", extra={"expired_count": expired_count})

        return expired_count
