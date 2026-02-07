"""Chore management tools for the choresir agent."""

import logging

import logfire
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext

from src.agents.base import Deps
from src.core.recurrence_parser import cron_to_human
from src.domain.chore import ChoreState
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


def _fuzzy_match_chore(chores: list[dict], title_query: str) -> dict | None:
    """
    Fuzzy match a chore by title.

    Args:
        chores: List of chore records
        title_query: User's search query

    Returns:
        Best matching chore or None
    """
    matches = _fuzzy_match_all_chores(chores, title_query)
    return matches[0] if matches else None


def _fuzzy_match_all_chores(chores: list[dict], title_query: str) -> list[dict]:
    """
    Fuzzy match all chores matching a title query.

    Args:
        chores: List of chore records
        title_query: User's search query

    Returns:
        List of all matching chores (may be empty)
    """
    title_lower = title_query.lower().strip()
    matches: list[dict] = []

    # Exact match (highest priority)
    for chore in chores:
        if chore["title"].lower() == title_lower:
            matches.append(chore)

    if matches:
        return matches

    # Contains match
    for chore in chores:
        if title_lower in chore["title"].lower():
            matches.append(chore)

    if matches:
        return matches

    # Partial word match
    query_words = set(title_lower.split())
    for chore in chores:
        chore_words = set(chore["title"].lower().split())
        if query_words & chore_words:  # Intersection
            matches.append(chore)

    return matches


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
    if household_match["current_state"] != ChoreState.TODO:
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
            household_match = _fuzzy_match_chore(all_chores, params.chore_title_fuzzy)

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
            matched_chore = _fuzzy_match_chore(all_chores, params.chore_title_fuzzy)

            if not matched_chore:
                return f"Error: No chore found matching '{params.chore_title_fuzzy}'."

            chore_id = matched_chore["id"]
            chore_title = matched_chore["title"]

            # Check if chore is already archived
            if matched_chore["current_state"] == ChoreState.ARCHIVED:
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


async def tool_respond_to_deletion(ctx: RunContext[Deps], params: RespondToDeletion) -> str:
    """
    Respond to a pending chore deletion request (approve or reject).

    Supports referencing by workflow_id directly or by chore title matching.

    Args:
        ctx: Agent runtime context with dependencies
        params: Deletion response parameters

    Returns:
        Success or error message
    """
    result = None
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
            workflow: dict | None = None

            if params.workflow_id:
                # Direct workflow ID reference
                workflow = await workflow_service.get_workflow(workflow_id=params.workflow_id)
                if not workflow:
                    return f"Error: Workflow '{params.workflow_id}' not found."

                if workflow["type"] != workflow_service.WorkflowType.DELETION_APPROVAL.value:
                    return f"Error: Workflow '{params.workflow_id}' is not a deletion approval workflow."

                if workflow["status"] != workflow_service.WorkflowStatus.PENDING.value:
                    return f"Error: Workflow '{params.workflow_id}' is not pending (status: {workflow['status']})."
            else:
                # Find workflow by chore title matching
                assert params.chore_title_fuzzy is not None  # Type narrowing: validated above
                all_chores = await chore_service.get_chores()

                # Find ALL matching chores (not just the first)
                matched_chores = _fuzzy_match_all_chores(all_chores, params.chore_title_fuzzy)

                if not matched_chores:
                    return (
                        f'No chore found matching "{params.chore_title_fuzzy}". '
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
                        f'No pending deletion request found for "{params.chore_title_fuzzy}". '
                        'To delete a chore, first request deletion with "Request deletion [chore title]".'
                    )

                if len(chores_with_pending_deletion) > 1:
                    # Multiple chores with pending deletion - ask for clarification
                    chore_list = ", ".join(f"'{c['title']}'" for c, _ in chores_with_pending_deletion)
                    return f"Multiple chores with pending deletion found: {chore_list}. Please specify which one."

                # Exactly one chore with pending deletion - use it
                _matched_chore, pending_workflow = chores_with_pending_deletion[0]
                workflow = pending_workflow

            # Get resolver name
            resolver = await user_service.get_user_by_id(user_id=ctx.deps.user_id)
            resolver_name = resolver.get("name", "Unknown")

            # Process the decision using workflow_service
            if decision_lower == "approve":
                await workflow_service.resolve_workflow(
                    workflow_id=workflow["id"],
                    resolver_user_id=ctx.deps.user_id,
                    resolver_name=resolver_name,
                    decision=workflow_service.WorkflowStatus.APPROVED,
                    reason=params.reason,
                )
                result = f"Approved deletion of '{workflow['target_title']}'. The chore has been archived."
            else:
                await workflow_service.resolve_workflow(
                    workflow_id=workflow["id"],
                    resolver_user_id=ctx.deps.user_id,
                    resolver_name=resolver_name,
                    decision=workflow_service.WorkflowStatus.REJECTED,
                    reason=params.reason,
                )
                result = f"Rejected deletion request for '{workflow['target_title']}'. The chore will remain active."

    except ValueError as e:
        logger.warning("Chore deletion response failed", extra={"error": str(e)})
        result = f"Error: {e!s}"
    except Exception as e:
        logger.error("Unexpected error in tool_respond_to_deletion", extra={"error": str(e)})
        result = "Error: Unable to process deletion response. Please try again."

    return result


def register_tools(agent: Agent[Deps, str]) -> None:
    """Register chore tools with the agent."""
    agent.tool(tool_define_chore)
    agent.tool(tool_log_chore)
    agent.tool(tool_request_chore_deletion)
    agent.tool(tool_respond_to_deletion)
