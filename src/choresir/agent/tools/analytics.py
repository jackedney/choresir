"""Analytics tools for the AI agent."""

from __future__ import annotations

from pydantic_ai import RunContext

from choresir.agent.agent import AgentDeps
from choresir.agent.registry import registry
from choresir.errors import NotFoundError

_DOMAIN_ERRORS = (NotFoundError,)


@registry.register
async def get_stats(
    ctx: RunContext[AgentDeps],
    member_id: int,
) -> str:
    """Get completion stats for a household member."""
    try:
        s = await ctx.deps.task_service.get_stats(member_id)
        count = s["completion_count"]
        return f"Member {s['member_id']}: {count} completions, rank #{s['rank']}."
    except _DOMAIN_ERRORS as e:
        return str(e)


@registry.register
async def get_leaderboard(
    ctx: RunContext[AgentDeps],
) -> str:
    """Get the household task completion leaderboard."""
    entries = await ctx.deps.task_service.get_leaderboard()
    if not entries:
        return "No completions recorded yet."
    return "\n".join(
        f"#{e['rank']} Member {e['member_id']}: {e['completion_count']}"
        for e in entries
    )


@registry.register
async def get_overdue_tasks(
    ctx: RunContext[AgentDeps],
) -> str:
    """Get all overdue tasks."""
    tasks = await ctx.deps.task_service.get_overdue()
    if not tasks:
        return "No overdue tasks."
    return "\n".join(f"- {t.title} (ID {t.id}, due: {t.deadline})" for t in tasks)
