"""Task and CompletionHistory table models."""

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Optional

from sqlmodel import Field, Relationship, SQLModel

from choresir.enums import TaskStatus, TaskVisibility, VerificationMode

if TYPE_CHECKING:
    from choresir.models.member import Member


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Task(SQLModel, table=True):
    """A household chore or task."""

    id: int | None = Field(default=None, primary_key=True)
    title: str
    description: str | None = None
    assignee_id: int = Field(foreign_key="member.id", index=True)
    status: TaskStatus = Field(default=TaskStatus.PENDING)
    verification_mode: VerificationMode = Field(default=VerificationMode.NONE)
    visibility: TaskVisibility = Field(default=TaskVisibility.SHARED)
    partner_id: int | None = Field(default=None, foreign_key="member.id")
    recurrence: str | None = None
    deadline: datetime | None = None
    next_deadline: datetime | None = None
    deletion_requested_by: int | None = Field(default=None, foreign_key="member.id")
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    assignee: Optional["Member"] = Relationship(
        back_populates="tasks",
        sa_relationship_kwargs={"foreign_keys": "[Task.assignee_id]"},
    )
    partner: Optional["Member"] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "[Task.partner_id]"},
    )
    completion_history: list["CompletionHistory"] = Relationship(
        back_populates="task",
    )


class CompletionHistory(SQLModel, table=True):
    """Immutable record of a task completion event."""

    id: int | None = Field(default=None, primary_key=True)
    task_id: int = Field(foreign_key="task.id", index=True)
    completed_by_id: int = Field(foreign_key="member.id")
    verified_by_id: int | None = Field(default=None, foreign_key="member.id")
    feedback: str | None = None
    completed_at: datetime = Field(default_factory=_utcnow)
    verified_at: datetime | None = None

    task: Optional["Task"] = Relationship(back_populates="completion_history")
