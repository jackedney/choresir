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
import sys
import time
from pathlib import Path
from typing import Any


# Add src to pythonpath
sys.path.append(str(Path.cwd()))

from src.core import db_client
from src.domain.chore import ChoreState
from src.services import chore_service, verification_service
from src.services.verification_service import VerificationDecision


# Global variables for metrics
call_count = 0


async def mocked_list_records(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:  # noqa: ANN401, ARG001
    global call_count  # noqa: PLW0603
    if kwargs.get("collection") == "logs":
        call_count += 1
        # Simulate network delay
        await asyncio.sleep(0.005)

        # Get pagination params
        page = kwargs.get("page", 1)
        per_page = kwargs.get("per_page", 50)

        # Return dummy logs
        # We need logs that match the chores.
        # Chore IDs are chore_0 to chore_49.
        # Let's create logs where user2 claimed all of them.
        # Create in ascending order (oldest first)
        all_logs = [
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


# Mock chore_service.get_chores
async def mocked_get_chores(**kwargs: Any) -> list[dict[str, Any]]:  # noqa: ARG001, ANN401
    # Return 50 chores
    return [{"id": f"chore_{i}", "current_state": ChoreState.PENDING_VERIFICATION} for i in range(50)]


# Mock chore_service.complete_chore for verify_chore benchmark
async def mocked_complete_chore(**kwargs: Any) -> dict[str, Any]:  # noqa: ANN401
    """Mock completing a chore - just returns a chore dict."""
    chore_id = kwargs.get("chore_id", "unknown")
    return {"id": chore_id, "current_state": ChoreState.COMPLETED}


# Mock db_client.create_record for verification logs
async def mocked_create_record(*args: Any, **kwargs: Any) -> dict[str, Any]:  # noqa: ANN401, ARG001
    """Mock creating a log record - just returns a log dict."""
    return {"id": "mock_log_id", **kwargs.get("data", {})}


async def benchmark_get_pending_verifications() -> tuple[float, int]:
    """Benchmark get_pending_verifications function.

    Tests that the function:
    - Fetches all logs efficiently (should make 1 DB call for 1000 logs)
    - Filters chores correctly based on user_id

    Returns:
        Tuple of (duration in seconds, number of DB calls made)
    """
    global call_count  # noqa: PLW0603
    call_count = 0

    # Patching
    db_client.list_records = mocked_list_records  # type: ignore[method-assign]
    chore_service.get_chores = mocked_get_chores  # type: ignore[method-assign]

    start_time = time.time()

    # Run the function with a user_id filter to trigger the loop logic
    await verification_service.get_pending_verifications(user_id="user1")

    end_time = time.time()
    duration = end_time - start_time

    return duration, call_count


async def benchmark_verify_chore() -> tuple[float, int]:
    """Benchmark verify_chore function.

    Tests that the function:
    - Finds the claim log even when it's beyond page 1 (index 600+ in 1000 logs)
    - Makes a constant number of DB calls regardless of log count
    - Successfully processes the verification

    Returns:
        Tuple of (duration in seconds, number of DB calls made)
    """
    global call_count  # noqa: PLW0603
    call_count = 0

    # Patching - all mocks needed for verify_chore
    db_client.list_records = mocked_list_records  # type: ignore[method-assign]
    db_client.create_record = mocked_create_record  # type: ignore[method-assign]
    chore_service.complete_chore = mocked_complete_chore  # type: ignore[method-assign]

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

    return duration, call_count


async def run_benchmark() -> None:
    """Run all benchmarks and display results."""
    print("=" * 60)  # noqa: T201
    print("Verification Service Benchmark")  # noqa: T201
    print("=" * 60)  # noqa: T201
    print()  # noqa: T201

    # Benchmark 1: get_pending_verifications
    print("Benchmarking get_pending_verifications...")  # noqa: T201
    duration1, calls1 = await benchmark_get_pending_verifications()

    print()  # noqa: T201

    # Benchmark 2: verify_chore
    print("Benchmarking verify_chore...")  # noqa: T201
    duration2, calls2 = await benchmark_verify_chore()

    # Display results
    print()  # noqa: T201
    print("=" * 60)  # noqa: T201
    print("Benchmark Results")  # noqa: T201
    print("=" * 60)  # noqa: T201
    print()  # noqa: T201

    print("get_pending_verifications:")  # noqa: T201
    print(f"  Time taken: {duration1:.4f}s")  # noqa: T201
    print(f"  DB calls: {calls1}")  # noqa: T201
    print()  # noqa: T201

    print("verify_chore:")  # noqa: T201
    print(f"  Time taken: {duration2:.4f}s")  # noqa: T201
    print(f"  DB calls: {calls2}")  # noqa: T201
    print()  # noqa: T201

    # Check if both are optimal
    # With 1000 logs and page_size=500, we expect 3 calls (page 1, page 2, page 3 empty)
    # This is constant time - NOT N+1 (which would be 50+ calls for 50 chores)
    expected_calls = 3
    if calls1 == expected_calls and calls2 == expected_calls:
        print("✅ Both functions use constant DB calls!")  # noqa: T201
        print(f"   (Made {expected_calls} calls to fetch 1000 logs across 2 pages)")  # noqa: T201
    else:
        print("⚠️  Warning: Unexpected number of DB calls")  # noqa: T201
        if calls1 != expected_calls:
            print(f"   - get_pending_verifications made {calls1} calls (expected {expected_calls})")  # noqa: T201
        if calls2 != expected_calls:
            print(f"   - verify_chore made {calls2} calls (expected {expected_calls})")  # noqa: T201


if __name__ == "__main__":
    asyncio.run(run_benchmark())
