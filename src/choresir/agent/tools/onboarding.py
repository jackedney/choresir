"""Member onboarding tools for the AI agent."""

from __future__ import annotations

from pydantic_ai import RunContext

from choresir.agent.registry import registry
from choresir.errors import NotFoundError


@registry.register
async def check_member_status(
    ctx: RunContext,  # type: ignore[type-arg]
    whatsapp_id: str,
) -> str:
    """Check if a member is pending onboarding or already active."""
    try:
        member = await ctx.deps.member_service.get_by_whatsapp_id(whatsapp_id)
        return (
            f"Member status: {member.status.value}. Name: {member.name or 'not set'}."
        )
    except NotFoundError:
        return "Member not found in the system."


@registry.register
async def register_name(
    ctx: RunContext,  # type: ignore[type-arg]
    whatsapp_id: str,
    name: str,
) -> str:
    """Register a member's name and activate their account."""
    try:
        member = await ctx.deps.member_service.activate(whatsapp_id, name)
        return f"Welcome {member.name}! Your account is now active."
    except NotFoundError:
        return "Member not found in the system."
    except Exception as e:  # noqa: BLE001
        return f"Failed to register name: {e}"
