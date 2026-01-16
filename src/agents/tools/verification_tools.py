"""Verification tools for the choresir agent."""

from datetime import datetime, timedelta
from typing import Literal

import logfire
from pydantic import BaseModel, Field

from src.agents.base import Deps
from src.agents.choresir_agent import agent
from src.core import db_client
from src.domain.chore import ChoreState
from src.services import chore_service, user_service, verification_service
from src.services.verification_service import VerificationDecision


class VerifyChore(BaseModel):
    """Parameters for verifying a chore completion."""

    log_id: str = Field(description="Log ID of the chore claim to verify")
    decision: Literal["APPROVE", "REJECT"] = Field(description="Verification decision")
    reason: str | None = Field(default=None, description="Optional reason for the decision")


class GetStatus(BaseModel):
    """Parameters for getting chore status."""

    target_user_phone: str | None = Field(
        default=None,
        description="Phone number of user to get status for (None for requesting user)",
    )
    time_range: int = Field(
        default=7,
        description="Number of days to look back (default: 7)",
    )


def _format_chore_status(chores: list[dict], user_name: str) -> str:
    """
    Format chore status for WhatsApp display.

    Args:
        chores: List of chore records
        user_name: Name of the user

    Returns:
        Formatted status message
    """
    if not chores:
        return f"{user_name}: No chores found."

    # Count by state
    pending = sum(1 for c in chores if c["current_state"] == ChoreState.PENDING_VERIFICATION)
    completed = sum(1 for c in chores if c["current_state"] == ChoreState.COMPLETED)
    todo = sum(1 for c in chores if c["current_state"] == ChoreState.TODO)

    # Find next due
    now = datetime.now()
    upcoming_chores = [
        c for c in chores if c["current_state"] == ChoreState.TODO and datetime.fromisoformat(c["deadline"]) > now
    ]

    next_due_msg = ""
    if upcoming_chores:
        next_chore = min(upcoming_chores, key=lambda c: c["deadline"])
        next_date = datetime.fromisoformat(next_chore["deadline"]).strftime("%b %d")
        next_due_msg = f" Next: '{next_chore['title']}' ({next_date})"

    return f"{user_name}: {todo} todo, {pending} pending, {completed} completed.{next_due_msg}"


@agent.tool
async def tool_verify_chore(ctx: Deps, params: VerifyChore) -> str:
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
                verifier_user_id=ctx.user_id,
                decision=decision_enum,
                reason=params.reason or "",
            )

            if params.decision == "APPROVE":
                deadline_str = datetime.fromisoformat(updated_chore["deadline"]).strftime("%b %d")
                return f"Chore '{chore['title']}' approved. Next deadline: {deadline_str}."
            return f"Chore '{chore['title']}' rejected. Moving to conflict resolution (voting will be implemented)."

    except PermissionError:
        logfire.warning("Self-verification attempt", user_id=ctx.user_id, log_id=params.log_id)
        return "Error: You cannot verify your own chore claim."
    except ValueError as e:
        logfire.warning("Verification failed", error=str(e))
        return f"Error: {e!s}"
    except Exception as e:
        logfire.error("Unexpected error in tool_verify_chore", error=str(e))
        return "Error: Unable to verify chore. Please try again."


@agent.tool
async def tool_get_status(ctx: Deps, params: GetStatus) -> str:
    """
    Get chore status summary for a user.

    Shows todo, pending, and completed chores within the time range.

    Args:
        ctx: Agent runtime context with dependencies
        params: Status query parameters

    Returns:
        Formatted status summary
    """
    try:
        with logfire.span("tool_get_status", target=params.target_user_phone):
            # Determine target user
            if params.target_user_phone:
                target_user = await user_service.get_user_by_phone(phone=params.target_user_phone)
                if not target_user:
                    return f"Error: User with phone {params.target_user_phone} not found."
                target_user_id = target_user["id"]
                target_user_name = target_user["name"]
            else:
                target_user_id = ctx.user_id
                target_user_name = ctx.user_name

            # Get chores for the user in the time range
            time_range_start = datetime.now() - timedelta(days=params.time_range)
            chores = await chore_service.get_chores(
                user_id=target_user_id,
                time_range_start=time_range_start,
            )

            return _format_chore_status(chores, target_user_name)

    except Exception as e:
        logfire.error("Unexpected error in tool_get_status", error=str(e))
        return "Error: Unable to retrieve status. Please try again."
