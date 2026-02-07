"""Chore domain models and enums."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ChoreState(StrEnum):
    """Chore completion state."""

    TODO = "TODO"
    PENDING_VERIFICATION = "PENDING_VERIFICATION"
    COMPLETED = "COMPLETED"
    CONFLICT = "CONFLICT"
    DEADLOCK = "DEADLOCK"
    ARCHIVED = "ARCHIVED"


class Chore(BaseModel):
    """Chore data transfer object."""

    id: str = Field(..., description="Unique chore ID from PocketBase")
    title: str = Field(..., description="Chore title (e.g., 'Wash Dishes')")
    description: str = Field(default="", description="Detailed chore description")
    schedule_cron: str = Field(
        ...,
        description="Schedule as CRON expression or interval (e.g., '0 20 * * *' or 'every 3 days')",
    )
    assigned_to: str = Field(..., description="User ID of assigned household member")
    current_state: ChoreState = Field(default=ChoreState.TODO, description="Current chore state")
    deadline: datetime = Field(..., description="Next deadline for chore completion")
