"""Scheduled job functions — thin wrappers that delegate to services."""

from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import async_sessionmaker

from choresir.enums import TaskStatus
from choresir.services.member_service import MemberService
from choresir.services.messaging import MessageSender, NullSender
from choresir.services.task_service import TaskService

logger = logging.getLogger(__name__)


async def send_daily_summary(
    session_factory: async_sessionmaker,
    sender: MessageSender,
    group_chat_id: str,
) -> None:
    """Query task stats and send a daily activity summary to the group."""
    async with session_factory() as session:
        svc = TaskService(session, sender, max_takeovers_per_week=0)
        tasks = await svc.list_tasks()
        overdue = await svc.get_overdue()
        by_status = {s: 0 for s in TaskStatus}
        for t in tasks:
            by_status[t.status] += 1
        lines = [
            "Daily Summary",
            f"  Pending: {by_status[TaskStatus.PENDING]}",
            f"  Awaiting verification: {by_status[TaskStatus.CLAIMED]}",
            f"  Completed: {by_status[TaskStatus.VERIFIED]}",
            f"  Overdue: {len(overdue)}",
        ]
        await sender.send(group_chat_id, "\n".join(lines))


async def send_weekly_leaderboard(
    session_factory: async_sessionmaker,
    sender: MessageSender,
    group_chat_id: str,
) -> None:
    """Query leaderboard rankings and send a weekly report."""
    async with session_factory() as session:
        svc = TaskService(session, sender, max_takeovers_per_week=0)
        board = await svc.get_leaderboard()
        if not board:
            msg = "Weekly Leaderboard\n  No completions yet!"
        else:
            lines = ["Weekly Leaderboard"]
            for e in board:
                lines.append(
                    f"  #{e['rank']} — Member {e['member_id']}"
                    f" ({e['completion_count']} completions)"
                )
            msg = "\n".join(lines)
        await sender.send(group_chat_id, msg)


async def send_overdue_reminders(
    session_factory: async_sessionmaker,
    sender: MessageSender,
    group_chat_id: str,
) -> None:
    """Query overdue tasks and send a reminder for each."""
    logger.info("Running overdue reminders job")
    async with session_factory() as session:
        svc = TaskService(session, sender, max_takeovers_per_week=0)
        overdue = await svc.get_overdue()
        logger.info("Found %d overdue tasks", len(overdue))
        for task in overdue:
            try:
                await sender.send(
                    group_chat_id,
                    f'Reminder: "{task.title}" is overdue'
                    f" (assigned to member {task.assignee_id}).",
                )
                logger.info("Sent overdue reminder for task %s", task.id)
            except Exception:
                logger.exception("Failed to send overdue reminder for task %s", task.id)


async def send_upcoming_reminders(
    session_factory: async_sessionmaker,
    sender: MessageSender,
    group_chat_id: str,
) -> None:
    """Query upcoming tasks (next 24h) and send a reminder for each."""
    logger.info("Running upcoming reminders job")
    async with session_factory() as session:
        svc = TaskService(session, sender, max_takeovers_per_week=0)
        upcoming = await svc.get_upcoming(hours=24)
        logger.info("Found %d upcoming tasks", len(upcoming))
        for task in upcoming:
            try:
                await sender.send(
                    group_chat_id,
                    f'Reminder: "{task.title}" is due soon'
                    f" (assigned to member {task.assignee_id}).",
                )
                logger.info("Sent upcoming reminder for task %s", task.id)
            except Exception:
                logger.exception(
                    "Failed to send upcoming reminder for task %s", task.id
                )


async def send_daily_personal_reminders(
    session_factory: async_sessionmaker,
    sender: MessageSender,
) -> None:
    """Send each active member a personalized list of their pending/claimed tasks."""
    logger.info("Running daily personal reminders job")
    async with session_factory() as session:
        member_svc = MemberService(session)
        task_svc = TaskService(session, sender, max_takeovers_per_week=0)

        members = await member_svc.list_active()
        logger.info("Found %d active members", len(members))

        for member in members:
            tasks = await task_svc.list_tasks(member_id=member.id)
            pending = [
                t for t in tasks if t.status in (TaskStatus.PENDING, TaskStatus.CLAIMED)
            ]

            if not pending:
                logger.debug("No pending tasks for member %s", member.id)
                continue

            lines = [f"Good morning, {member.name or 'there'}! Your chores for today:"]
            for t in pending:
                status = (
                    "awaiting verification"
                    if t.status == TaskStatus.CLAIMED
                    else "pending"
                )
                dl = f" (due: {t.deadline.strftime('%a %b %d')})" if t.deadline else ""
                lines.append(f"  • {t.title}{dl} [{status}]")

            try:
                await sender.send(member.whatsapp_id, "\n".join(lines))
                logger.info("Sent daily reminder to member %s", member.id)
            except Exception:
                logger.exception(
                    "Failed to send daily reminder to member %s", member.id
                )


async def reset_recurring_tasks(
    session_factory: async_sessionmaker,
) -> None:
    """Reset verified recurring tasks that may have been missed."""
    async with session_factory() as session:
        sender = NullSender()
        svc = TaskService(session, sender, max_takeovers_per_week=0)
        await svc.reset_recurring_tasks()
