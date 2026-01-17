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


# Global variables for metrics
call_count = 0


async def mocked_list_records(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:  # noqa: ANN401, ARG001
    global call_count  # noqa: PLW0603
    if kwargs.get("collection") == "logs":
        call_count += 1
        # Simulate network delay
        await asyncio.sleep(0.005)
        # Return dummy logs
        # We need logs that match the chores.
        # Chore IDs are chore_0 to chore_49.
        # Let's create logs where user2 claimed all of them.
        return [
            {
                "id": f"log_{i}",
                "action": "claimed_completion",
                "chore_id": f"chore_{i % 50}",
                "user_id": "user2",
            }
            for i in range(1000)
        ]
    return []


# Mock chore_service.get_chores
async def mocked_get_chores(**kwargs: Any) -> list[dict[str, Any]]:  # noqa: ARG001, ANN401
    # Return 50 chores
    return [
        {"id": f"chore_{i}", "current_state": ChoreState.PENDING_VERIFICATION}
        for i in range(50)
    ]


async def run_benchmark() -> None:
    global call_count  # noqa: PLW0602

    # Patching
    db_client.list_records = mocked_list_records
    chore_service.get_chores = mocked_get_chores

    print("Starting benchmark...")  # noqa: T201
    start_time = time.time()

    # Run the function with a user_id filter to trigger the loop logic
    await verification_service.get_pending_verifications(user_id="user1")

    end_time = time.time()
    duration = end_time - start_time

    print(f"Time taken: {duration:.4f} seconds")  # noqa: T201
    print(f"db_client.list_records calls: {call_count}")  # noqa: T201


if __name__ == "__main__":
    asyncio.run(run_benchmark())
