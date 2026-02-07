"""Recurrence parsing utilities for chore scheduling."""

import re
from datetime import datetime, timedelta

from croniter import croniter


def cron_to_human(cron_expr: str) -> str:
    """Convert a CRON expression to human-readable text.

    Args:
        cron_expr: CRON expression (e.g., "0 12 * * 1") or INTERVAL format

    Returns:
        Human-readable description (e.g., "every Monday at 12:00 PM")
    """
    # Handle INTERVAL format (e.g., "INTERVAL:3:0 0 * * *")
    if cron_expr.startswith("INTERVAL:"):
        parts = cron_expr.split(":")
        days = int(parts[1])
        if days == 1:
            return "daily"
        return f"every {days} days"

    # Parse CRON expression
    parts = cron_expr.split()
    if len(parts) != 5:
        return cron_expr  # Return as-is if not valid

    minute, hour, day_of_month, month, day_of_week = parts

    # Build time string
    time_str = ""
    if hour != "*" and minute != "*":
        try:
            h = int(hour)
            m = int(minute)
            if h == 0 and m == 0:
                time_str = " at midnight"
            elif h == 12 and m == 0:
                time_str = " at noon"
            else:
                period = "AM" if h < 12 else "PM"
                display_hour = h if h <= 12 else h - 12
                if display_hour == 0:
                    display_hour = 12
                if m == 0:
                    time_str = f" at {display_hour}:00 {period}"
                else:
                    time_str = f" at {display_hour}:{m:02d} {period}"
        except ValueError:
            pass

    # Determine frequency
    weekday_names = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"]

    # Daily (every day of week, every day of month)
    if day_of_week == "*" and day_of_month == "*" and month == "*":
        return f"daily{time_str}"

    # Weekly (specific day of week)
    if day_of_month == "*" and month == "*" and day_of_week != "*":
        try:
            # Handle comma-separated days
            if "," in day_of_week:
                days = [weekday_names[int(d)] for d in day_of_week.split(",")]
                return f"every {', '.join(days)}{time_str}"
            dow = int(day_of_week)
            return f"every {weekday_names[dow]}{time_str}"
        except (ValueError, IndexError):
            pass

    # Monthly (specific day of month)
    if day_of_week == "*" and month == "*" and day_of_month != "*":
        try:
            dom = int(day_of_month)
            suffix = "th"
            if dom in (1, 21, 31):
                suffix = "st"
            elif dom in (2, 22):
                suffix = "nd"
            elif dom in (3, 23):
                suffix = "rd"
            return f"monthly on the {dom}{suffix}{time_str}"
        except ValueError:
            pass

    # Fallback: return a simplified description
    return f"scheduled ({cron_expr})"


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
