"""Agent instance and proxy for tool registration.

This module is separated to avoid circular imports between the agent
and tools that need to register themselves with the agent.
"""

import logfire
from pydantic_ai import Agent
from pydantic_ai.models.openrouter import OpenRouterModel, OpenRouterProvider

from src.agents.base import Deps
from src.core.config import settings


class _LogfireState:
    """Singleton state for logfire configuration."""

    configured = False


def _ensure_logfire_configured() -> None:
    """Ensure Logfire is configured (lazy initialization)."""
    if not _LogfireState.configured:
        if settings.logfire_token:
            logfire.configure(token=settings.logfire_token)
        _LogfireState.configured = True


class _AgentState:
    """Singleton state for agent instance."""

    instance: Agent[Deps, str] | None = None


def _get_agent() -> Agent[Deps, str]:
    """Get or create the agent instance (lazy initialization)."""
    if _AgentState.instance is None:
        _ensure_logfire_configured()

        # Initialize the agent with OpenRouter
        api_key = settings.require_credential("openrouter_api_key", "OpenRouter API key")
        provider = OpenRouterProvider(api_key=api_key)
        model = OpenRouterModel(
            model_name=settings.model_id,
            provider=provider,
        )

        # Create the agent
        _AgentState.instance = Agent(
            model=model,
            deps_type=Deps,
            retries=2,
        )

        # Import tools AFTER agent creation to avoid circular imports
        # This allows tools to use @agent.tool decorator at module level
        from src.agents.tools import (  # noqa: F401
            analytics_tools,
            chore_tools,
            onboarding_tools,
            pantry_tools,
            verification_tools,
        )

    return _AgentState.instance


# Backwards compatibility: export agent that lazily initializes
# Tools import this and use @agent.tool decorator
class _AgentProxy:
    """Proxy for lazy agent access."""

    def __getattr__(self, name: str) -> object:
        return getattr(_get_agent(), name)


agent: Agent[Deps, str] = _AgentProxy()  # type: ignore[assignment]
