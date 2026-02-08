"""Recurrence parsing utilities for chore scheduling."""

import re
from datetime import datetime, timedelta

from croniter import croniter


# Constants for magic numbers
CRON_PARTS_COUNT = 5
NOON_HOUR = 12
HOURS_IN_HALF_DAY = 12

WEEKDAY_NAMES = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]


def _format_time_string(hour: int, minute: int) -> str:
    """Format hour and minute into a human-readable time string.

    Args:
        hour: Hour in 24-hour format (0-23)
        minute: Minute (0-59)

    Returns:
        Formatted time string (e.g., " at 3:00 PM", " at midnight", " at noon")
    """
    if hour == 0 and minute == 0:
        return " at midnight"
    if hour == NOON_HOUR and minute == 0:
        return " at noon"

    period = "AM" if hour < HOURS_IN_HALF_DAY else "PM"
    display_hour = hour if hour <= HOURS_IN_HALF_DAY else hour - HOURS_IN_HALF_DAY
    if display_hour == 0:
        display_hour = HOURS_IN_HALF_DAY

    if minute == 0:
        return f" at {display_hour}:00 {period}"
    return f" at {display_hour}:{minute:02d} {period}"


def _parse_time_from_cron(hour: str, minute: str) -> str:
    """Parse hour and minute from CRON parts into a time string.

    Args:
        hour: Hour part from CRON expression
        minute: Minute part from CRON expression

    Returns:
        Formatted time string, or empty string if parsing fails
    """
    if hour == "*" or minute == "*":
        return ""
    try:
        return _format_time_string(int(hour), int(minute))
    except ValueError:
        return ""


def _format_weekly_schedule(day_of_week: str, time_str: str) -> str | None:
    """Format a weekly schedule description.

    Args:
        day_of_week: Day of week from CRON expression
        time_str: Formatted time string

    Returns:
        Human-readable weekly schedule, or None if parsing fails
    """
    try:
        if "," in day_of_week:
            days = [WEEKDAY_NAMES[int(d)] for d in day_of_week.split(",")]
            return f"every {', '.join(days)}{time_str}"
        dow = int(day_of_week)
        return f"every {WEEKDAY_NAMES[dow]}{time_str}"
    except (ValueError, IndexError):
        return None


def _get_day_suffix(day: int) -> str:
    """Get the ordinal suffix for a day number.

    Args:
        day: Day of month (1-31)

    Returns:
        Ordinal suffix ("st", "nd", "rd", or "th")
    """
    if day in (1, 21, 31):
        return "st"
    if day in (2, 22):
        return "nd"
    if day in (3, 23):
        return "rd"
    return "th"


def _format_monthly_schedule(day_of_month: str, time_str: str) -> str | None:
    """Format a monthly schedule description.

    Args:
        day_of_month: Day of month from CRON expression
        time_str: Formatted time string

    Returns:
        Human-readable monthly schedule, or None if parsing fails
    """
    try:
        dom = int(day_of_month)
        suffix = _get_day_suffix(dom)
        return f"monthly on the {dom}{suffix}{time_str}"
    except ValueError:
        return None


def _parse_interval_format(cron_expr: str) -> str | None:
    """Parse INTERVAL format and return human-readable description.

    Args:
        cron_expr: CRON expression that may be in INTERVAL format

    Returns:
        Human-readable description, or None if not an INTERVAL format
    """
    if not cron_expr.startswith("INTERVAL:"):
        return None
    parts = cron_expr.split(":")
    days = int(parts[1])
    if days == 1:
        return "daily"
    return f"every {days} days"


def _parse_standard_cron(cron_expr: str) -> str:
    """Parse standard CRON expression and return human-readable description.

    Args:
        cron_expr: Standard CRON expression (e.g., "0 12 * * 1")

    Returns:
        Human-readable description
    """
    parts = cron_expr.split()
    if len(parts) != CRON_PARTS_COUNT:
        return cron_expr  # Return as-is if not valid

    minute, hour, day_of_month, month, day_of_week = parts
    time_str = _parse_time_from_cron(hour, minute)

    # Daily (every day of week, every day of month)
    if day_of_week == "*" and day_of_month == "*" and month == "*":
        return f"daily{time_str}"

    # Weekly (specific day of week)
    if day_of_month == "*" and month == "*" and day_of_week != "*":
        result = _format_weekly_schedule(day_of_week, time_str)
        if result is not None:
            return result

    # Monthly (specific day of month)
    if day_of_week == "*" and month == "*" and day_of_month != "*":
        result = _format_monthly_schedule(day_of_month, time_str)
        if result is not None:
            return result

    # Fallback: return a simplified description
    return f"scheduled ({cron_expr})"


def cron_to_human(cron_expr: str) -> str:
    """Convert a CRON expression to human-readable text.

    Args:
        cron_expr: CRON expression (e.g., "0 12 * * 1") or INTERVAL format

    Returns:
        Human-readable description (e.g., "every Monday at 12:00 PM")
    """
    # Handle INTERVAL format (e.g., "INTERVAL:3:0 0 * * *")
    interval_result = _parse_interval_format(cron_expr)
    if interval_result is not None:
        return interval_result

    # Parse standard CRON expression
    return _parse_standard_cron(cron_expr)


def parse_recurrence_to_cron(recurrence: str) -> str:
    """Parse recurrence string to CRON expression.

    Supports:
    - Direct CRON expressions (e.g., "0 20 * * *")
    - Interval format (e.g., "every 3 days")

    Args:
        recurrence: Recurrence string

    Returns:
        CRON expression

    Raises:
        ValueError: If recurrence format is invalid
    """
    # Check if already a valid CRON expression
    if croniter.is_valid(recurrence):
        return recurrence

    # Parse "every X days" format
    match = re.match(r"^every\s+(\d+)\s+days?$", recurrence.lower())
    if match:
        days = int(match.group(1))
        # Encode interval in CRON string: INTERVAL:N:cron_expression
        # This allows us to add N days programmatically instead of using invalid CRON syntax
        return f"INTERVAL:{days}:0 0 * * *"

    msg = f"Invalid recurrence format: {recurrence}. Use CRON expression or 'every X days'"
    raise ValueError(msg)


def parse_recurrence_for_personal_chore(recurrence: str) -> tuple[str | None, datetime | None]:
    """Parse recurrence string for personal chores.

    Supports:
    - Direct CRON expressions (e.g., "0 20 * * *")
    - "every X days" format (e.g., "every 3 days")
    - "every morning" → 0 8 * * * (daily at 8 AM)
    - "every Friday" → 0 8 * * 5 (weekly on Friday at 8 AM)
    - "by Friday" → one-time task with due date (no recurrence)

    Args:
        recurrence: Recurrence string from user input

    Returns:
        Tuple of (cron_expression, due_date)
        - If recurring: (cron_string, None)
        - If one-time: (None, due_date)

    Raises:
        ValueError: If recurrence format is invalid
    """
    recurrence_lower = recurrence.lower().strip()

    # Check if already a valid CRON expression
    if croniter.is_valid(recurrence):
        return (recurrence, None)

    # Parse "every X days" format
    match = re.match(r"^every\s+(\d+)\s+days?$", recurrence_lower)
    if match:
        days = int(match.group(1))
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
