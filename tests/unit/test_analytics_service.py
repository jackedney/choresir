"""Unit tests for analytics_service module."""

import json
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

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

    return in_memory_db


@pytest.fixture
def mock_redis():
    """Mock Redis client for testing."""
    with patch("src.services.analytics_service.redis_client") as mock:
        # Default behavior: cache miss
        mock.get = AsyncMock(return_value=None)
        mock.set = AsyncMock()
        yield mock


@pytest.fixture
async def sample_users(patched_analytics_db):
    """Create sample users for testing."""
    user1 = await patched_analytics_db.create_record(
        collection="users",
        data={
            "name": "Alice",
            "phone": "+1234567890",
            "status": "active",
        },
    )
    user2 = await patched_analytics_db.create_record(
        collection="users",
        data={
            "name": "Bob",
            "phone": "+1234567891",
            "status": "active",
        },
    )
    user3 = await patched_analytics_db.create_record(
        collection="users",
        data={
            "name": "Charlie",
            "phone": "+1234567892",
            "status": "active",
        },
    )
    return [user1, user2, user3]


@pytest.fixture
async def sample_completion_logs(patched_analytics_db, sample_users):
    """Create sample completion logs for testing."""
    now = datetime.now(UTC)
    logs = []

    # Alice: 5 completions
    for i in range(5):
        log = await patched_analytics_db.create_record(
            collection="logs",
            data={
                "user_id": sample_users[0]["id"],
                "action": "approve_verification",
                "timestamp": (now - timedelta(days=i)).isoformat(),
                "chore_id": f"chore_{i}",
            },
        )
        logs.append(log)

    # Bob: 3 completions
    for i in range(3):
        log = await patched_analytics_db.create_record(
            collection="logs",
            data={
                "user_id": sample_users[1]["id"],
                "action": "approve_verification",
                "timestamp": (now - timedelta(days=i)).isoformat(),
                "chore_id": f"chore_{i + 10}",
            },
        )
        logs.append(log)

    # Charlie: 1 completion
    log = await patched_analytics_db.create_record(
        collection="logs",
        data={
            "user_id": sample_users[2]["id"],
            "action": "approve_verification",
            "timestamp": now.isoformat(),
            "chore_id": "chore_20",
        },
    )
    logs.append(log)

    return logs


@pytest.mark.unit
class TestGetLeaderboardCaching:
    """Tests for get_leaderboard Redis caching behavior."""

    async def test_leaderboard_cache_miss(self, patched_analytics_db, mock_redis, sample_users, sample_completion_logs):
        """First call fetches from DB and stores in cache."""
        # Mock cache miss
        mock_redis.get.return_value = None

        result = await analytics_service.get_leaderboard(period_days=30)

        # Verify result
        assert len(result) == 3
        assert result[0].user_name == "Alice"
        assert result[0].completion_count == 5
        assert result[1].user_name == "Bob"
        assert result[1].completion_count == 3
        assert result[2].user_name == "Charlie"
        assert result[2].completion_count == 1

        # Verify cache was checked
        mock_redis.get.assert_called_once_with("choresir:leaderboard:30")

        # Verify cache was updated
        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        assert call_args[0][0] == "choresir:leaderboard:30"  # cache key
        cached_data = json.loads(call_args[0][1])
        assert len(cached_data) == 3
        assert call_args[0][2] == 60  # TTL in seconds (reduced from 300)

    async def test_leaderboard_cache_hit(self, patched_analytics_db, mock_redis, sample_users):
        """Second call within TTL returns cached data without DB query."""
        # Mock cache hit with pre-existing data
        cached_leaderboard = [
            {"user_id": "user1", "user_name": "Alice", "completion_count": 10},
            {"user_id": "user2", "user_name": "Bob", "completion_count": 5},
        ]
        mock_redis.get.return_value = json.dumps(cached_leaderboard)

        result = await analytics_service.get_leaderboard(period_days=30)

        # Verify cached data was returned as models
        assert len(result) == 2
        assert result[0].user_id == "user1"
        assert result[0].user_name == "Alice"
        assert result[0].completion_count == 10
        assert result[1].user_id == "user2"
        assert result[1].user_name == "Bob"
        assert result[1].completion_count == 5

        # Verify cache was checked
        mock_redis.get.assert_called_once_with("choresir:leaderboard:30")

        # Verify cache was NOT updated (we got a hit)
        mock_redis.set.assert_not_called()

    async def test_leaderboard_cache_different_periods(
        self, patched_analytics_db, mock_redis, sample_users, sample_completion_logs
    ):
        """Different period_days use different cache keys."""
        mock_redis.get.return_value = None

        # Call with different periods
        await analytics_service.get_leaderboard(period_days=7)
        await analytics_service.get_leaderboard(period_days=30)

        # Verify different cache keys were used
        assert mock_redis.get.call_count == 2
        cache_keys = [call[0][0] for call in mock_redis.get.call_args_list]
        assert "choresir:leaderboard:7" in cache_keys
        assert "choresir:leaderboard:30" in cache_keys

    async def test_leaderboard_cache_corrupted_data(
        self, patched_analytics_db, mock_redis, sample_users, sample_completion_logs
    ):
        """Corrupted cache data falls back to DB query."""
        # Mock cache with invalid JSON
        mock_redis.get.return_value = "invalid json {{"

        result = await analytics_service.get_leaderboard(period_days=30)

        # Verify DB was queried and result is correct
        assert len(result) == 3
        assert result[0].user_name == "Alice"

        # Verify cache was regenerated
        mock_redis.set.assert_called_once()


@pytest.mark.unit
class TestGetLeaderboardRedisUnavailability:
    """Tests for get_leaderboard when Redis is unavailable."""

    async def test_leaderboard_redis_connection_error(
        self, patched_analytics_db, mock_redis, sample_users, sample_completion_logs
    ):
        """Redis connection error falls back to DB query gracefully."""
        # Mock Redis connection error
        mock_redis.get.side_effect = ConnectionError("Redis unavailable")

        result = await analytics_service.get_leaderboard(period_days=30)

        # Verify function still works and returns correct data
        assert len(result) == 3
        assert result[0].user_name == "Alice"
        assert result[0].completion_count == 5

        # Cache update should not be attempted since Redis is down
        # (the exception will be caught during set operation too)

    async def test_leaderboard_redis_cache_write_fails(
        self, patched_analytics_db, mock_redis, sample_users, sample_completion_logs
    ):
        """Cache write failure doesn't break the function."""
        # Mock cache miss
        mock_redis.get.return_value = None
        # Mock cache write failure
        mock_redis.set.side_effect = ConnectionError("Redis write failed")

        result = await analytics_service.get_leaderboard(period_days=30)

        # Verify function still returns correct data
        assert len(result) == 3
        assert result[0].user_name == "Alice"


@pytest.mark.unit
class TestGetLeaderboardBulkFetch:
    """Tests for get_leaderboard bulk user fetch optimization."""

    async def test_leaderboard_bulk_user_fetch(
        self, patched_analytics_db, mock_redis, sample_users, sample_completion_logs
    ):
        """Verify users are fetched in bulk, not individually."""
        mock_redis.get.return_value = None

        # Track list_records calls
        list_records_calls = []
        original_list_records = patched_analytics_db.list_records

        async def track_list_records(collection, **kwargs):
            list_records_calls.append(collection)
            return await original_list_records(collection, **kwargs)

        # Patch the db_client module function that analytics_service uses
        with patch("src.services.analytics_service.db_client.list_records", track_list_records):
            result = await analytics_service.get_leaderboard(period_days=30)

        # Verify users collection was queried exactly once (bulk fetch)
        users_queries = [c for c in list_records_calls if c == "users"]
        assert len(users_queries) == 1

        # Verify result is correct
        assert len(result) == 3

    async def test_leaderboard_missing_user(self, patched_analytics_db, mock_redis, sample_users):
        """User in completion logs but not in users table is handled gracefully."""
        mock_redis.get.return_value = None

        # Create completion log for non-existent user
        await patched_analytics_db.create_record(
            collection="logs",
            data={
                "user_id": "nonexistent_user",
                "action": "approve_verification",
                "timestamp": datetime.now(UTC).isoformat(),
                "chore_id": "chore_99",
            },
        )

        result = await analytics_service.get_leaderboard(period_days=30)

        # Verify missing user is skipped and logged, but doesn't break the function
        # Result should only include existing users
        user_ids = [entry.user_id for entry in result]
        assert "nonexistent_user" not in user_ids

    async def test_leaderboard_empty(self, patched_analytics_db, mock_redis, sample_users):
        """Empty leaderboard (no completions) works correctly."""
        mock_redis.get.return_value = None

        # No completion logs created
        result = await analytics_service.get_leaderboard(period_days=30)

        # Verify empty list is returned
        assert result == []

        # Verify cache was still updated with empty list
        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        cached_data = json.loads(call_args[0][1])
        assert cached_data == []


@pytest.mark.unit
class TestGetLeaderboardEdgeCases:
    """Tests for edge cases in get_leaderboard."""

    async def test_leaderboard_single_user(self, patched_analytics_db, mock_redis, sample_users):
        """Leaderboard with only one user works correctly."""
        mock_redis.get.return_value = None

        # Create completion log for only one user
        await patched_analytics_db.create_record(
            collection="logs",
            data={
                "user_id": sample_users[0]["id"],
                "action": "approve_verification",
                "timestamp": datetime.now(UTC).isoformat(),
                "chore_id": "chore_1",
            },
        )

        result = await analytics_service.get_leaderboard(period_days=30)

        assert len(result) == 1
        assert result[0].user_name == "Alice"
        assert result[0].completion_count == 1

    async def test_leaderboard_tied_users(self, patched_analytics_db, mock_redis, sample_users):
        """Users with same completion count are handled correctly."""
        mock_redis.get.return_value = None

        now = datetime.now(UTC)

        # Alice: 3 completions
        for i in range(3):
            await patched_analytics_db.create_record(
                collection="logs",
                data={
                    "user_id": sample_users[0]["id"],
                    "action": "approve_verification",
                    "timestamp": (now - timedelta(days=i)).isoformat(),
                    "chore_id": f"chore_a_{i}",
                },
            )

        # Bob: 3 completions (tied with Alice)
        for i in range(3):
            await patched_analytics_db.create_record(
                collection="logs",
                data={
                    "user_id": sample_users[1]["id"],
                    "action": "approve_verification",
                    "timestamp": (now - timedelta(days=i)).isoformat(),
                    "chore_id": f"chore_b_{i}",
                },
            )

        result = await analytics_service.get_leaderboard(period_days=30)

        # Both users should be in result with same count
        assert len(result) == 2
        assert result[0].completion_count == 3
        assert result[1].completion_count == 3

    async def test_leaderboard_period_filtering(self, patched_analytics_db, mock_redis, sample_users):
        """Leaderboard correctly filters by period_days."""
        mock_redis.get.return_value = None

        now = datetime.now(UTC)

        # Create old completion (outside 7-day period)
        await patched_analytics_db.create_record(
            collection="logs",
            data={
                "user_id": sample_users[0]["id"],
                "action": "approve_verification",
                "timestamp": (now - timedelta(days=10)).isoformat(),
                "chore_id": "old_chore",
            },
        )

        # Create recent completion (within 7-day period)
        await patched_analytics_db.create_record(
            collection="logs",
            data={
                "user_id": sample_users[1]["id"],
                "action": "approve_verification",
                "timestamp": (now - timedelta(days=2)).isoformat(),
                "chore_id": "recent_chore",
            },
        )

        result = await analytics_service.get_leaderboard(period_days=7)

        # Only recent completion should be counted
        assert len(result) == 1
        assert result[0].user_name == "Bob"
        assert result[0].completion_count == 1

    async def test_leaderboard_multiple_completions_same_user(self, patched_analytics_db, mock_redis, sample_users):
        """Multiple completions by same user are counted correctly."""
        mock_redis.get.return_value = None

        now = datetime.now(UTC)

        # Create 10 completions for Alice
        for i in range(10):
            await patched_analytics_db.create_record(
                collection="logs",
                data={
                    "user_id": sample_users[0]["id"],
                    "action": "approve_verification",
                    "timestamp": (now - timedelta(hours=i)).isoformat(),
                    "chore_id": f"chore_{i}",
                },
            )

        result = await analytics_service.get_leaderboard(period_days=30)

        assert len(result) == 1
        assert result[0].user_name == "Alice"
        assert result[0].completion_count == 10


@pytest.mark.unit
class TestGetUserStatistics:
    """Tests for get_user_statistics function."""

    async def test_get_user_statistics_with_leaderboard_rank(
        self, patched_analytics_db, mock_redis, sample_users, sample_completion_logs
    ):
        """User statistics include correct rank from leaderboard."""
        mock_redis.get.return_value = None

        result = await analytics_service.get_user_statistics(user_id=sample_users[0]["id"], period_days=30)

        assert result.user_id == sample_users[0]["id"]
        assert result.user_name == "Alice"
        assert result.completions == 5
        assert result.rank == 1  # Alice is first with 5 completions

    async def test_get_user_statistics_no_completions(self, patched_analytics_db, mock_redis, sample_users):
        """User with no completions has None rank and 0 completions."""
        mock_redis.get.return_value = None

        # Create a user with no completions
        new_user = await patched_analytics_db.create_record(
            collection="users",
            data={
                "name": "NewUser",
                "phone": "+9999999999",
                "status": "active",
            },
        )

        result = await analytics_service.get_user_statistics(user_id=new_user["id"], period_days=30)

        assert result.user_id == new_user["id"]
        assert result.user_name == "NewUser"
        assert result.completions == 0
        assert result.rank is None


@pytest.mark.unit
class TestGetLeaderboardIntegration:
    """Integration tests for get_leaderboard with realistic scenarios."""

    async def test_leaderboard_end_to_end_no_cache(
        self, patched_analytics_db, mock_redis, sample_users, sample_completion_logs
    ):
        """Full flow: cache miss -> DB query -> cache update -> verify result."""
        mock_redis.get.return_value = None

        result = await analytics_service.get_leaderboard(period_days=30)

        # Verify complete result
        assert len(result) == 3
        # Verify result is a LeaderboardEntry model with expected fields
        assert hasattr(result[0], "user_id")
        assert hasattr(result[0], "user_name")
        assert hasattr(result[0], "completion_count")

        # Verify ordering (descending by count)
        assert result[0].completion_count >= result[1].completion_count
        assert result[1].completion_count >= result[2].completion_count

        # Verify cache operations
        mock_redis.get.assert_called_once()
        mock_redis.set.assert_called_once()

    async def test_leaderboard_end_to_end_with_cache(self, patched_analytics_db, mock_redis):
        """Full flow: cache hit -> return cached data -> no DB query."""
        cached_data = [
            {"user_id": "u1", "user_name": "User1", "completion_count": 100},
        ]
        mock_redis.get.return_value = json.dumps(cached_data)

        result = await analytics_service.get_leaderboard(period_days=30)

        # Verify cached data was returned as models
        assert len(result) == 1
        assert result[0].user_id == "u1"
        assert result[0].user_name == "User1"
        assert result[0].completion_count == 100

        # Verify no cache update
        mock_redis.set.assert_not_called()


@pytest.mark.unit
class TestInvalidateLeaderboardCache:
    """Tests for invalidate_leaderboard_cache function."""

    async def test_invalidate_cache_deletes_all_keys(self, mock_redis):
        """Verify all leaderboard cache keys are deleted with retry logic."""
        # Mock Redis keys() to return multiple leaderboard keys
        mock_redis.keys = AsyncMock(
            return_value=["choresir:leaderboard:7", "choresir:leaderboard:30", "choresir:leaderboard:90"]
        )
        mock_redis.delete_with_retry = AsyncMock(return_value=True)

        await analytics_service.invalidate_leaderboard_cache()

        # Verify pattern was used to find keys
        mock_redis.keys.assert_called_once_with("choresir:leaderboard:*")

        # Verify all keys were deleted with retry in one call
        mock_redis.delete_with_retry.assert_called_once_with(
            "choresir:leaderboard:7", "choresir:leaderboard:30", "choresir:leaderboard:90"
        )

    async def test_invalidate_cache_no_keys_found(self, mock_redis):
        """No-op when no leaderboard cache keys exist."""
        # Mock Redis keys() to return empty list
        mock_redis.keys = AsyncMock(return_value=[])
        mock_redis.delete_with_retry = AsyncMock()

        await analytics_service.invalidate_leaderboard_cache()

        # Verify keys() was called
        mock_redis.keys.assert_called_once_with("choresir:leaderboard:*")

        # Verify delete_with_retry was NOT called (no keys to delete)
        mock_redis.delete_with_retry.assert_not_called()

    async def test_invalidate_cache_redis_unavailable(self, mock_redis):
        """Gracefully handles Redis connection errors."""
        # Mock Redis keys() to raise connection error
        mock_redis.keys = AsyncMock(side_effect=ConnectionError("Redis unavailable"))

        # Should not raise exception
        await analytics_service.invalidate_leaderboard_cache()

        # Function should complete without error

    async def test_invalidate_cache_delete_fails(self, mock_redis):
        """Gracefully handles Redis delete errors (queues for retry)."""
        # Mock Redis keys() to return keys, but delete_with_retry() fails
        mock_redis.keys = AsyncMock(return_value=["choresir:leaderboard:7", "choresir:leaderboard:30"])
        mock_redis.delete_with_retry = AsyncMock(return_value=False)  # Returns False on failure

        # Should not raise exception
        await analytics_service.invalidate_leaderboard_cache()

        # Keys should have been found
        mock_redis.keys.assert_called_once()
        # Delete with retry should have been attempted
        mock_redis.delete_with_retry.assert_called_once()

    async def test_invalidate_cache_single_key(self, mock_redis):
        """Works correctly with a single cache key."""
        # Mock Redis keys() to return single key
        mock_redis.keys = AsyncMock(return_value=["choresir:leaderboard:30"])
        mock_redis.delete_with_retry = AsyncMock(return_value=True)

        await analytics_service.invalidate_leaderboard_cache()

        # Verify single key was deleted with retry
        mock_redis.delete_with_retry.assert_called_once_with("choresir:leaderboard:30")
