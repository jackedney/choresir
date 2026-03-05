"""MessageJob table model for the SQLite-backed job queue."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel

from choresir.enums import JobStatus


def _utcnow() -> datetime:
    return datetime.now(UTC)


class MessageJob(SQLModel, table=True):
    """Queued WhatsApp message for async processing."""

    id: str = Field(primary_key=True)
    sender_id: str = Field(index=True)
    group_id: str
    body: str
    status: JobStatus = Field(default=JobStatus.PENDING, index=True)
    attempts: int = Field(default=0)
    run_after: datetime | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    claimed_at: datetime | None = None
    completed_at: datetime | None = None
