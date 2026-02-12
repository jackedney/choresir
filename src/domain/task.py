"""Task domain models and enums (unified replacement for chore + personal_chore)."""

from enum import StrEnum

from pydantic import BaseModel, Field


class TaskScope(StrEnum):
    """Whether a task is shared with household or personal."""

    SHARED = "shared"
    PERSONAL = "personal"


class VerificationType(StrEnum):
    """How task completion is verified."""

    NONE = "none"  # Auto-complete, no verification needed
    PEER = "peer"  # Any household member can verify
    PARTNER = "partner"  # Specific accountability partner verifies


class TaskState(StrEnum):
    """Task lifecycle state."""

    TODO = "TODO"
    PENDING_VERIFICATION = "PENDING_VERIFICATION"
    COMPLETED = "COMPLETED"
    ARCHIVED = "ARCHIVED"


class Task(BaseModel):
    """Task data transfer object."""

    id: str = Field(..., description="Unique task ID from database")
    created: str = Field(..., description="Creation timestamp (ISO format)")
    updated: str = Field(..., description="Last update timestamp (ISO format)")
    title: str = Field(..., description="Task title")
    description: str = Field(default="", description="Detailed task description")
    schedule_cron: str | None = Field(default=None, description="CRON expression or interval")
    deadline: str | None = Field(default=None, description="Next deadline (ISO format)")
    owner_id: str | None = Field(default=None, description="Creator/owner user ID")
    assigned_to: str | None = Field(default=None, description="Assigned user ID")
    scope: TaskScope = Field(..., description="shared or personal")
    verification: VerificationType = Field(
        default=VerificationType.NONE,
        description="How completion is verified",
    )
    accountability_partner_id: str | None = Field(
        default=None,
        description="Partner user ID for partner verification",
    )
    current_state: TaskState = Field(default=TaskState.TODO, description="Current lifecycle state")
    module: str = Field(default="task", description="Module tag for extensibility")
