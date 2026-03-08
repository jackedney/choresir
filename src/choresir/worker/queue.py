"""Job queue operations for the SQLite-backed message processing pipeline."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col

from choresir.enums import JobStatus
from choresir.models.job import MessageJob


async def claim_next_job(session: AsyncSession) -> MessageJob | None:
    """Atomically claim the next pending job ready for processing."""
    now = datetime.now(UTC)
    stmt = (
        update(MessageJob)
        .where(
            col(MessageJob.status) == JobStatus.PENDING,
            (col(MessageJob.run_after) <= now) | (col(MessageJob.run_after).is_(None)),
        )
        .values(status=JobStatus.PROCESSING, claimed_at=now)
        .returning(MessageJob)
    )
    result = await session.execute(stmt)
    row = result.first()
    await session.commit()
    if row is None:
        return None
    return row[0]


async def complete_job(session: AsyncSession, job: MessageJob) -> None:
    """Mark a job as successfully completed."""
    now = datetime.now(UTC)
    stmt = (
        update(MessageJob)
        .where(col(MessageJob.id) == job.id)
        .values(status=JobStatus.DONE, completed_at=now)
    )
    await session.execute(stmt)
    await session.commit()


async def retry_job(
    session: AsyncSession,
    job: MessageJob,
    delay_seconds: int,
) -> None:
    """Return a job to pending with incremented attempts and a run_after delay."""
    now = datetime.now(UTC)
    stmt = (
        update(MessageJob)
        .where(col(MessageJob.id) == job.id)
        .values(
            status=JobStatus.PENDING,
            attempts=job.attempts + 1,
            run_after=now + timedelta(seconds=delay_seconds),
        )
    )
    await session.execute(stmt)
    await session.commit()


async def fail_job(session: AsyncSession, job: MessageJob) -> None:
    """Mark a job as permanently failed."""
    stmt = (
        update(MessageJob)
        .where(col(MessageJob.id) == job.id)
        .values(status=JobStatus.FAILED)
    )
    await session.execute(stmt)
    await session.commit()
