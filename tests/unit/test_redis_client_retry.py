"""Unit tests for in-memory cache client."""

import asyncio

import pytest

from src.core.redis_client import RedisClient


@pytest.mark.unit
class TestRedisClient:
    """Tests for in-memory cache client."""

    async def test_get_set_with_ttl(self):
        """Verify basic get/set operations work correctly with TTL."""
        client = RedisClient()

        await client.set("key1", "value1", ttl_seconds=60)
        result = await client.get("key1")

        assert result == "value1"

    async def test_get_expired_key(self):
        """Verify expired keys return None."""
        client = RedisClient()

        await client.set("key1", "value1", ttl_seconds=1)
        await asyncio.sleep(1.1)
        result = await client.get("key1")

        assert result is None

    async def test_get_nonexistent_key(self):
        """Verify nonexistent keys return None."""
        client = RedisClient()

        result = await client.get("nonexistent")

        assert result is None

    async def test_delete_key(self):
        """Verify delete operation works."""
        client = RedisClient()

        await client.set("key1", "value1", ttl_seconds=60)
        await client.delete("key1")
        result = await client.get("key1")

        assert result is None

    async def test_delete_multiple_keys(self):
        """Verify delete operation works with multiple keys."""
        client = RedisClient()

        await client.set("key1", "value1", ttl_seconds=60)
        await client.set("key2", "value2", ttl_seconds=60)
        await client.delete("key1", "key2")

        assert await client.get("key1") is None
        assert await client.get("key2") is None

    async def test_keys_pattern(self):
        """Verify keys() returns matching keys."""
        client = RedisClient()

        await client.set("leaderboard:user1", "100", ttl_seconds=60)
        await client.set("leaderboard:user2", "200", ttl_seconds=60)
        await client.set("other:key", "value", ttl_seconds=60)

        keys = await client.keys("leaderboard:*")

        assert len(keys) == 2
        assert "leaderboard:user1" in keys
        assert "leaderboard:user2" in keys

    async def test_keys_pattern_with_expired(self):
        """Verify keys() excludes expired keys."""
        client = RedisClient()

        await client.set("leaderboard:user1", "100", ttl_seconds=1)
        await client.set("leaderboard:user2", "200", ttl_seconds=60)
        await asyncio.sleep(1.1)

        keys = await client.keys("leaderboard:*")

        assert len(keys) == 1
        assert "leaderboard:user2" in keys

    async def test_set_if_not_exists_new_key(self):
        """Verify set_if_not_exists creates new key."""
        client = RedisClient()

        result = await client.set_if_not_exists("key1", "value1", ttl_seconds=60)

        assert result is True
        assert await client.get("key1") == "value1"

    async def test_set_if_not_exists_existing_key(self):
        """Verify set_if_not_exists doesn't overwrite existing key."""
        client = RedisClient()

        await client.set("key1", "value1", ttl_seconds=60)
        result = await client.set_if_not_exists("key1", "value2", ttl_seconds=60)

        assert result is False
        assert await client.get("key1") == "value1"

    async def test_set_if_not_exists_expired_key(self):
        """Verify set_if_not_exists overwrites expired key."""
        client = RedisClient()

        await client.set("key1", "value1", ttl_seconds=1)
        await asyncio.sleep(1.1)
        result = await client.set_if_not_exists("key1", "value2", ttl_seconds=60)

        assert result is True
        assert await client.get("key1") == "value2"

    async def test_increment_new_key(self):
        """Verify increment creates new key with value 1."""
        client = RedisClient()

        result = await client.increment("counter1")

        assert result == 1
        assert await client.get("counter1") == "1"

    async def test_increment_existing_key(self):
        """Verify increment increments existing key."""
        client = RedisClient()

        await client.set("counter1", "5", ttl_seconds=60)
        result = await client.increment("counter1")

        assert result == 6
        assert await client.get("counter1") == "6"

    async def test_increment_expired_key(self):
        """Verify increment resets expired key to 1."""
        client = RedisClient()

        await client.set("counter1", "5", ttl_seconds=1)
        await asyncio.sleep(1.1)
        result = await client.increment("counter1")

        assert result == 1
        assert await client.get("counter1") == "1"

    async def test_increment_non_numeric_value(self):
        """Verify increment resets non-numeric value to 1."""
        client = RedisClient()

        await client.set("counter1", "not_a_number", ttl_seconds=60)
        result = await client.increment("counter1")

        assert result == 1
        assert await client.get("counter1") == "1"

    async def test_expire_existing_key(self):
        """Verify expire updates TTL on existing key."""
        client = RedisClient()

        await client.set("key1", "value1", ttl_seconds=1)
        await asyncio.sleep(0.5)
        result = await client.expire("key1", ttl_seconds=60)

        assert result is True
        await asyncio.sleep(0.6)
        assert await client.get("key1") == "value1"

    async def test_expire_expired_key(self):
        """Verify expire returns False for expired key."""
        client = RedisClient()

        await client.set("key1", "value1", ttl_seconds=1)
        await asyncio.sleep(1.1)
        result = await client.expire("key1", ttl_seconds=60)

        assert result is False

    async def test_expire_nonexistent_key(self):
        """Verify expire returns False for nonexistent key."""
        client = RedisClient()

        result = await client.expire("key1", ttl_seconds=60)

        assert result is False

    async def test_health_status(self):
        """Verify health status is tracked correctly."""
        client = RedisClient()

        await client.set("key1", "value1", ttl_seconds=60)
        await client.get("key1")
        await client.delete("key2")

        status = client.get_health_status()

        assert status["enabled"] is True
        assert status["connected"] is True
        assert status["total_operations"] == 3
        assert status["failure_count"] == 0
        assert status["last_successful_operation"] is not None
        assert status["cache_size"] == 1

    async def test_ping(self):
        """Verify ping returns True when available."""
        client = RedisClient()

        result = await client.ping()

        assert result is True

    async def test_close_stops_cleanup_task(self):
        """Verify close stops background cleanup task."""
        client = RedisClient()

        await client.start_cleanup_task()
        assert client._cleanup_task is not None

        await client.close()

        assert client._shutdown_event.is_set()

    async def test_cleanup_task_removes_expired_keys(self):
        """Verify background cleanup task removes expired keys."""
        client = RedisClient()

        await client.set("key1", "value1", ttl_seconds=1)
        await client.set("key2", "value2", ttl_seconds=60)

        await client.start_cleanup_task()
        await asyncio.sleep(1.5)

        keys = await client.keys("*")

        assert len(keys) == 1
        assert "key2" in keys

    async def test_delete_with_retry(self):
        """Verify delete_with_retry works (same as delete for in-memory)."""
        client = RedisClient()

        await client.set("key1", "value1", ttl_seconds=60)
        result = await client.delete_with_retry("key1")

        assert result is True
        assert await client.get("key1") is None
