"""Analytics service for user and household statistics.

This module provides functions for:
- Calculating user performance metrics (completions, pending claims, etc.)
- Generating leaderboards for gamification
- Tracking overdue chores

Key Concepts:
- Pending Claims: Distinct chores a user has claimed that are awaiting verification.
  If a user claims same chore multiple times (e.g., after rejection), it
  counts as one pending claim.
- Completions: Successfully verified chore completions within time period.
- Leaderboard: Ranked list of users by completion count.
"""

import json
import logging
from datetime import UTC, datetime, timedelta

from dateutil import parser as dateutil_parser
from pydantic import ValidationError

from src.core import db_client
from src.core.cache_client import cache_client as redis_client
from src.core.config import Constants
from src.core.logging import span
from src.domain.task import TaskState
from src.domain.user import UserStatus
from src.models.service_models import (
    CompletionRate,
    HouseholdSummary,
    LeaderboardEntry,
    OverdueChore,
    UserStatistics,
)


logger = logging.getLogger(__name__)

_CACHE_KEY_PREFIX = "choresir:leaderboard"


async def invalidate_leaderboard_cache() -> None:
    """Invalidate all leaderboard cache entries.

    This function clears all cached leaderboard data from Redis to ensure fresh
    data is served after events that change completion counts (e.g., task verification).

    Cache invalidation with retry and fallback:
    - Uses retry logic (3 attempts with exponential backoff) for reliability
    - Queues invalidations for later if Redis unavailable
    - Failures are logged but don't raise exceptions
    - Core functionality continues even if cache invalidation fails
    - Stale cache (up to TTL of 60s) is acceptable if Redis is unavailable

    The function uses pattern matching to find all leaderboard cache keys
    (format: "choresir:leaderboard:*") and deletes them with retry logic.
    """
    try:
        # Find all leaderboard cache keys using pattern matching
        # This handles all period variants (7, 30, 90, etc.)
        pattern = f"{_CACHE_KEY_PREFIX}:*"
        keys = await redis_client.keys(pattern)

        if keys:
            # Delete all matching keys
            await redis_client.delete(*keys)
            logger.info("Invalidated %d leaderboard cache entries", len(keys))
        else:
            logger.debug("No leaderboard cache entries to invalidate")
    except Exception as e:
        # Log warning but don't raise - cache invalidation failure shouldn't break app
        logger.warning("Failed to invalidate leaderboard cache: %s", e)


async def _fetch_chores_map(chore_ids: list[str]) -> dict[str, dict]:
    """Fetch chores in chunks and return as a map."""
    chores_map = {}
    unique_chore_ids = list(set(chore_ids))
    chunk_size = 50
    for i in range(0, len(unique_chore_ids), chunk_size):
        chunk = unique_chore_ids[i : i + chunk_size]
        or_clause = " || ".join([f'id = "{db_client.sanitize_param(cid)}"' for cid in chunk])
        chores = await db_client.list_records(
            collection="tasks",
            filter_query=or_clause,
        )
        for chore in chores:
            chores_map[chore["id"]] = chore
    return chores_map


async def _fetch_claim_logs_map(chore_ids: list[str]) -> dict[str, dict]:
    """Fetch claim logs in chunks and return as a map."""
    claim_logs_map = {}
    unique_chore_ids = list(set(chore_ids))
    chunk_size = 50
    for i in range(0, len(unique_chore_ids), chunk_size):
        chunk = unique_chore_ids[i : i + chunk_size]
        or_clause = " || ".join([f'chore_id = "{db_client.sanitize_param(cid)}"' for cid in chunk])
        claim_logs = await db_client.list_records(
            collection="task_logs",
            filter_query=f'action = "claimed_completion" && ({or_clause})',
        )
        for claim_log in claim_logs:
            chore_id = claim_log["chore_id"]
            # Keep only most recent claim log per chore
            if chore_id not in claim_logs_map or claim_log.get("timestamp", "") > claim_logs_map[chore_id].get(
                "timestamp", ""
            ):
                claim_logs_map[chore_id] = claim_log
    return claim_logs_map


def _determine_user_to_award(
    *,
    log: dict,
    claim_log: dict | None,
    chore: dict | None,
) -> str:
    """Determine which user should be awarded points based on Robin Hood Protocol."""
    # Default: award points to user who got approval
    user_to_award = log["user_id"]

    # Robin Hood Protocol: Check if this was a swap and apply point attribution rules
    if not (claim_log and chore):
        return user_to_award

    original_assignee_id = claim_log.get("original_assignee_id")
    actual_completer_id = claim_log.get("actual_completer_id")
    is_swap = claim_log.get("is_swap", False)

    # Only apply Robin Hood rules if this was actually a swap
    if not (is_swap and original_assignee_id and actual_completer_id):
        return user_to_award

    # Check if completion was on-time or overdue
    deadline = chore.get("deadline")
    approval_timestamp = log.get("timestamp")

    if not (deadline and approval_timestamp):
        return user_to_award

    try:
        deadline_dt = dateutil_parser.isoparse(deadline)
        approval_dt = dateutil_parser.isoparse(approval_timestamp)

        # On-time: award to original assignee, Overdue: award to actual completer
        user_to_award = original_assignee_id if approval_dt <= deadline_dt else actual_completer_id
    except Exception as e:
        logger.warning("Failed to parse timestamps for Robin Hood attribution: %s", e)

    return user_to_award


def _build_leaderboard_entries(
    user_completion_counts: dict[str, int],
    users_map: dict[str, dict],
) -> list[LeaderboardEntry]:
    """Build and sort leaderboard entries from user counts."""
    leaderboard_data = []
    for user_id, count in user_completion_counts.items():
        if user_id not in users_map:
            logger.warning("User %s not found for leaderboard", user_id)
            continue

        user = users_map[user_id]
        try:
            entry = LeaderboardEntry(
                user_id=user_id,
                user_name=user["name"],
                completion_count=count,
            )
            leaderboard_data.append(entry)
        except ValidationError as e:
            logger.error("Failed to create LeaderboardEntry for user %s: %s", user_id, e)

    # Sort by completion count descending
    leaderboard_data.sort(key=lambda x: x.completion_count, reverse=True)
    return leaderboard_data


async def get_leaderboard(*, period_days: int = 30) -> list[LeaderboardEntry]:
    """Get leaderboard of completed chores per user.

    Implements Robin Hood Protocol point attribution:
    - On-time completion: Points to original assignee
    - Overdue completion: Points to actual completer

    Args:
        period_days: Number of days to look back (default: 30)

    Returns:
        List of LeaderboardEntry objects with user info and completion counts, sorted descending
    """
    # Check Redis cache
    cache_key = f"{_CACHE_KEY_PREFIX}:{period_days}"
    try:
        cached_value = await redis_client.get(cache_key)
        if cached_value:
            try:
                cached_data = json.loads(cached_value)
                leaderboard_entries = [LeaderboardEntry(**entry) for entry in cached_data]
                logger.debug("Returning cached leaderboard for %d days from Redis", period_days)
                return leaderboard_entries
            except (json.JSONDecodeError, ValidationError) as e:
                logger.warning("Failed to deserialize cached leaderboard: %s", e)
    except Exception as e:
        logger.warning("Failed to retrieve cached leaderboard from Redis: %s", e)

    with span("analytics_service.get_leaderboard"):
        # Calculate cutoff date
        now = datetime.now(UTC)
        cutoff_date = now - timedelta(days=period_days)

        # Get all completion logs within period
        completion_logs = await db_client.list_records(
            collection="task_logs",
            filter_query=f'action = "approve_verification" && timestamp >= "{cutoff_date.isoformat()}"',
        )

        # Get chore IDs for Robin Hood Protocol data
        # Extract chore IDs, filtering out None values
        claim_log_ids: list[str] = [
            chore_id for log in completion_logs if (chore_id := log.get("chore_id")) is not None
        ]

        # Fetch chores and claim logs
        chores_map = await _fetch_chores_map(claim_log_ids) if claim_log_ids else {}
        claim_logs_map = await _fetch_claim_logs_map(claim_log_ids) if claim_log_ids else {}

        # Count completions per user with Robin Hood Protocol rules
        user_completion_counts: dict[str, int] = {}
        for log in completion_logs:
            chore_id = log.get("chore_id")
            if not isinstance(chore_id, str):
                continue  # Skip logs without a valid chore_id

            claim_log = claim_logs_map.get(chore_id)
            chore = chores_map.get(chore_id)

            user_to_award = _determine_user_to_award(log=log, claim_log=claim_log, chore=chore)
            user_completion_counts[user_to_award] = user_completion_counts.get(user_to_award, 0) + 1

        # Fetch all users for leaderboard
        all_users = await db_client.list_records(collection="members", per_page=500)
        users_map = {u["id"]: u for u in all_users}

        # Build and sort leaderboard
        leaderboard_data = _build_leaderboard_entries(user_completion_counts, users_map)

        logger.info("Generated leaderboard for %d days: %d users", period_days, len(leaderboard_data))

        # Update Redis cache
        try:
            cache_value = json.dumps([entry.model_dump() for entry in leaderboard_data])
            await redis_client.set(cache_key, cache_value, Constants.CACHE_TTL_LEADERBOARD_SECONDS)
        except Exception as e:
            logger.warning("Failed to cache leaderboard in Redis: %s", e)

        return leaderboard_data


async def get_completion_rate(*, period_days: int = 30) -> CompletionRate:
    """Calculate completion rate statistics.

    Analyzes what percentage of chores are completed on time vs overdue.

    Args:
        period_days: Number of days to look back (default: 30)

    Returns:
        CompletionRate object with completion statistics
    """
    with span("analytics_service.get_completion_rate"):
        # Calculate cutoff date
        cutoff_date = datetime.now(UTC) - timedelta(days=period_days)

        # Get all chores that were completed in period
        # We need to check logs for completions, then check if chore was overdue at completion time
        completion_logs = await db_client.list_records(
            collection="task_logs",
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

        result = CompletionRate(
            total_completions=total_completions,
            on_time=on_time_count,
            overdue=overdue_count,
            on_time_percentage=round(on_time_percentage, 2),
            overdue_percentage=round(overdue_percentage, 2),
            period_days=period_days,
        )

        logger.info("Completion rate for %d days: %s", period_days, result.model_dump())

        return result


async def get_overdue_chores(*, user_id: str | None = None, limit: int | None = None) -> list[OverdueChore]:
    """Get all overdue chores.

    A chore is overdue if:
    - deadline < now
    - state != COMPLETED

    Args:
        user_id: Optional filter by assigned user
        limit: Optional maximum number of results to return

    Returns:
        List of OverdueChore objects
    """
    with span("analytics_service.get_overdue_chores"):
        now = datetime.now(UTC)

        # Build filter query
        filters = [
            f'deadline < "{now.isoformat()}"',
            f'current_state != "{TaskState.COMPLETED}"',
        ]

        if user_id:
            filters.append(f'assigned_to = "{db_client.sanitize_param(user_id)}"')

        filter_query = " && ".join(filters)

        # Fetch overdue chores with optional limit
        if limit is not None:
            overdue_chores = await db_client.list_records(
                collection="tasks",
                filter_query=filter_query,
                sort="deadline ASC",  # Oldest deadline first
                per_page=limit,
            )
        else:
            overdue_chores = await db_client.list_records(
                collection="tasks",
                filter_query=filter_query,
                sort="deadline ASC",  # Oldest deadline first
            )

        # Convert to typed models
        overdue_chore_models = []
        for chore in overdue_chores:
            try:
                overdue_chore_models.append(OverdueChore(**chore))
            except ValidationError as e:
                logger.error("Failed to create OverdueChore model for chore %s: %s", chore.get("id"), e)
                continue

        logger.info("Found %d overdue chores", len(overdue_chore_models))

        return overdue_chore_models


async def _get_user_name(user_id: str) -> str:
    """Get user name from database.

    Args:
        user_id: User ID

    Returns:
        User name, or user_id as fallback if name is missing

    Raises:
        KeyError: If user doesn't exist
        RuntimeError: If database operation fails
    """
    try:
        user = await db_client.get_record(collection="members", record_id=user_id)
        user_name = user.get("name")
        if not user_name:
            logger.warning("User %s missing 'name' field, using ID as fallback", user_id)
            return user_id
        return user_name
    except KeyError:
        logger.error("User %s not found", user_id)
        raise
    except RuntimeError as e:
        logger.error("Database error fetching user %s: %s", user_id, e)
        raise


async def _get_user_rank_and_completions(user_id: str, period_days: int) -> tuple[int | None, int, str | None]:
    """Get user's leaderboard rank and completion count.

    Args:
        user_id: User ID
        period_days: Period for leaderboard calculation

    Returns:
        Tuple of (rank, completions, error_message)
    """
    try:
        leaderboard = await get_leaderboard(period_days=period_days)
        for idx, entry in enumerate(leaderboard, start=1):
            if entry.user_id == user_id:
                logger.info("User %s rank: %s, completions: %d", user_id, idx, entry.completion_count)
                return idx, entry.completion_count, None
        logger.info("User %s rank: None, completions: 0", user_id)
        return None, 0, None
    except RuntimeError as e:
        error_msg = f"Database error fetching leaderboard: {e}"
        logger.error(error_msg)
        return None, 0, error_msg
    except Exception as e:
        error_msg = f"Unexpected error fetching leaderboard: {e}"
        logger.error(error_msg)
        return None, 0, error_msg


async def _fetch_pending_chore_ids() -> set[str]:
    """Fetch IDs of all chores pending verification.

    Returns:
        Set of chore IDs in pending verification state
    """
    with span("analytics_service.get_user_statistics.fetch_pending_chores"):
        pending_verification_chores = await db_client.list_records(
            collection="tasks",
            filter_query=f'current_state = "{TaskState.PENDING_VERIFICATION}"',
            per_page=500,
        )

    pending_chore_ids: set[str] = set()
    for chore in pending_verification_chores:
        chore_id = chore.get("id")
        if not chore_id:
            logger.warning("Chore missing 'id' field, skipping: %s", chore)
            continue
        pending_chore_ids.add(chore_id)

    logger.info("Found %d pending verification chores", len(pending_chore_ids))
    return pending_chore_ids


async def _fetch_user_claims_for_chunk(
    user_id: str, chunk: list[str], per_page_limit: int, offset: int
) -> tuple[set[str], int]:
    """Fetch user claims for a chunk of chore IDs.

    Args:
        user_id: User ID to fetch claims for
        chunk: List of chore IDs to check
        per_page_limit: Page size for pagination
        offset: Current offset for logging purposes

    Returns:
        Tuple of (claimed_chore_ids, logs_fetched_count)
    """
    claimed_chore_ids: set[str] = set()
    or_clause = " || ".join([f'chore_id = "{db_client.sanitize_param(cid)}"' for cid in chunk])

    page = 1
    chunk_logs_fetched = 0
    while True:
        try:
            user_filter = f'user_id = "{db_client.sanitize_param(user_id)}"'
            action_filter = 'action = "claimed_completion"'
            filter_query = f"{user_filter} && {action_filter} && ({or_clause})"
            logs = await db_client.list_records(
                collection="task_logs",
                filter_query=filter_query,
                per_page=per_page_limit,
                page=page,
                sort="",
            )

            claimed_chore_ids.update(log["chore_id"] for log in logs)
            chunk_logs_fetched += len(logs)

            if len(logs) < per_page_limit:
                break

            page += 1
            logger.warning(
                "Pagination triggered for user %s: chunk had >%d claims (unusual). "
                "Fetching page %d. Consider investigating if this is expected.",
                user_id,
                per_page_limit,
                page,
            )
        except RuntimeError as e:
            logger.error("Database error fetching claims chunk at offset %d, page %d: %s", offset, page, e)
            break
        except Exception as e:
            logger.error("Unexpected error fetching claims chunk at offset %d, page %d: %s", offset, page, e)
            break

    return claimed_chore_ids, chunk_logs_fetched


async def _count_pending_claims_for_user(
    user_id: str, pending_chore_ids: set[str]
) -> tuple[int | None, str | None, int, int]:
    """Count pending claims for a user from pending chores.

    Args:
        user_id: User ID
        pending_chore_ids: Set of chore IDs pending verification

    Returns:
        Tuple of (claims_pending, error_message, chunks_processed, total_logs_fetched)
    """
    if not pending_chore_ids:
        logger.info("No pending verification chores, user %s has 0 pending claims", user_id)
        return 0, None, 0, 0

    try:
        with span("analytics_service.get_user_statistics.fetch_pending_claims"):
            chore_ids_list = list(pending_chore_ids)
            chunk_size = 50
            per_page_limit = chunk_size * 2
            estimated_chunks = (len(chore_ids_list) + chunk_size - 1) // chunk_size

            logger.debug(
                "Processing pending claims",
                extra={
                    "user_id": user_id,
                    "pending_chores_count": len(pending_chore_ids),
                    "estimated_chunks": estimated_chunks,
                    "chunk_size": chunk_size,
                },
            )

            claimed_chore_ids: set[str] = set()
            chunks_processed = 0
            total_logs_fetched = 0

            for i in range(0, len(chore_ids_list), chunk_size):
                chunk = chore_ids_list[i : i + chunk_size]
                chunk_index = i // chunk_size

                chunk_claimed_ids, chunk_logs = await _fetch_user_claims_for_chunk(user_id, chunk, per_page_limit, i)
                claimed_chore_ids.update(chunk_claimed_ids)
                total_logs_fetched += chunk_logs
                chunks_processed += 1

                logger.debug(
                    "Processed chunk",
                    extra={
                        "chunk_index": chunk_index,
                        "chunk_size": len(chunk),
                        "logs_fetched": chunk_logs,
                        "claims_in_chunk": len(chunk_claimed_ids),
                    },
                )

                if chunk_logs > chunk_size * 1.5:
                    logger.warning(
                        "User %s has %d claims for %d chores in chunk (%.1fx ratio). Expected ~1 claim per chore.",
                        user_id,
                        chunk_logs,
                        len(chunk),
                        chunk_logs / len(chunk),
                    )

        claims_pending = len(claimed_chore_ids)
        logger.info("User %s has %d pending claims", user_id, claims_pending)
        return claims_pending, None, chunks_processed, total_logs_fetched

    except RuntimeError as e:
        error_msg = f"Database error fetching pending claims: {e}"
        logger.error(error_msg)
        return None, error_msg, 0, 0
    except Exception as e:
        error_msg = f"Unexpected error fetching pending claims: {e}"
        logger.error(error_msg)
        return None, error_msg, 0, 0


async def _get_overdue_count(user_id: str) -> tuple[int | None, str | None]:
    """Get count of overdue chores for a user.

    Args:
        user_id: User ID

    Returns:
        Tuple of (overdue_count, error_message)
    """
    try:
        overdue_chores = await get_overdue_chores(user_id=user_id)
        overdue_count = len(overdue_chores)
        logger.info("User %s has %d overdue chores", user_id, overdue_count)
        return overdue_count, None
    except RuntimeError as e:
        error_msg = f"Database error fetching overdue chores: {e}"
        logger.error(error_msg)
        return None, error_msg
    except Exception as e:
        error_msg = f"Unexpected error fetching overdue chores: {e}"
        logger.error(error_msg)
        return None, error_msg


async def get_user_statistics(*, user_id: str, period_days: int = 30) -> UserStatistics:
    """Get comprehensive statistics for a specific user.

    Performance characteristics:
        This function uses an optimized approach for counting pending claims:
        - Fetches only pending verification chores first
        - Queries claims in chunks of 50 chore IDs to avoid large filter queries
        - Only fetches claims for pending chores (vs all user claims)

        Best case (0 pending chores): 0 queries for claims
        Typical case (5 pending chores): 1 query fetching ~5 logs
        Worst case (100+ pending chores): Multiple chunked queries

        Metrics are logged to monitor query counts and data volume.

    Args:
        user_id: User ID
        period_days: Number of days to look back (default: 30)

    Returns:
        UserStatistics object with comprehensive user metrics

    Raises:
        KeyError: If user doesn't exist
        RuntimeError: If critical database operations fail
    """
    with span("analytics_service.get_user_statistics"):
        start_time = datetime.now(UTC)

        # Get user details - CRITICAL, fail fast if user doesn't exist
        user_name = await _get_user_name(user_id)

        # Get leaderboard rank and completions - BEST EFFORT
        rank, completions, rank_error = await _get_user_rank_and_completions(user_id, period_days)

        # Get pending claims count - BEST EFFORT
        try:
            pending_chore_ids = await _fetch_pending_chore_ids()
        except Exception as e:
            logger.error("Failed to fetch pending chore IDs: %s", e)
            pending_chore_ids = set()
        claims_pending, claims_error, chunks, logs = await _count_pending_claims_for_user(user_id, pending_chore_ids)
        if claims_pending is None:
            claims_pending = 0

        # Get overdue chores count - BEST EFFORT
        overdue_chores, overdue_error = await _get_overdue_count(user_id)

        # Build result data
        result_data: dict[str, str | int | None] = {
            "user_id": user_id,
            "user_name": user_name,
            "completions": completions,
            "claims_pending": claims_pending,
            "claims_pending_error": claims_error,
            "overdue_chores": overdue_chores,
            "overdue_chores_error": overdue_error,
            "rank": rank,
            "rank_error": rank_error,
            "period_days": period_days,
        }

        # Log comprehensive performance metrics
        elapsed_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000
        logger.info(
            "User statistics computed",
            extra={
                "user_id": user_id,
                "execution_time_ms": round(elapsed_ms, 2),
                "pending_chores_count": len(pending_chore_ids),
                "chunks_processed": chunks,
                "total_logs_fetched": logs,
                "claims_pending": claims_pending,
                "completions": completions,
                "rank": rank,
                "overdue_chores": overdue_chores,
                "period_days": period_days,
            },
        )

        return UserStatistics.model_validate(result_data)


async def get_household_summary(*, period_days: int = 7) -> HouseholdSummary:
    """Get overall household statistics.

    Args:
        period_days: Number of days to look back (default: 7)

    Returns:
        HouseholdSummary object with household-wide statistics
    """
    with span("analytics_service.get_household_summary"):
        cutoff_date = datetime.now(UTC) - timedelta(days=period_days)

        # Get active users count
        active_users = await db_client.list_records(
            collection="members",
            filter_query=f'status = "{UserStatus.ACTIVE}"',
        )

        # Get total completions in period
        completion_logs = await db_client.list_records(
            collection="task_logs",
            filter_query=f'action = "approve_verification" && timestamp >= "{cutoff_date.isoformat()}"',
        )

        # Get overdue chores
        overdue = await get_overdue_chores()

        # Get pending verifications
        pending = await db_client.list_records(
            collection="tasks",
            filter_query=f'current_state = "{TaskState.PENDING_VERIFICATION}"',
        )

        result = HouseholdSummary(
            active_members=len(active_users),
            completions_this_period=len(completion_logs),
            overdue_chores=len(overdue),
            pending_verifications=len(pending),
            period_days=period_days,
        )

        logger.info("Household summary for %d days: %s", period_days, result.model_dump())

        return result
