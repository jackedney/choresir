"""Module Protocol defining the plugin interface for modular architecture."""

from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING, Protocol

from pydantic import BaseModel


if TYPE_CHECKING:
    from pydantic_ai import Agent

    from src.agents.base import Deps


class ScheduledJob(BaseModel):
    """Scheduled job definition."""

    id: str
    name: str
    cron: str
    func: Callable[[], Awaitable[None]]


class ConfigField(BaseModel):
    """Configuration field definition."""

    name: str
    type: str
    required: bool
    default: str | None = None
    description: str


class Module(Protocol):
    """Protocol defining the interface for feature modules. Self-contained plugins with schemas, tools, and config."""

    @property
    def name(self) -> str:
        """Module name (unique identifier)."""
        ...

    @property
    def description(self) -> str:
        """Module description (human-readable)."""
        ...

    def get_table_schemas(self) -> dict[str, str]:
        """Return table schemas for this module.

        Returns:
            Dictionary mapping table names to CREATE TABLE SQL statements
        """
        ...

    def get_indexes(self) -> list[str]:
        """Return indexes for this module's tables.

        Returns:
            List of CREATE INDEX SQL statements
        """
        ...

    def register_tools(self, agent: "Agent[Deps, str]") -> None:
        """Register tools with the agent instance.

        Args:
            agent: Pydantic AI agent instance to register tools with
        """
        ...

    def get_system_prompt_section(self) -> str:
        """Return the system prompt section for this module.

        Returns:
            System prompt text describing module capabilities
        """
        ...

    def get_scheduled_jobs(self) -> list[ScheduledJob]:
        """Return scheduled jobs for this module.

        Returns:
            List of ScheduledJob definitions
        """
        ...

    def get_config_fields(self) -> list[ConfigField]:
        """Return configuration fields for this module.

        Returns:
            List of ConfigField definitions
        """
        ...
