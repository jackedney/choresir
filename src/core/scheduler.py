"""Scheduler for automated jobs (reminders, reports, etc.)."""

import logging

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from src.core import db_client
from src.core.config import constants
from src.domain.user import UserStatus
from src.interface.whatsapp_sender import send_text_message
from src.services.analytics_service import get_household_summary, get_overdue_chores


logger = logging.getLogger(__name__)

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
            logger.info("Sent overdue reminder to %s (%d chores)", user["name"], len(chores))
            return True

        logger.warning("Failed to send reminder to %s: %s", user["name"], result.error)
        return False

    except db_client.RecordNotFoundError:
        logger.warning("User %s not found for overdue reminders", user_id)
        return False
    except Exception as e:
        logger.exception("Error sending reminder to user %s: %s", user_id, e)
        return False


async def send_overdue_reminders() -> None:
    """Send reminders to users with overdue chores.

    Runs daily at 8am. Checks for overdue chores and sends WhatsApp
    messages to assigned users.
    """
    logger.info("Running overdue chore reminders job")

    try:
        # Get all overdue chores
        overdue_chores = await get_overdue_chores()

        if not overdue_chores:
            logger.info("No overdue chores found")
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

        logger.info("Completed overdue reminders job: %d/%d users notified", sent_count, len(chores_by_user))

    except Exception as e:
        logger.exception("Error in overdue reminders job: %s", e)


async def send_daily_report() -> None:
    """Send daily household summary report to all active users.

    Runs daily at 9pm. Sends a summary of the day's completions,
    current conflicts, and pending verifications.
    """
    logger.info("Running daily report job")

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
                    logger.debug("Sent daily report to %s", user["name"])
                else:
                    logger.warning("Failed to send daily report to %s: %s", user["name"], result.error)

            except Exception as e:
                logger.exception("Error sending daily report to user %s: %s", user["id"], e)
                continue

        logger.info("Completed daily report job: sent to %d/%d users", sent_count, len(active_users))

    except Exception as e:
        logger.exception("Error in daily report job: %s", e)


def start_scheduler() -> None:
    """Start the scheduler and register all jobs.

    This should be called during FastAPI app startup.
    """
    logger.info("Starting scheduler")

    # Schedule overdue reminders job (daily at 8am)
    scheduler.add_job(
        send_overdue_reminders,
        trigger=CronTrigger(hour=constants.DAILY_REMINDER_HOUR, minute=0),
        id="overdue_reminders",
        name="Send Overdue Chore Reminders",
        replace_existing=True,
    )
    logger.info("Scheduled overdue reminders job: daily at %d:00", constants.DAILY_REMINDER_HOUR)

    # Schedule daily report job (daily at 9pm)
    scheduler.add_job(
        send_daily_report,
        trigger=CronTrigger(hour=constants.DAILY_REPORT_HOUR, minute=0),
        id="daily_report",
        name="Send Daily Household Report",
        replace_existing=True,
    )
    logger.info("Scheduled daily report job: daily at %d:00", constants.DAILY_REPORT_HOUR)

    # Start the scheduler
    scheduler.start()
    logger.info("Scheduler started successfully")


def stop_scheduler() -> None:
    """Stop the scheduler.

    This should be called during FastAPI app shutdown.
    """
    logger.info("Stopping scheduler")
    scheduler.shutdown(wait=True)
    logger.info("Scheduler stopped")
