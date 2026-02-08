"""Verification tools for the choresir agent."""

import logging
from datetime import datetime, timedelta
from typing import Literal

import logfire
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext

from src.agents.base import Deps
from src.services import chore_service, user_service, verification_service, workflow_service


logger = logging.getLogger(__name__)


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


class VerifyChore(BaseModel):
    """Parameters for verifying a chore completion."""

    workflow_id: str | None = Field(
        default=None,
        description="Workflow ID (optional, for direct reference)",
    )
    chore_title_fuzzy: str | None = Field(
        default=None,
        description="Chore title or partial match (fuzzy search, used if workflow_id not provided)",
    )
    decision: Literal["APPROVE", "REJECT"] = Field(description="Verification decision")
    reason: str | None = Field(default=None, description="Optional reason for the decision")


class ListMyChores(BaseModel):
    """Parameters for listing household chores assigned to a user."""

    target_user_phone: str | None = Field(
        default=None,
        description="Phone number of user to list chores for (None for requesting user)",
    )
    time_range: int = Field(
        default=7,
        description="Number of days to look back (default: 7)",
    )


def _format_chore_list(chores: list[dict], user_name: str) -> str:
    """
    Format chore list for WhatsApp display.

    Args:
        chores: List of chore records
        user_name: Name of the user

    Returns:
        Formatted chore list
    """
    if not chores:
        return f"{user_name} has no household chores assigned."

    now = datetime.now().astimezone()
    lines = [f"{user_name}'s Household Chores:"]

    # Group by state (compare as strings for robustness)
    todo_chores = [c for c in chores if c.get("current_state") == "TODO"]
    pending_chores = [c for c in chores if c.get("current_state") == "PENDING_VERIFICATION"]

    # Show TODO chores with deadlines
    for chore in sorted(todo_chores, key=lambda c: c.get("deadline", "")):
        deadline_str = chore.get("deadline", "")
        if deadline_str:
            deadline = datetime.fromisoformat(deadline_str)
            # Make naive datetimes timezone-aware for comparison
            if deadline.tzinfo is None:
                deadline = deadline.astimezone()
            status = "OVERDUE" if deadline < now else deadline.strftime("%b %d")
        else:
            status = "no deadline"
        lines.append(f"• {chore['title']} (due {status})")

    # Show pending verification
    for chore in pending_chores:
        lines.append(f"• {chore['title']} (pending verification)")

    return "\n".join(lines)


async def _get_verification_workflow_by_id(workflow_id: str) -> dict | str:
    """Get and validate a verification workflow by ID.

    Args:
        workflow_id: The workflow ID to look up

    Returns:
        The workflow dict if valid, or an error message string
    """
    workflow = await workflow_service.get_workflow(workflow_id=workflow_id)
    if not workflow:
        return f"Error: Workflow '{workflow_id}' not found."

    if workflow["type"] != workflow_service.WorkflowType.CHORE_VERIFICATION.value:
        return f"Error: Workflow '{workflow_id}' is not a chore verification workflow."

    if workflow["status"] != workflow_service.WorkflowStatus.PENDING.value:
        return f"Error: Workflow '{workflow_id}' is not pending (status: {workflow['status']})."

    return workflow


async def _get_verification_workflow_by_chore_title(chore_title_fuzzy: str) -> dict | str:
    """Find a verification workflow by chore title matching.

    Args:
        chore_title_fuzzy: The chore title to fuzzy match

    Returns:
        The workflow dict if found, or an error message string
    """
    all_chores = await chore_service.get_chores()
    matched_chores = _fuzzy_match_all_chores(all_chores, chore_title_fuzzy)

    if not matched_chores:
        return f'No chore found matching "{chore_title_fuzzy}".'

    # Find which matched chores have pending verification requests
    chores_with_pending_verification: list[tuple[dict, dict]] = []
    for chore in matched_chores:
        pending_workflow = await verification_service.get_pending_verification_workflow(chore_id=chore["id"])
        if pending_workflow:
            chores_with_pending_verification.append((chore, pending_workflow))

    if not chores_with_pending_verification:
        return f'No pending verification found for "{chore_title_fuzzy}".'

    if len(chores_with_pending_verification) > 1:
        chore_list = ", ".join(f"'{c['title']}'" for c, _ in chores_with_pending_verification)
        return f"Multiple chores with pending verification found: {chore_list}. Please specify which one."

    # Exactly one chore with pending verification - use it
    _matched_chore, pending_workflow = chores_with_pending_verification[0]
    return pending_workflow


async def _resolve_verification_workflow(
    workflow: dict,
    user_id: str,
    decision_lower: str,
    reason: str,
) -> str:
    """Resolve a verification workflow with the given decision.

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
        return f"Approved verification of '{workflow['target_title']}'."

    await workflow_service.resolve_workflow(
        workflow_id=workflow["id"],
        resolver_user_id=user_id,
        resolver_name=resolver_name,
        decision=workflow_service.WorkflowStatus.REJECTED,
        reason=reason,
    )
    return (
        f"Rejected verification of '{workflow['target_title']}'. "
        "Moving to conflict resolution (voting will be implemented)."
    )


async def tool_verify_chore(ctx: RunContext[Deps], params: VerifyChore) -> str:
    """Verify or reject a chore completion claim.

    Prevents self-verification. Approvals mark chore as completed.
    Rejections move to conflict resolution (voting).

    Supports referencing by workflow_id directly or by chore title matching.

    Args:
        ctx: Agent runtime context with dependencies
        params: Verification parameters

    Returns:
        Success or error message
    """
    try:
        with logfire.span("tool_verify_chore", workflow_id=params.workflow_id, decision=params.decision):
            # Validate input
            if not params.workflow_id and not params.chore_title_fuzzy:
                return "Error: Either workflow_id or chore_title_fuzzy must be provided."

            # Normalize decision
            decision_lower = params.decision.lower().strip()
            if decision_lower not in ("approve", "reject"):
                return f"Error: Invalid decision '{params.decision}'. Must be 'approve' or 'reject'."

            # Determine the workflow to resolve
            if params.workflow_id:
                workflow_result = await _get_verification_workflow_by_id(params.workflow_id)
            else:
                assert params.chore_title_fuzzy is not None  # Type narrowing: validated above
                workflow_result = await _get_verification_workflow_by_chore_title(params.chore_title_fuzzy)

            # Check if we got an error message instead of a workflow
            if isinstance(workflow_result, str):
                return workflow_result

            # Resolve the workflow
            return await _resolve_verification_workflow(
                workflow=workflow_result,
                user_id=ctx.deps.user_id,
                decision_lower=decision_lower,
                reason=params.reason or "",
            )

    except ValueError as e:
        logger.warning("Verification failed", extra={"error": str(e)})
        return f"Error: {e!s}"
    except Exception as e:
        logger.error("Unexpected error in tool_verify_chore", extra={"error": str(e)})
        return "Error: Unable to verify chore. Please try again."


async def tool_list_my_chores(ctx: RunContext[Deps], params: ListMyChores) -> str:
    """
    List household chores assigned to a user.

    Use this when the user asks "what chores do I have?", "my chores", "list chores",
    or wants to see their assigned household tasks. Shows todo, pending, and completed
    chores within the time range.

    Args:
        ctx: Agent runtime context with dependencies
        params: Query parameters

    Returns:
        Formatted list of household chores
    """
    try:
        with logfire.span("tool_list_my_chores", target=params.target_user_phone):
            # Determine target user
            if params.target_user_phone:
                target_user = await user_service.get_user_by_phone(phone=params.target_user_phone)
                if not target_user:
                    return f"Error: User with phone {params.target_user_phone} not found."
                target_user_id = target_user["id"]
                target_user_name = target_user["name"]
            else:
                target_user_id = ctx.deps.user_id
                target_user_name = ctx.deps.user_name

            # Get chores for the user in the time range
            time_range_start = datetime.now() - timedelta(days=params.time_range)
            chores = await chore_service.get_chores(
                user_id=target_user_id,
                time_range_start=time_range_start,
            )

            return _format_chore_list(chores, target_user_name)

    except Exception:
        logger.exception("Unexpected error in tool_list_my_chores")
        return "Error: Unable to retrieve chores. Please try again."


def register_tools(agent: Agent[Deps, str]) -> None:
    """Register tools with the agent."""
    agent.tool(tool_verify_chore)
    agent.tool(tool_list_my_chores)
