"""Worker loop with rate limiting and retry logic for message processing."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable, Coroutine
from typing import Any

from aiolimiter import AsyncLimiter
from sqlalchemy.ext.asyncio import async_sessionmaker

from choresir.config import Settings
from choresir.models.job import MessageJob
from choresir.worker.queue import claim_next_job, complete_job, fail_job, retry_job

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 1.0
_RATE_LIMIT_RETRY_DELAY = 5


def init_limiters(
    settings: Settings,
) -> tuple[AsyncLimiter, dict[str, AsyncLimiter]]:
    """Create global limiter and empty per-user dict from settings."""
    global_limiter = AsyncLimiter(
        settings.global_rate_limit_count,
        settings.global_rate_limit_seconds,
    )
    user_limiters: dict[str, AsyncLimiter] = {}
    return global_limiter, user_limiters


def get_user_limiter(
    user_limiters: dict[str, AsyncLimiter],
    user_id: str,
    settings: Settings,
) -> AsyncLimiter:
    """Lazy-create and return a per-user rate limiter."""
    if user_id not in user_limiters:
        user_limiters[user_id] = AsyncLimiter(
            settings.per_user_rate_limit_count,
            settings.per_user_rate_limit_seconds,
        )
    return user_limiters[user_id]


async def _process_job(
    job: MessageJob,
    session_factory: async_sessionmaker,
    process_fn: Callable[[MessageJob], Coroutine[Any, Any, None]],
    global_limiter: AsyncLimiter,
    user_limiters: dict[str, AsyncLimiter],
    settings: Settings,
) -> None:
    """Process a single claimed job with rate limiting and error handling."""
    try:
        # Check global rate limit
        if not global_limiter.has_capacity(1):
            logger.info("Global rate limit reached, deferring job %s", job.id)
            async with session_factory() as session:
                await retry_job(session, job, _RATE_LIMIT_RETRY_DELAY)
            return

        # Check per-user rate limit
        user_limiter = get_user_limiter(user_limiters, job.sender_id, settings)
        if not user_limiter.has_capacity(1):
            logger.info(
                "Per-user rate limit for %s, deferring job %s",
                job.sender_id,
                job.id,
            )
            async with session_factory() as session:
                await retry_job(session, job, _RATE_LIMIT_RETRY_DELAY)
            return

        # Acquire rate limit capacity and process
        async with global_limiter, user_limiter:
            await process_fn(job)

        async with session_factory() as session:
            await complete_job(session, job)

    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Error processing job %s", job.id)
        try:
            async with session_factory() as session:
                await fail_job(session, job)
        except Exception:
            logger.exception("Failed to mark job %s as failed", job.id)


async def message_worker_loop(
    session_factory: async_sessionmaker,
    process_fn: Callable[[MessageJob], Coroutine[Any, Any, None]],
    settings: Settings,
) -> None:
    """Run the message processing worker in an infinite loop.

    Claims jobs from the queue, applies rate limits, calls process_fn,
    and handles retries and failures. Designed to run as a background
    coroutine cancelled during shutdown.
    """
    global_limiter, user_limiters = init_limiters(settings)

    while True:
        try:
            async with session_factory() as session:
                job = await claim_next_job(session)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Error claiming next job")
            await asyncio.sleep(_POLL_INTERVAL)
            continue

        if job is None:
            await asyncio.sleep(_POLL_INTERVAL)
            continue

        await _process_job(
            job,
            session_factory,
            process_fn,
            global_limiter,
            user_limiters,
            settings,
        )
