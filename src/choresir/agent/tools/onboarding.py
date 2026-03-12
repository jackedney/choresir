"""Member onboarding tools for the AI agent."""

from __future__ import annotations

from pydantic_ai import RunContext

from choresir.agent.agent import AgentDeps
from choresir.agent.registry import registry
from choresir.errors import InvalidTransitionError, NotFoundError

_DOMAIN_ERRORS = (NotFoundError, InvalidTransitionError)


@registry.register
async def check_member_status(
    ctx: RunContext[AgentDeps],
) -> str:
    """Check if the sender is pending onboarding or already active."""
    try:
        member = await ctx.deps.member_service.get_by_whatsapp_id(ctx.deps.sender_id)
    except NotFoundError:
        member = await ctx.deps.member_service.register_pending(ctx.deps.sender_id)
    return f"Member status: {member.status.value}. Name: {member.name or 'not set'}."


@registry.register
async def register_name(
    ctx: RunContext[AgentDeps],
    name: str,
) -> str:
    """Register the sender's name and activate their account."""
    try:
        member = await ctx.deps.member_service.activate(ctx.deps.sender_id, name)
        return f"Welcome {member.name}! Your account is now active."
    except _DOMAIN_ERRORS as e:
        return str(e)
