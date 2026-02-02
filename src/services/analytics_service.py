"""Analytics service for user and household statistics.

This module provides functions for:
- Calculating user performance metrics (completions, pending claims, etc.)
- Generating leaderboards for gamification
- Tracking overdue chores

Key Concepts:
- Pending Claims: Distinct chores a user has claimed that are awaiting verification.
  If a user claims the same chore multiple times (e.g., after rejection), it
  counts as one pending claim.
- Completions: Successfully verified chore completions within the time period.
- Leaderboard: Ranked list of users by completion count.
"""

import json
import logging
from datetime import UTC, datetime, timedelta

from dateutil import parser as dateutil_parser
from pydantic import ValidationError

from src.core import db_client
from src.core.config import Constants
from src.core.logging import span
from src.core.redis_client import redis_client
from src.domain.chore import ChoreState
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
    data is served after events that change completion counts (e.g., chore verification).

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
            # Delete all matching keys with retry logic for critical operation
            success = await redis_client.delete_with_retry(*keys)
            if success:
                logger.info(f"Invalidated {len(keys)} leaderboard cache entries")
            else:
                logger.warning(f"Failed to invalidate {len(keys)} cache entries, queued for retry")
        else:
            logger.debug("No leaderboard cache entries to invalidate")
    except Exception as e:
        # Log warning but don't raise - cache invalidation failure shouldn't break app
        logger.warning(f"Failed to invalidate leaderboard cache: {e}")


async def _fetch_chores_map(chore_ids: list[str]) -> dict[str, dict]:
    """Fetch chores in chunks and return as a map."""
    chores_map = {}
    unique_chore_ids = list(set(chore_ids))
    for i in range(0, len(unique_chore_ids), Constants.ANALYTICS_CHUNK_SIZE):
        chunk = unique_chore_ids[i : i + Constants.ANALYTICS_CHUNK_SIZE]
        or_clause = " || ".join([f'id = "{cid}"' for cid in chunk])
        chores = await db_client.list_records(
            collection="chores",
            filter_query=or_clause,
        )
        for chore in chores:
            chores_map[chore["id"]] = chore
    return chores_map


async def _fetch_claim_logs_map(chore_ids: list[str]) -> dict[str, dict]:
    """Fetch claim logs in chunks and return as a map."""
    claim_logs_map = {}
    unique_chore_ids = list(set(chore_ids))
    for i in range(0, len(unique_chore_ids), Constants.ANALYTICS_CHUNK_SIZE):
        chunk = unique_chore_ids[i : i + Constants.ANALYTICS_CHUNK_SIZE]
        or_clause = " || ".join([f'chore_id = "{cid}"' for cid in chunk])
        claim_logs = await db_client.list_records(
            collection="logs",
            filter_query=f'action = "claimed_completion" && ({or_clause})',
        )
        for claim_log in claim_logs:
            chore_id = claim_log["chore_id"]
            # Keep only the most recent claim log per chore
            if chore_id not in claim_logs_map or claim_log.get("timestamp", "") > claim_logs_map[chore_id].get(
                "timestamp", ""
            ):
                claim_logs_map[chore_id] = claim_log
    return claim_logs_map


def _determine_user_to_award(
    log: dict,
    claim_log: dict | None,
    chore: dict | None,
) -> str:
    """Determine which user should be awarded points based on Robin Hood Protocol."""
    # Default: award points to the user who got approval
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
        logger.warning(f"Failed to parse timestamps for Robin Hood attribution: {e}")

    return user_to_award


def _build_leaderboard_entries(
    user_completion_counts: dict[str, int],
    users_map: dict[str, dict],
) -> list[LeaderboardEntry]:
    """Build and sort leaderboard entries from user counts."""
    leaderboard_data = []
    for user_id, count in user_completion_counts.items():
        if user_id not in users_map:
            logger.warning(f"User {user_id} not found for leaderboard")
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
            logger.error(f"Failed to create LeaderboardEntry for user {user_id}: {e}")

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
                logger.debug(f"Returning cached leaderboard for {period_days} days from Redis")
                return leaderboard_entries
            except (json.JSONDecodeError, ValidationError) as e:
                logger.warning(f"Failed to deserialize cached leaderboard: {e}")
    except Exception as e:
        logger.warning(f"Failed to retrieve cached leaderboard from Redis: {e}")

    with span("analytics_service.get_leaderboard"):
        # Calculate cutoff date
        now = datetime.now(UTC)
        cutoff_date = now - timedelta(days=period_days)

        # Get all completion logs within period
        completion_logs = await db_client.list_records(
            collection="logs",
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

            user_to_award = _determine_user_to_award(log, claim_log, chore)
            user_completion_counts[user_to_award] = user_completion_counts.get(user_to_award, 0) + 1

        # Fetch all users for leaderboard
        all_users = await db_client.list_records(collection="users", per_page=500)
        users_map = {u["id"]: u for u in all_users}

        # Build and sort leaderboard
        leaderboard_data = _build_leaderboard_entries(user_completion_counts, users_map)

        logger.info(f"Generated leaderboard for {period_days} days: {len(leaderboard_data)} users")

        # Update Redis cache
        try:
            cache_value = json.dumps([entry.model_dump() for entry in leaderboard_data])
            await redis_client.set(cache_key, cache_value, Constants.CACHE_TTL_LEADERBOARD_SECONDS)
        except Exception as e:
            logger.warning(f"Failed to cache leaderboard in Redis: {e}")

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

        result = CompletionRate(
            total_completions=total_completions,
            on_time=on_time_count,
            overdue=overdue_count,
            on_time_percentage=round(on_time_percentage, 2),
            overdue_percentage=round(overdue_percentage, 2),
            period_days=period_days,
        )

        logger.info(f"Completion rate for {period_days} days: {result.model_dump()}")

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

        # Convert to typed models
        overdue_chore_models = []
        for chore in overdue_chores:
            try:
                overdue_chore_models.append(OverdueChore(**chore))
            except ValidationError as e:
                logger.error(f"Failed to create OverdueChore model for chore {chore.get('id')}: {e}")
                continue

        logger.info(f"Found {len(overdue_chore_models)} overdue chores")

        return overdue_chore_models


async def get_user_statistics(*, user_id: str, period_days: int = 30) -> UserStatistics:  # noqa: C901, PLR0912, PLR0915
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

        # Initialize performance metrics
        pending_chore_ids: set[str] = set()
        chunks_processed = 0
        total_logs_fetched = 0

        # Get user details - CRITICAL, fail fast if user doesn't exist
        try:
            user = await db_client.get_record(collection="users", record_id=user_id)
            user_name = user.get("name")
            if not user_name:
                logger.warning(f"User {user_id} missing 'name' field, using ID as fallback")
                user_name = user_id
        except KeyError:
            logger.error(f"User {user_id} not found")
            raise
        except RuntimeError as e:
            logger.error(f"Database error fetching user {user_id}: {e}")
            raise

        # Initialize result dictionary (will be converted to model at the end)
        result_data: dict[str, str | int | None] = {
            "user_id": user_id,
            "user_name": user_name,
            "completions": 0,
            "claims_pending": None,
            "claims_pending_error": None,
            "overdue_chores": None,
            "overdue_chores_error": None,
            "rank": None,
            "rank_error": None,
            "period_days": period_days,
        }

        # Get leaderboard to find rank - BEST EFFORT
        try:
            leaderboard = await get_leaderboard(period_days=period_days)
            for idx, entry in enumerate(leaderboard, start=1):
                if entry.user_id == user_id:
                    result_data["rank"] = idx
                    result_data["completions"] = entry.completion_count
                    break

            logger.info(f"User {user_id} rank: {result_data['rank']}, completions: {result_data['completions']}")
        except RuntimeError as e:
            error_msg = f"Database error fetching leaderboard: {e}"
            logger.error(error_msg)
            result_data["rank_error"] = error_msg
        except Exception as e:
            error_msg = f"Unexpected error fetching leaderboard: {e}"
            logger.error(error_msg)
            result_data["rank_error"] = error_msg

        # Get pending verification chores - BEST EFFORT
        try:
            with span("analytics_service.get_user_statistics.fetch_pending_chores"):
                pending_verification_chores = await db_client.list_records(
                    collection="chores",
                    filter_query=f'current_state = "{ChoreState.PENDING_VERIFICATION}"',
                    per_page=500,
                )

            # Validate and collect chore IDs
            for chore in pending_verification_chores:
                chore_id = chore.get("id")
                if not chore_id:
                    logger.warning(f"Chore missing 'id' field, skipping: {chore}")
                    continue
                pending_chore_ids.add(chore_id)

            logger.info(f"Found {len(pending_chore_ids)} pending verification chores")

            # Business Rule: Claim Lifecycle
            # 1. User claims chore → chore state: TODO → PENDING_VERIFICATION
            # 2a. Approved → chore state: PENDING_VERIFICATION → COMPLETED
            # 2b. Rejected → chore state: PENDING_VERIFICATION → CONFLICT
            # 3. After conflict resolution, chore may return to TODO and be reclaimed
            #
            # For statistics, we count the number of distinct chores in PENDING_VERIFICATION
            # that have been claimed by the user, regardless of claim history.

            # Count claims that are still pending (chore in PENDING_VERIFICATION state)
            # Note: We count DISTINCT chores, not total claim logs. If a user claimed
            # the same chore multiple times (e.g., after rejection), it counts as one
            # pending claim since the chore is the unit of work, not the log entry.
            claimed_chore_ids: set[str] = set()

            if pending_chore_ids:
                try:
                    with span("analytics_service.get_user_statistics.fetch_pending_claims"):
                        # Optimize: Only fetch claims for the specific chores that are pending
                        # This avoids fetching thousands of historical claims for completed chores.
                        # We process in chunks to avoid potentially long filter queries.
                        chore_ids_list = list(pending_chore_ids)
                        per_page_limit = Constants.ANALYTICS_CHUNK_SIZE * 2  # 2x buffer for expected 1 claim per chore
                        estimated_chunks = (
                            len(chore_ids_list) + Constants.ANALYTICS_CHUNK_SIZE - 1
                        ) // Constants.ANALYTICS_CHUNK_SIZE

                        logger.debug(
                            "Processing pending claims",
                            extra={
                                "user_id": user_id,
                                "pending_chores_count": len(pending_chore_ids),
                                "estimated_chunks": estimated_chunks,
                                "chunk_size": Constants.ANALYTICS_CHUNK_SIZE,
                            },
                        )

                        for i in range(0, len(chore_ids_list), Constants.ANALYTICS_CHUNK_SIZE):
                            chunk = chore_ids_list[i : i + Constants.ANALYTICS_CHUNK_SIZE]
                            chunk_index = i // Constants.ANALYTICS_CHUNK_SIZE
                            or_clause = " || ".join([f'chore_id = "{cid}"' for cid in chunk])

                            # Fetch claims with pagination handling
                            page = 1
                            chunk_claims = 0
                            chunk_logs_fetched = 0
                            while True:
                                try:
                                    filter_query = (
                                        f'user_id = "{user_id}" && action = "claimed_completion" && ({or_clause})'
                                    )
                                    logs = await db_client.list_records(
                                        collection="logs",
                                        filter_query=filter_query,
                                        per_page=per_page_limit,
                                        page=page,
                                        sort="",  # No sort to avoid issues
                                    )

                                    # Add unique chore IDs from this chunk
                                    claimed_chore_ids.update(log["chore_id"] for log in logs)

                                    chunk_claims += len(logs)
                                    chunk_logs_fetched += len(logs)

                                    # If we got fewer logs than per_page, we've fetched all records
                                    if len(logs) < per_page_limit:
                                        break

                                    # Otherwise, there might be more records - fetch next page
                                    page += 1
                                    logger.warning(
                                        "Pagination triggered for user %s: chunk had >%d claims (unusual). "
                                        "Fetching page %d. Consider investigating if this is expected.",
                                        user_id,
                                        per_page_limit,
                                        page,
                                    )
                                except RuntimeError as e:
                                    error_msg = f"Database error fetching claims chunk at offset {i}, page {page}: {e}"
                                    logger.error(error_msg)
                                    # Continue with next chunk, don't fail entire operation
                                    break
                                except Exception as e:
                                    error_msg = (
                                        f"Unexpected error fetching claims chunk at offset {i}, page {page}: {e}"
                                    )
                                    logger.error(error_msg)
                                    # Continue with next chunk, don't fail entire operation
                                    break

                            total_logs_fetched += chunk_logs_fetched
                            chunks_processed += 1

                            logger.debug(
                                "Processed chunk",
                                extra={
                                    "chunk_index": chunk_index,
                                    "chunk_size": len(chunk),
                                    "logs_fetched": chunk_logs_fetched,
                                    "claims_in_chunk": chunk_claims,
                                },
                            )

                            # Log if chunk size is unusually large (indicates potential data anomaly)
                            if chunk_claims > Constants.ANALYTICS_CHUNK_SIZE * 1.5:
                                logger.warning(
                                    "User %s has %d claims for %d chores in chunk (%.1fx ratio). "
                                    "Expected ~1 claim per chore.",
                                    user_id,
                                    chunk_claims,
                                    len(chunk),
                                    chunk_claims / len(chunk),
                                )

                    # Count distinct chores, not total logs
                    claims_pending = len(claimed_chore_ids)
                    result_data["claims_pending"] = claims_pending
                    logger.info(f"User {user_id} has {claims_pending} pending claims")

                except RuntimeError as e:
                    error_msg = f"Database error fetching pending claims: {e}"
                    logger.error(error_msg)
                    result_data["claims_pending_error"] = error_msg
                except Exception as e:
                    error_msg = f"Unexpected error fetching pending claims: {e}"
                    logger.error(error_msg)
                    result_data["claims_pending_error"] = error_msg
            else:
                # No pending chores, so 0 pending claims
                result_data["claims_pending"] = 0
                logger.info(f"No pending verification chores, user {user_id} has 0 pending claims")

        except RuntimeError as e:
            error_msg = f"Database error fetching pending verification chores: {e}"
            logger.error(error_msg)
            result_data["claims_pending_error"] = error_msg
        except Exception as e:
            error_msg = f"Unexpected error fetching pending verification chores: {e}"
            logger.error(error_msg)
            result_data["claims_pending_error"] = error_msg

        # Get overdue chores assigned to user - BEST EFFORT
        try:
            overdue_chores = await get_overdue_chores(user_id=user_id)
            result_data["overdue_chores"] = len(overdue_chores)
            logger.info(f"User {user_id} has {result_data['overdue_chores']} overdue chores")
        except RuntimeError as e:
            error_msg = f"Database error fetching overdue chores: {e}"
            logger.error(error_msg)
            result_data["overdue_chores_error"] = error_msg
        except Exception as e:
            error_msg = f"Unexpected error fetching overdue chores: {e}"
            logger.error(error_msg)
            result_data["overdue_chores_error"] = error_msg

        # Log comprehensive performance metrics
        elapsed_ms = (datetime.now(UTC) - start_time).total_seconds() * 1000
        logger.info(
            "User statistics computed",
            extra={
                "user_id": user_id,
                "execution_time_ms": round(elapsed_ms, 2),
                "pending_chores_count": len(pending_chore_ids),
                "chunks_processed": chunks_processed,
                "total_logs_fetched": total_logs_fetched,
                "claims_pending": result_data.get("claims_pending"),
                "completions": result_data.get("completions"),
                "rank": result_data.get("rank"),
                "overdue_chores": result_data.get("overdue_chores"),
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

        result = HouseholdSummary(
            active_members=len(active_users),
            completions_this_period=len(completion_logs),
            current_conflicts=len(conflicts),
            overdue_chores=len(overdue),
            pending_verifications=len(pending),
            period_days=period_days,
        )

        logger.info(f"Household summary for {period_days} days: {result.model_dump()}")

        return result
