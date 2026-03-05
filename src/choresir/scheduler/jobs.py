"""Scheduled job functions — thin wrappers that delegate to services."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import async_sessionmaker

from choresir.enums import TaskStatus
from choresir.services.messaging import MessageSender
from choresir.services.task_service import TaskService


async def send_daily_summary(
    session_factory: async_sessionmaker,
    sender: MessageSender,
    group_chat_id: str,
) -> None:
    """Query task stats and send a daily activity summary to the group."""
    async with session_factory() as session:
        svc = TaskService(session, max_takeovers_per_week=0)
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
        svc = TaskService(session, max_takeovers_per_week=0)
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
    async with session_factory() as session:
        svc = TaskService(session, max_takeovers_per_week=0)
        for task in await svc.get_overdue():
            await sender.send(
                group_chat_id,
                f'Reminder: "{task.title}" is overdue'
                f" (assigned to member {task.assignee_id}).",
            )


async def reset_recurring_tasks(
    session_factory: async_sessionmaker,
) -> None:
    """Reset verified recurring tasks that may have been missed."""
    async with session_factory() as session:
        svc = TaskService(session, max_takeovers_per_week=0)
        changed = False
        for task in await svc.list_tasks():
            if task.status == TaskStatus.VERIFIED and task.recurrence:
                svc._handle_recurrence_reset(task)
                session.add(task)
                changed = True
        if changed:
            await session.commit()
