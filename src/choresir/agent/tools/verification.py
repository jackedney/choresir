"""Verification tools for the AI agent."""

from __future__ import annotations

from pydantic_ai import RunContext

from choresir.agent.agent import AgentDeps
from choresir.agent.registry import registry
from choresir.errors import (
    AuthorizationError,
    InvalidTransitionError,
    NotFoundError,
    TakeoverLimitExceededError,
)

_DOMAIN_ERRORS = (
    NotFoundError,
    AuthorizationError,
    InvalidTransitionError,
    TakeoverLimitExceededError,
)


@registry.register
async def complete_task(
    ctx: RunContext[AgentDeps],
    task_id: int,
    member_id: int,
) -> str:
    """Mark a task as complete."""
    try:
        task = await ctx.deps.task_service.claim_completion(task_id, member_id)
        if task.status.value == "verified":
            return f"Task '{task.title}' completed."
        return f"Task '{task.title}' awaiting verification."
    except _DOMAIN_ERRORS as e:
        return str(e)


@registry.register
async def verify_completion(
    ctx: RunContext[AgentDeps],
    task_id: int,
    verifier_id: int,
    feedback: str | None = None,
) -> str:
    """Verify a task completion claim."""
    try:
        task = await ctx.deps.task_service.verify_completion(
            task_id, verifier_id, feedback
        )
        return f"Task '{task.title}' verified."
    except _DOMAIN_ERRORS as e:
        return str(e)


@registry.register
async def reject_completion(
    ctx: RunContext[AgentDeps],
    task_id: int,
    verifier_id: int,
) -> str:
    """Reject a completion claim, returning task to pending."""
    try:
        task = await ctx.deps.task_service.reject_completion(task_id, verifier_id)
        return f"Task '{task.title}' rejected, back to pending."
    except _DOMAIN_ERRORS as e:
        return str(e)
