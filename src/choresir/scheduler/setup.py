"""Scheduler configuration and job registration."""

from __future__ import annotations

import functools

from apscheduler import AsyncScheduler, ConflictPolicy
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy.ext.asyncio import async_sessionmaker

from choresir.scheduler.jobs import (
    reset_recurring_tasks,
    send_daily_summary,
    send_overdue_reminders,
    send_upcoming_reminders,
    send_weekly_leaderboard,
)
from choresir.services.messaging import MessageSender

_REPLACE = ConflictPolicy.replace


async def create_scheduler(
    session_factory: async_sessionmaker,
    sender: MessageSender,
    group_chat_id: str,
) -> AsyncScheduler:
    """Create an AsyncScheduler with all cron jobs registered."""
    scheduler = AsyncScheduler()
    args = (session_factory, sender, group_chat_id)

    await scheduler.add_schedule(
        functools.partial(send_daily_summary, *args),
        CronTrigger(hour=20, minute=0),
        id="daily_summary",
        conflict_policy=_REPLACE,
    )
    await scheduler.add_schedule(
        functools.partial(send_weekly_leaderboard, *args),
        CronTrigger(day_of_week="sun", hour=18, minute=0),
        id="weekly_leaderboard",
        conflict_policy=_REPLACE,
    )
    await scheduler.add_schedule(
        functools.partial(send_overdue_reminders, *args),
        CronTrigger(hour="8,12,18", minute=0),
        id="overdue_reminders",
        conflict_policy=_REPLACE,
    )
    await scheduler.add_schedule(
        functools.partial(send_upcoming_reminders, *args),
        CronTrigger(hour=6, minute=0),
        id="upcoming_reminders",
        conflict_policy=_REPLACE,
    )
    await scheduler.add_schedule(
        functools.partial(reset_recurring_tasks, session_factory),
        CronTrigger(minute=0),
        id="recurring_reset",
        conflict_policy=_REPLACE,
    )
    return scheduler
