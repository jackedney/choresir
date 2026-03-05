"""Scheduled job functions — thin wrappers that delegate to services."""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import async_sessionmaker

from choresir.enums import TaskStatus
from choresir.services.messaging import MessageSender
from choresir.services.task_service import TaskService

logger = logging.getLogger(__name__)


async def send_daily_summary(
    session_factory: async_sessionmaker,
    sender: MessageSender,
    group_chat_id: str,
) -> None:
    """Query task stats and send a daily activity summary to the group."""
    async with session_factory() as session:
        svc = TaskService(session)
        all_tasks = await svc.list_tasks()
        pending = [t for t in all_tasks if t.status == TaskStatus.PENDING]
        claimed = [t for t in all_tasks if t.status == TaskStatus.CLAIMED]
        verified = [t for t in all_tasks if t.status == TaskStatus.VERIFIED]
        overdue = await svc.get_overdue()

        lines = [
            "Daily Summary",
            f"  Pending: {len(pending)}",
            f"  Awaiting verification: {len(claimed)}",
            f"  Completed: {len(verified)}",
            f"  Overdue: {len(overdue)}",
        ]
        await sender.send(group_chat_id, "\n".join(lines))
    logger.info("Sent daily summary")


async def send_weekly_leaderboard(
    session_factory: async_sessionmaker,
    sender: MessageSender,
    group_chat_id: str,
) -> None:
    """Query leaderboard rankings and send a weekly report to the group."""
    async with session_factory() as session:
        svc = TaskService(session)
        leaderboard = await svc.get_leaderboard()

        if not leaderboard:
            await sender.send(
                group_chat_id,
                "Weekly Leaderboard\n  No completions yet!",
            )
        else:
            lines = ["Weekly Leaderboard"]
            for entry in leaderboard:
                lines.append(
                    f"  #{entry['rank']} — Member {entry['member_id']}"
                    f" ({entry['completion_count']} completions)"
                )
            await sender.send(group_chat_id, "\n".join(lines))
    logger.info("Sent weekly leaderboard")


async def send_overdue_reminders(
    session_factory: async_sessionmaker,
    sender: MessageSender,
    group_chat_id: str,
) -> None:
    """Query overdue tasks and send a reminder for each."""
    async with session_factory() as session:
        svc = TaskService(session)
        overdue = await svc.get_overdue()

        for task in overdue:
            await sender.send(
                group_chat_id,
                f'Reminder: "{task.title}" is overdue'
                f" (assigned to member {task.assignee_id}).",
            )
        count = len(overdue)
    logger.info("Sent overdue reminders count=%d", count)


async def reset_recurring_tasks(
    session_factory: async_sessionmaker,
) -> None:
    """Reset verified recurring tasks that may have been missed."""
    async with session_factory() as session:
        svc = TaskService(session)
        all_tasks = await svc.list_tasks()
        reset_count = 0
        for task in all_tasks:
            if task.status == TaskStatus.VERIFIED and task.recurrence is not None:
                svc._handle_recurrence_reset(task)
                session.add(task)
                reset_count += 1
        if reset_count:
            await session.commit()
    logger.info("Reset recurring tasks count=%d", reset_count)
