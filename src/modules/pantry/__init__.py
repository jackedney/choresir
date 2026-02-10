"""Pantry module for inventory and shopping list management."""

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from pydantic_ai import Agent

    from src.agents.base import Deps

from src.core.module import ConfigField, ScheduledJob


class PantryModule:
    """Pantry module for inventory and shopping list management.

    Provides:
    - Shopping list management (add, remove, get, checkout)
    - Pantry inventory tracking (mark items low/out, check status)
    """

    @property
    def name(self) -> str:
        """Module name (unique identifier)."""
        return "pantry"

    @property
    def description(self) -> str:
        """Module description (human-readable)."""
        return "Pantry inventory and shopping list management"

    def get_table_schemas(self) -> dict[str, str]:
        """Return table schemas for this module."""
        return {
            "pantry_items": """CREATE TABLE IF NOT EXISTS pantry_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created TEXT NOT NULL DEFAULT (datetime('now')),
        updated TEXT NOT NULL DEFAULT (datetime('now')),
        name TEXT NOT NULL UNIQUE,
        quantity INTEGER,
        status TEXT NOT NULL CHECK (status IN ('IN_STOCK', 'LOW', 'OUT')),
        last_restocked TEXT
    )""",
            "shopping_list": """CREATE TABLE IF NOT EXISTS shopping_list (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created TEXT NOT NULL DEFAULT (datetime('now')),
        updated TEXT NOT NULL DEFAULT (datetime('now')),
        item_name TEXT NOT NULL,
        added_by INTEGER NOT NULL REFERENCES members(id),
        added_at TEXT NOT NULL,
        quantity INTEGER,
        notes TEXT
    )""",
        }

    def get_indexes(self) -> list[str]:
        """Return indexes for this module's tables."""
        return ["CREATE INDEX IF NOT EXISTS idx_shopping_list_added_by ON shopping_list (added_by)"]

    def register_tools(self, agent: "Agent[Deps, str]") -> None:
        """Register tools with the agent instance."""
        import src.modules.pantry.tools

        src.modules.pantry.tools.register_tools(agent)

    def get_system_prompt_section(self) -> str:
        """Return the system prompt section for this module."""
        import src.modules.pantry.prompt

        return src.modules.pantry.prompt.PANTRY_PROMPT_SECTION

    def get_scheduled_jobs(self) -> list[ScheduledJob]:
        """Return scheduled jobs for this module."""
        return []

    def get_config_fields(self) -> list[ConfigField]:
        """Return configuration fields for this module."""
        return []
