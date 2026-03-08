"""Integration tests for job queue operations."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from choresir.enums import JobStatus
from choresir.models.job import MessageJob
from choresir.worker.queue import claim_next_job, complete_job, fail_job, retry_job


@pytest.fixture
async def sf(engine):
    return async_sessionmaker(engine, expire_on_commit=False)


async def _insert(sf, job_id="job-1", **kw):
    job = MessageJob(
        id=job_id,
        sender_id="s@c.us",
        group_id="g@g.us",
        body="x",
        **kw,
    )
    async with sf() as s:
        s.add(job)
        await s.commit()


@pytest.mark.anyio
async def test_claim_next_job_returns_pending(sf):
    await _insert(sf, "job-claim")
    async with sf() as s:
        claimed = await claim_next_job(s)
    assert claimed is not None
    assert claimed.id == "job-claim"
    assert claimed.status == JobStatus.PROCESSING
    assert claimed.claimed_at is not None


@pytest.mark.anyio
async def test_claim_next_job_skips_future_run_after(sf):
    future = datetime.now(UTC) + timedelta(hours=1)
    await _insert(sf, "job-future", run_after=future)
    async with sf() as s:
        assert await claim_next_job(s) is None


@pytest.mark.anyio
async def test_complete_job_sets_done(sf):
    await _insert(sf, "job-done")
    async with sf() as s:
        claimed = await claim_next_job(s)
    assert claimed is not None
    async with sf() as s:
        await complete_job(s, claimed)
    async with sf() as s:
        job = await s.get(MessageJob, "job-done")
        assert job is not None
        assert job.status == JobStatus.DONE
        assert job.completed_at is not None


@pytest.mark.anyio
async def test_retry_job_increments_attempts(sf):
    await _insert(sf, "job-retry")
    async with sf() as s:
        claimed = await claim_next_job(s)
    assert claimed is not None
    async with sf() as s:
        await retry_job(s, claimed, 10)
    async with sf() as s:
        job = await s.get(MessageJob, "job-retry")
        assert job is not None
        assert job.status == JobStatus.PENDING
        assert job.attempts == 1
        assert job.run_after is not None
        now = datetime.now(UTC).replace(tzinfo=None)
        ra = job.run_after
        if ra.tzinfo:
            ra = ra.replace(tzinfo=None)
        assert ra > now


@pytest.mark.anyio
async def test_fail_job_sets_failed(sf):
    await _insert(sf, "job-fail")
    async with sf() as s:
        claimed = await claim_next_job(s)
    assert claimed is not None
    async with sf() as s:
        await fail_job(s, claimed)
    async with sf() as s:
        job = await s.get(MessageJob, "job-fail")
        assert job is not None
        assert job.status == JobStatus.FAILED
