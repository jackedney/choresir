"""Verification tools for the choresir agent."""

import logging
from datetime import datetime, timedelta
from typing import Literal

import logfire
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext

from src.agents.base import Deps
from src.core import db_client
from src.services import chore_service, user_service, verification_service
from src.services.verification_service import VerificationDecision


logger = logging.getLogger(__name__)


class VerifyChore(BaseModel):
    """Parameters for verifying a chore completion."""

    log_id: str = Field(description="Log ID of the chore claim to verify")
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
            if deadline < now:
                status = "OVERDUE"
            else:
                status = deadline.strftime("%b %d")
        else:
            status = "no deadline"
        lines.append(f"• {chore['title']} (due {status})")

    # Show pending verification
    for chore in pending_chores:
        lines.append(f"• {chore['title']} (pending verification)")

    return "\n".join(lines)


async def tool_verify_chore(ctx: RunContext[Deps], params: VerifyChore) -> str:
    """
    Verify or reject a chore completion claim.

    Prevents self-verification. Approvals mark chore as completed.
    Rejections move to conflict resolution (voting).

    Args:
        ctx: Agent runtime context with dependencies
        params: Verification parameters

    Returns:
        Success or error message
    """
    try:
        with logfire.span("tool_verify_chore", log_id=params.log_id, decision=params.decision):
            # Get the log to find the chore ID
            log_record = await db_client.get_record(collection="logs", record_id=params.log_id)
            chore_id = log_record["chore_id"]

            # Get chore details for response
            chore = await chore_service.get_chore_by_id(chore_id=chore_id)

            # Perform verification
            decision_enum = VerificationDecision(params.decision)
            updated_chore = await verification_service.verify_chore(
                chore_id=chore_id,
                verifier_user_id=ctx.deps.user_id,
                decision=decision_enum,
                reason=params.reason or "",
            )

            if params.decision == "APPROVE":
                deadline_str = datetime.fromisoformat(updated_chore["deadline"]).strftime("%b %d")
                return f"Chore '{chore['title']}' approved. Next deadline: {deadline_str}."
            return f"Chore '{chore['title']}' rejected. Moving to conflict resolution (voting will be implemented)."

    except PermissionError:
        logger.warning("Self-verification attempt", extra={"user_id": ctx.deps.user_id, "log_id": params.log_id})
        return "Error: You cannot verify your own chore claim."
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
