"""Analytics service for household chore statistics."""

import json
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from src.core import db_client
from src.core.logging import span
from src.core.redis_client import redis_client
from src.domain.chore import ChoreState
from src.domain.user import UserStatus


logger = logging.getLogger(__name__)

_CACHE_TTL_SECONDS = 300  # 5 minutes
_CACHE_KEY_PREFIX = "choresir:leaderboard"


async def invalidate_leaderboard_cache() -> None:
    """Invalidate all leaderboard cache entries.

    This function clears all cached leaderboard data from Redis to ensure fresh
    data is served after events that change completion counts (e.g., chore verification).

    Cache invalidation is best-effort:
    - Failures are logged but don't raise exceptions
    - Core functionality continues even if cache invalidation fails
    - Stale cache (up to TTL) is acceptable if Redis is unavailable

    The function uses pattern matching to find all leaderboard cache keys
    (format: "choresir:leaderboard:*") and deletes them in a single operation.
    """
    try:
        # Find all leaderboard cache keys using pattern matching
        # This handles all period variants (7, 30, 90, etc.)
        pattern = f"{_CACHE_KEY_PREFIX}:*"
        keys = await redis_client.keys(pattern)

        if keys:
            # Delete all matching keys in a single operation
            await redis_client.delete(*keys)
            logger.info("Invalidated %d leaderboard cache entries", len(keys))
        else:
            logger.debug("No leaderboard cache entries to invalidate")
    except Exception as e:
        # Log warning but don't raise - cache invalidation failure shouldn't break app
        logger.warning("Failed to invalidate leaderboard cache: %s", e)


async def get_leaderboard(*, period_days: int = 30) -> list[dict[str, Any]]:
    """Get leaderboard of completed chores per user.

    Args:
        period_days: Number of days to look back (default: 30)

    Returns:
        List of dicts with user info and completion counts, sorted descending
        Format: [{"user_id": str, "user_name": str, "completion_count": int}, ...]
    """
    # Check Redis cache
    cache_key = f"{_CACHE_KEY_PREFIX}:{period_days}"
    try:
        cached_value = await redis_client.get(cache_key)
        if cached_value:
            try:
                leaderboard = json.loads(cached_value)
                logger.debug("Returning cached leaderboard for %d days from Redis", period_days)
                return leaderboard
            except json.JSONDecodeError as e:
                logger.warning("Failed to deserialize cached leaderboard: %s", e)
                # Continue to regenerate cache
    except Exception as e:
        logger.warning("Failed to retrieve cached leaderboard from Redis: %s", e)
        # Continue without cache - will fetch from DB

    with span("analytics_service.get_leaderboard"):
        # Calculate cutoff date
        now = datetime.now(UTC)
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

        # Optimization: Fetch all users in a single query to avoid N+1 queries
        # Previously, we called get_record() for each user (one query per user)
        # Now we fetch all users once and build an in-memory map for O(1) lookups
        # Per-page limit of 500 is sufficient for typical household sizes (2-20 members)
        # If a household exceeds 500 users, only the first 500 will be included in leaderboard
        # This is acceptable as such large households are extremely unlikely
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

        # Update Redis cache
        try:
            cache_value = json.dumps(leaderboard)
            await redis_client.set(cache_key, cache_value, _CACHE_TTL_SECONDS)
        except Exception as e:
            logger.warning("Failed to cache leaderboard in Redis: %s", e)
            # Continue without caching - function still returns correct data

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
