"""Unit tests for Redis client retry and fallback functionality."""

from unittest.mock import AsyncMock

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from src.core.redis_client import RedisClient


@pytest.mark.unit
class TestRedisRetryLogic:
    """Tests for Redis retry logic and fallback queue."""

    async def test_delete_with_retry_success_first_attempt(self):
        """Verify delete_with_retry succeeds on first attempt."""
        client = RedisClient()

        # Mock successful Redis client
        client._enabled = True
        client._client = AsyncMock()
        client._client.delete = AsyncMock()

        result = await client.delete_with_retry("key1", "key2")

        assert result is True
        client._client.delete.assert_called_once_with("key1", "key2")

    async def test_delete_with_retry_success_after_retries(self):
        """Verify delete_with_retry succeeds after retries."""
        client = RedisClient()

        # Mock Redis client that fails twice then succeeds
        client._enabled = True
        client._client = AsyncMock()
        client._client.delete = AsyncMock(
            side_effect=[
                RedisConnectionError("First failure"),
                RedisConnectionError("Second failure"),
                None,  # Success on third attempt
            ]
        )

        result = await client.delete_with_retry("key1")

        assert result is True
        assert client._client.delete.call_count == 3

    async def test_delete_with_retry_queues_on_failure(self):
        """Verify delete_with_retry queues keys when all retries fail."""
        client = RedisClient()

        # Mock Redis client that always fails
        client._enabled = True
        client._client = AsyncMock()
        client._client.delete = AsyncMock(side_effect=RedisConnectionError("Always fails"))

        result = await client.delete_with_retry("key1", "key2")

        assert result is False
        # Keys should be in the fallback queue
        assert len(client._invalidation_queue) == 1
        assert client._invalidation_queue[0] == ("key1", "key2")

    async def test_delete_with_retry_queues_when_unavailable(self):
        """Verify delete_with_retry queues keys when Redis unavailable."""
        client = RedisClient()

        # Mock unavailable Redis
        client._enabled = False
        client._client = None

        result = await client.delete_with_retry("key1")

        assert result is False
        # Keys should be in the fallback queue
        assert len(client._invalidation_queue) == 1
        assert client._invalidation_queue[0] == ("key1",)

    async def test_process_invalidation_queue_success(self):
        """Verify queued invalidations are processed when Redis recovers."""
        client = RedisClient()

        # Add items to queue
        client._invalidation_queue.append(("key1", "key2"))
        client._invalidation_queue.append(("key3",))

        # Mock successful Redis client
        client._enabled = True
        client._client = AsyncMock()
        client._client.delete = AsyncMock()

        await client._process_invalidation_queue()

        # Both items should be processed
        assert len(client._invalidation_queue) == 0
        assert client._client.delete.call_count == 2

    async def test_process_invalidation_queue_partial_failure(self):
        """Verify queue processing stops on failure to prevent infinite loop."""
        client = RedisClient()

        # Add items to queue
        client._invalidation_queue.append(("key1",))
        client._invalidation_queue.append(("key2",))

        # Mock Redis that fails on first delete
        client._enabled = True
        client._client = AsyncMock()
        client._client.delete = AsyncMock(side_effect=RedisConnectionError("Failure"))

        await client._process_invalidation_queue()

        # Failed item should be re-queued
        assert len(client._invalidation_queue) == 2
        # Only one delete attempted before stopping
        assert client._client.delete.call_count == 1

    async def test_health_status_tracking(self):
        """Verify health status is tracked correctly."""
        client = RedisClient()

        # Mock successful Redis client
        client._enabled = True
        client._client = AsyncMock()
        client._client.get = AsyncMock(return_value="value")
        client._client.setex = AsyncMock()
        client._client.delete = AsyncMock()

        # Perform operations
        await client.get("key1")
        await client.set("key2", "value", 60)
        await client.delete("key3")

        status = client.get_health_status()

        assert status["enabled"] is True
        assert status["connected"] is True
        assert status["total_operations"] == 3
        assert status["failure_count"] == 0
        assert status["last_successful_operation"] is not None

    async def test_health_status_tracks_failures(self):
        """Verify health status tracks failures."""
        client = RedisClient()

        # Mock Redis that fails
        client._enabled = True
        client._client = AsyncMock()
        client._client.get = AsyncMock(side_effect=RedisConnectionError("Failure"))
        client._client.delete = AsyncMock(side_effect=RedisConnectionError("Failure"))

        # Perform operations that fail
        await client.get("key1")
        await client.delete("key2")

        status = client.get_health_status()

        assert status["total_operations"] == 2
        assert status["failure_count"] == 2

    async def test_fallback_queue_max_size(self):
        """Verify fallback queue respects maxlen limit."""
        client = RedisClient()

        # Mock unavailable Redis
        client._enabled = False
        client._client = None

        # Add more items than maxlen (1000)
        for i in range(1050):
            await client.delete_with_retry(f"key{i}")

        # Queue should not exceed maxlen
        assert len(client._invalidation_queue) == 1000
