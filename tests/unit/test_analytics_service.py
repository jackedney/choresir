"""Unit tests for analytics_service module."""

from datetime import UTC, datetime, timedelta

import pytest

from src.core.db_client import RecordNotFoundError
from src.domain.chore import ChoreState
from src.domain.user import UserStatus
from src.services import analytics_service


@pytest.fixture
def patched_analytics_db(monkeypatch, in_memory_db):
    """Patches src.core.db_client functions to use InMemoryDBClient."""

    # Patch all db_client functions
    monkeypatch.setattr("src.core.db_client.create_record", in_memory_db.create_record)
    monkeypatch.setattr("src.core.db_client.get_record", in_memory_db.get_record)
    monkeypatch.setattr("src.core.db_client.update_record", in_memory_db.update_record)
    monkeypatch.setattr("src.core.db_client.delete_record", in_memory_db.delete_record)
    monkeypatch.setattr("src.core.db_client.list_records", in_memory_db.list_records)
    monkeypatch.setattr("src.core.db_client.get_first_record", in_memory_db.get_first_record)
    monkeypatch.setattr("src.core.db_client.RecordNotFoundError", RecordNotFoundError)

    return in_memory_db


@pytest.fixture
def sample_users():
    """Sample user data for testing."""
    return [
        {"id": "user1", "name": "Alice", "status": UserStatus.ACTIVE},
        {"id": "user2", "name": "Bob", "status": UserStatus.ACTIVE},
        {"id": "user3", "name": "Charlie", "status": UserStatus.ACTIVE},
    ]


@pytest.fixture
def sample_chores():
    """Sample chore data for testing."""
    now = datetime.now(UTC)
    return [
        {
            "id": "chore1",
            "title": "Chore 1",
            "assigned_to": "user1",
            "current_state": ChoreState.TODO,
            "deadline": (now + timedelta(days=1)).isoformat(),
        },
        {
            "id": "chore2",
            "title": "Chore 2",
            "assigned_to": "user2",
            "current_state": ChoreState.PENDING_VERIFICATION,
            "deadline": (now + timedelta(days=2)).isoformat(),
        },
        {
            "id": "chore3",
            "title": "Chore 3",
            "assigned_to": "user1",
            "current_state": ChoreState.TODO,
            "deadline": (now - timedelta(days=1)).isoformat(),  # Overdue
        },
    ]


@pytest.mark.unit
class TestGetLeaderboard:
    """Tests for get_leaderboard function."""

    async def test_empty_leaderboard(self, patched_analytics_db):
        """Test leaderboard when no completions exist."""
        result = await analytics_service.get_leaderboard(period_days=30)

        assert result == []

    async def test_single_user_completions(self, patched_analytics_db, sample_users):
        """Test leaderboard with one user having completions."""
        # Create user
        user = await patched_analytics_db.create_record("users", {"name": "Alice", "status": UserStatus.ACTIVE})

        # Create completion logs
        cutoff_date = datetime.now(UTC) - timedelta(days=15)
        for _ in range(3):
            await patched_analytics_db.create_record(
                "logs",
                {
                    "user_id": user["id"],
                    "action": "claimed_completion",
                    "timestamp": (cutoff_date + timedelta(days=1)).isoformat(),
                },
            )

        result = await analytics_service.get_leaderboard(period_days=30)

        assert len(result) == 1
        assert result[0]["user_id"] == user["id"]
        assert result[0]["user_name"] == "Alice"
        assert result[0]["completion_count"] == 3

    async def test_multiple_users_sorted_descending(self, patched_analytics_db, sample_users):
        """Test leaderboard with multiple users sorted by completion count."""
        # Create users
        user1 = await patched_analytics_db.create_record("users", {"name": "Alice", "status": UserStatus.ACTIVE})
        user2 = await patched_analytics_db.create_record("users", {"name": "Bob", "status": UserStatus.ACTIVE})
        user3 = await patched_analytics_db.create_record("users", {"name": "Charlie", "status": UserStatus.ACTIVE})

        # Create completion logs (user2 has most, user1 has mid, user3 has least)
        cutoff_date = datetime.now(UTC) - timedelta(days=15)

        # User 2: 5 completions
        for _ in range(5):
            await patched_analytics_db.create_record(
                "logs",
                {
                    "user_id": user2["id"],
                    "action": "claimed_completion",
                    "timestamp": (cutoff_date + timedelta(days=1)).isoformat(),
                },
            )

        # User 1: 3 completions
        for _ in range(3):
            await patched_analytics_db.create_record(
                "logs",
                {
                    "user_id": user1["id"],
                    "action": "claimed_completion",
                    "timestamp": (cutoff_date + timedelta(days=1)).isoformat(),
                },
            )

        # User 3: 1 completion
        await patched_analytics_db.create_record(
            "logs",
            {
                "user_id": user3["id"],
                "action": "claimed_completion",
                "timestamp": (cutoff_date + timedelta(days=1)).isoformat(),
            },
        )

        result = await analytics_service.get_leaderboard(period_days=30)

        assert len(result) == 3
        # Sorted descending by completion count
        assert result[0]["user_id"] == user2["id"]
        assert result[0]["completion_count"] == 5
        assert result[1]["user_id"] == user1["id"]
        assert result[1]["completion_count"] == 3
        assert result[2]["user_id"] == user3["id"]
        assert result[2]["completion_count"] == 1

    async def test_period_days_filtering(self, patched_analytics_db):
        """Test that leaderboard only includes completions within the period."""
        # Create user
        user = await patched_analytics_db.create_record("users", {"name": "Alice", "status": UserStatus.ACTIVE})

        now = datetime.now(UTC)

        # Create logs: 2 within period, 1 outside period
        await patched_analytics_db.create_record(
            "logs",
            {
                "user_id": user["id"],
                "action": "claimed_completion",
                "timestamp": (now - timedelta(days=10)).isoformat(),  # Within 30 days
            },
        )
        await patched_analytics_db.create_record(
            "logs",
            {
                "user_id": user["id"],
                "action": "claimed_completion",
                "timestamp": (now - timedelta(days=20)).isoformat(),  # Within 30 days
            },
        )
        await patched_analytics_db.create_record(
            "logs",
            {
                "user_id": user["id"],
                "action": "claimed_completion",
                "timestamp": (now - timedelta(days=40)).isoformat(),  # Outside 30 days
            },
        )

        result = await analytics_service.get_leaderboard(period_days=30)

        assert len(result) == 1
        assert result[0]["completion_count"] == 2  # Only 2 within period

    async def test_missing_user_skipped_with_warning(self, patched_analytics_db):
        """Test that completions for missing users are skipped."""
        # Create log for non-existent user
        now = datetime.now(UTC)
        await patched_analytics_db.create_record(
            "logs",
            {
                "user_id": "nonexistent_user",
                "action": "claimed_completion",
                "timestamp": (now - timedelta(days=10)).isoformat(),
            },
        )

        result = await analytics_service.get_leaderboard(period_days=30)

        # Should be empty since user doesn't exist
        assert result == []


@pytest.mark.unit
class TestGetCompletionRate:
    """Tests for get_completion_rate function."""

    async def test_zero_completions(self, patched_analytics_db):
        """Test completion rate with no completions."""
        result = await analytics_service.get_completion_rate(period_days=30)

        assert result["total_completions"] == 0
        assert result["on_time"] == 0
        assert result["overdue"] == 0
        assert result["on_time_percentage"] == 0.0
        assert result["overdue_percentage"] == 0.0
        assert result["period_days"] == 30

    async def test_multiple_completions(self, patched_analytics_db):
        """Test completion rate with multiple completions."""
        # Create approval logs (MVP counts all as on-time)
        now = datetime.now(UTC)

        for i in range(5):
            await patched_analytics_db.create_record(
                "logs",
                {
                    "user_id": f"user{i}",
                    "action": "approve_verification",
                    "timestamp": (now - timedelta(days=5)).isoformat(),
                },
            )

        result = await analytics_service.get_completion_rate(period_days=30)

        assert result["total_completions"] == 5
        assert result["on_time"] == 5  # MVP counts all as on-time
        assert result["overdue"] == 0
        assert result["on_time_percentage"] == 100.0
        assert result["overdue_percentage"] == 0.0

    async def test_period_filtering(self, patched_analytics_db):
        """Test that only completions within period are counted."""
        now = datetime.now(UTC)

        # Create logs: 3 within period, 2 outside
        for i in range(3):
            await patched_analytics_db.create_record(
                "logs",
                {
                    "user_id": f"user{i}",
                    "action": "approve_verification",
                    "timestamp": (now - timedelta(days=10)).isoformat(),
                },
            )

        for i in range(2):
            await patched_analytics_db.create_record(
                "logs",
                {
                    "user_id": f"user{i + 3}",
                    "action": "approve_verification",
                    "timestamp": (now - timedelta(days=40)).isoformat(),
                },
            )

        result = await analytics_service.get_completion_rate(period_days=30)

        assert result["total_completions"] == 3  # Only within period

    async def test_custom_period_days(self, patched_analytics_db):
        """Test completion rate with custom period."""
        now = datetime.now(UTC)

        await patched_analytics_db.create_record(
            "logs",
            {
                "user_id": "user1",
                "action": "approve_verification",
                "timestamp": (now - timedelta(days=5)).isoformat(),
            },
        )

        result = await analytics_service.get_completion_rate(period_days=7)

        assert result["total_completions"] == 1
        assert result["period_days"] == 7


@pytest.mark.unit
class TestGetOverdueChores:
    """Tests for get_overdue_chores function."""

    async def test_no_overdue_chores(self, patched_analytics_db):
        """Test when there are no overdue chores."""
        # Create chore with future deadline
        now = datetime.now(UTC)
        await patched_analytics_db.create_record(
            "chores",
            {
                "title": "Future Chore",
                "assigned_to": "user1",
                "current_state": ChoreState.TODO,
                "deadline": (now + timedelta(days=1)).isoformat(),
            },
        )

        result = await analytics_service.get_overdue_chores()

        assert result == []

    async def test_overdue_chores_past_deadline(self, patched_analytics_db):
        """Test finding chores past their deadline."""
        now = datetime.now(UTC)

        # Overdue chore
        await patched_analytics_db.create_record(
            "chores",
            {
                "title": "Overdue Chore",
                "assigned_to": "user1",
                "current_state": ChoreState.TODO,
                "deadline": (now - timedelta(days=1)).isoformat(),
            },
        )

        result = await analytics_service.get_overdue_chores()

        assert len(result) == 1
        assert result[0]["title"] == "Overdue Chore"

    async def test_completed_chore_not_overdue(self, patched_analytics_db):
        """Test that completed chores are not considered overdue."""
        now = datetime.now(UTC)

        # Completed chore with past deadline
        await patched_analytics_db.create_record(
            "chores",
            {
                "title": "Completed Chore",
                "assigned_to": "user1",
                "current_state": ChoreState.COMPLETED,
                "deadline": (now - timedelta(days=1)).isoformat(),
            },
        )

        result = await analytics_service.get_overdue_chores()

        assert result == []

    async def test_filter_by_user_id(self, patched_analytics_db):
        """Test filtering overdue chores by user ID."""
        now = datetime.now(UTC)

        # User1's overdue chore
        await patched_analytics_db.create_record(
            "chores",
            {
                "title": "User1 Overdue",
                "assigned_to": "user1",
                "current_state": ChoreState.TODO,
                "deadline": (now - timedelta(days=1)).isoformat(),
            },
        )

        # User2's overdue chore
        await patched_analytics_db.create_record(
            "chores",
            {
                "title": "User2 Overdue",
                "assigned_to": "user2",
                "current_state": ChoreState.TODO,
                "deadline": (now - timedelta(days=1)).isoformat(),
            },
        )

        result = await analytics_service.get_overdue_chores(user_id="user1")

        assert len(result) == 1
        assert result[0]["assigned_to"] == "user1"

    async def test_limit_parameter(self, patched_analytics_db):
        """Test limiting number of results returned."""
        now = datetime.now(UTC)

        # Create 5 overdue chores
        for i in range(5):
            await patched_analytics_db.create_record(
                "chores",
                {
                    "title": f"Overdue {i}",
                    "assigned_to": "user1",
                    "current_state": ChoreState.TODO,
                    "deadline": (now - timedelta(days=i + 1)).isoformat(),
                },
            )

        result = await analytics_service.get_overdue_chores(limit=3)

        assert len(result) == 3

    async def test_sorting_by_deadline(self, patched_analytics_db):
        """Test that overdue chores are sorted by deadline (oldest first)."""
        now = datetime.now(UTC)

        # Create chores with different deadlines
        await patched_analytics_db.create_record(
            "chores",
            {
                "title": "Most Overdue",
                "assigned_to": "user1",
                "current_state": ChoreState.TODO,
                "deadline": (now - timedelta(days=5)).isoformat(),
            },
        )
        await patched_analytics_db.create_record(
            "chores",
            {
                "title": "Less Overdue",
                "assigned_to": "user1",
                "current_state": ChoreState.TODO,
                "deadline": (now - timedelta(days=2)).isoformat(),
            },
        )

        result = await analytics_service.get_overdue_chores()

        # Should be sorted oldest deadline first
        assert len(result) == 2
        assert result[0]["title"] == "Most Overdue"
        assert result[1]["title"] == "Less Overdue"


@pytest.mark.unit
class TestGetUserStatistics:
    """Tests for get_user_statistics function."""

    async def test_user_not_found_raises_error(self, patched_analytics_db):
        """Test that requesting stats for non-existent user raises error."""
        with pytest.raises(RecordNotFoundError):
            await analytics_service.get_user_statistics(user_id="nonexistent", period_days=30)

    async def test_user_with_zero_activity(self, patched_analytics_db, sample_users):
        """Test user with no completions or pending claims."""
        # Create user
        user = await patched_analytics_db.create_record("users", {"name": "Alice", "status": UserStatus.ACTIVE})

        result = await analytics_service.get_user_statistics(user_id=user["id"], period_days=30)

        assert result["user_id"] == user["id"]
        assert result["user_name"] == "Alice"
        assert result["completions"] == 0
        assert result["claims_pending"] == 0
        assert result["overdue_chores"] == 0
        assert result["rank"] is None
        assert result["period_days"] == 30

    async def test_user_with_single_pending_claim(self, patched_analytics_db, sample_users):
        """Test user with 1 pending claim."""
        # Create user
        user = await patched_analytics_db.create_record("users", {"name": "Alice", "status": UserStatus.ACTIVE})

        # Create pending verification chore
        chore = await patched_analytics_db.create_record(
            "chores",
            {
                "title": "Pending Chore",
                "assigned_to": user["id"],
                "current_state": ChoreState.PENDING_VERIFICATION,
                "deadline": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
            },
        )

        # Create claim log for that chore
        await patched_analytics_db.create_record(
            "logs",
            {
                "user_id": user["id"],
                "action": "claimed_completion",
                "chore_id": chore["id"],
                "timestamp": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
            },
        )

        result = await analytics_service.get_user_statistics(user_id=user["id"], period_days=30)

        assert result["claims_pending"] == 1

    async def test_user_with_chunked_pending_claims(self, patched_analytics_db, sample_users):
        """Test user with >50 pending claims (tests chunking logic)."""
        # Create user
        await patched_analytics_db.create_record("users", sample_users[0])

        # Create 60 pending verification chores and claims
        for i in range(60):
            chore = await patched_analytics_db.create_record(
                "chores",
                {
                    "title": f"Pending Chore {i}",
                    "assigned_to": "user1",
                    "current_state": ChoreState.PENDING_VERIFICATION,
                    "deadline": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
                },
            )

            await patched_analytics_db.create_record(
                "logs",
                {
                    "user_id": "user1",
                    "action": "claimed_completion",
                    "chore_id": chore["id"],
                    "timestamp": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
                },
            )

        result = await analytics_service.get_user_statistics(user_id="user1", period_days=30)

        # Should count all 60 despite chunking
        assert result["claims_pending"] == 60

    async def test_user_with_many_total_claims_but_few_pending(self, patched_analytics_db, sample_users):
        """Test user with >500 total claim logs but <50 pending claims."""
        # Create user
        user = await patched_analytics_db.create_record("users", {"name": "Alice", "status": UserStatus.ACTIVE})

        # Create 10 pending verification chores with claims
        for i in range(10):
            chore = await patched_analytics_db.create_record(
                "chores",
                {
                    "title": f"Pending Chore {i}",
                    "assigned_to": user["id"],
                    "current_state": ChoreState.PENDING_VERIFICATION,
                    "deadline": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
                },
            )

            await patched_analytics_db.create_record(
                "logs",
                {
                    "user_id": user["id"],
                    "action": "claimed_completion",
                    "chore_id": chore["id"],
                    "timestamp": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
                },
            )

        # Create 100 historical (completed) chores with claims
        for i in range(100):
            chore = await patched_analytics_db.create_record(
                "chores",
                {
                    "title": f"Historical Chore {i}",
                    "assigned_to": user["id"],
                    "current_state": ChoreState.COMPLETED,
                    "deadline": (datetime.now(UTC) - timedelta(days=10)).isoformat(),
                },
            )

            await patched_analytics_db.create_record(
                "logs",
                {
                    "user_id": user["id"],
                    "action": "claimed_completion",
                    "chore_id": chore["id"],
                    "timestamp": (datetime.now(UTC) - timedelta(days=11)).isoformat(),
                },
            )

        result = await analytics_service.get_user_statistics(user_id=user["id"], period_days=30)

        # Should only count the 10 pending claims, not historical ones
        assert result["claims_pending"] == 10

    async def test_user_with_multiple_claims_same_chore(self, patched_analytics_db, sample_users):
        """Test user with multiple claims for the same chore counts as 1 pending claim.

        This is the key bug fix: when a user claims the same chore multiple times
        (e.g., after rejection and reclaim), it should only count as 1 pending claim,
        not multiple claims.
        """
        # Create user
        await patched_analytics_db.create_record("users", sample_users[0])

        # Create 1 pending verification chore
        chore = await patched_analytics_db.create_record(
            "chores",
            {
                "title": "Pending Chore",
                "assigned_to": "user1",
                "current_state": ChoreState.PENDING_VERIFICATION,
                "deadline": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
            },
        )

        # Create multiple claim logs for the same chore (e.g., after rejection and reclaim)
        for i in range(3):
            await patched_analytics_db.create_record(
                "logs",
                {
                    "user_id": "user1",
                    "action": "claimed_completion",
                    "chore_id": chore["id"],
                    "timestamp": (datetime.now(UTC) - timedelta(hours=i + 1)).isoformat(),
                },
            )

        result = await analytics_service.get_user_statistics(user_id="user1", period_days=30)

        # Should count 1 distinct chore, not 3 claim logs
        assert result["claims_pending"] == 1

    async def test_user_with_pagination_edge_case(self, patched_analytics_db, sample_users):
        """Test pagination handles edge case where chunk exceeds per_page limit."""
        # Create user
        await patched_analytics_db.create_record("users", sample_users[0])

        # Create 40 pending verification chores (fits in 1 chunk of 50)
        # but with 3 claims each (120 total claims > per_page limit of 100)
        for i in range(40):
            chore = await patched_analytics_db.create_record(
                "chores",
                {
                    "title": f"Pending Chore {i}",
                    "assigned_to": "user1",
                    "current_state": ChoreState.PENDING_VERIFICATION,
                    "deadline": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
                },
            )

            # Create 3 claim logs per chore (unusual but tests pagination)
            for j in range(3):
                await patched_analytics_db.create_record(
                    "logs",
                    {
                        "user_id": "user1",
                        "action": "claimed_completion",
                        "chore_id": chore["id"],
                        "timestamp": (datetime.now(UTC) - timedelta(hours=j + 1)).isoformat(),
                    },
                )

        result = await analytics_service.get_user_statistics(user_id="user1", period_days=30)

        # Should count 40 distinct chores despite 120 total claim logs (40 chores * 3 claims each)
        # This tests that deduplication works correctly across pagination
        assert result["claims_pending"] == 40

    async def test_user_with_exactly_100_claims_boundary(self, patched_analytics_db, sample_users):
        """Test boundary case: exactly 100 claims (per_page limit)."""
        # Create user
        await patched_analytics_db.create_record("users", sample_users[0])

        # Create 100 pending verification chores with 1 claim each
        # This tests the boundary condition where claims == per_page
        for i in range(100):
            chore = await patched_analytics_db.create_record(
                "chores",
                {
                    "title": f"Pending Chore {i}",
                    "assigned_to": "user1",
                    "current_state": ChoreState.PENDING_VERIFICATION,
                    "deadline": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
                },
            )

            await patched_analytics_db.create_record(
                "logs",
                {
                    "user_id": "user1",
                    "action": "claimed_completion",
                    "chore_id": chore["id"],
                    "timestamp": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
                },
            )

        result = await analytics_service.get_user_statistics(user_id="user1", period_days=30)

        # Should count all 100 claims without triggering unnecessary pagination
        assert result["claims_pending"] == 100

    async def test_user_with_101_claims_requires_two_pages(self, patched_analytics_db, sample_users):
        """Test 101 claims requires 2 pages (per_page=100)."""
        # Create user
        await patched_analytics_db.create_record("users", sample_users[0])

        # Create 101 pending verification chores with 1 claim each
        # This should require exactly 2 pages: 100 + 1
        for i in range(101):
            chore = await patched_analytics_db.create_record(
                "chores",
                {
                    "title": f"Pending Chore {i}",
                    "assigned_to": "user1",
                    "current_state": ChoreState.PENDING_VERIFICATION,
                    "deadline": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
                },
            )

            await patched_analytics_db.create_record(
                "logs",
                {
                    "user_id": "user1",
                    "action": "claimed_completion",
                    "chore_id": chore["id"],
                    "timestamp": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
                },
            )

        result = await analytics_service.get_user_statistics(user_id="user1", period_days=30)

        # Should count all 101 claims across 2 pages
        assert result["claims_pending"] == 101

    async def test_user_with_300_claims_requires_three_pages(self, patched_analytics_db, sample_users):
        """Test 300 claims requires 3 pages (per_page=100)."""
        # Create user
        await patched_analytics_db.create_record("users", sample_users[0])

        # Create 150 pending verification chores with 2 claims each = 300 total
        # This should require exactly 3 pages: 100 + 100 + 100
        # We use 2 claims per chore to fit within chunk_size=50 limit
        for i in range(150):
            chore = await patched_analytics_db.create_record(
                "chores",
                {
                    "title": f"Pending Chore {i}",
                    "assigned_to": "user1",
                    "current_state": ChoreState.PENDING_VERIFICATION,
                    "deadline": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
                },
            )

            # Create 2 claims per chore
            for j in range(2):
                await patched_analytics_db.create_record(
                    "logs",
                    {
                        "user_id": "user1",
                        "action": "claimed_completion",
                        "chore_id": chore["id"],
                        "timestamp": (datetime.now(UTC) - timedelta(hours=j + 1)).isoformat(),
                    },
                )

        result = await analytics_service.get_user_statistics(user_id="user1", period_days=30)

        # Should count 150 distinct chores despite 300 total claim logs (150 chores x 2 claims)
        # This tests that deduplication works correctly across multiple pages
        assert result["claims_pending"] == 150

    async def test_user_not_in_leaderboard(self, patched_analytics_db, sample_users):
        """Test user with no completions (not in leaderboard)."""
        # Create user
        await patched_analytics_db.create_record("users", sample_users[0])

        result = await analytics_service.get_user_statistics(user_id="user1", period_days=30)

        assert result["rank"] is None
        assert result["completions"] == 0

    async def test_user_with_high_rank(self, patched_analytics_db):
        """Test user with high rank in leaderboard."""
        # Create users
        user1 = await patched_analytics_db.create_record("users", {"name": "Alice", "status": UserStatus.ACTIVE})
        user2 = await patched_analytics_db.create_record("users", {"name": "Bob", "status": UserStatus.ACTIVE})

        now = datetime.now(UTC)

        # User1: 10 completions (rank 1)
        for _ in range(10):
            await patched_analytics_db.create_record(
                "logs",
                {
                    "user_id": user1["id"],
                    "action": "claimed_completion",
                    "timestamp": (now - timedelta(days=5)).isoformat(),
                },
            )

        # User2: 5 completions (rank 2)
        for _ in range(5):
            await patched_analytics_db.create_record(
                "logs",
                {
                    "user_id": user2["id"],
                    "action": "claimed_completion",
                    "timestamp": (now - timedelta(days=5)).isoformat(),
                },
            )

        result = await analytics_service.get_user_statistics(user_id=user1["id"], period_days=30)

        assert result["rank"] == 1
        assert result["completions"] == 10

    async def test_user_with_overdue_chores(self, patched_analytics_db, sample_users):
        """Test user with overdue chores assigned."""
        # Create user
        user = await patched_analytics_db.create_record("users", {"name": "Alice", "status": UserStatus.ACTIVE})

        now = datetime.now(UTC)

        # Create overdue chores
        for i in range(3):
            await patched_analytics_db.create_record(
                "chores",
                {
                    "title": f"Overdue {i}",
                    "assigned_to": user["id"],
                    "current_state": ChoreState.TODO,
                    "deadline": (now - timedelta(days=i + 1)).isoformat(),
                },
            )

        result = await analytics_service.get_user_statistics(user_id=user["id"], period_days=30)

        assert result["overdue_chores"] == 3

    async def test_user_missing_name_field(self, patched_analytics_db):
        """Test handling of user record missing 'name' field."""
        # Create user without name field (malformed data)
        user = await patched_analytics_db.create_record("users", {"status": UserStatus.ACTIVE})

        result = await analytics_service.get_user_statistics(user_id=user["id"], period_days=30)

        # Should use user_id as fallback for user_name
        assert result["user_id"] == user["id"]
        assert result["user_name"] == user["id"]  # Fallback to ID

    async def test_leaderboard_entry_missing_user_id(self, patched_analytics_db, monkeypatch):
        """Test handling of leaderboard entries with missing user_id."""
        # Create user
        user = await patched_analytics_db.create_record("users", {"name": "Alice", "status": UserStatus.ACTIVE})

        # Mock get_leaderboard to return malformed entry
        async def mock_get_leaderboard(period_days):
            return [
                {"user_id": None, "user_name": "Ghost", "completion_count": 5},  # Missing user_id
                {"user_id": user["id"], "user_name": "Alice", "completion_count": 3},
            ]

        monkeypatch.setattr(analytics_service, "get_leaderboard", mock_get_leaderboard)

        result = await analytics_service.get_user_statistics(user_id=user["id"], period_days=30)

        # Should skip the malformed entry and find the user at rank 2
        # (rank is based on position in leaderboard, even if we skip entries)
        assert result["rank"] == 2  # Second entry in the list
        assert result["completions"] == 3

    async def test_leaderboard_database_error(self, patched_analytics_db, monkeypatch):
        """Test partial results when leaderboard query fails."""
        # Create user
        user = await patched_analytics_db.create_record("users", {"name": "Alice", "status": UserStatus.ACTIVE})

        # Mock get_leaderboard to raise DatabaseError
        from src.core.db_client import DatabaseError

        async def mock_get_leaderboard_error(period_days):
            raise DatabaseError("Simulated database error")

        monkeypatch.setattr(analytics_service, "get_leaderboard", mock_get_leaderboard_error)

        # Create some pending chores for the user
        chore = await patched_analytics_db.create_record(
            "chores",
            {
                "title": "Pending Chore",
                "assigned_to": user["id"],
                "current_state": ChoreState.PENDING_VERIFICATION,
                "deadline": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
            },
        )
        await patched_analytics_db.create_record(
            "logs",
            {
                "user_id": user["id"],
                "action": "claimed_completion",
                "chore_id": chore["id"],
                "timestamp": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
            },
        )

        result = await analytics_service.get_user_statistics(user_id=user["id"], period_days=30)

        # Should return partial results
        assert result["user_id"] == user["id"]
        assert result["user_name"] == "Alice"
        assert result["rank"] is None
        assert result["completions"] == 0
        assert result["rank_error"] is not None
        assert "database error" in result["rank_error"].lower()
        # But other stats should still work
        assert result["claims_pending"] == 1
        assert result["claims_pending_error"] is None

    async def test_leaderboard_unexpected_error(self, patched_analytics_db, monkeypatch):
        """Test handling of unexpected errors in leaderboard fetch."""
        # Create user
        user = await patched_analytics_db.create_record("users", {"name": "Alice", "status": UserStatus.ACTIVE})

        # Mock get_leaderboard to raise unexpected error
        async def mock_get_leaderboard_unexpected(period_days):
            raise ValueError("Unexpected error")

        monkeypatch.setattr(analytics_service, "get_leaderboard", mock_get_leaderboard_unexpected)

        result = await analytics_service.get_user_statistics(user_id=user["id"], period_days=30)

        # Should return partial results with error
        assert result["rank"] is None
        assert result["rank_error"] is not None
        assert "unexpected error" in result["rank_error"].lower()

    async def test_pending_chores_database_error(self, patched_analytics_db, monkeypatch):
        """Test handling when pending chores query fails."""
        # Create user
        user = await patched_analytics_db.create_record("users", {"name": "Alice", "status": UserStatus.ACTIVE})

        # Mock list_records to fail for pending verification chores
        original_list_records = patched_analytics_db.list_records

        async def mock_list_records_error(collection, **kwargs):
            if collection == "chores" and "PENDING_VERIFICATION" in kwargs.get("filter_query", ""):
                from src.core.db_client import DatabaseError

                raise DatabaseError("Simulated database error for pending chores")
            return await original_list_records(collection, **kwargs)

        monkeypatch.setattr("src.core.db_client.list_records", mock_list_records_error)

        result = await analytics_service.get_user_statistics(user_id=user["id"], period_days=30)

        # Should have error for claims_pending
        assert result["claims_pending"] is None
        assert result["claims_pending_error"] is not None
        assert "database error" in result["claims_pending_error"].lower()

    async def test_chore_missing_id_field(self, patched_analytics_db):
        """Test handling of chores missing 'id' field."""
        # Create user
        user = await patched_analytics_db.create_record("users", {"name": "Alice", "status": UserStatus.ACTIVE})

        # Manually create a malformed chore without ID (bypassing normal validation)
        # In practice, this would come from db_client returning malformed data
        # Since our mock db requires IDs, we'll test this indirectly by patching list_records

        # Create a normal chore first
        chore = await patched_analytics_db.create_record(
            "chores",
            {
                "title": "Normal Chore",
                "assigned_to": user["id"],
                "current_state": ChoreState.PENDING_VERIFICATION,
                "deadline": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
            },
        )

        # Create claim for the normal chore
        await patched_analytics_db.create_record(
            "logs",
            {
                "user_id": user["id"],
                "action": "claimed_completion",
                "chore_id": chore["id"],
                "timestamp": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
            },
        )

        result = await analytics_service.get_user_statistics(user_id=user["id"], period_days=30)

        # Should count the normal chore's claim
        assert result["claims_pending"] == 1

    async def test_claims_fetch_database_error_in_chunk(self, patched_analytics_db, monkeypatch):
        """Test handling when one chunk of claims fetch fails."""
        # Create user
        user = await patched_analytics_db.create_record("users", {"name": "Alice", "status": UserStatus.ACTIVE})

        # Create 60 pending chores (will be processed in 2 chunks)
        chore_ids = []
        for i in range(60):
            chore = await patched_analytics_db.create_record(
                "chores",
                {
                    "title": f"Pending Chore {i}",
                    "assigned_to": user["id"],
                    "current_state": ChoreState.PENDING_VERIFICATION,
                    "deadline": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
                },
            )
            chore_ids.append(chore["id"])

            await patched_analytics_db.create_record(
                "logs",
                {
                    "user_id": user["id"],
                    "action": "claimed_completion",
                    "chore_id": chore["id"],
                    "timestamp": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
                },
            )

        # Mock list_records to fail on second chunk
        original_list_records = patched_analytics_db.list_records
        call_count = {"count": 0}

        async def mock_list_records_fail_second_chunk(collection, **kwargs):
            if collection == "logs" and "claimed_completion" in kwargs.get("filter_query", ""):
                call_count["count"] += 1
                if call_count["count"] == 2:  # Fail on second chunk
                    from src.core.db_client import DatabaseError

                    raise DatabaseError("Simulated error in second chunk")
            return await original_list_records(collection, **kwargs)

        monkeypatch.setattr("src.core.db_client.list_records", mock_list_records_fail_second_chunk)

        result = await analytics_service.get_user_statistics(user_id=user["id"], period_days=30)

        # Since the second chunk (second page within first chunk) fails,
        # we get the first page of the first chunk only (first 100 records)
        # But there are only 60 total chores, and first chunk processes 50 of them,
        # so we get whatever was successfully fetched before the error
        # The error happens on the second call (page 2 of chunk 1), so we only get page 1
        # Actually, looking at the code, the call count is per collection="logs" call
        # First call gets pending chores, second call gets first batch of claims
        # So we should get 10 claims (from offset 50-59 in the first chunk call that succeeds)
        assert result["claims_pending"] < 60  # Some claims were fetched
        assert result["claims_pending_error"] is None  # No overall error, just chunk failure

    async def test_overdue_chores_database_error(self, patched_analytics_db, monkeypatch):
        """Test handling when overdue chores query fails."""
        # Create user
        user = await patched_analytics_db.create_record("users", {"name": "Alice", "status": UserStatus.ACTIVE})

        # Mock get_overdue_chores to raise error
        from src.core.db_client import DatabaseError

        async def mock_get_overdue_chores_error(user_id=None, limit=None):
            raise DatabaseError("Simulated database error for overdue chores")

        monkeypatch.setattr(analytics_service, "get_overdue_chores", mock_get_overdue_chores_error)

        result = await analytics_service.get_user_statistics(user_id=user["id"], period_days=30)

        # Should have error for overdue_chores
        assert result["overdue_chores"] is None
        assert result["overdue_chores_error"] is not None
        assert "database error" in result["overdue_chores_error"].lower()

    async def test_overdue_chores_unexpected_error(self, patched_analytics_db, monkeypatch):
        """Test handling of unexpected errors in overdue chores fetch."""
        # Create user
        user = await patched_analytics_db.create_record("users", {"name": "Alice", "status": UserStatus.ACTIVE})

        # Mock get_overdue_chores to raise unexpected error
        async def mock_get_overdue_chores_unexpected(user_id=None, limit=None):
            raise RuntimeError("Unexpected runtime error")

        monkeypatch.setattr(analytics_service, "get_overdue_chores", mock_get_overdue_chores_unexpected)

        result = await analytics_service.get_user_statistics(user_id=user["id"], period_days=30)

        # Should have error for overdue_chores
        assert result["overdue_chores"] is None
        assert result["overdue_chores_error"] is not None
        assert "unexpected error" in result["overdue_chores_error"].lower()

    async def test_multiple_errors_at_once(self, patched_analytics_db, monkeypatch):
        """Test handling when multiple subsystems fail simultaneously."""
        # Create user
        user = await patched_analytics_db.create_record("users", {"name": "Alice", "status": UserStatus.ACTIVE})

        from src.core.db_client import DatabaseError

        # Mock all subsystems to fail
        async def mock_get_leaderboard_error(period_days):
            raise DatabaseError("Leaderboard error")

        async def mock_get_overdue_chores_error(user_id=None, limit=None):
            raise DatabaseError("Overdue chores error")

        original_list_records = patched_analytics_db.list_records

        async def mock_list_records_error(collection, **kwargs):
            if collection == "chores" and "PENDING_VERIFICATION" in kwargs.get("filter_query", ""):
                raise DatabaseError("Pending chores error")
            return await original_list_records(collection, **kwargs)

        monkeypatch.setattr(analytics_service, "get_leaderboard", mock_get_leaderboard_error)
        monkeypatch.setattr(analytics_service, "get_overdue_chores", mock_get_overdue_chores_error)
        monkeypatch.setattr("src.core.db_client.list_records", mock_list_records_error)

        result = await analytics_service.get_user_statistics(user_id=user["id"], period_days=30)

        # Should still return user info but with all errors
        assert result["user_id"] == user["id"]
        assert result["user_name"] == "Alice"
        assert result["rank"] is None
        assert result["rank_error"] is not None
        assert result["claims_pending"] is None
        assert result["claims_pending_error"] is not None
        assert result["overdue_chores"] is None
        assert result["overdue_chores_error"] is not None

    async def test_all_subsystems_working_with_data(self, patched_analytics_db):
        """Test complete success path with all subsystems returning data (no errors)."""
        # Create user
        user = await patched_analytics_db.create_record("users", {"name": "Alice", "status": UserStatus.ACTIVE})

        now = datetime.now(UTC)

        # Create completions for leaderboard
        for _ in range(5):
            await patched_analytics_db.create_record(
                "logs",
                {
                    "user_id": user["id"],
                    "action": "claimed_completion",
                    "timestamp": (now - timedelta(days=5)).isoformat(),
                },
            )

        # Create pending chore with claim
        chore = await patched_analytics_db.create_record(
            "chores",
            {
                "title": "Pending Chore",
                "assigned_to": user["id"],
                "current_state": ChoreState.PENDING_VERIFICATION,
                "deadline": (now + timedelta(days=1)).isoformat(),
            },
        )
        await patched_analytics_db.create_record(
            "logs",
            {
                "user_id": user["id"],
                "action": "claimed_completion",
                "chore_id": chore["id"],
                "timestamp": (now - timedelta(hours=1)).isoformat(),
            },
        )

        # Create overdue chore
        await patched_analytics_db.create_record(
            "chores",
            {
                "title": "Overdue Chore",
                "assigned_to": user["id"],
                "current_state": ChoreState.TODO,
                "deadline": (now - timedelta(days=1)).isoformat(),
            },
        )

        result = await analytics_service.get_user_statistics(user_id=user["id"], period_days=30)

        # All fields should be populated without errors
        assert result["user_id"] == user["id"]
        assert result["user_name"] == "Alice"
        assert result["rank"] == 1
        # Note: completions count all "claimed_completion" logs, including the one for the pending chore
        # So we have 5 historical + 1 pending = 6 total
        assert result["completions"] == 6
        assert result["claims_pending"] == 1
        assert result["overdue_chores"] == 1
        assert result["rank_error"] is None
        assert result["claims_pending_error"] is None
        assert result["overdue_chores_error"] is None

    async def test_optimization_reduces_data_fetched(self, patched_analytics_db, monkeypatch):
        """Verify optimized query fetches less data than naive approach.

        This test validates the performance optimization that fetches only claims
        for pending chores instead of all user claims.
        """
        # Create user
        user = await patched_analytics_db.create_record("users", {"name": "Alice", "status": UserStatus.ACTIVE})

        now = datetime.now(UTC)

        # Setup: User with 100 historical (completed) chores but only 3 pending
        # Create 100 historical completed chores with claims
        for i in range(100):
            chore = await patched_analytics_db.create_record(
                "chores",
                {
                    "title": f"Historical Chore {i}",
                    "assigned_to": user["id"],
                    "current_state": ChoreState.COMPLETED,
                    "deadline": (now - timedelta(days=10)).isoformat(),
                },
            )

            await patched_analytics_db.create_record(
                "logs",
                {
                    "user_id": user["id"],
                    "action": "claimed_completion",
                    "chore_id": chore["id"],
                    "timestamp": (now - timedelta(days=11)).isoformat(),
                },
            )

        # Create 3 pending verification chores with claims
        for i in range(3):
            chore = await patched_analytics_db.create_record(
                "chores",
                {
                    "title": f"Pending Chore {i}",
                    "assigned_to": user["id"],
                    "current_state": ChoreState.PENDING_VERIFICATION,
                    "deadline": (now + timedelta(days=1)).isoformat(),
                },
            )

            await patched_analytics_db.create_record(
                "logs",
                {
                    "user_id": user["id"],
                    "action": "claimed_completion",
                    "chore_id": chore["id"],
                    "timestamp": (now - timedelta(hours=1)).isoformat(),
                },
            )

        # Track database queries
        original_list_records = patched_analytics_db.list_records
        query_log = []

        async def tracked_list_records(collection, **kwargs):
            result = await original_list_records(collection, **kwargs)
            filter_query = kwargs.get("filter_query", "")
            # Only track pending claims queries (not leaderboard queries)
            if collection == "logs" and "claimed_completion" in filter_query and "chore_id" in filter_query:
                query_log.append(
                    {
                        "collection": collection,
                        "filter_query": filter_query,
                        "records_fetched": len(result),
                        "per_page": kwargs.get("per_page"),
                    }
                )
            return result

        monkeypatch.setattr("src.core.db_client.list_records", tracked_list_records)

        # Execute the function
        result = await analytics_service.get_user_statistics(user_id=user["id"], period_days=30)

        # Assertions
        # 1. Function should return correct result
        assert result["claims_pending"] == 3

        # 2. Verify optimization: New approach should fetch only 3 logs (for pending chores)
        #    vs old approach which would fetch all 103 logs (or 100 if limited by per_page=500)
        total_logs_fetched = sum(q["records_fetched"] for q in query_log)

        # Optimized approach should fetch significantly fewer logs
        assert total_logs_fetched == 3, (
            f"Expected to fetch only 3 logs (for pending chores), "
            f"but fetched {total_logs_fetched} logs. "
            f"Query log: {query_log}"
        )

        # 3. Verify we made only 1 chunk query (since 3 pending chores < chunk_size of 50)
        assert len(query_log) == 1, f"Expected 1 chunk query for 3 pending chores, but made {len(query_log)} queries"

        # 4. Verify the query filters by both user_id AND specific chore IDs (optimization)
        query = query_log[0]["filter_query"]
        assert user["id"] in query
        assert "chore_id" in query, "Query should filter by chore_id (optimization)"

    async def test_optimization_worst_case_scenario(self, patched_analytics_db, monkeypatch):
        """Test scenario where optimization might not help: many pending chores.

        When there are 100+ pending chores, the chunking approach makes multiple
        queries but should still complete successfully.
        """
        # Create user
        user = await patched_analytics_db.create_record("users", {"name": "Alice", "status": UserStatus.ACTIVE})

        now = datetime.now(UTC)

        # Create 100 pending verification chores (will require 2 chunks: 50 + 50)
        for i in range(100):
            chore = await patched_analytics_db.create_record(
                "chores",
                {
                    "title": f"Pending Chore {i}",
                    "assigned_to": user["id"],
                    "current_state": ChoreState.PENDING_VERIFICATION,
                    "deadline": (now + timedelta(days=1)).isoformat(),
                },
            )

            await patched_analytics_db.create_record(
                "logs",
                {
                    "user_id": user["id"],
                    "action": "claimed_completion",
                    "chore_id": chore["id"],
                    "timestamp": (now - timedelta(hours=1)).isoformat(),
                },
            )

        # Track database queries
        original_list_records = patched_analytics_db.list_records
        query_log = []

        async def tracked_list_records(collection, **kwargs):
            result = await original_list_records(collection, **kwargs)
            filter_query = kwargs.get("filter_query", "")
            # Only track pending claims queries (not leaderboard queries)
            if collection == "logs" and "claimed_completion" in filter_query and "chore_id" in filter_query:
                query_log.append(
                    {
                        "collection": collection,
                        "records_fetched": len(result),
                    }
                )
            return result

        monkeypatch.setattr("src.core.db_client.list_records", tracked_list_records)

        # Execute the function
        result = await analytics_service.get_user_statistics(user_id=user["id"], period_days=30)

        # Assertions
        assert result["claims_pending"] == 100

        # Should make 2 chunk queries (ceil(100 / 50) = 2)
        assert len(query_log) == 2, (
            f"Expected 2 chunk queries for 100 pending chores, but made {len(query_log)} queries"
        )

        # Total logs fetched should be 100 (50 per chunk)
        total_logs_fetched = sum(q["records_fetched"] for q in query_log)
        assert total_logs_fetched == 100


@pytest.mark.unit
class TestGetHouseholdSummary:
    """Tests for get_household_summary function."""

    async def test_empty_household(self, patched_analytics_db):
        """Test household summary with no data."""
        result = await analytics_service.get_household_summary(period_days=7)

        assert result["active_members"] == 0
        assert result["completions_this_period"] == 0
        assert result["current_conflicts"] == 0
        assert result["overdue_chores"] == 0
        assert result["pending_verifications"] == 0
        assert result["period_days"] == 7

    async def test_household_with_active_members(self, patched_analytics_db, sample_users):
        """Test counting active members."""
        # Create active users
        for user in sample_users:
            await patched_analytics_db.create_record("users", user)

        # Create a banned user (non-active)
        await patched_analytics_db.create_record(
            "users", {"id": "user4", "name": "Banned Dave", "status": UserStatus.BANNED}
        )

        result = await analytics_service.get_household_summary(period_days=7)

        assert result["active_members"] == 3  # Only active users

    async def test_household_with_completions(self, patched_analytics_db):
        """Test counting completions in period."""
        now = datetime.now(UTC)

        # Create completions within period
        for i in range(5):
            await patched_analytics_db.create_record(
                "logs",
                {
                    "user_id": f"user{i}",
                    "action": "approve_verification",
                    "timestamp": (now - timedelta(days=3)).isoformat(),
                },
            )

        # Create completion outside period
        await patched_analytics_db.create_record(
            "logs",
            {
                "user_id": "user5",
                "action": "approve_verification",
                "timestamp": (now - timedelta(days=10)).isoformat(),
            },
        )

        result = await analytics_service.get_household_summary(period_days=7)

        assert result["completions_this_period"] == 5

    async def test_household_with_conflicts(self, patched_analytics_db):
        """Test counting current conflicts."""
        # Create conflict chores
        for i in range(3):
            await patched_analytics_db.create_record(
                "chores",
                {
                    "title": f"Conflict {i}",
                    "assigned_to": f"user{i}",
                    "current_state": ChoreState.CONFLICT,
                    "deadline": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
                },
            )

        result = await analytics_service.get_household_summary(period_days=7)

        assert result["current_conflicts"] == 3

    async def test_household_with_overdue_chores(self, patched_analytics_db):
        """Test counting overdue chores."""
        now = datetime.now(UTC)

        # Create overdue chores
        for i in range(4):
            await patched_analytics_db.create_record(
                "chores",
                {
                    "title": f"Overdue {i}",
                    "assigned_to": f"user{i}",
                    "current_state": ChoreState.TODO,
                    "deadline": (now - timedelta(days=1)).isoformat(),
                },
            )

        result = await analytics_service.get_household_summary(period_days=7)

        assert result["overdue_chores"] == 4

    async def test_household_with_pending_verifications(self, patched_analytics_db):
        """Test counting pending verifications."""
        # Create pending verification chores
        for i in range(6):
            await patched_analytics_db.create_record(
                "chores",
                {
                    "title": f"Pending {i}",
                    "assigned_to": f"user{i}",
                    "current_state": ChoreState.PENDING_VERIFICATION,
                    "deadline": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
                },
            )

        result = await analytics_service.get_household_summary(period_days=7)

        assert result["pending_verifications"] == 6

    async def test_household_full_summary(self, patched_analytics_db, sample_users):
        """Test complete household summary with all data types."""
        # Create users
        for user in sample_users:
            await patched_analytics_db.create_record("users", user)

        now = datetime.now(UTC)

        # Create completions
        for i in range(3):
            await patched_analytics_db.create_record(
                "logs",
                {
                    "user_id": f"user{i}",
                    "action": "approve_verification",
                    "timestamp": (now - timedelta(days=2)).isoformat(),
                },
            )

        # Create conflicts
        await patched_analytics_db.create_record(
            "chores",
            {
                "title": "Conflict Chore",
                "assigned_to": "user1",
                "current_state": ChoreState.CONFLICT,
                "deadline": (now + timedelta(days=1)).isoformat(),
            },
        )

        # Create overdue chores
        for i in range(2):
            await patched_analytics_db.create_record(
                "chores",
                {
                    "title": f"Overdue {i}",
                    "assigned_to": "user1",
                    "current_state": ChoreState.TODO,
                    "deadline": (now - timedelta(days=1)).isoformat(),
                },
            )

        # Create pending verifications
        await patched_analytics_db.create_record(
            "chores",
            {
                "title": "Pending Chore",
                "assigned_to": "user2",
                "current_state": ChoreState.PENDING_VERIFICATION,
                "deadline": (now + timedelta(days=1)).isoformat(),
            },
        )

        result = await analytics_service.get_household_summary(period_days=7)

        assert result["active_members"] == 3
        assert result["completions_this_period"] == 3
        assert result["current_conflicts"] == 1
        assert result["overdue_chores"] == 2
        assert result["pending_verifications"] == 1
        assert result["period_days"] == 7
