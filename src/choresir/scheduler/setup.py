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
    send_weekly_leaderboard,
)
from choresir.services.messaging import MessageSender


async def create_scheduler(
    session_factory: async_sessionmaker,
    sender: MessageSender,
    group_chat_id: str,
) -> AsyncScheduler:
    """Create an AsyncScheduler with all cron jobs registered."""
    scheduler = AsyncScheduler()

    # Bind dependencies to job functions via functools.partial
    daily_summary = functools.partial(
        send_daily_summary, session_factory, sender, group_chat_id
    )
    weekly_leaderboard = functools.partial(
        send_weekly_leaderboard, session_factory, sender, group_chat_id
    )
    overdue_reminders = functools.partial(
        send_overdue_reminders, session_factory, sender, group_chat_id
    )
    recurring_reset = functools.partial(reset_recurring_tasks, session_factory)

    # Daily summary at 8pm every day
    await scheduler.add_schedule(
        daily_summary,
        CronTrigger(hour=20, minute=0),
        id="daily_summary",
        conflict_policy=ConflictPolicy.replace,
    )

    # Weekly leaderboard at 6pm every Sunday
    await scheduler.add_schedule(
        weekly_leaderboard,
        CronTrigger(day_of_week="sun", hour=18, minute=0),
        id="weekly_leaderboard",
        conflict_policy=ConflictPolicy.replace,
    )

    # Overdue reminders at 8am, 12pm, 6pm every day
    await scheduler.add_schedule(
        overdue_reminders,
        CronTrigger(hour="8,12,18", minute=0),
        id="overdue_reminders",
        conflict_policy=ConflictPolicy.replace,
    )

    # Recurring task reset every hour on the hour
    await scheduler.add_schedule(
        recurring_reset,
        CronTrigger(minute=0),
        id="recurring_reset",
        conflict_policy=ConflictPolicy.replace,
    )

    return scheduler
