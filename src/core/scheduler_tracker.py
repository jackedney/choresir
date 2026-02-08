"""Job execution tracking and monitoring for scheduled jobs."""

import asyncio
import logging
from collections import deque
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime
from typing import Any

from src.core.admin_notifier import notify_admins
from src.core.redis_client import redis_client


logger = logging.getLogger(__name__)


class JobTracker:
    """Track job execution history and health status."""

    def __init__(self) -> None:
        """Initialize job tracker."""
        # Fallback in-memory storage when Redis is unavailable
        self._memory_storage: dict[str, dict[str, Any]] = {}
        self._dead_letter_queue: deque[tuple[str, str, str]] = deque(maxlen=100)

    async def record_job_start(self, job_name: str) -> None:
        """Record job execution start.

        Args:
            job_name: Name of the scheduled job
        """
        now = datetime.now(UTC)
        key = f"scheduler:job:{job_name}:current_run"

        if redis_client.is_available:
            await redis_client.set(key, now.isoformat(), ttl_seconds=3600)
        else:
            if job_name not in self._memory_storage:
                self._memory_storage[job_name] = {}
            self._memory_storage[job_name]["current_run"] = now.isoformat()

    async def record_job_success(self, job_name: str) -> None:
        """Record successful job execution.

        Args:
            job_name: Name of the scheduled job
        """
        now = datetime.now(UTC)

        if redis_client.is_available:
            # Update last successful run
            await redis_client.set(
                f"scheduler:job:{job_name}:last_success",
                now.isoformat(),
                ttl_seconds=86400 * 7,  # Keep for 7 days
            )

            # Reset consecutive failures
            await redis_client.set(
                f"scheduler:job:{job_name}:consecutive_failures",
                "0",
                ttl_seconds=86400 * 7,
            )

            # Increment success count
            await redis_client.increment(f"scheduler:job:{job_name}:success_count")
            await redis_client.expire(f"scheduler:job:{job_name}:success_count", 86400 * 7)

            # Clear current run
            await redis_client.delete(f"scheduler:job:{job_name}:current_run")
        else:
            if job_name not in self._memory_storage:
                self._memory_storage[job_name] = {}

            self._memory_storage[job_name]["last_success"] = now.isoformat()
            self._memory_storage[job_name]["consecutive_failures"] = 0
            self._memory_storage[job_name]["success_count"] = self._memory_storage[job_name].get("success_count", 0) + 1
            self._memory_storage[job_name].pop("current_run", None)

    async def record_job_failure(self, job_name: str, error: str) -> int | None:
        """Record failed job execution.

        Args:
            job_name: Name of the scheduled job
            error: Error message
        """
        now = datetime.now(UTC)

        if redis_client.is_available:
            # Update last failure
            await redis_client.set(
                f"scheduler:job:{job_name}:last_failure",
                now.isoformat(),
                ttl_seconds=86400 * 7,
            )

            # Store last error
            await redis_client.set(
                f"scheduler:job:{job_name}:last_error",
                error[:500],  # Truncate long errors
                ttl_seconds=86400 * 7,
            )

            # Increment consecutive failures
            consecutive_key = f"scheduler:job:{job_name}:consecutive_failures"
            consecutive_failures = await redis_client.increment(consecutive_key)
            await redis_client.expire(consecutive_key, 86400 * 7)

            # Increment total failure count
            await redis_client.increment(f"scheduler:job:{job_name}:failure_count")
            await redis_client.expire(f"scheduler:job:{job_name}:failure_count", 86400 * 7)

            # Clear current run
            await redis_client.delete(f"scheduler:job:{job_name}:current_run")

            return consecutive_failures
        if job_name not in self._memory_storage:
            self._memory_storage[job_name] = {}

        self._memory_storage[job_name]["last_failure"] = now.isoformat()
        self._memory_storage[job_name]["last_error"] = error[:500]

        consecutive_failures = self._memory_storage[job_name].get("consecutive_failures", 0) + 1
        self._memory_storage[job_name]["consecutive_failures"] = consecutive_failures

        failure_count = self._memory_storage[job_name].get("failure_count", 0) + 1
        self._memory_storage[job_name]["failure_count"] = failure_count
        self._memory_storage[job_name].pop("current_run", None)

        return consecutive_failures

    async def get_job_status(self, job_name: str) -> dict[str, Any]:
        """Get job execution status.

        Args:
            job_name: Name of the scheduled job

        Returns:
            Dict with job status information
        """
        if redis_client.is_available:
            last_success = await redis_client.get(f"scheduler:job:{job_name}:last_success")
            last_failure = await redis_client.get(f"scheduler:job:{job_name}:last_failure")
            last_error = await redis_client.get(f"scheduler:job:{job_name}:last_error")
            consecutive_failures = await redis_client.get(f"scheduler:job:{job_name}:consecutive_failures")
            success_count = await redis_client.get(f"scheduler:job:{job_name}:success_count")
            failure_count = await redis_client.get(f"scheduler:job:{job_name}:failure_count")
            current_run = await redis_client.get(f"scheduler:job:{job_name}:current_run")

            return {
                "job_name": job_name,
                "last_success": last_success,
                "last_failure": last_failure,
                "last_error": last_error,
                "consecutive_failures": int(consecutive_failures) if consecutive_failures else 0,
                "success_count": int(success_count) if success_count else 0,
                "failure_count": int(failure_count) if failure_count else 0,
                "currently_running": current_run is not None,
                "current_run_started": current_run,
            }
        job_data = self._memory_storage.get(job_name, {})
        return {
            "job_name": job_name,
            "last_success": job_data.get("last_success"),
            "last_failure": job_data.get("last_failure"),
            "last_error": job_data.get("last_error"),
            "consecutive_failures": job_data.get("consecutive_failures", 0),
            "success_count": job_data.get("success_count", 0),
            "failure_count": job_data.get("failure_count", 0),
            "currently_running": "current_run" in job_data,
            "current_run_started": job_data.get("current_run"),
        }

    async def add_to_dead_letter_queue(self, job_name: str, error: str, context: str) -> None:
        """Add persistently failed job to dead letter queue.

        Args:
            job_name: Name of the scheduled job
            error: Error message
            context: Additional context about the failure
        """
        timestamp = datetime.now(UTC).isoformat()
        self._dead_letter_queue.append((job_name, error, context))

        logger.error(
            "Job added to dead letter queue",
            extra={
                "job_name": job_name,
                "error": error,
                "context": context,
                "timestamp": timestamp,
            },
        )

        # Store in Redis if available
        if redis_client.is_available:
            dlq_key = f"scheduler:dlq:{job_name}:{timestamp}"
            await redis_client.set(
                dlq_key,
                f"{error} | {context}",
                ttl_seconds=86400 * 30,  # Keep for 30 days
            )

    def get_dead_letter_queue(self) -> list[dict[str, str]]:
        """Get all items in dead letter queue.

        Returns:
            List of dead letter queue items
        """
        return [
            {
                "job_name": job_name,
                "error": error,
                "context": context,
            }
            for job_name, error, context in self._dead_letter_queue
        ]


# Global job tracker instance
job_tracker = JobTracker()


async def retry_job_with_backoff(
    job_func: Callable[[], Awaitable[None]],
    job_name: str,
    max_retries: int = 3,
    base_delay: float = 2.0,
) -> None:
    """Execute job with retry logic and exponential backoff.

    Args:
        job_func: Async function to execute
        job_name: Name of the job for tracking
        max_retries: Maximum number of retry attempts
        base_delay: Base delay in seconds for exponential backoff
    """
    await job_tracker.record_job_start(job_name)

    last_error = None
    for attempt in range(max_retries):
        try:
            logger.info("Executing %s (attempt %d/%d)", job_name, attempt + 1, max_retries)
            await job_func()

            # Success - record and return
            await job_tracker.record_job_success(job_name)
            logger.info("%s completed successfully", job_name)
            return

        except Exception as e:
            last_error = str(e)
            logger.error(
                "%s failed on attempt %d/%d: %s",
                job_name,
                attempt + 1,
                max_retries,
                last_error,
            )

            # If this is not the last attempt, wait before retrying
            if attempt < max_retries - 1:
                delay = base_delay**attempt
                logger.info("Retrying %s in %ds", job_name, delay)
                await asyncio.sleep(delay)

    # All retries exhausted - record failure
    error_msg = f"Failed after {max_retries} attempts: {last_error}"
    consecutive_failures = await job_tracker.record_job_failure(job_name, error_msg)

    # Notify admins on failure
    logger.error(
        f"{job_name} failed after all retry attempts",
        extra={
            "error": error_msg,
            "consecutive_failures": consecutive_failures,
        },
    )

    await notify_admins(
        message=f"Scheduled job '{job_name}' failed after {max_retries} attempts: {last_error}",
        severity="critical",
    )

    # Add to dead letter queue if failures are persistent (3+ consecutive)
    consecutive_failure_threshold = 3
    if consecutive_failures and consecutive_failures >= consecutive_failure_threshold:
        await job_tracker.add_to_dead_letter_queue(
            job_name=job_name,
            error=last_error or "Unknown error",
            context=f"Failed {consecutive_failures} consecutive times",
        )

        await notify_admins(
            message=(
                f"Scheduled job '{job_name}' has {consecutive_failures} consecutive failures "
                "and was added to dead letter queue"
            ),
            severity="critical",
        )
