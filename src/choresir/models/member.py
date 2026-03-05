"""Member table model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlmodel import Field, Relationship, SQLModel

from choresir.enums import MemberRole, MemberStatus

if TYPE_CHECKING:
    from choresir.models.task import Task


class Member(SQLModel, table=True):
    """A household member registered via WhatsApp."""

    id: int | None = Field(default=None, primary_key=True)
    whatsapp_id: str = Field(unique=True, index=True)
    name: str | None = None
    role: MemberRole = Field(default=MemberRole.MEMBER)
    status: MemberStatus = Field(default=MemberStatus.PENDING)

    tasks: list[Task] = Relationship(
        back_populates="assignee",
        sa_relationship_kwargs={"foreign_keys": "Task.assignee_id"},
    )
