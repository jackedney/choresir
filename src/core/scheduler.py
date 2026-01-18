"""Scheduler for automated jobs (reminders, reports, etc.)."""

from datetime import UTC, datetime

import logfire
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.core import db_client
from src.core.config import constants
from src.domain.user import UserStatus
from src.interface.whatsapp_sender import send_text_message
from src.services import personal_chore_service, personal_verification_service
from src.services.analytics_service import get_household_summary, get_leaderboard, get_overdue_chores


# Rank position constants
RANK_FIRST = 1
RANK_SECOND = 2
RANK_THIRD = 3

# Completion threshold constants for dynamic titles
COMPLETIONS_CARRYING_TEAM = 5
COMPLETIONS_NEEDS_IMPROVEMENT = 2

# Global scheduler instance
scheduler = AsyncIOScheduler()


async def _send_reminder_to_user(*, user_id: str, chores: list[dict]) -> bool:
    """Send overdue reminder to a single user.

    Args:
        user_id: User ID to send reminder to
        chores: List of overdue chores assigned to user

    Returns:
        True if reminder was sent successfully, False otherwise
    """
    try:
        # Get user details
        user = await db_client.get_record(collection="users", record_id=user_id)

        # Skip if not active
        if user["status"] != UserStatus.ACTIVE:
            return False

        # Build reminder message
        chore_list = "\n".join([f"• {chore['title']} (due: {chore['deadline'][:10]})" for chore in chores])

        message = (
            f"🔔 Overdue Chore Reminder\n\n"
            f"You have {len(chores)} overdue chore(s):\n\n"
            f"{chore_list}\n\n"
            f"Please complete these tasks as soon as possible."
        )

        # Send WhatsApp message
        result = await send_text_message(
            to_phone=user["phone"],
            text=message,
        )

        if result.success:
            logfire.info(f"Sent overdue reminder to {user['name']} ({len(chores)} chores)")
            return True

        logfire.warn(f"Failed to send reminder to {user['name']}: {result.error}")
        return False

    except KeyError:
        logfire.warn(f"User {user_id} not found for overdue reminders")
        return False
    except Exception as e:
        logfire.error(f"Error sending reminder to user {user_id}: {e}")
        return False


async def send_overdue_reminders() -> None:
    """Send reminders to users with overdue chores.

    Runs daily at 8am. Checks for overdue chores and sends WhatsApp
    messages to assigned users.
    """
    logfire.info("Running overdue chore reminders job")

    try:
        # Get all overdue chores
        overdue_chores = await get_overdue_chores()

        if not overdue_chores:
            logfire.info("No overdue chores found")
            return

        # Group chores by assigned user
        chores_by_user: dict[str, list[dict]] = {}
        for chore in overdue_chores:
            user_id = chore.get("assigned_to")
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

        logfire.info(f"Completed overdue reminders job: {sent_count}/{len(chores_by_user)} users notified")

    except Exception as e:
        logfire.error(f"Error in overdue reminders job: {e}")


async def send_daily_report() -> None:
    """Send daily household summary report to all active users.

    Runs daily at 9pm. Sends a summary of the day's completions,
    current conflicts, and pending verifications.
    """
    logfire.info("Running daily report job")

    try:
        # Get household summary for today (last 1 day)
        summary = await get_household_summary(period_days=1)

        # Build report message
        message = (
            f"📊 Daily Household Report\n\n"
            f"Today's Summary:\n"
            f"✅ Completions: {summary['completions_this_period']}\n"
            f"⏰ Overdue: {summary['overdue_chores']}\n"
            f"⏳ Pending Verification: {summary['pending_verifications']}\n"
            f"⚠️ Conflicts: {summary['current_conflicts']}\n\n"
            f"Active Members: {summary['active_members']}"
        )

        # Add context if there are items needing attention
        if summary["overdue_chores"] > 0 or summary["pending_verifications"] > 0:
            message += "\n\nRemember to complete overdue chores and verify pending tasks!"

        # Get all active users
        active_users = await db_client.list_records(
            collection="users",
            filter_query=f'status = "{UserStatus.ACTIVE}"',
        )

        if not active_users:
            logfire.info("No active users to send daily report")
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
                    logfire.debug(f"Sent daily report to {user['name']}")
                else:
                    logfire.warn(f"Failed to send daily report to {user['name']}: {result.error}")

            except Exception as e:
                logfire.error(f"Error sending daily report to user {user['id']}: {e}")
                continue

        logfire.info(f"Completed daily report job: sent to {sent_count}/{len(active_users)} users")

    except Exception as e:
        logfire.error(f"Error in daily report job: {e}")


def _get_rank_emoji(rank: int) -> str:
    """Get emoji for leaderboard rank.

    Args:
        rank: Position in leaderboard (1-indexed)

    Returns:
        Rank emoji string
    """
    if rank == RANK_FIRST:
        return "🥇"
    if rank == RANK_SECOND:
        return "🥈"
    if rank == RANK_THIRD:
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
    if rank == RANK_FIRST and completions >= COMPLETIONS_CARRYING_TEAM:
        return '"Carrying the team!"'
    if rank == RANK_FIRST:
        return '"MVP!"'
    if rank == total_users and completions == 0:
        return '"The Observer"'
    if rank == total_users and completions <= COMPLETIONS_NEEDS_IMPROVEMENT:
        return '"Room for improvement"'
    return ""


def _format_weekly_leaderboard(leaderboard: list[dict], overdue: list[dict]) -> str:
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
        total_completions = sum(entry["completion_count"] for entry in leaderboard)
        total_users = len(leaderboard)

        # Show all users (max 10 for readability)
        for rank, entry in enumerate(leaderboard[:10], start=1):
            emoji = _get_rank_emoji(rank)
            name = entry["user_name"]
            count = entry["completion_count"]
            title = _get_dynamic_title(rank, total_users, count)

            if title:
                lines.append(f"{emoji} *{name}* ({count} chores) - _{title}_")
            else:
                lines.append(f"{emoji} *{name}* ({count} chores)")

        lines.append("")
        lines.append(f"*Total House Output:* {total_completions} chores")

    # Add most neglected chore info
    if overdue:
        # Find the most overdue chore
        now = datetime.now(UTC)

        # Filter out chores with invalid deadlines
        valid_overdue = []
        for chore in overdue:
            try:
                deadline = datetime.fromisoformat(chore["deadline"])
                # If deadline is naive (no timezone), assume UTC
                if deadline.tzinfo is None:
                    deadline = deadline.replace(tzinfo=UTC)
                valid_overdue.append((chore, deadline))
            except (ValueError, TypeError) as e:
                logfire.warn(
                    "Failed to parse deadline for chore",
                    chore_id=chore.get("id"),
                    chore_title=chore.get("title"),
                    deadline=chore.get("deadline"),
                    error=str(e),
                )
                continue

        if valid_overdue:
            # Already the most overdue since sorted by +deadline
            most_overdue_chore, most_overdue_deadline = valid_overdue[0]
            overdue_days = (now - most_overdue_deadline).days
            day_word = "day" if overdue_days == 1 else "days"
            lines.append(
                f'*Most Neglected Chore:* "{most_overdue_chore["title"]}" (Overdue by {overdue_days} {day_word})'
            )

    return "\n".join(lines)


async def send_weekly_leaderboard() -> None:
    """Send weekly leaderboard report to all active users.

    Runs every Sunday at 8pm. Sends a gamified summary of the week's
    chore completions with rankings, dynamic titles, and household stats.
    """
    logfire.info("Running weekly leaderboard job")

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
            collection="users",
            filter_query=f'status = "{UserStatus.ACTIVE}"',
        )

        if not active_users:
            logfire.info("No active users to send weekly leaderboard")
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
                    logfire.debug(f"Sent weekly leaderboard to {user['name']}")
                else:
                    logfire.warn(f"Failed to send weekly leaderboard to {user['name']}: {result.error}")

            except Exception as e:
                logfire.error(f"Error sending weekly leaderboard to user {user['id']}: {e}")
                continue

        logfire.info(f"Completed weekly leaderboard job: sent to {sent_count}/{len(active_users)} users")

    except Exception as e:
        logfire.error(f"Error in weekly leaderboard job: {e}")


async def send_personal_chore_reminders() -> None:
    """Send reminders for personal chores due today.

    Runs daily at 8 AM. Sends DM reminders to users with personal chores
    that have recurring patterns triggering today.
    """
    logfire.info("Running personal chore reminders job")

    try:
        today = datetime.now(UTC).date()

        # Get all active users
        active_users = await db_client.list_records(
            collection="users",
            filter_query=f'status = "{UserStatus.ACTIVE}"',
        )

        if not active_users:
            logfire.info("No active users for personal chore reminders")
            return

        sent_count = 0

        for user in active_users:
            try:
                # Get user's active personal chores
                personal_chores = await personal_chore_service.get_personal_chores(
                    owner_phone=user["phone"],
                    status="ACTIVE",
                )

                # Filter chores that are due today (have recurrence pattern)
                due_today = []
                for chore in personal_chores:
                    recurrence = chore.get("recurrence", "")
                    due_date_str = chore.get("due_date", "")

                    # For recurring chores, check if they're due based on last completion
                    # For one-time chores, check if due_date is today
                    if due_date_str:
                        try:
                            due_date = datetime.fromisoformat(due_date_str).date()
                            if due_date == today:
                                due_today.append(chore)
                        except (ValueError, AttributeError):
                            continue
                    elif recurrence:
                        # For recurring chores, we'll remind daily at 8 AM
                        # (This is a simple implementation; could be enhanced with cron parsing)
                        due_today.append(chore)

                if not due_today:
                    continue

                # Build reminder message
                chore_list = "\n".join([f"• {chore['title']}" for chore in due_today])

                message = (
                    f"🔔 Personal Chore Reminder\n\n"
                    f"You have {len(due_today)} personal task(s) today:\n\n"
                    f"{chore_list}\n\n"
                    f"Reply 'done [task]' when complete."
                )

                # Send DM
                result = await send_text_message(
                    to_phone=user["phone"],
                    text=message,
                )

                if result.success:
                    sent_count += 1
                    logfire.debug(f"Sent personal chore reminder to {user['name']}")
                else:
                    logfire.warn(f"Failed to send personal chore reminder to {user['name']}: {result.error}")

            except Exception as e:
                logfire.error(f"Error sending reminder to user {user['id']}: {e}")
                continue

        logfire.info(f"Completed personal chore reminders: sent to {sent_count}/{len(active_users)} users")

    except Exception as e:
        logfire.error(f"Error in personal chore reminders job: {e}")


async def auto_verify_personal_chores() -> None:
    """Auto-verify personal chore logs pending for > 48 hours.

    Runs every hour. Finds logs in PENDING state older than 48 hours
    and auto-verifies them (partner didn't respond in time).
    """
    logfire.info("Running personal chore auto-verification job")

    try:
        # Call the auto-verification service
        count = await personal_verification_service.auto_verify_expired_logs()

        logfire.info(f"Completed auto-verification job: {count} logs auto-verified")

    except Exception as e:
        logfire.error(f"Error in auto-verification job: {e}")


def start_scheduler() -> None:
    """Start the scheduler and register all jobs.

    This should be called during FastAPI app startup.
    """
    logfire.info("Starting scheduler")

    # Schedule overdue reminders job (daily at 8am)
    scheduler.add_job(
        send_overdue_reminders,
        trigger=CronTrigger(hour=constants.DAILY_REMINDER_HOUR, minute=0),
        id="overdue_reminders",
        name="Send Overdue Chore Reminders",
        replace_existing=True,
    )
    logfire.info(f"Scheduled overdue reminders job: daily at {constants.DAILY_REMINDER_HOUR}:00")

    # Schedule daily report job (daily at 9pm)
    scheduler.add_job(
        send_daily_report,
        trigger=CronTrigger(hour=constants.DAILY_REPORT_HOUR, minute=0),
        id="daily_report",
        name="Send Daily Household Report",
        replace_existing=True,
    )
    logfire.info(f"Scheduled daily report job: daily at {constants.DAILY_REPORT_HOUR}:00")

    # Schedule weekly leaderboard job (Sunday at 8pm)
    scheduler.add_job(
        send_weekly_leaderboard,
        trigger=CronTrigger(
            day_of_week=constants.WEEKLY_REPORT_DAY,
            hour=constants.WEEKLY_REPORT_HOUR,
            minute=0,
        ),
        id="weekly_leaderboard",
        name="Send Weekly Leaderboard Report",
        replace_existing=True,
    )
    logfire.info(
        f"Scheduled weekly leaderboard job: day {constants.WEEKLY_REPORT_DAY} at {constants.WEEKLY_REPORT_HOUR}:00"
    )

    # Schedule personal chore reminders (daily at 8am)
    scheduler.add_job(
        send_personal_chore_reminders,
        trigger=CronTrigger(hour=8, minute=0),
        id="personal_chore_reminders",
        name="Send Personal Chore Reminders",
        replace_existing=True,
    )
    logfire.info("Scheduled personal chore reminders job: daily at 8:00")

    # Schedule auto-verification (hourly)
    scheduler.add_job(
        auto_verify_personal_chores,
        trigger=CronTrigger(hour="*", minute=0),  # Every hour at minute 0
        id="auto_verify_personal",
        name="Auto-Verify Personal Chores",
        replace_existing=True,
    )
    logfire.info("Scheduled auto-verification job: hourly")

    # Start the scheduler
    scheduler.start()
    logfire.info("Scheduler started successfully")


def stop_scheduler() -> None:
    """Stop the scheduler.

    This should be called during FastAPI app shutdown.
    """
    logfire.info("Stopping scheduler")
    scheduler.shutdown(wait=True)
    logfire.info("Scheduler stopped")
