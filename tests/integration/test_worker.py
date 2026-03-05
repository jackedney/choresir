"""Integration tests for job queue operations (claim, complete, retry, fail)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from choresir.enums import JobStatus
from choresir.models.job import MessageJob
from choresir.worker.queue import claim_next_job, complete_job, fail_job, retry_job


@pytest.fixture
async def session_factory(engine):
    """Provide a session factory bound to the in-memory engine."""
    return async_sessionmaker(engine, expire_on_commit=False)


async def _insert_job(
    session_factory: async_sessionmaker,
    job_id: str = "job-1",
    *,
    status: JobStatus = JobStatus.PENDING,
    run_after: datetime | None = None,
    attempts: int = 0,
) -> MessageJob:
    """Insert a job directly and return it."""
    job = MessageJob(
        id=job_id,
        sender_id="sender@c.us",
        group_id="group@g.us",
        body="test body",
        status=status,
        attempts=attempts,
        run_after=run_after,
    )
    async with session_factory() as session:
        session.add(job)
        await session.commit()
    return job


# -- claim_next_job ------------------------------------------------------------


@pytest.mark.anyio
async def test_claim_next_job_returns_pending(session_factory: async_sessionmaker):
    """Claiming picks a pending job and sets its status to processing."""
    await _insert_job(session_factory, "job-claim")

    async with session_factory() as session:
        claimed = await claim_next_job(session)

    assert claimed is not None
    assert claimed.id == "job-claim"
    assert claimed.status == JobStatus.PROCESSING
    assert claimed.claimed_at is not None


@pytest.mark.anyio
async def test_claim_next_job_skips_future_run_after(
    session_factory: async_sessionmaker,
):
    """A job with run_after in the future is not claimed."""
    future = datetime.now(UTC) + timedelta(hours=1)
    await _insert_job(session_factory, "job-future", run_after=future)

    async with session_factory() as session:
        claimed = await claim_next_job(session)

    assert claimed is None


# -- complete_job --------------------------------------------------------------


@pytest.mark.anyio
async def test_complete_job_sets_done(session_factory: async_sessionmaker):
    """Completing a claimed job transitions it to done."""
    await _insert_job(session_factory, "job-done")

    async with session_factory() as session:
        claimed = await claim_next_job(session)
    assert claimed is not None

    async with session_factory() as session:
        await complete_job(session, claimed)

    async with session_factory() as session:
        job = await session.get(MessageJob, "job-done")
        assert job is not None
        assert job.status == JobStatus.DONE
        assert job.completed_at is not None


# -- retry_job -----------------------------------------------------------------


@pytest.mark.anyio
async def test_retry_job_increments_attempts(session_factory: async_sessionmaker):
    """Retry sets pending with incremented attempts and a run_after."""
    await _insert_job(session_factory, "job-retry")

    async with session_factory() as session:
        claimed = await claim_next_job(session)
    assert claimed is not None

    delay_seconds = 10
    async with session_factory() as session:
        await retry_job(session, claimed, delay_seconds)

    async with session_factory() as session:
        job = await session.get(MessageJob, "job-retry")
        assert job is not None
        assert job.status == JobStatus.PENDING
        assert job.attempts == 1
        assert job.run_after is not None
        # SQLite returns naive datetimes; compare accordingly
        now_naive = datetime.now(UTC).replace(tzinfo=None)
        run_after = (
            job.run_after.replace(tzinfo=None)
            if job.run_after.tzinfo
            else job.run_after
        )
        assert run_after > now_naive


# -- fail_job ------------------------------------------------------------------


@pytest.mark.anyio
async def test_fail_job_sets_failed(session_factory: async_sessionmaker):
    """Failing a job marks it as permanently failed."""
    await _insert_job(session_factory, "job-fail")

    async with session_factory() as session:
        claimed = await claim_next_job(session)
    assert claimed is not None

    async with session_factory() as session:
        await fail_job(session, claimed)

    async with session_factory() as session:
        job = await session.get(MessageJob, "job-fail")
        assert job is not None
        assert job.status == JobStatus.FAILED
