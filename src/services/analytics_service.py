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

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from src.core import db_client
from src.core.logging import span
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
    with span("analytics_service.get_leaderboard"):
        # Calculate cutoff date
        cutoff_date = datetime.now(UTC) - timedelta(days=period_days)

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

        # Get user details and build leaderboard
        leaderboard = []
        for user_id, count in user_completion_counts.items():
            try:
                user = await db_client.get_record(collection="users", record_id=user_id)
                leaderboard.append(
                    {
                        "user_id": user_id,
                        "user_name": user["name"],
                        "completion_count": count,
                    }
                )
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


async def get_user_statistics(*, user_id: str, period_days: int = 30) -> dict[str, Any]:  # noqa: C901, PLR0912, PLR0915
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
        Dict with user statistics:
        {
            "user_id": str,
            "user_name": str,
            "completions": int,  # Completed chores in the period
            "claims_pending": int | None,  # Number of distinct chores claimed by this user
                                           # that are currently in PENDING_VERIFICATION state.
                                           # If a chore was claimed multiple times (e.g., rejected
                                           # and reclaimed), it counts as one pending claim.
                                           # None if query failed.
            "claims_pending_error": str | None,
            "overdue_chores": int | None,  # Chores assigned to user past their deadline, None if query failed
            "overdue_chores_error": str | None,
            "rank": int | None,  # Position in leaderboard (1-indexed), None if not on leaderboard or error
            "rank_error": str | None,
            "period_days": int,  # Period used for statistics calculation
        }

    Raises:
        db_client.RecordNotFoundError: If user doesn't exist
        db_client.DatabaseError: If critical database operations fail
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
                logger.warning("User %s missing 'name' field, using ID as fallback", user_id)
                user_name = user_id
        except db_client.RecordNotFoundError:
            logger.error("User %s not found", user_id)
            raise
        except db_client.DatabaseError as e:
            logger.error("Database error fetching user %s: %s", user_id, e)
            raise

        # Initialize result with default values
        result = {
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
                entry_user_id = entry.get("user_id")
                if not entry_user_id:
                    logger.warning("Leaderboard entry missing 'user_id', skipping: %s", entry)
                    continue

                if entry_user_id == user_id:
                    result["rank"] = idx
                    result["completions"] = entry.get("completion_count", 0)
                    break

            logger.info("User %s rank: %s, completions: %d", user_id, result["rank"], result["completions"])
        except db_client.DatabaseError as e:
            error_msg = f"Database error fetching leaderboard: {e}"
            logger.error(error_msg)
            result["rank_error"] = error_msg
        except Exception as e:
            error_msg = f"Unexpected error fetching leaderboard: {e}"
            logger.error(error_msg)
            result["rank_error"] = error_msg

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
                    logger.warning("Chore missing 'id' field, skipping: %s", chore)
                    continue
                pending_chore_ids.add(chore_id)

            logger.info("Found %d pending verification chores", len(pending_chore_ids))

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
                        chunk_size = 50
                        per_page_limit = chunk_size * 2  # 2x buffer for expected 1 claim per chore
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

                        for i in range(0, len(chore_ids_list), chunk_size):
                            chunk = chore_ids_list[i : i + chunk_size]
                            chunk_index = i // chunk_size
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
                                except db_client.DatabaseError as e:
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
                            if chunk_claims > chunk_size * 1.5:
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
                    result["claims_pending"] = claims_pending
                    logger.info("User %s has %d pending claims", user_id, claims_pending)

                except db_client.DatabaseError as e:
                    error_msg = f"Database error fetching pending claims: {e}"
                    logger.error(error_msg)
                    result["claims_pending_error"] = error_msg
                except Exception as e:
                    error_msg = f"Unexpected error fetching pending claims: {e}"
                    logger.error(error_msg)
                    result["claims_pending_error"] = error_msg
            else:
                # No pending chores, so 0 pending claims
                result["claims_pending"] = 0
                logger.info("No pending verification chores, user %s has 0 pending claims", user_id)

        except db_client.DatabaseError as e:
            error_msg = f"Database error fetching pending verification chores: {e}"
            logger.error(error_msg)
            result["claims_pending_error"] = error_msg
        except Exception as e:
            error_msg = f"Unexpected error fetching pending verification chores: {e}"
            logger.error(error_msg)
            result["claims_pending_error"] = error_msg

        # Get overdue chores assigned to user - BEST EFFORT
        try:
            overdue_chores = await get_overdue_chores(user_id=user_id)
            result["overdue_chores"] = len(overdue_chores)
            logger.info("User %s has %d overdue chores", user_id, result["overdue_chores"])
        except db_client.DatabaseError as e:
            error_msg = f"Database error fetching overdue chores: {e}"
            logger.error(error_msg)
            result["overdue_chores_error"] = error_msg
        except Exception as e:
            error_msg = f"Unexpected error fetching overdue chores: {e}"
            logger.error(error_msg)
            result["overdue_chores_error"] = error_msg

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
                "claims_pending": result.get("claims_pending"),
                "completions": result.get("completions"),
                "rank": result.get("rank"),
                "overdue_chores": result.get("overdue_chores"),
                "period_days": period_days,
            },
        )

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
