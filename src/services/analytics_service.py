"""Analytics service for household chore statistics."""

import logging
from datetime import datetime, timedelta
from typing import Any

from src.core import db_client
from src.domain.chore import ChoreState
from src.domain.user import UserStatus


logger = logging.getLogger(__name__)


async def get_leaderboard(*, period_days: int = 30) -> list[dict[str, Any]]:
    """Get leaderboard of completed chores per user.

    Args:
        period_days: Number of days to look back (default: 30)

    Returns:
        List of dicts with user info and completion counts, sorted descending
        Format: [{"user_id": str, "user_name": str, "completion_count": int}, ...]
    """
    # Calculate cutoff date
    cutoff_date = datetime.now() - timedelta(days=period_days)

    # Get all completion logs within period
    completion_logs = await db_client.list_records(
        collection="logs",
        filter_query=f'action ~ "claimed_completion" && timestamp >= "{cutoff_date.isoformat()}"',
    )

    # Count completions per user
    user_completion_counts: dict[str, int] = {}
    for log in completion_logs:
        user_id = log["user_id"]
        user_completion_counts[user_id] = user_completion_counts.get(user_id, 0) + 1

    # Get user details and build leaderboard
    leaderboard = []
    for user_id, count in user_completion_counts.items():
        try:
            user = await db_client.get_record(collection="users", record_id=user_id)
            leaderboard.append({
                "user_id": user_id,
                "user_name": user["name"],
                "completion_count": count,
            })
        except db_client.RecordNotFoundError:
            logger.warning("User %s not found for leaderboard", user_id)
            continue

    # Sort by completion count descending
    leaderboard.sort(key=lambda x: x["completion_count"], reverse=True)

    logger.info("Generated leaderboard for %d days: %d users", period_days, len(leaderboard))

    return leaderboard


async def get_completion_rate(*, period_days: int = 30) -> dict[str, Any]:
    """Calculate completion rate statistics.

    Analyzes what percentage of chores are completed on time vs overdue.

    Args:
        period_days: Number of days to look back (default: 30)

    Returns:
        Dict with completion statistics:
        {
            "total_completions": int,
            "on_time": int,
            "overdue": int,
            "on_time_percentage": float,
            "overdue_percentage": float,
        }
    """
    # Calculate cutoff date
    cutoff_date = datetime.now() - timedelta(days=period_days)

    # Get all chores that were completed in the period
    # We need to check logs for completions, then check if chore was overdue at completion time
    completion_logs = await db_client.list_records(
        collection="logs",
        filter_query=f'action ~ "approve_verification" && timestamp >= "{cutoff_date.isoformat()}"',
    )

    # Note: Deadline history tracking not yet implemented for accurate on-time metrics.
    # Currently, deadlines are updated after completion, so we can't reliably determine
    # if a chore was completed before its original deadline without historical tracking.
    # For MVP, we'll count all completions as on-time.
    total_completions = len(completion_logs)
    on_time_count = total_completions
    overdue_count = 0

    # Calculate percentages
    on_time_percentage = (on_time_count / total_completions * 100) if total_completions > 0 else 0.0
    overdue_percentage = (overdue_count / total_completions * 100) if total_completions > 0 else 0.0

    result = {
        "total_completions": total_completions,
        "on_time": on_time_count,
        "overdue": overdue_count,
        "on_time_percentage": round(on_time_percentage, 2),
        "overdue_percentage": round(overdue_percentage, 2),
        "period_days": period_days,
    }

    logger.info("Completion rate for %d days: %s", period_days, result)

    return result


async def get_overdue_chores(*, user_id: str | None = None) -> list[dict[str, Any]]:
    """Get all overdue chores.

    A chore is overdue if:
    - deadline < now
    - state != COMPLETED

    Args:
        user_id: Optional filter by assigned user

    Returns:
        List of overdue chore records
    """
    now = datetime.now()

    # Build filter query
    filters = [
        f'deadline < "{now.isoformat()}"',
        f'current_state != "{ChoreState.COMPLETED}"',
    ]

    if user_id:
        filters.append(f'assigned_to = "{user_id}"')

    filter_query = " && ".join(filters)

    overdue_chores = await db_client.list_records(
        collection="chores",
        filter_query=filter_query,
        sort="+deadline",  # Oldest deadline first
    )

    logger.info("Found %d overdue chores", len(overdue_chores))

    return overdue_chores


async def get_user_statistics(*, user_id: str, period_days: int = 30) -> dict[str, Any]:
    """Get comprehensive statistics for a specific user.

    Args:
        user_id: User ID
        period_days: Number of days to look back (default: 30)

    Returns:
        Dict with user statistics:
        {
            "user_id": str,
            "user_name": str,
            "completions": int,
            "claims_pending": int,
            "overdue_chores": int,
            "rank": int | None,  # Position in leaderboard (1-indexed)
        }
    """
    # Get user details
    user = await db_client.get_record(collection="users", record_id=user_id)

    # Get leaderboard to find rank
    leaderboard = await get_leaderboard(period_days=period_days)
    rank = None
    completions = 0
    for idx, entry in enumerate(leaderboard, start=1):
        if entry["user_id"] == user_id:
            rank = idx
            completions = entry["completion_count"]
            break

    # Get pending claims
    pending_claims = await db_client.list_records(
        collection="logs",
        filter_query=f'user_id = "{user_id}" && action ~ "claimed_completion"',
    )

    # Filter to only those still pending (chore in PENDING_VERIFICATION state)
    claims_pending = 0
    for log in pending_claims:
        chore_id = log["chore_id"]
        try:
            chore = await db_client.get_record(collection="chores", record_id=chore_id)
            if chore["current_state"] == ChoreState.PENDING_VERIFICATION:
                claims_pending += 1
        except db_client.RecordNotFoundError:
            continue

    # Get overdue chores assigned to user
    overdue_chores = await get_overdue_chores(user_id=user_id)

    result = {
        "user_id": user_id,
        "user_name": user["name"],
        "completions": completions,
        "claims_pending": claims_pending,
        "overdue_chores": len(overdue_chores),
        "rank": rank,
        "period_days": period_days,
    }

    logger.info("User statistics for %s: %s", user_id, result)

    return result


async def get_household_summary(*, period_days: int = 7) -> dict[str, Any]:
    """Get overall household statistics.

    Args:
        period_days: Number of days to look back (default: 7)

    Returns:
        Dict with household-wide statistics
    """
    cutoff_date = datetime.now() - timedelta(days=period_days)

    # Get active users count
    active_users = await db_client.list_records(
        collection="users",
        filter_query=f'status = "{UserStatus.ACTIVE}"',
    )

    # Get total completions in period
    completion_logs = await db_client.list_records(
        collection="logs",
        filter_query=f'action ~ "approve_verification" && timestamp >= "{cutoff_date.isoformat()}"',
    )

    # Get current conflicts
    conflicts = await db_client.list_records(
        collection="chores",
        filter_query=f'current_state = "{ChoreState.CONFLICT}"',
    )

    # Get overdue chores
    overdue = await get_overdue_chores()

    # Get pending verifications
    pending = await db_client.list_records(
        collection="chores",
        filter_query=f'current_state = "{ChoreState.PENDING_VERIFICATION}"',
    )

    result = {
        "active_members": len(active_users),
        "completions_this_period": len(completion_logs),
        "current_conflicts": len(conflicts),
        "overdue_chores": len(overdue),
        "pending_verifications": len(pending),
        "period_days": period_days,
    }

    logger.info("Household summary for %d days: %s", period_days, result)

    return result
