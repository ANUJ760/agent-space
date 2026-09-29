"""Tests for M25 — Redis Integration.

Validates:
- RedisClient basic operations: get, set, delete, exists, expire
- Redis presence tracking: set_presence, get_presence, remove_presence
- Redis rate limiting: check_rate_limit allows up to limit and rejects exceeding requests
- Redis ephemeral locks: acquire_lock, release_lock, and async context manager
- Health checking: ping and health_check payload structure
"""

import pytest
from app.redis import RedisClient, RedisLockError


@pytest.fixture()
async def redis_client() -> RedisClient:
    """Create in-memory Redis client for testing."""
    client = RedisClient(url="memory://test")
    await client.connect()
    try:
        yield client
    finally:
        await client.disconnect()


class TestRedisClientBasics:
    async def test_set_and_get(self, redis_client: RedisClient) -> None:
        await redis_client.set("foo", "bar")
        val = await redis_client.get("foo")
        assert val == "bar"

    async def test_get_nonexistent(self, redis_client: RedisClient) -> None:
        val = await redis_client.get("nonexistent_key")
        assert val is None

    async def test_delete(self, redis_client: RedisClient) -> None:
        await redis_client.set("to_delete", "val")
        assert await redis_client.exists("to_delete") is True
        deleted = await redis_client.delete("to_delete")
        assert deleted is True
        assert await redis_client.exists("to_delete") is False
        assert await redis_client.get("to_delete") is None

    async def test_expire(self, redis_client: RedisClient) -> None:
        await redis_client.set("temp", "val")
        success = await redis_client.expire("temp", 3600)
        assert success is True

    async def test_ping(self, redis_client: RedisClient) -> None:
        assert await redis_client.ping() is True

    async def test_health_check(self, redis_client: RedisClient) -> None:
        health = await redis_client.health_check()
        assert health["status"] == "up"
        assert isinstance(health["latency_ms"], float)
        assert health["error"] is None


class TestRedisPresence:
    async def test_presence_lifecycle(self, redis_client: RedisClient) -> None:
        agent_id = "agent-123"

        # Initially offline
        status = await redis_client.get_presence(agent_id)
        assert status is None

        # Set online
        await redis_client.set_presence(agent_id, status="busy", ttl_seconds=120)
        status = await redis_client.get_presence(agent_id)
        assert status == "busy"

        # Explicit disconnect
        await redis_client.remove_presence(agent_id)
        status = await redis_client.get_presence(agent_id)
        assert status is None


class TestRedisRateLimiting:
    async def test_rate_limiting(self, redis_client: RedisClient) -> None:
        key = "client-ip-127.0.0.1"
        limit = 3

        # First 3 requests allowed
        for i in range(1, 4):
            allowed, remaining, _ = await redis_client.check_rate_limit(key, limit=limit, window_seconds=60)
            assert allowed is True
            assert remaining == limit - i

        # 4th request rejected
        allowed, remaining, _ = await redis_client.check_rate_limit(key, limit=limit, window_seconds=60)
        assert allowed is False
        assert remaining == 0


class TestRedisEphemeralLocks:
    async def test_lock_acquire_and_release(self, redis_client: RedisClient) -> None:
        lock_name = "task-sync-123"

        # Worker 1 acquires lock
        token1 = await redis_client.acquire_lock(lock_name, timeout_seconds=30)
        assert token1 is not None

        # Worker 2 attempts to acquire same lock — should fail
        token2 = await redis_client.acquire_lock(lock_name, timeout_seconds=30)
        assert token2 is None

        # Worker 2 attempts release with wrong token — fails
        released = await redis_client.release_lock(lock_name, "wrong-token")
        assert released is False

        # Worker 1 releases lock
        released = await redis_client.release_lock(lock_name, token1)
        assert released is True

        # Now Worker 2 can acquire
        token3 = await redis_client.acquire_lock(lock_name, timeout_seconds=30)
        assert token3 is not None
        await redis_client.release_lock(lock_name, token3)

    async def test_lock_context_manager(self, redis_client: RedisClient) -> None:
        lock_name = "resource-abc"

        async with redis_client.lock(lock_name, timeout_seconds=10):
            # Inside context, lock is held
            token_second = await redis_client.acquire_lock(lock_name)
            assert token_second is None

        # Outside context, lock is automatically released
        token_after = await redis_client.acquire_lock(lock_name)
        assert token_after is not None
        await redis_client.release_lock(lock_name, token_after)

    async def test_lock_context_manager_contention_raises(self, redis_client: RedisClient) -> None:
        lock_name = "contested-lock"
        tok = await redis_client.acquire_lock(lock_name, timeout_seconds=60)
        assert tok is not None

        with pytest.raises(RedisLockError):
            async with redis_client.lock(lock_name, timeout_seconds=5):
                pass

        await redis_client.release_lock(lock_name, tok)
