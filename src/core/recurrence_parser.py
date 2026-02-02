"""Recurrence parsing utilities for chore scheduling."""

import functools
import re
from datetime import datetime, timedelta

from croniter import croniter


@functools.lru_cache(maxsize=256)
def parse_recurrence_to_cron(recurrence: str) -> str:
    """Parse recurrence string to CRON expression or INTERVAL:N:cron format."""
    # Normalize input by stripping whitespace
    recurrence_normalized = recurrence.strip()

    # Check if already a valid CRON expression
    if croniter.is_valid(recurrence_normalized):
        return recurrence_normalized

    # Parse "every X days" format
    match = re.match(r"^every\s+(\d+)\s+days?$", recurrence_normalized.lower())
    if match:
        days = int(match.group(1))
        if days <= 0:
            msg = f"Invalid interval: {days} days. Interval must be a positive integer"
            raise ValueError(msg)
        # Encode interval in CRON string: INTERVAL:N:cron_expression
        # This allows us to add N days programmatically instead of using invalid CRON syntax
        return f"INTERVAL:{days}:0 0 * * *"

    msg = f"Invalid recurrence format: {recurrence}. Use CRON expression or 'every X days'"
    raise ValueError(msg)


def parse_recurrence_for_personal_chore(recurrence: str) -> tuple[str | None, datetime | None]:
    """Parse recurrence string for personal chores supporting CRON, interval, or natural language formats."""
    recurrence_lower = recurrence.lower().strip()

    # Check if already a valid CRON expression
    if croniter.is_valid(recurrence):
        return (recurrence, None)

    # Parse "every X days" format
    match = re.match(r"^every\s+(\d+)\s+days?$", recurrence_lower)
    if match:
        days = int(match.group(1))
        if days <= 0:
            msg = f"Invalid interval: {days} days. Interval must be a positive integer"
            raise ValueError(msg)
        return (f"INTERVAL:{days}:0 0 * * *", None)

    # Parse "every morning"
    if recurrence_lower == "every morning":
        return ("0 8 * * *", None)

    # Parse "every [weekday]" (e.g., "every friday")
    weekday_match = re.match(r"^every\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)$", recurrence_lower)
    if weekday_match:
        weekday_map = {
            "monday": 1,
            "tuesday": 2,
            "wednesday": 3,
            "thursday": 4,
            "friday": 5,
            "saturday": 6,
            "sunday": 0,
        }
        day_num = weekday_map[weekday_match.group(1)]
        return (f"0 8 * * {day_num}", None)

    # Parse "by [weekday]" (e.g., "by friday") - one-time task
    by_match = re.match(r"^by\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)$", recurrence_lower)
    if by_match:
        # Calculate next occurrence of this weekday
        today = datetime.now().date()
        target_weekday_map = {
            "monday": 0,
            "tuesday": 1,
            "wednesday": 2,
            "thursday": 3,
            "friday": 4,
            "saturday": 5,
            "sunday": 6,
        }
        target_weekday = target_weekday_map[by_match.group(1)]
        current_weekday = today.weekday()

        # Calculate days until target weekday
        days_ahead = target_weekday - current_weekday
        if days_ahead <= 0:  # Target day already happened this week
            days_ahead += 7

        due_date = datetime.combine(today + timedelta(days=days_ahead), datetime.min.time().replace(hour=8, minute=0))
        return (None, due_date)

    # Invalid format
    msg = (
        f"Invalid recurrence format: {recurrence}. "
        f"Use CRON expression, 'every X days', 'every morning', "
        f"'every [weekday]', or 'by [weekday]'"
    )
    raise ValueError(msg)
