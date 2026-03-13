"""Scheduler configuration and job registration."""

from __future__ import annotations

import functools
import logging
from datetime import UTC

from apscheduler import AsyncScheduler, ConflictPolicy
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.ext.asyncio import async_sessionmaker

from choresir.scheduler.jobs import (
    reset_recurring_tasks,
    send_daily_personal_reminders,
    send_daily_summary,
    send_overdue_reminders,
    send_upcoming_reminders,
    send_weekly_leaderboard,
)
from choresir.services.messaging import MessageSender

logger = logging.getLogger(__name__)

_REPLACE = ConflictPolicy.replace


def create_scheduler() -> AsyncScheduler:
    """Create an AsyncScheduler instance."""
    return AsyncScheduler()


async def register_schedules(
    scheduler: AsyncScheduler,
    session_factory: async_sessionmaker,
    sender: MessageSender,
    group_chat_id: str,
) -> None:
    """Register all cron jobs on an already-initialized scheduler."""
    logger.info("Registering scheduler jobs")
    args = (session_factory, sender, group_chat_id)

    await scheduler.add_schedule(
        functools.partial(send_daily_summary, *args),
        CronTrigger(hour=20, minute=0, timezone=UTC),
        id="daily_summary",
        conflict_policy=_REPLACE,
    )
    logger.info("Registered daily_summary job at 20:00 UTC")

    await scheduler.add_schedule(
        functools.partial(send_weekly_leaderboard, *args),
        CronTrigger(day_of_week="sun", hour=18, minute=0, timezone=UTC),
        id="weekly_leaderboard",
        conflict_policy=_REPLACE,
    )
    logger.info("Registered weekly_leaderboard job at Sun 18:00 UTC")

    await scheduler.add_schedule(
        functools.partial(send_overdue_reminders, *args),
        CronTrigger(hour="8,12,18", minute=0, timezone=UTC),
        id="overdue_reminders",
        conflict_policy=_REPLACE,
    )
    logger.info("Registered overdue_reminders job at 8:00, 12:00, 18:00 UTC")

    await scheduler.add_schedule(
        functools.partial(send_upcoming_reminders, *args),
        CronTrigger(hour=6, minute=0, timezone=UTC),
        id="upcoming_reminders",
        conflict_policy=_REPLACE,
    )
    logger.info("Registered upcoming_reminders job at 6:00 UTC")

    await scheduler.add_schedule(
        functools.partial(send_daily_personal_reminders, session_factory, sender),
        CronTrigger(hour=7, minute=0, timezone=UTC),
        id="daily_personal_reminders",
        conflict_policy=_REPLACE,
    )
    logger.info("Registered daily_personal_reminders job at 7:00 UTC")

    await scheduler.add_schedule(
        functools.partial(reset_recurring_tasks, session_factory),
        CronTrigger(minute=0, timezone=UTC),
        id="recurring_reset",
        conflict_policy=_REPLACE,
    )
    logger.info("Registered recurring_reset job every hour UTC")
    logger.info("All scheduler jobs registered")
