"""Onboarding tools for the choresir agent."""

import logging

import logfire
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext

from src.agents.base import Deps
from src.services import user_service


logger = logging.getLogger(__name__)


class ApproveMember(BaseModel):
    """Parameters for approving a pending member."""

    target_phone: str = Field(description="Phone number of the user to approve (E.164 format)")


async def tool_approve_member(ctx: RunContext[Deps], params: ApproveMember) -> str:
    """
    Approve a pending member (admin-only).

    Changes user status from pending_name to active.

    Args:
        ctx: Agent runtime context with dependencies
        params: Approval parameters

    Returns:
        Success or error message
    """
    try:
        with logfire.span("tool_approve_member", admin_id=ctx.deps.user_id, target=params.target_phone):
            # Admin-only check will be performed in the service layer
            await user_service.approve_member(
                admin_user_id=ctx.deps.user_id,
                target_phone=params.target_phone,
            )

            return f"User {params.target_phone} has been approved and is now active."

    except PermissionError as e:
        logger.warning("Unauthorized approval attempt", extra={"user_id": ctx.deps.user_id, "error": str(e)})
        return "Error: Only admins can approve members."
    except ValueError as e:
        logger.warning("Approval failed", extra={"error": str(e)})
        return f"Error: {e!s}"
    except Exception as e:
        logger.error("Unexpected error in tool_approve_member", extra={"error": str(e)})
        return "Error: Unable to approve member. Please try again."


def register_tools(agent: Agent[Deps, str]) -> None:
    """Register tools with the agent."""
    agent.tool(tool_approve_member)
