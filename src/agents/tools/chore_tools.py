"""Chore management tools for the choresir agent."""

import logging

import logfire
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext

from src.agents.base import Deps
from src.core.fuzzy_match import fuzzy_match, fuzzy_match_all
from src.core.recurrence_parser import cron_to_human
from src.domain.task import TaskState
from src.services import (
    chore_service,
    deletion_service,
    notification_service,
    personal_chore_service,
    robin_hood_service,
    user_service,
    verification_service,
    workflow_service,
)


logger = logging.getLogger(__name__)


class DefineChore(BaseModel):
    """Parameters for defining a new chore."""

    title: str = Field(description="Chore title (e.g., 'Take out trash')")
    recurrence: str = Field(description="Recurrence string (e.g., 'every 3 days' or CRON format)")
    assignee_phone: str | None = Field(
        default=None,
        description="Phone number of user to assign chore to (None for unassigned)",
    )
    description: str = Field(default="", description="Optional detailed description")


class LogChore(BaseModel):
    """Parameters for logging a chore completion."""

    chore_title_fuzzy: str = Field(description="Chore title or partial match (fuzzy search)")
    notes: str | None = Field(default=None, description="Optional notes about completion")
    is_swap: bool = Field(
        default=False,
        description="True if this is a Robin Hood swap (one user doing another's chore)",
    )


class RequestChoreDeletion(BaseModel):
    """Parameters for requesting chore deletion."""

    chore_title_fuzzy: str = Field(description="Chore title or partial match (fuzzy search)")
    reason: str = Field(default="", description="Optional reason for requesting deletion")


class RespondToDeletion(BaseModel):
    """Parameters for responding to a deletion request."""

    workflow_id: str | None = Field(
        default=None,
        description="Workflow ID (optional, for direct reference)",
    )
    chore_title_fuzzy: str | None = Field(
        default=None,
        description="Chore title or partial match (fuzzy search, used if workflow_id not provided)",
    )
    decision: str = Field(description="Decision: 'approve' or 'reject'")
    reason: str = Field(default="", description="Optional reason for the decision")


class BatchRespondToWorkflows(BaseModel):
    """Parameters for batch responding to multiple workflows."""

    workflow_ids: list[str] | None = Field(
        default=None,
        description="List of workflow IDs to action (optional, for direct reference)",
    )
    indices: list[int] | None = Field(
        default=None,
        description="List of 1-based indices from 'REQUESTS YOU CAN ACTION' section (optional)",
    )
    decision: str = Field(description="Decision: 'approve' or 'reject'")
    reason: str = Field(default="", description="Optional reason for the decision")


async def tool_define_chore(_ctx: RunContext[Deps], params: DefineChore) -> str:
    """
    Define a new chore with recurrence schedule.

    Args:
        ctx: Agent runtime context with dependencies
        params: Chore definition parameters

    Returns:
        Success or error message
    """
    try:
        with logfire.span("tool_define_chore", title=params.title):
            # If assignee phone is provided, look up user ID
            assignee_id = None
            if params.assignee_phone:
                user = await user_service.get_user_by_phone(phone=params.assignee_phone)
                if not user:
                    return f"Error: User with phone {params.assignee_phone} not found."
                assignee_id = user["id"]

            # Create the chore
            chore = await chore_service.create_chore(
                title=params.title,
                description=params.description,
                recurrence=params.recurrence,
                assigned_to=assignee_id,
            )

            # Convert schedule to human-readable format
            schedule_human = cron_to_human(chore.get("schedule_cron", params.recurrence))
            assignee_msg = f"assigned to {params.assignee_phone}" if assignee_id else "unassigned"
            return f"Created chore '{params.title}' - {schedule_human}, {assignee_msg}."

    except ValueError as e:
        logger.warning("Chore creation failed", extra={"error": str(e)})
        return f"Error: {e!s}"
    except Exception as e:
        logger.error("Unexpected error in tool_define_chore", extra={"error": str(e), "type": type(e).__name__})
        return f"Error: Unable to create chore - {e!s}"


async def _handle_robin_hood_swap(ctx: RunContext[Deps], household_match: dict, chore_title: str) -> str | None:
    """
    Handle Robin Hood swap validation and tracking.

    Returns:
        Error message if validation fails, None if successful
    """
    # Verify that the claimer is not the original assignee
    if household_match["assigned_to"] == ctx.deps.user_id:
        return (
            f"Error: You are already assigned to '{chore_title}'. "
            f"Robin Hood swaps are only for taking over another member's chore."
        )

    # Check weekly takeover limit
    can_takeover, error_message = await robin_hood_service.can_perform_takeover(ctx.deps.user_id)
    if not can_takeover:
        return f"Error: {error_message}"

    # Increment takeover count
    try:
        await robin_hood_service.increment_weekly_takeover_count(ctx.deps.user_id)
    except RuntimeError as e:
        logger.error("Failed to increment takeover count: %s", e)
        return "Error: Unable to process Robin Hood swap. Please try again."

    return None


async def _validate_chore_logging(
    ctx: RunContext[Deps],
    household_match: dict | None,
    personal_match: dict | None,
    chore_title_fuzzy: str,
    is_swap: bool,
) -> str | None:
    """
    Validate chore logging request.

    Returns:
        Error message if validation fails, None if successful
    """
    # Check for collision
    if household_match and personal_match:
        return (
            f"I found both a household chore '{household_match['title']}' and "
            f"your personal chore '{personal_match['title']}'. "
            f"Please be more specific: use '/personal done {chore_title_fuzzy}' "
            f"for personal chores or provide the full household chore name."
        )

    # No collision - proceed with household chore logging
    if not household_match:
        return f"Error: No household chore found matching '{chore_title_fuzzy}'."

    chore_title = household_match["title"]

    # Check if chore is in TODO state
    if household_match["current_state"] != TaskState.TODO:
        return (
            f"Error: Chore '{chore_title}' is in state '{household_match['current_state']}' "
            f"and cannot be logged right now."
        )

    # Robin Hood Protocol: Check if this is a swap and enforce weekly limits
    if is_swap:
        return await _handle_robin_hood_swap(ctx, household_match, chore_title)

    return None


async def tool_log_chore(ctx: RunContext[Deps], params: LogChore) -> str:
    """
    Log a chore completion and request verification.

    Supports fuzzy matching for chore titles and Robin Hood swaps.
    Checks for name collisions with personal chores.
    Enforces weekly takeover limits for Robin Hood swaps.

    Args:
        ctx: Agent runtime context with dependencies
        params: Chore logging parameters

    Returns:
        Success or error message
    """
    try:
        with logfire.span("tool_log_chore", title=params.chore_title_fuzzy, is_swap=params.is_swap):
            # Get all household chores to fuzzy match
            all_chores = await chore_service.get_chores()

            # Fuzzy match the household chore
            household_match = fuzzy_match(all_chores, params.chore_title_fuzzy)

            # Get user's personal chores to check for collision
            personal_chores = await personal_chore_service.get_personal_chores(
                owner_phone=ctx.deps.user_phone,
                status="ACTIVE",
            )
            personal_match = personal_chore_service.fuzzy_match_personal_chore(
                personal_chores, params.chore_title_fuzzy
            )

            # Validate the chore logging request
            validation_error = await _validate_chore_logging(
                ctx, household_match, personal_match, params.chore_title_fuzzy, params.is_swap
            )
            if validation_error:
                return validation_error

            # At this point, household_match is guaranteed to be not None
            assert household_match is not None  # Type narrowing for static analysis
            chore_id = household_match["id"]
            chore_title = household_match["title"]

            # Log the completion
            await verification_service.request_verification(
                chore_id=chore_id,
                claimer_user_id=ctx.deps.user_id,
                notes=params.notes or "",
                is_swap=params.is_swap,
            )

            swap_msg = " (Robin Hood swap)" if params.is_swap else ""
            return (
                f"Logged completion of '{chore_title}'{swap_msg}. Awaiting verification from another household member."
            )

    except ValueError as e:
        logger.warning("Chore logging failed", extra={"error": str(e)})
        return f"Error: {e!s}"
    except Exception as e:
        logger.error("Unexpected error in tool_log_chore", extra={"error": str(e)})
        return "Error: Unable to log chore. Please try again."


async def tool_request_chore_deletion(ctx: RunContext[Deps], params: RequestChoreDeletion) -> str:
    """
    Request deletion of a household chore (requires another member to approve).

    This initiates a two-step deletion process. Another household member
    must approve the deletion within 48 hours for the chore to be removed.

    Args:
        ctx: Agent runtime context with dependencies
        params: Deletion request parameters

    Returns:
        Success or error message
    """
    try:
        with logfire.span("tool_request_chore_deletion", title=params.chore_title_fuzzy):
            # Get all chores to fuzzy match
            all_chores = await chore_service.get_chores()

            # Fuzzy match the chore
            matched_chore = fuzzy_match(all_chores, params.chore_title_fuzzy)

            if not matched_chore:
                return f"Error: No chore found matching '{params.chore_title_fuzzy}'."

            chore_id = matched_chore["id"]
            chore_title = matched_chore["title"]

            # Check if chore is already archived
            if matched_chore["current_state"] == TaskState.ARCHIVED:
                return f"Error: Chore '{chore_title}' is already archived."

            # Request deletion
            log_record = await deletion_service.request_chore_deletion(
                chore_id=chore_id,
                requester_user_id=ctx.deps.user_id,
                reason=params.reason,
            )

            # Send notifications to other household members
            try:
                await notification_service.send_deletion_request_notification(
                    log_id=log_record["id"],
                    chore_id=chore_id,
                    chore_title=chore_title,
                    requester_user_id=ctx.deps.user_id,
                )
            except Exception:
                # Log but don't fail the request
                logger.exception(
                    "Failed to send deletion request notifications for chore %s",
                    chore_id,
                )

            return f"Requested deletion of '{chore_title}'. Another household member must approve this within 48 hours."

    except ValueError as e:
        logger.warning("Chore deletion request failed", extra={"error": str(e)})
        return f"Error: {e!s}"
    except Exception as e:
        logger.error("Unexpected error in tool_request_chore_deletion", extra={"error": str(e)})
        return "Error: Unable to request chore deletion. Please try again."


async def _get_workflow_by_id(workflow_id: str) -> dict | str:
    """Get and validate a deletion workflow by ID.

    Args:
        workflow_id: The workflow ID to look up

    Returns:
        The workflow dict if valid, or an error message string
    """
    workflow = await workflow_service.get_workflow(workflow_id=workflow_id)
    if not workflow:
        return f"Error: Workflow '{workflow_id}' not found."

    if workflow["type"] != workflow_service.WorkflowType.DELETION_APPROVAL.value:
        return f"Error: Workflow '{workflow_id}' is not a deletion approval workflow."

    if workflow["status"] != workflow_service.WorkflowStatus.PENDING.value:
        return f"Error: Workflow '{workflow_id}' is not pending (status: {workflow['status']})."

    return workflow


async def _get_workflow_by_chore_title(chore_title_fuzzy: str) -> dict | str:
    """Find a deletion workflow by chore title matching.

    Args:
        chore_title_fuzzy: The chore title to fuzzy match

    Returns:
        The workflow dict if found, or an error message string
    """
    all_chores = await chore_service.get_chores()
    matched_chores = fuzzy_match_all(all_chores, chore_title_fuzzy)

    if not matched_chores:
        return (
            f'No chore found matching "{chore_title_fuzzy}". '
            'To delete a chore, first request deletion with "Request deletion [chore title]".'
        )

    # Find which matched chores have pending deletion requests
    chores_with_pending_deletion: list[tuple[dict, dict]] = []
    for chore in matched_chores:
        pending_workflow = await deletion_service.get_pending_deletion_workflow(chore_id=chore["id"])
        if pending_workflow:
            chores_with_pending_deletion.append((chore, pending_workflow))

    if not chores_with_pending_deletion:
        return (
            f'No pending deletion request found for "{chore_title_fuzzy}". '
            'To delete a chore, first request deletion with "Request deletion [chore title]".'
        )

    if len(chores_with_pending_deletion) > 1:
        chore_list = ", ".join(f"'{c['title']}'" for c, _ in chores_with_pending_deletion)
        return f"Multiple chores with pending deletion found: {chore_list}. Please specify which one."

    # Exactly one chore with pending deletion - use it
    _matched_chore, pending_workflow = chores_with_pending_deletion[0]
    return pending_workflow


async def _resolve_deletion_workflow(
    workflow: dict,
    user_id: str,
    decision_lower: str,
    reason: str,
) -> str:
    """Resolve a deletion workflow with the given decision.

    Args:
        workflow: The workflow to resolve
        user_id: The resolving user's ID
        decision_lower: The normalized decision ('approve' or 'reject')
        reason: Reason for the decision

    Returns:
        Success message
    """
    resolver = await user_service.get_user_by_id(user_id=user_id)
    resolver_name = resolver.get("name", "Unknown")

    if decision_lower == "approve":
        await workflow_service.resolve_workflow(
            workflow_id=workflow["id"],
            resolver_user_id=user_id,
            resolver_name=resolver_name,
            decision=workflow_service.WorkflowStatus.APPROVED,
            reason=reason,
        )
        return f"Approved deletion of '{workflow['target_title']}'. The chore has been archived."

    await workflow_service.resolve_workflow(
        workflow_id=workflow["id"],
        resolver_user_id=user_id,
        resolver_name=resolver_name,
        decision=workflow_service.WorkflowStatus.REJECTED,
        reason=reason,
    )
    return f"Rejected deletion request for '{workflow['target_title']}'. The chore will remain active."


async def tool_respond_to_deletion(ctx: RunContext[Deps], params: RespondToDeletion) -> str:
    """Respond to a pending chore deletion request (approve or reject).

    Supports referencing by workflow_id directly or by chore title matching.

    Args:
        ctx: Agent runtime context with dependencies
        params: Deletion response parameters

    Returns:
        Success or error message
    """
    try:
        with logfire.span("tool_respond_to_deletion", workflow_id=params.workflow_id, decision=params.decision):
            # Validate input
            if not params.workflow_id and not params.chore_title_fuzzy:
                return "Error: Either workflow_id or chore_title_fuzzy must be provided."

            # Normalize decision
            decision_lower = params.decision.lower().strip()
            if decision_lower not in ("approve", "reject"):
                return f"Error: Invalid decision '{params.decision}'. Must be 'approve' or 'reject'."

            # Determine the workflow to resolve
            if params.workflow_id:
                workflow_result = await _get_workflow_by_id(params.workflow_id)
            else:
                assert params.chore_title_fuzzy is not None  # Type narrowing: validated above
                workflow_result = await _get_workflow_by_chore_title(params.chore_title_fuzzy)

            # Check if we got an error message instead of a workflow
            if isinstance(workflow_result, str):
                return workflow_result

            # Resolve the workflow
            return await _resolve_deletion_workflow(
                workflow=workflow_result,
                user_id=ctx.deps.user_id,
                decision_lower=decision_lower,
                reason=params.reason or "",
            )

    except ValueError as e:
        logger.warning("Chore deletion response failed", extra={"error": str(e)})
        return f"Error: {e!s}"
    except Exception as e:
        logger.error("Unexpected error in tool_respond_to_deletion", extra={"error": str(e)})
        return "Error: Unable to process deletion response. Please try again."


def _resolve_workflow_ids_from_indices(
    indices: list[int],
    actionable_workflows: list[dict],
) -> list[str] | str:
    """Resolve workflow IDs from 1-based indices.

    Args:
        indices: List of 1-based indices
        actionable_workflows: List of actionable workflow dicts

    Returns:
        List of workflow IDs, or an error message string
    """
    if not actionable_workflows:
        return "No actionable workflows found. You have no pending requests from others to approve or reject."

    # Check for 'all' keyword (indices = [0] or user said 'all')
    if len(indices) == 1 and indices[0] == 0:
        return [wf["id"] for wf in actionable_workflows]

    # Convert 1-based indices to workflow IDs
    workflow_ids: list[str] = []
    for idx in indices:
        if 1 <= idx <= len(actionable_workflows):
            workflow_ids.append(actionable_workflows[idx - 1]["id"])
        else:
            logger.warning(
                "Index out of range",
                extra={
                    "index": idx,
                    "total_workflows": len(actionable_workflows),
                },
            )

    return workflow_ids


async def _get_batch_workflow_ids(
    params: BatchRespondToWorkflows,
    user_id: str,
) -> list[str] | str:
    """Determine which workflow IDs to resolve based on params.

    Args:
        params: Batch workflow response parameters
        user_id: The user ID for looking up actionable workflows

    Returns:
        List of workflow IDs, or an error message string
    """
    if params.workflow_ids:
        return params.workflow_ids

    if params.indices:
        actionable_workflows = await workflow_service.get_actionable_workflows(user_id=user_id)
        result = _resolve_workflow_ids_from_indices(params.indices, actionable_workflows)
        if isinstance(result, str):
            return result
        if not result:
            return "No valid workflows to action. Check the indices or workflow IDs provided."
        return result

    return "Error: Either workflow_ids or indices must be provided."


async def _batch_resolve_and_format(
    workflow_ids: list[str],
    user_id: str,
    decision_lower: str,
    reason: str,
) -> str:
    """Batch resolve workflows and format the response message.

    Args:
        workflow_ids: List of workflow IDs to resolve
        user_id: The resolving user's ID
        decision_lower: The normalized decision ('approve' or 'reject')
        reason: Optional reason for the decision

    Returns:
        Summary message of resolved workflows
    """
    resolver = await user_service.get_user_by_id(user_id=user_id)
    resolver_name = resolver.get("name", "Unknown")

    decision_status = (
        workflow_service.WorkflowStatus.APPROVED
        if decision_lower == "approve"
        else workflow_service.WorkflowStatus.REJECTED
    )

    resolved_workflows = await workflow_service.batch_resolve_workflows(
        workflow_ids=workflow_ids,
        resolver_user_id=user_id,
        resolver_name=resolver_name,
        decision=decision_status,
        reason=reason,
    )

    if not resolved_workflows:
        return (
            "No workflows were resolved. You may have tried to approve your own requests or already-resolved workflows."
        )

    # Build summary message
    action_verb = "Approved" if decision_lower == "approve" else "Rejected"
    workflow_titles = [wf["target_title"] for wf in resolved_workflows]
    titles_quoted = '", "'.join(workflow_titles)

    if len(resolved_workflows) == 1:
        return f'{action_verb} 1 workflow: "{titles_quoted}"'
    return f'{action_verb} {len(resolved_workflows)} workflows: "{titles_quoted}"'


async def tool_batch_respond_to_workflows(ctx: RunContext[Deps], params: BatchRespondToWorkflows) -> str:
    """Batch approve or reject multiple workflows at once.

    Supports three modes of operation:
    1. Direct workflow IDs: Provide workflow_ids list
    2. Indexed references: Provide indices list (1-based from 'REQUESTS YOU CAN ACTION')
    3. All workflows: Set indices to [0] or 'all' keyword to action all actionable workflows

    Args:
        ctx: Agent runtime context with dependencies
        params: Batch workflow response parameters

    Returns:
        Summary message of resolved workflows or error message
    """
    try:
        with logfire.span("tool_batch_respond_to_workflows", decision=params.decision):
            # Normalize decision
            decision_lower = params.decision.lower().strip()
            if decision_lower not in ("approve", "reject"):
                return f"Error: Invalid decision '{params.decision}'. Must be 'approve' or 'reject'."

            # Determine which workflows to resolve
            workflow_ids_result = await _get_batch_workflow_ids(params, ctx.deps.user_id)
            if isinstance(workflow_ids_result, str):
                return workflow_ids_result

            return await _batch_resolve_and_format(
                workflow_ids=workflow_ids_result,
                user_id=ctx.deps.user_id,
                decision_lower=decision_lower,
                reason=params.reason or "",
            )

    except ValueError as e:
        logger.warning("Batch workflow response failed", extra={"error": str(e)})
        return f"Error: {e!s}"
    except Exception as e:
        logger.error("Unexpected error in tool_batch_respond_to_workflows", extra={"error": str(e)})
        return "Error: Unable to process batch workflow response. Please try again."


def register_tools(agent: Agent[Deps, str]) -> None:
    """Register chore tools with the agent."""
    agent.tool(tool_define_chore)
    agent.tool(tool_log_chore)
    agent.tool(tool_request_chore_deletion)
    agent.tool(tool_respond_to_deletion)
    agent.tool(tool_batch_respond_to_workflows)
