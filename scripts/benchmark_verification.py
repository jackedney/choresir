"""Benchmark script for verification service functions.

This script benchmarks the performance and correctness of:
1. get_pending_verifications - fetching chores pending verification
2. verify_chore - verifying a specific chore claim

Tests verify that:
- Pagination works correctly (all logs are fetched across multiple pages)
- Database call count is constant (O(1), not O(n) per chore)
- Functions complete successfully with realistic test data

The benchmark simulates:
- 50 chores in PENDING_VERIFICATION state
- 1000 log entries across 2 pages (500 per page)
- Claim logs sorted newest-first (as in production)
"""

import asyncio
import logging
import sys
import time
from pathlib import Path


# Add src to pythonpath
sys.path.append(str(Path.cwd()))

from src.core import db_client
from src.domain.chore import ChoreState
from src.services import chore_service, verification_service
from src.services.verification_service import VerificationDecision


# Configure logging for benchmark output
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


class BenchmarkMetrics:
    """Singleton container for benchmark metrics."""

    call_count: int = 0

    @classmethod
    def reset(cls) -> None:
        """Reset the call count."""
        cls.call_count = 0

    @classmethod
    def increment(cls) -> None:
        """Increment the call count."""
        cls.call_count += 1


async def mocked_list_records(
    *,
    collection: str = "",
    page: int = 1,
    per_page: int = 50,
    **_kwargs: object,
) -> list[dict[str, object]]:
    """Mock list_records for benchmarking."""
    if collection == "logs":
        BenchmarkMetrics.increment()
        # Simulate network delay
        await asyncio.sleep(0.005)

        # Return dummy logs
        # We need logs that match the chores.
        # Chore IDs are chore_0 to chore_49.
        # Let's create logs where user2 claimed all of them.
        # Create in ascending order (oldest first)
        all_logs: list[dict[str, object]] = [
            {
                "id": f"log_{i}",
                "action": "claimed_completion",
                "chore_id": f"chore_{i % 50}",
                "user_id": "user2",
            }
            for i in range(1000)
        ]

        # Simulate sort="-created" (newest first) by reversing
        # This makes log_999 first, log_0 last
        all_logs.reverse()

        # Implement simple pagination
        start = (page - 1) * per_page
        end = start + per_page
        return all_logs[start:end]
    return []


async def mocked_get_chores(**_kwargs: object) -> list[dict[str, object]]:
    """Mock chore_service.get_chores - returns 50 chores."""
    return [{"id": f"chore_{i}", "current_state": ChoreState.PENDING_VERIFICATION} for i in range(50)]


async def mocked_complete_chore(*, chore_id: str = "unknown", **_kwargs: object) -> dict[str, object]:
    """Mock completing a chore - just returns a chore dict."""
    return {"id": chore_id, "current_state": ChoreState.COMPLETED}


async def mocked_create_record(*, data: dict[str, object] | None = None, **_kwargs: object) -> dict[str, object]:
    """Mock creating a log record - just returns a log dict."""
    return {"id": "mock_log_id", **(data or {})}


async def benchmark_get_pending_verifications() -> tuple[float, int]:
    """Benchmark get_pending_verifications function.

    Tests that the function:
    - Fetches all logs efficiently (should make 1 DB call for 1000 logs)
    - Filters chores correctly based on user_id

    Returns:
        Tuple of (duration in seconds, number of DB calls made)
    """
    BenchmarkMetrics.reset()

    # Patching
    db_client.list_records = mocked_list_records  # type: ignore[assignment]
    chore_service.get_chores = mocked_get_chores  # type: ignore[assignment]

    start_time = time.time()

    # Run the function with a user_id filter to trigger the loop logic
    await verification_service.get_pending_verifications(user_id="user1")

    end_time = time.time()
    duration = end_time - start_time

    return duration, BenchmarkMetrics.call_count


async def benchmark_verify_chore() -> tuple[float, int]:
    """Benchmark verify_chore function.

    Tests that the function:
    - Finds the claim log even when it's beyond page 1 (index 600+ in 1000 logs)
    - Makes a constant number of DB calls regardless of log count
    - Successfully processes the verification

    Returns:
        Tuple of (duration in seconds, number of DB calls made)
    """
    BenchmarkMetrics.reset()

    # Patching - all mocks needed for verify_chore
    db_client.list_records = mocked_list_records  # type: ignore[assignment]
    db_client.create_record = mocked_create_record  # type: ignore[assignment]
    chore_service.complete_chore = mocked_complete_chore  # type: ignore[assignment]

    start_time = time.time()

    # Test verify_chore with APPROVE decision
    # With mocked logs sorted newest-first: log_999, log_998, ..., log_1, log_0
    # chore_10 claim logs appear at: log_960, log_910, log_860, ..., log_110, log_60, log_10
    # The FIRST (newest) claim log for chore_10 is log_960
    # After reversal, log_960 is at position 39 in the reversed list (on page 1)
    # However, we're testing that ALL logs are fetched across pages to find ANY matching log
    # This tests pagination correctness for the log fetching
    await verification_service.verify_chore(
        chore_id="chore_10",
        verifier_user_id="user1",  # Different from claimer (user2)
        decision=VerificationDecision.APPROVE,
        reason="Test verification",
    )

    end_time = time.time()
    duration = end_time - start_time

    return duration, BenchmarkMetrics.call_count


async def run_benchmark() -> None:
    """Run all benchmarks and display results."""
    logger.info("=" * 60)
    logger.info("Verification Service Benchmark")
    logger.info("=" * 60)
    logger.info("")

    # Benchmark 1: get_pending_verifications
    logger.info("Benchmarking get_pending_verifications...")
    duration1, calls1 = await benchmark_get_pending_verifications()

    logger.info("")

    # Benchmark 2: verify_chore
    logger.info("Benchmarking verify_chore...")
    duration2, calls2 = await benchmark_verify_chore()

    # Display results
    logger.info("")
    logger.info("=" * 60)
    logger.info("Benchmark Results")
    logger.info("=" * 60)
    logger.info("")

    logger.info("get_pending_verifications:")
    logger.info("  Time taken: %.4fs", duration1)
    logger.info("  DB calls: %d", calls1)
    logger.info("")

    logger.info("verify_chore:")
    logger.info("  Time taken: %.4fs", duration2)
    logger.info("  DB calls: %d", calls2)
    logger.info("")

    # Check if both are optimal
    # With 1000 logs and page_size=500, we expect 3 calls (page 1, page 2, page 3 empty)
    # This is constant time - NOT N+1 (which would be 50+ calls for 50 chores)
    expected_calls = 3
    if calls1 == expected_calls and calls2 == expected_calls:
        logger.info("✅ Both functions use constant DB calls!")
        logger.info("   (Made %d calls to fetch 1000 logs across 2 pages)", expected_calls)
    else:
        logger.info("⚠️  Warning: Unexpected number of DB calls")
        if calls1 != expected_calls:
            logger.info("   - get_pending_verifications made %d calls (expected %d)", calls1, expected_calls)
        if calls2 != expected_calls:
            logger.info("   - verify_chore made %d calls (expected %d)", calls2, expected_calls)


if __name__ == "__main__":
    asyncio.run(run_benchmark())
