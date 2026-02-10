"""Onboarding module for household member management."""

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from pydantic_ai import Agent

    from src.agents.base import Deps

from src.core.module import ConfigField, ScheduledJob


class OnboardingModule:
    """Onboarding module for household member management.

    Provides:
    - Member approval workflow (admin-only)
    - Onboarding tools for joining households
    """

    @property
    def name(self) -> str:
        """Module name (unique identifier)."""
        return "onboarding"

    @property
    def description(self) -> str:
        """Module description (human-readable)."""
        return "Household member onboarding and approval management"

    def get_table_schemas(self) -> dict[str, str]:
        """Return table schemas for this module."""
        return {}

    def get_indexes(self) -> list[str]:
        """Return indexes for this module's tables."""
        return []

    def register_tools(self, agent: "Agent[Deps, str]") -> None:
        """Register tools with the agent instance."""
        import src.modules.onboarding.tools

        src.modules.onboarding.tools.register_tools(agent)

    def get_system_prompt_section(self) -> str:
        """Return the system prompt section for this module."""
        import src.modules.onboarding.prompt

        return src.modules.onboarding.prompt.ONBOARDING_PROMPT_SECTION

    def get_scheduled_jobs(self) -> list[ScheduledJob]:
        """Return scheduled jobs for this module."""
        return []

    def get_config_fields(self) -> list[ConfigField]:
        """Return configuration fields for this module."""
        return []
