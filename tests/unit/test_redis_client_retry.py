"""Unit tests for Redis client replacement."""

import pytest
from src.core.redis_client import RedisClient


@pytest.mark.unit
class TestRedisClient:
    """Tests for Redis client implementation."""

    @pytest.mark.asyncio
    async def test_set_and_get(self):
        client = RedisClient()
        await client.set("key1", "value1", 60)
        value = await client.get("key1")
        assert value == "value1"

    @pytest.mark.asyncio
    async def test_ttl_expiration(self):
        client = RedisClient()
        # Set negative TTL to expire immediately
        await client.set("key1", "value1", -1)
        value = await client.get("key1")
        assert value is None

    @pytest.mark.asyncio
    async def test_delete(self):
        client = RedisClient()
        await client.set("key1", "value1", 60)
        await client.delete("key1")
        value = await client.get("key1")
        assert value is None

    @pytest.mark.asyncio
    async def test_set_if_not_exists(self):
        client = RedisClient()
        assert await client.set_if_not_exists("key1", "value1", 60) is True
        assert await client.set_if_not_exists("key1", "value2", 60) is False
        assert await client.get("key1") == "value1"

    @pytest.mark.asyncio
    async def test_increment(self):
        client = RedisClient()
        val = await client.increment("counter")
        assert val == 1
        val = await client.increment("counter")
        assert val == 2
