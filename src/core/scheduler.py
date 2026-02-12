"""Scheduler for automated jobs (reminders, reports, etc.)."""

import logging
from functools import partial

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.core.module_registry import get_modules
from src.core.scheduler_tracker import retry_job_with_backoff
from src.services import group_context_service, workflow_service


logger = logging.getLogger(__name__)

# Cron expression has 5 parts: minute hour day_of_month month day_of_week
CRON_PART_COUNT = 5

# Global scheduler instance
scheduler = AsyncIOScheduler()


async def expire_workflows() -> None:
    """Expire pending workflows past their expiration time.

    Runs every hour. Finds workflows where expires_at < now and status = PENDING,
    then updates their status to EXPIRED.
    """
    logger.info("Running workflow expiry job")

    try:
        # Call workflow service expiry function
        count = await workflow_service.expire_old_workflows()

        logger.info(f"Completed workflow expiry job: {count} workflows expired")

    except Exception as e:
        logger.error(f"Error in workflow expiry job: {e}")


async def cleanup_group_context() -> None:
    """Delete expired group context messages.

    Runs every hour. Finds messages where expires_at < now and deletes them
    to prevent unbounded database growth.
    """
    logger.info("Running group context cleanup job")

    try:
        # Call group context cleanup function
        count = await group_context_service.cleanup_expired_group_context()

        logger.info(f"Completed group context cleanup job: {count} messages deleted")

    except Exception as e:
        logger.error(f"Error in group context cleanup job: {e}")


def _parse_cron_expression(cron: str) -> dict[str, str | int | None]:
    """Parse cron expression into CronTrigger arguments.

    Args:
        cron: Cron expression (e.g., "0 8 * * *" or "0 20 * * 0")

    Returns:
        Dictionary with CronTrigger keyword arguments
    """
    parts = cron.split()
    if len(parts) != CRON_PART_COUNT:
        msg = f"Invalid cron expression: {cron}"
        raise ValueError(msg)

    # Cron format: minute hour day_of_month month day_of_week
    return {
        "minute": parts[0],
        "hour": parts[1],
        "day": parts[2],
        "month": parts[3],
        "day_of_week": parts[4],
    }


def start_scheduler() -> None:
    """Start the scheduler and register all jobs.

    This should be called during FastAPI app startup.
    """
    logger.info("Starting scheduler")

    # Register core jobs
    scheduler.add_job(
        partial(retry_job_with_backoff, expire_workflows, "expire_workflows"),
        trigger=CronTrigger(hour="*", minute=45),
        id="expire_workflows",
        name="Expire Workflows",
        replace_existing=True,
    )
    logger.info("Scheduled workflow expiry job: hourly at :45")

    scheduler.add_job(
        partial(retry_job_with_backoff, cleanup_group_context, "cleanup_group_context"),
        trigger=CronTrigger(hour="*", minute=50),
        id="cleanup_group_context",
        name="Cleanup Group Context",
        replace_existing=True,
    )
    logger.info("Scheduled group context cleanup job: hourly at :50")

    # Register module jobs
    modules = get_modules()
    for module_name, module in modules.items():
        try:
            scheduled_jobs = module.get_scheduled_jobs()
            for job in scheduled_jobs:
                # Parse cron expression
                cron_args = _parse_cron_expression(job.cron)

                # Register job
                scheduler.add_job(
                    job.func,
                    trigger=CronTrigger(**cron_args),
                    id=job.id,
                    name=job.name,
                    replace_existing=True,
                )
                logger.info(f"Scheduled module job '{job.id}' from module '{module_name}': {job.cron}")
        except Exception as e:
            logger.error(
                f"Failed to register jobs from module '{module_name}': {e}",
                exc_info=True,
            )

    # Start scheduler
    scheduler.start()
    logger.info("Scheduler started successfully")


def stop_scheduler() -> None:
    """Stop the scheduler.

    This should be called during FastAPI app shutdown.
    """
    logger.info("Stopping scheduler")
    scheduler.shutdown(wait=True)
    logger.info("Scheduler stopped")
