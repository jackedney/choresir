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
        return {
            "tasks": """CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created TEXT NOT NULL DEFAULT (datetime('now')),
        updated TEXT NOT NULL DEFAULT (datetime('now')),
        title TEXT NOT NULL,
        description TEXT,
        schedule_cron TEXT,
        deadline TEXT,
        owner_id INTEGER REFERENCES members(id),
        assigned_to INTEGER REFERENCES members(id),
        scope TEXT NOT NULL CHECK (scope IN ('shared', 'personal')),
        verification TEXT NOT NULL DEFAULT 'none'
            CHECK (verification IN ('none', 'peer', 'partner')),
        accountability_partner_id INTEGER REFERENCES members(id),
        current_state TEXT NOT NULL DEFAULT 'TODO'
            CHECK (current_state IN ('TODO', 'PENDING_VERIFICATION', 'COMPLETED', 'ARCHIVED')),
        module TEXT NOT NULL DEFAULT 'task'
    )""",
            "task_logs": """CREATE TABLE IF NOT EXISTS task_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created TEXT NOT NULL DEFAULT (datetime('now')),
        updated TEXT NOT NULL DEFAULT (datetime('now')),
        task_id INTEGER REFERENCES tasks(id),
        user_id INTEGER REFERENCES members(id),
        action TEXT NOT NULL,
        notes TEXT,
        timestamp TEXT,
        verification_status TEXT CHECK (
            verification_status IN ('SELF_VERIFIED', 'PENDING', 'VERIFIED', 'REJECTED')
        ),
        verifier_id INTEGER REFERENCES members(id),
        verifier_feedback TEXT,
        original_assignee_id INTEGER REFERENCES members(id),
        actual_completer_id INTEGER REFERENCES members(id),
        is_swap INTEGER DEFAULT 0
    )""",
            "robin_hood_swaps": """CREATE TABLE IF NOT EXISTS robin_hood_swaps (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created TEXT NOT NULL DEFAULT (datetime('now')),
        updated TEXT NOT NULL DEFAULT (datetime('now')),
        user_id INTEGER NOT NULL REFERENCES members(id),
        week_start_date TEXT NOT NULL,
        takeover_count INTEGER NOT NULL,
        UNIQUE(user_id, week_start_date)
    )""",
        }

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
