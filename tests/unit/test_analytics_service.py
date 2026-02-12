"""Unit tests for analytics_service module."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest

import src.modules.tasks.analytics as analytics_service
from tests.unit.conftest import DatabaseClient


@pytest.fixture
async def patched_analytics_db(mock_db_module_for_unit_tests: Any, db_client: None) -> DatabaseClient:
    """Patches settings and database for analytics service tests.

    Uses real SQLite database via db_client fixture from tests/conftest.py.
    Settings are patched by mock_db_module_for_unit_tests fixture.
    """
    return DatabaseClient()


@pytest.mark.unit
class TestGetLeaderboard:
    """Tests for get_leaderboard function."""

    async def test_leaderboard_returns_correct_order(self, patched_analytics_db: DatabaseClient) -> None:
        """Leaderboard returns users ordered by completion count descending."""
        now = datetime.now(UTC)

        users = []
        for i, name in enumerate(["Alice", "Bob", "Charlie"]):
            user = await patched_analytics_db.create_record(
                collection="members",
                data={"name": name, "phone": f"+123456789{i}", "role": "member", "status": "active"},
            )
            users.append(user)

        tasks = []
        for i in range(10):
            task = await patched_analytics_db.create_record(
                collection="tasks",
                data={
                    "title": f"Task {i}",
                    "description": f"Description {i}",
                    "schedule_cron": "0 9 * * *",
                    "current_state": "TODO",
                    "assigned_to": users[i % 3]["id"],
                    "scope": "shared",
                },
            )
            tasks.append(task)

        for i in range(5):
            await patched_analytics_db.create_record(
                collection="task_logs",
                data={
                    "user_id": users[0]["id"],
                    "action": "approve_verification",
                    "timestamp": (now - timedelta(days=i)).isoformat(),
                    "task_id": tasks[i]["id"],
                },
            )

        for i in range(3):
            await patched_analytics_db.create_record(
                collection="task_logs",
                data={
                    "user_id": users[1]["id"],
                    "action": "approve_verification",
                    "timestamp": (now - timedelta(days=i)).isoformat(),
                    "task_id": tasks[5 + i]["id"],
                },
            )

        await patched_analytics_db.create_record(
            collection="task_logs",
            data={
                "user_id": users[2]["id"],
                "action": "approve_verification",
                "timestamp": now.isoformat(),
                "task_id": tasks[8]["id"],
            },
        )

        result = await analytics_service.get_leaderboard(period_days=30)

        assert len(result) == 3
        assert result[0].user_name == "Alice"
        assert result[0].completion_count == 5
        assert result[1].user_name == "Bob"
        assert result[1].completion_count == 3
        assert result[2].user_name == "Charlie"
        assert result[2].completion_count == 1

    async def test_leaderboard_empty(self, patched_analytics_db: DatabaseClient) -> None:
        """Empty leaderboard (no completions) works correctly."""
        for i, name in enumerate(["Alice", "Bob", "Charlie"]):
            await patched_analytics_db.create_record(
                collection="members",
                data={"name": name, "phone": f"+123456789{i}", "role": "member", "status": "active"},
            )

        result = await analytics_service.get_leaderboard(period_days=30)

        assert result == []

    async def test_leaderboard_single_user(self, patched_analytics_db: DatabaseClient) -> None:
        """Leaderboard with only one user works correctly."""
        now = datetime.now(UTC)

        user = await patched_analytics_db.create_record(
            collection="members",
            data={"name": "Alice", "phone": "+1234567890", "role": "member", "status": "active"},
        )

        task = await patched_analytics_db.create_record(
            collection="tasks",
            data={
                "title": "Task 0",
                "description": "Description",
                "schedule_cron": "0 9 * * *",
                "current_state": "TODO",
                "assigned_to": user["id"],
                "scope": "shared",
            },
        )

        await patched_analytics_db.create_record(
            collection="task_logs",
            data={
                "user_id": user["id"],
                "action": "approve_verification",
                "timestamp": now.isoformat(),
                "task_id": task["id"],
            },
        )

        result = await analytics_service.get_leaderboard(period_days=30)

        assert len(result) == 1
        assert result[0].user_name == "Alice"
        assert result[0].completion_count == 1

    async def test_leaderboard_tied_users(self, patched_analytics_db: DatabaseClient) -> None:
        """Users with same completion count are handled correctly."""
        now = datetime.now(UTC)

        users = []
        for i, name in enumerate(["Alice", "Bob"]):
            user = await patched_analytics_db.create_record(
                collection="members",
                data={"name": name, "phone": f"+123456789{i}", "role": "member", "status": "active"},
            )
            users.append(user)

        tasks = []
        for i in range(6):
            task = await patched_analytics_db.create_record(
                collection="tasks",
                data={
                    "title": f"Task {i}",
                    "description": f"Description {i}",
                    "schedule_cron": "0 9 * * *",
                    "current_state": "TODO",
                    "assigned_to": users[i % 2]["id"],
                    "scope": "shared",
                },
            )
            tasks.append(task)

        for i in range(3):
            await patched_analytics_db.create_record(
                collection="task_logs",
                data={
                    "user_id": users[0]["id"],
                    "action": "approve_verification",
                    "timestamp": (now - timedelta(days=i)).isoformat(),
                    "task_id": tasks[i]["id"],
                },
            )

        for i in range(3):
            await patched_analytics_db.create_record(
                collection="task_logs",
                data={
                    "user_id": users[1]["id"],
                    "action": "approve_verification",
                    "timestamp": (now - timedelta(days=i)).isoformat(),
                    "task_id": tasks[3 + i]["id"],
                },
            )

        result = await analytics_service.get_leaderboard(period_days=30)

        assert len(result) == 2
        assert result[0].completion_count == 3
        assert result[1].completion_count == 3

    async def test_leaderboard_period_filtering(self, patched_analytics_db: DatabaseClient) -> None:
        """Leaderboard correctly filters by period_days."""
        now = datetime.now(UTC)

        users = []
        for i, name in enumerate(["Alice", "Bob"]):
            user = await patched_analytics_db.create_record(
                collection="members",
                data={"name": name, "phone": f"+123456789{i}", "role": "member", "status": "active"},
            )
            users.append(user)

        tasks = []
        for i in range(2):
            task = await patched_analytics_db.create_record(
                collection="tasks",
                data={
                    "title": f"Task {i}",
                    "description": f"Description {i}",
                    "schedule_cron": "0 9 * * *",
                    "current_state": "TODO",
                    "assigned_to": users[i]["id"],
                    "scope": "shared",
                },
            )
            tasks.append(task)

        await patched_analytics_db.create_record(
            collection="task_logs",
            data={
                "user_id": users[0]["id"],
                "action": "approve_verification",
                "timestamp": (now - timedelta(days=10)).isoformat(),
                "task_id": tasks[0]["id"],
            },
        )

        await patched_analytics_db.create_record(
            collection="task_logs",
            data={
                "user_id": users[1]["id"],
                "action": "approve_verification",
                "timestamp": (now - timedelta(days=2)).isoformat(),
                "task_id": tasks[1]["id"],
            },
        )

        result = await analytics_service.get_leaderboard(period_days=7)

        assert len(result) == 1
        assert result[0].user_name == "Bob"
        assert result[0].completion_count == 1

    async def test_leaderboard_multiple_completions_same_user(self, patched_analytics_db: DatabaseClient) -> None:
        """Multiple completions by same user are counted correctly."""
        now = datetime.now(UTC)

        user = await patched_analytics_db.create_record(
            collection="members",
            data={"name": "Alice", "phone": "+1234567890", "role": "member", "status": "active"},
        )

        tasks = []
        for i in range(10):
            task = await patched_analytics_db.create_record(
                collection="tasks",
                data={
                    "title": f"Task {i}",
                    "description": f"Description {i}",
                    "schedule_cron": "0 9 * * *",
                    "current_state": "TODO",
                    "assigned_to": user["id"],
                    "scope": "shared",
                },
            )
            tasks.append(task)

        for i in range(10):
            await patched_analytics_db.create_record(
                collection="task_logs",
                data={
                    "user_id": user["id"],
                    "action": "approve_verification",
                    "timestamp": (now - timedelta(hours=i)).isoformat(),
                    "task_id": tasks[i]["id"],
                },
            )

        result = await analytics_service.get_leaderboard(period_days=30)

        assert len(result) == 1
        assert result[0].user_name == "Alice"
        assert result[0].completion_count == 10


@pytest.mark.unit
class TestGetUserStatistics:
    """Tests for get_user_statistics function."""

    async def test_get_user_statistics_with_leaderboard_rank(self, patched_analytics_db: DatabaseClient) -> None:
        """User statistics include correct rank from leaderboard."""
        now = datetime.now(UTC)

        users = []
        for i, name in enumerate(["Alice", "Bob", "Charlie"]):
            user = await patched_analytics_db.create_record(
                collection="members",
                data={"name": name, "phone": f"+123456789{i}", "role": "member", "status": "active"},
            )
            users.append(user)

        tasks = []
        for i in range(10):
            task = await patched_analytics_db.create_record(
                collection="tasks",
                data={
                    "title": f"Task {i}",
                    "description": f"Description {i}",
                    "schedule_cron": "0 9 * * *",
                    "current_state": "TODO",
                    "assigned_to": users[i % 3]["id"],
                    "scope": "shared",
                },
            )
            tasks.append(task)

        for i in range(5):
            await patched_analytics_db.create_record(
                collection="task_logs",
                data={
                    "user_id": users[0]["id"],
                    "action": "approve_verification",
                    "timestamp": (now - timedelta(days=i)).isoformat(),
                    "task_id": tasks[i]["id"],
                },
            )

        result = await analytics_service.get_user_statistics(user_id=users[0]["id"], period_days=30)

        assert result.user_id == users[0]["id"]
        assert result.user_name == "Alice"
        assert result.completions == 5
        assert result.rank == 1

    async def test_get_user_statistics_no_completions(self, patched_analytics_db: DatabaseClient) -> None:
        """User with no completions has None rank and 0 completions."""
        new_user = await patched_analytics_db.create_record(
            collection="members",
            data={
                "name": "NewUser",
                "phone": "+9999999999",
                "role": "member",
                "status": "active",
            },
        )

        result = await analytics_service.get_user_statistics(user_id=new_user["id"], period_days=30)

        assert result.user_id == new_user["id"]
        assert result.user_name == "NewUser"
        assert result.completions == 0
        assert result.rank is None
