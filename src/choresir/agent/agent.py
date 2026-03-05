"""PydanticAI agent definition with dynamic system prompt."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from pydantic_ai import Agent, RunContext

from choresir.config import Settings
from choresir.services.member_service import MemberService
from choresir.services.task_service import TaskService

_PROMPT = (Path(__file__).parent / "prompts" / "base.txt").read_text()
_DEFAULT_MODEL = "litellm/openrouter/anthropic/claude-sonnet-4-20250514"


@dataclass
class AgentDeps:
    """Dependencies injected into every agent run."""

    task_service: TaskService
    member_service: MemberService


def create_agent(settings: Settings) -> Agent[AgentDeps, str]:
    """Build and return a configured PydanticAI agent."""
    agent: Agent[AgentDeps, str] = Agent(
        settings.llm_model or _DEFAULT_MODEL,
        deps_type=AgentDeps,
        system_prompt=_PROMPT,
    )

    @agent.system_prompt
    async def _household_ctx(ctx: RunContext[AgentDeps]) -> str:
        members = await ctx.deps.member_service.list_active()
        tasks = await ctx.deps.task_service.list_tasks()
        parts = []
        if members:
            lines = [f"- {m.name} (ID {m.id})" for m in members]
            parts.append("Active members:\n" + "\n".join(lines))
        if tasks:
            lines = [
                f"- [{t.status.value}] {t.title} (ID {t.id})"
                for t in tasks
            ]
            parts.append("Current tasks:\n" + "\n".join(lines))
        return "\n\n".join(parts) if parts else ""

    import choresir.agent.tools  # noqa: F401
    from choresir.agent.registry import registry

    registry.apply(agent)
    return agent
