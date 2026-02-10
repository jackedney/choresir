"""Tasks module for chore management."""

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from pydantic_ai import Agent

    from src.agents.base import Deps

from src.core.module import ConfigField, ScheduledJob


class TasksModule:
    """Tasks module for household chore management.

    Provides:
    - Task CRUD operations (shared and personal chores)
    - Verification workflows
    - State machine for task lifecycle
    - Deletion approval workflows
    - Analytics and leaderboards
    - Robin Hood Protocol for task takeovers
    - Scheduled jobs for reminders and reports
    """

    @property
    def name(self) -> str:
        """Module name (unique identifier)."""
        return "tasks"

    @property
    def description(self) -> str:
        """Module description (human-readable)."""
        return "Household chore management with verification, analytics, and gamification"

    def get_table_schemas(self) -> dict[str, str]:
        """Return table schemas for this module."""
        import src.core.schema

        return src.core.schema.TASK_MODULE_SCHEMAS

    def get_indexes(self) -> list[str]:
        """Return indexes for this module's tables."""
        return [
            "CREATE INDEX IF NOT EXISTS idx_tasks_assigned_to ON tasks (assigned_to)",
            "CREATE INDEX IF NOT EXISTS idx_tasks_owner_id ON tasks (owner_id)",
            "CREATE INDEX IF NOT EXISTS idx_tasks_scope ON tasks (scope)",
            "CREATE INDEX IF NOT EXISTS idx_tasks_current_state ON tasks (current_state)",
            "CREATE INDEX IF NOT EXISTS idx_task_logs_task_id ON task_logs (task_id)",
            "CREATE INDEX IF NOT EXISTS idx_task_logs_user_id ON task_logs (user_id)",
            "CREATE INDEX IF NOT EXISTS idx_task_logs_original_assignee_id ON task_logs (original_assignee_id)",
            "CREATE INDEX IF NOT EXISTS idx_task_logs_actual_completer_id ON task_logs (actual_completer_id)",
            "CREATE INDEX IF NOT EXISTS idx_task_logs_verification_status ON task_logs (verification_status)",
        ]

    def register_tools(self, agent: "Agent[Deps, str]") -> None:
        """Register tools with the agent instance."""
        import src.modules.tasks.tools

        src.modules.tasks.tools.register_tools(agent)

    def get_system_prompt_section(self) -> str:
        """Return the system prompt section for this module."""
        import src.modules.tasks.prompt

        return src.modules.tasks.prompt.TASK_PROMPT_SECTION

    def get_scheduled_jobs(self) -> list[ScheduledJob]:
        """Return scheduled jobs for this module."""
        import src.modules.tasks.scheduler_jobs

        return src.modules.tasks.scheduler_jobs.get_scheduled_jobs()

    def get_config_fields(self) -> list[ConfigField]:
        """Return configuration fields for this module."""
        return []
