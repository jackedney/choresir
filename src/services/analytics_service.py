"""Analytics service for household chore statistics."""

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from src.core import db_client
from src.core.logging import span
from src.domain.chore import ChoreState
from src.domain.user import UserStatus


logger = logging.getLogger(__name__)

# Simple in-memory cache for leaderboard: {period_days: (timestamp, data)}
_leaderboard_cache: dict[int, tuple[datetime, list[dict[str, Any]]]] = {}
_CACHE_TTL_SECONDS = 300  # 5 minutes


async def get_leaderboard(*, period_days: int = 30) -> list[dict[str, Any]]:
    """Get leaderboard of completed chores per user.

    Args:
        period_days: Number of days to look back (default: 30)

    Returns:
        List of dicts with user info and completion counts, sorted descending
        Format: [{"user_id": str, "user_name": str, "completion_count": int}, ...]
    """
    # Check cache
    now = datetime.now(UTC)
    if period_days in _leaderboard_cache:
        cached_ts, cached_data = _leaderboard_cache[period_days]
        if (now - cached_ts).total_seconds() < _CACHE_TTL_SECONDS:
            logger.debug("Returning cached leaderboard for %d days", period_days)
            return cached_data

    with span("analytics_service.get_leaderboard"):
        # Calculate cutoff date
        cutoff_date = now - timedelta(days=period_days)

        # Get all completion logs within period
        completion_logs = await db_client.list_records(
            collection="logs",
            filter_query=f'action = "claimed_completion" && timestamp >= "{cutoff_date.isoformat()}"',
        )

        # Count completions per user
        user_completion_counts: dict[str, int] = {}
        for log in completion_logs:
            user_id = log["user_id"]
            user_completion_counts[user_id] = user_completion_counts.get(user_id, 0) + 1

        # Get all users in one batch to avoid N+1 queries
        # Assuming household size is small enough to fit in one page (default 500 here to be safe)
        all_users = await db_client.list_records(collection="users", per_page=500)
        users_map = {u["id"]: u for u in all_users}

        # Build leaderboard
        leaderboard = []
        for user_id, count in user_completion_counts.items():
            if user_id in users_map:
                user = users_map[user_id]
                leaderboard.append(
                    {
                        "user_id": user_id,
                        "user_name": user["name"],
                        "completion_count": count,
                    }
                )
            else:
                logger.warning("User %s not found for leaderboard", user_id)
                continue

        # Sort by completion count descending
        leaderboard.sort(key=lambda x: x["completion_count"], reverse=True)

        logger.info("Generated leaderboard for %d days: %d users", period_days, len(leaderboard))

        # Update cache
        _leaderboard_cache[period_days] = (now, leaderboard)

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
    with span("analytics_service.get_completion_rate"):
        # Calculate cutoff date
        cutoff_date = datetime.now(UTC) - timedelta(days=period_days)

        # Get all chores that were completed in the period
        # We need to check logs for completions, then check if chore was overdue at completion time
        completion_logs = await db_client.list_records(
            collection="logs",
            filter_query=f'action = "approve_verification" && timestamp >= "{cutoff_date.isoformat()}"',
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


async def get_overdue_chores(*, user_id: str | None = None, limit: int | None = None) -> list[dict[str, Any]]:
    """Get all overdue chores.

    A chore is overdue if:
    - deadline < now
    - state != COMPLETED

    Args:
        user_id: Optional filter by assigned user
        limit: Optional maximum number of results to return

    Returns:
        List of overdue chore records
    """
    with span("analytics_service.get_overdue_chores"):
        now = datetime.now(UTC)

        # Build filter query
        filters = [
            f'deadline < "{now.isoformat()}"',
            f'current_state != "{ChoreState.COMPLETED}"',
        ]

        if user_id:
            filters.append(f'assigned_to = "{user_id}"')

        filter_query = " && ".join(filters)

        # Fetch overdue chores with optional limit
        if limit is not None:
            overdue_chores = await db_client.list_records(
                collection="chores",
                filter_query=filter_query,
                sort="+deadline",  # Oldest deadline first
                per_page=limit,
            )
        else:
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
    with span("analytics_service.get_user_statistics"):
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

        # Get all pending verification chores first (single query)
        pending_verification_chores = await db_client.list_records(
            collection="chores",
            filter_query=f'current_state = "{ChoreState.PENDING_VERIFICATION}"',
            per_page=500,
        )
        pending_chore_ids = {chore["id"] for chore in pending_verification_chores}

        # Get pending claims for this user
        pending_claims = await db_client.list_records(
            collection="logs",
            filter_query=f'user_id = "{user_id}" && action = "claimed_completion"',
            per_page=500,
            sort="",  # No sort to avoid issues
        )

        # Count claims that are still pending (chore in PENDING_VERIFICATION state)
        claims_pending = sum(1 for log in pending_claims if log["chore_id"] in pending_chore_ids)

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
    with span("analytics_service.get_household_summary"):
        cutoff_date = datetime.now(UTC) - timedelta(days=period_days)

        # Get active users count
        active_users = await db_client.list_records(
            collection="users",
            filter_query=f'status = "{UserStatus.ACTIVE}"',
        )

        # Get total completions in period
        completion_logs = await db_client.list_records(
            collection="logs",
            filter_query=f'action = "approve_verification" && timestamp >= "{cutoff_date.isoformat()}"',
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
