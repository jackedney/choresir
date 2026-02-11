"""Scheduled jobs for tasks module.

This module provides scheduled jobs for:
- Overdue chore reminders
- Daily household reports
- Weekly leaderboard reports
- Personal chore reminders
- Auto-verification of personal chores
"""

import logging
from datetime import UTC, date, datetime

from src.core import db_client, message_templates
from src.core.config import Constants
from src.core.db_client import sanitize_param
from src.core.recurrence_parser import parse_recurrence_to_cron
from src.core.scheduler_tracker import retry_job_with_backoff
from src.domain.user import UserStatus
from src.interface.whatsapp_sender import send_text_message
from src.models.service_models import LeaderboardEntry, OverdueChore
from src.modules.tasks import service
from src.services import workflow_service


logger = logging.getLogger(__name__)


async def _send_reminder_to_user(*, user_id: str, chores: list[OverdueChore]) -> bool:
    """Send overdue reminder to a single user.

    Args:
        user_id: User ID to send reminder to
        chores: List of overdue chores assigned to user

    Returns:
        True if reminder was sent successfully, False otherwise
    """
    try:
        # Get user details
        user = await db_client.get_record(collection="members", record_id=user_id)

        # Skip if not active
        if user["status"] != UserStatus.ACTIVE:
            return False

        # Build reminder message
        items = [(chore.title, chore.deadline[:10]) for chore in chores]
        message = message_templates.overdue_reminder(items=items)

        # Send WhatsApp message
        result = await send_text_message(
            to_phone=user["phone"],
            text=message,
        )

        if result.success:
            logger.info("Sent overdue reminder to %s (%d chores)", user["name"], len(chores))
            return True

        logger.warning(f"Failed to send reminder to {user['name']}: {result.error}")
        return False
    except KeyError:
        logger.warning(f"User {user_id} not found for overdue reminders")
        return False
    except Exception as e:
        logger.error(f"Error sending reminder to user {user_id}: {e}")
        return False


async def send_overdue_reminders() -> None:
    """Send reminders to users with overdue chores.

    Runs daily at 8am. Checks for overdue chores and sends WhatsApp
    messages to assigned users.
    """
    from src.modules.tasks.analytics import get_overdue_chores

    logger.info("Running overdue chore reminders job")

    try:
        # Get all overdue chores
        overdue_chores = await get_overdue_chores()

        if not overdue_chores:
            logger.info("No overdue chores found")
            return

        # Group chores by assigned user
        chores_by_user: dict[str, list[OverdueChore]] = {}
        for chore in overdue_chores:
            user_id = chore.assigned_to
            if not user_id:
                continue  # Skip unassigned chores

            if user_id not in chores_by_user:
                chores_by_user[user_id] = []
            chores_by_user[user_id].append(chore)

        # Send reminders to each user
        sent_count = 0
        for user_id, chores in chores_by_user.items():
            if await _send_reminder_to_user(user_id=user_id, chores=chores):
                sent_count += 1

        logger.info("Completed overdue reminders job: %d/%d users notified", sent_count, len(chores_by_user))
    except Exception as e:
        logger.error(f"Error in overdue reminders job: {e}")


async def send_daily_report() -> None:
    """Send daily household summary report to all active users.

    Runs daily at 9pm. Sends a summary of day's completions
    and pending verifications.
    """
    from src.modules.tasks.analytics import get_household_summary

    logger.info("Running daily report job")

    try:
        # Get household summary for today (last 1 day)
        summary = await get_household_summary(period_days=1)

        # Build report message
        message = message_templates.daily_report(
            completions=summary.completions_this_period,
            overdue=summary.overdue_chores,
            pending_verifications=summary.pending_verifications,
            active_members=summary.active_members,
        )

        # Get all active users
        active_users = await db_client.list_records(
            collection="members",
            filter_query=f'status = "{UserStatus.ACTIVE}"',
        )

        if not active_users:
            logger.info("No active users to send daily report")
            return

        # Send report to each active user
        sent_count = 0
        for user in active_users:
            try:
                result = await send_text_message(
                    to_phone=user["phone"],
                    text=message,
                )

                if result.success:
                    sent_count += 1
                    logger.debug(f"Sent daily report to {user['name']}")
                else:
                    logger.warning(f"Failed to send daily report to {user['name']}: {result.error}")
            except Exception as e:
                logger.error(f"Error sending daily report to user {user['id']}: {e}")
                continue

        logger.info("Completed daily report job: sent to %d/%d users", sent_count, len(active_users))
    except Exception as e:
        logger.error(f"Error in daily report job: {e}")


def _get_rank_emoji(rank: int) -> str:
    """Get emoji for leaderboard rank.

    Args:
        rank: Position in leaderboard (1-indexed)

    Returns:
        Rank emoji string
    """
    if rank == Constants.LEADERBOARD_RANK_FIRST:
        return "🥇"
    if rank == Constants.LEADERBOARD_RANK_SECOND:
        return "🥈"
    if rank == Constants.LEADERBOARD_RANK_THIRD:
        return "🥉"
    return f"{rank}."


def _get_dynamic_title(rank: int, total_users: int, completions: int) -> str:
    """Get dynamic title based on performance.

    Args:
        rank: Position in leaderboard
        total_users: Total number of users
        completions: Number of completions

    Returns:
        Dynamic title string
    """
    if rank == Constants.LEADERBOARD_RANK_FIRST and completions >= Constants.LEADERBOARD_COMPLETIONS_CARRYING_TEAM:
        return '"Carrying the team!"'
    if rank == Constants.LEADERBOARD_RANK_FIRST:
        return '"MVP!"'
    if rank == total_users and completions == 0:
        return '"The Observer"'
    if rank == total_users and completions <= Constants.LEADERBOARD_COMPLETIONS_NEEDS_IMPROVEMENT:
        return '"Room for improvement"'
    return ""


def _format_weekly_leaderboard(leaderboard: list[LeaderboardEntry], overdue: list[OverdueChore]) -> str:
    """Format weekly leaderboard for WhatsApp display.

    Args:
        leaderboard: List of leaderboard entries
        overdue: List of overdue chores

    Returns:
        Formatted weekly report message
    """
    lines = ["🏆 *Weekly Chore Report*", ""]

    if not leaderboard:
        lines.append("No completions this week.")
    else:
        total_completions = sum(entry.completion_count for entry in leaderboard)
        total_users = len(leaderboard)

        # Show all users (max 10 for readability)
        for rank, entry in enumerate(leaderboard[:10], start=1):
            emoji = _get_rank_emoji(rank)
            name = entry.user_name
            count = entry.completion_count
            title = _get_dynamic_title(rank, total_users, count)

            if title:
                lines.append(f"{emoji} *{name}* ({count} chores) - _{title}_")
            else:
                lines.append(f"{emoji} *{name}* ({count} chores)")

        lines.append("")
        lines.append(f"*Total House Output:* {total_completions} chores")

    # Add most neglected chore info
    if overdue:
        # Find most overdue chore
        now = datetime.now(UTC)

        # Filter out chores with invalid deadlines
        valid_overdue = []
        for chore in overdue:
            try:
                deadline = datetime.fromisoformat(chore.deadline)
                # If deadline is naive (no timezone), assume UTC
                if deadline.tzinfo is None:
                    deadline = deadline.replace(tzinfo=UTC)
                valid_overdue.append((chore, deadline))
            except (ValueError, TypeError) as e:
                logger.warning(
                    "Failed to parse deadline for chore",
                    extra={
                        "chore_id": chore.id,
                        "chore_title": chore.title,
                        "deadline": chore.deadline,
                        "error": str(e),
                    },
                )
                continue

        if valid_overdue:
            # Already sorted by +deadline
            most_overdue_chore, most_overdue_deadline = valid_overdue[0]
            overdue_days = (now - most_overdue_deadline).days
            day_word = "day" if overdue_days == 1 else "days"
            lines.append(f'*Most Neglected Chore:* "{most_overdue_chore.title}" (Overdue by {overdue_days} {day_word})')

    return "\n".join(lines)


async def send_weekly_leaderboard() -> None:
    """Send weekly leaderboard report to all active users.

    Runs every Sunday at 8pm. Sends a gamified summary of week's
    chore completions with rankings, dynamic titles, and household stats.
    """
    from src.modules.tasks.analytics import get_leaderboard, get_overdue_chores

    logger.info("Running weekly leaderboard job")

    try:
        # Get weekly leaderboard (last 7 days)
        leaderboard = await get_leaderboard(period_days=7)

        # Get overdue chores for "most neglected" stat
        # Only need the oldest one (limit=1 for performance)
        overdue = await get_overdue_chores(limit=1)

        # Build formatted message
        message = _format_weekly_leaderboard(leaderboard, overdue)

        # Get all active users
        active_users = await db_client.list_records(
            collection="members",
            filter_query=f'status = "{UserStatus.ACTIVE}"',
        )

        if not active_users:
            logger.info("No active users to send weekly leaderboard")
            return

        # Send report to each active user
        sent_count = 0
        for user in active_users:
            try:
                result = await send_text_message(
                    to_phone=user["phone"],
                    text=message,
                )

                if result.success:
                    sent_count += 1
                    logger.debug(f"Sent weekly leaderboard to {user['name']}")
                else:
                    logger.warning(f"Failed to send weekly leaderboard to {user['name']}: {result.error}")
            except Exception as e:
                logger.error(f"Error sending weekly leaderboard to user {user['id']}: {e}")
                continue

        logger.info("Completed weekly leaderboard job: sent to %d/%d users", sent_count, len(active_users))
    except Exception as e:
        logger.error(f"Error in weekly leaderboard job: {e}")


async def _get_last_completion_date(chore_id: str, owner_phone: str) -> date | None:
    """Get the last completion date for a personal chore.

    Args:
        chore_id: Personal chore ID
        owner_phone: Owner's phone number

    Returns:
        Date of last completion, or None if never completed
    """
    try:
        # Query for most recent completion log
        logs = await db_client.list_records(
            collection="task_logs",
            filter_query=(
                f'task_id = "{sanitize_param(chore_id)}" && '  # noqa: S608
                f'action = "claimed_completion" && '
                f'user_id IN (SELECT id FROM members WHERE phone = "{sanitize_param(owner_phone)}")'
            ),
            sort="timestamp DESC",
            per_page=1,
        )

        if logs:
            completed_at_str = logs[0].get("timestamp", "")
            if completed_at_str:
                return datetime.fromisoformat(completed_at_str).date()

        return None
    except Exception as e:
        logger.warning(f"Error fetching last completion for chore {chore_id}: {e}")
        return None


def _is_recurring_chore_due_today(recurrence: str, last_completion: date | None, today: date) -> bool:
    """Check if a recurring chore is due today based on its recurrence pattern.

    Args:
        recurrence: Recurrence pattern (cron expression, "every X days", etc.)
        last_completion: Date of last completion, or None if never completed
        today: Today's date

    Returns:
        True if chore is due today based on its recurrence pattern
    """
    try:
        # Parse recurrence to cron expression
        cron_expr = parse_recurrence_to_cron(recurrence)

        # Handle special INTERVAL format (e.g., "INTERVAL:3:0 0 * * *")
        if cron_expr.startswith("INTERVAL:"):
            return _check_interval_due_today(cron_expr, last_completion, today)

        # For standard cron expressions
        from croniter import croniter

        if croniter.is_valid(cron_expr):
            return _check_cron_due_today(cron_expr, last_completion, today)

        # If we can't parse it, default to not due (to avoid spam)
        logger.warning(f"Could not parse recurrence pattern: {recurrence}")
        return False
    except Exception as e:
        logger.warning(f"Error checking recurrence pattern '{recurrence}': {e}")
        return False


def _check_interval_due_today(cron_expr: str, last_completion: date | None, today: date) -> bool:
    """Check if an interval-based chore is due today."""
    parts = cron_expr.split(":")
    interval_days = int(parts[1])
    base_cron = parts[2]

    # If never completed, check if today matches base cron schedule
    if last_completion is None:
        from croniter import croniter

        if croniter.is_valid(base_cron):
            cron = croniter(base_cron, datetime.combine(today, datetime.min.time()))
            next_occurrence = cron.get_current(datetime)
            return next_occurrence.date() == today
        return True

    # Check if enough days have passed since last completion
    days_since_completion = (today - last_completion).days
    if days_since_completion < interval_days:
        return False

    # Verify today matches base cron schedule
    from croniter import croniter

    if croniter.is_valid(base_cron):
        cron = croniter(base_cron, datetime.combine(today, datetime.min.time()))
        next_occurrence = cron.get_current(datetime)
        return next_occurrence.date() == today
    return True


def _check_cron_due_today(cron_expr: str, last_completion: date | None, today: date) -> bool:
    """Check if a cron-based chore is due today."""
    from croniter import croniter

    today_dt = datetime.combine(today, datetime.min.time())
    cron = croniter(cron_expr, today_dt)

    # If never completed, check if today matches schedule
    if last_completion is None:
        current_occurrence = cron.get_current(datetime)
        return current_occurrence.date() == today

    # Get next scheduled occurrence after last completion
    last_completion_dt = datetime.combine(last_completion, datetime.min.time())
    cron_from_last = croniter(cron_expr, last_completion_dt)
    next_occurrence = cron_from_last.get_next(datetime)
    next_occurrence_date = next_occurrence.date()

    # Due if next occurrence is today or earlier
    return next_occurrence_date <= today


async def _is_chore_due_today(chore: dict, today: date) -> bool:
    """Check if a personal chore is due today.

    Args:
        chore: Personal chore dictionary
        today: Today's date

    Returns:
        True if chore is due today
    """
    due_date_str = chore.get("deadline", "")
    recurrence = chore.get("schedule_cron", "")

    # For one-time chores, check if due_date is today
    if due_date_str:
        try:
            due_date = datetime.fromisoformat(due_date_str).date()
            return due_date == today
        except (ValueError, AttributeError):
            return False

    # For recurring chores, check against recurrence pattern and last completion
    if recurrence:
        chore_id = chore.get("id", "")
        # Get owner phone from the task
        import src.services.user_service

        user = await src.services.user_service.get_user_by_id(user_id=chore["owner_id"])
        owner_phone = user.get("phone", "") if user else ""

        if not chore_id or not owner_phone:
            logger.warning(f"Missing chore_id or owner_phone for chore: {chore}")
            return False

        last_completion = await _get_last_completion_date(chore_id, owner_phone)
        return _is_recurring_chore_due_today(recurrence, last_completion, today)

    # No due_date and no recurrence - not due
    return False


def _build_reminder_message(chores: list[dict]) -> str:
    """Build reminder message for personal chores."""
    return message_templates.personal_reminder(items=[c["title"] for c in chores])


async def _send_personal_chore_reminder_to_user(user: dict, today: date) -> bool:
    """Send personal chore reminder to a single user. Returns True if sent successfully."""
    # Get user's active personal chores
    personal_chores = await service.get_personal_chores(
        owner_id=user["id"],
        include_archived=False,
    )

    # Filter chores that are due today (check each chore asynchronously)
    due_today = []
    for chore in personal_chores:
        if await _is_chore_due_today(chore, today):
            due_today.append(chore)

    if not due_today:
        return False

    # Send DM
    message = _build_reminder_message(due_today)
    result = await send_text_message(
        to_phone=user["phone"],
        text=message,
    )

    if result.success:
        logger.debug(f"Sent personal chore reminder to {user['name']}")
        return True

    logger.warning(f"Failed to send personal chore reminder to {user['name']}: {result.error}")
    return False


async def send_personal_chore_reminders() -> None:
    """Send reminders for personal chores due today.

    Runs daily at 8 AM. Sends DM reminders to users with personal chores
    that have recurring patterns triggering today.
    """
    logger.info("Running personal chore reminders job")

    try:
        today = datetime.now(UTC).date()

        # Get all active users
        active_users = await db_client.list_records(
            collection="members",
            filter_query=f'status = "{UserStatus.ACTIVE}"',
        )

        if not active_users:
            logger.info("No active users for personal chore reminders")
            return

        # Send reminders to all users
        sent_count = 0
        for user in active_users:
            try:
                if await _send_personal_chore_reminder_to_user(user, today):
                    sent_count += 1
            except Exception as e:
                logger.error(f"Error sending reminder to user {user['id']}: {e}")
                continue

        logger.info("Completed personal chore reminders: sent to %d/%d users", sent_count, len(active_users))
    except Exception as e:
        logger.error(f"Error in personal chore reminders job: {e}")


async def auto_verify_personal_chores() -> None:
    """Auto-verify personal chore logs pending for > 48 hours.

    Runs every hour. Finds logs in PENDING state older than 48 hours
    and auto-verifies them (partner didn't respond in time).
    """
    logger.info("Running personal chore auto-verification job")

    try:
        pass
    except Exception as e:
        logger.error(f"Error in auto-verification job: {e}")


async def auto_expire_workflows() -> None:
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


def get_scheduled_jobs() -> list:
    """Return scheduled jobs for tasks module.

    Returns:
        List of ScheduledJob definitions
    """

    from src.core.module import ScheduledJob

    return [
        ScheduledJob(
            id="overdue_reminders",
            name="Send Overdue Chore Reminders",
            cron="0 8 * * *",
            func=lambda: retry_job_with_backoff(send_overdue_reminders, "overdue_reminders"),
        ),
        ScheduledJob(
            id="daily_report",
            name="Send Daily Household Report",
            cron="0 21 * * *",
            func=lambda: retry_job_with_backoff(send_daily_report, "daily_report"),
        ),
        ScheduledJob(
            id="weekly_leaderboard",
            name="Send Weekly Leaderboard Report",
            cron="0 20 * * 0",
            func=lambda: retry_job_with_backoff(send_weekly_leaderboard, "weekly_leaderboard"),
        ),
        ScheduledJob(
            id="personal_chore_reminders",
            name="Send Personal Chore Reminders",
            cron="0 8 * * *",
            func=lambda: retry_job_with_backoff(send_personal_chore_reminders, "personal_chore_reminders"),
        ),
    ]
