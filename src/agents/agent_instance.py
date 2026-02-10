"""Agent instance and proxy for tool registration.

This module is separated to avoid circular imports between the agent
and tools that need to register themselves with the agent.
"""

import logging

import logfire
from pydantic_ai import Agent
from pydantic_ai.models.openrouter import OpenRouterModel, OpenRouterModelSettings
from pydantic_ai.providers.openrouter import OpenRouterProvider

from src.agents.base import Deps
from src.core.config import settings
from src.core.module_registry import get_modules


logger = logging.getLogger(__name__)


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


def _create_agent() -> Agent[Deps, str]:
    """Create the agent instance (called once during initialization)."""
    _ensure_logfire_configured()

    # Initialize the agent with OpenRouter
    api_key = settings.require_credential("openrouter_api_key", "OpenRouter API key")
    provider = OpenRouterProvider(api_key=api_key)

    # Configure provider routing if specified
    model_settings: OpenRouterModelSettings | None = None
    if settings.model_provider:
        model_settings = OpenRouterModelSettings(openrouter_provider={"only": [settings.model_provider]})

    model = OpenRouterModel(
        model_name=settings.model_id,
        provider=provider,
        settings=model_settings,
    )

    # Create the agent with retry support
    # Note: Retries are now handled by our custom retry handler
    # which provides intelligent error classification, exponential backoff,
    # and circuit breaker pattern
    return Agent(
        model=model,
        deps_type=Deps,
        retries=0,  # Disable native retries, use our custom handler
    )


def get_agent() -> Agent[Deps, str]:
    """Get or create the agent instance with all tools registered."""
    if _AgentState.instance is None:
        _AgentState.instance = _create_agent()
        _register_all_tools(_AgentState.instance)

    return _AgentState.instance


def _register_all_tools(agent_instance: Agent[Deps, str]) -> None:
    """Register all tool modules with the agent."""
    # Iterate through registered modules and register their tools
    # This avoids decorator execution at import time
    for module in get_modules().values():
        module.register_tools(agent_instance)
