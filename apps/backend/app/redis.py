"""Redis abstraction layer for Agent Space.

Provides a typed RedisClient abstraction used exclusively for:
- Cache
- Presence tracking
- Rate limiting
- Ephemeral distributed locks
- Short-lived state

NOTE: Redis is NEVER used as authoritative state for tasks, projects, or users.
PostgreSQL remains the single source of authoritative truth.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any

import structlog

logger = structlog.stdlib.get_logger(__name__)


class RedisLockError(Exception):
    """Raised when acquiring or releasing a Redis ephemeral lock fails."""


class EphemeralLock:
    """Async context manager for an ephemeral Redis lock."""

    def __init__(self, client: RedisClient, name: str, timeout_seconds: int = 10):
        self.client = client
        self.name = name
        self.timeout_seconds = timeout_seconds
        self.token: str | None = None

    async def __aenter__(self) -> EphemeralLock:
        self.token = await self.client.acquire_lock(self.name, self.timeout_seconds)
        if self.token is None:
            raise RedisLockError(f"Could not acquire ephemeral lock for '{self.name}'")
        return self

    async def __aexit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        if self.token is not None:
            await self.client.release_lock(self.name, self.token)


class InMemoryRedisBackend:
    """Thread-safe / asyncio-safe in-memory Redis fallback for testing."""

    def __init__(self) -> None:
        self._store: dict[str, tuple[str, float | None]] = {}
        self._lock = asyncio.Lock()

    def _is_expired(self, key: str) -> bool:
        if key not in self._store:
            return True
        _, expiry = self._store[key]
        if expiry is not None and time.monotonic() > expiry:
            del self._store[key]
            return True
        return False

    async def get(self, key: str) -> str | None:
        async with self._lock:
            if self._is_expired(key):
                return None
            return self._store[key][0]

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        async with self._lock:
            expiry = (time.monotonic() + ex) if ex is not None else None
            self._store[key] = (value, expiry)
            return True

    async def delete(self, key: str) -> bool:
        async with self._lock:
            if key in self._store:
                del self._store[key]
                return True
            return False

    async def exists(self, key: str) -> bool:
        async with self._lock:
            return not self._is_expired(key)

    async def expire(self, key: str, seconds: int) -> bool:
        async with self._lock:
            if self._is_expired(key):
                return False
            val, _ = self._store[key]
            self._store[key] = (val, time.monotonic() + seconds)
            return True

    async def ping(self) -> bool:
        return True

    async def incr(self, key: str) -> int:
        async with self._lock:
            if self._is_expired(key):
                self._store[key] = ("1", None)
                return 1
            val, expiry = self._store[key]
            new_val = int(val) + 1
            self._store[key] = (str(new_val), expiry)
            return new_val


class RedisClient:
    """Redis client abstraction for caching, presence, rate limiting, and ephemeral locks."""

    def __init__(self, url: str = "redis://localhost:6379/0", pool_size: int = 10, timeout: int = 5):
        self.url = url
        self.pool_size = pool_size
        self.timeout = timeout
        self._redis: Any = None
        self._in_memory: InMemoryRedisBackend | None = None
        self._is_in_memory = url.startswith("memory://")

    async def connect(self) -> None:
        """Initialize connection pool to Redis."""
        if self._is_in_memory:
            self._in_memory = InMemoryRedisBackend()
            logger.info("redis_connected_in_memory")
            return

        import redis.asyncio as aioredis

        self._redis = aioredis.from_url(
            self.url,
            max_connections=self.pool_size,
            socket_timeout=self.timeout,
            decode_responses=True,
        )
        logger.info("redis_connecting", url=self.url)

    async def disconnect(self) -> None:
        """Close Redis connection pool."""
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None
        self._in_memory = None
        logger.info("redis_disconnected")

    async def ping(self) -> bool:
        """Verify Redis connectivity."""
        if self._is_in_memory:
            return True
        if self._redis is None:
            await self.connect()
        try:
            async with asyncio.timeout(self.timeout):
                return bool(await self._redis.ping())
        except Exception as exc:
            logger.warning("redis_ping_failed", error=str(exc))
            return False

    async def get(self, key: str) -> str | None:
        """Fetch string value by key."""
        if self._is_in_memory and self._in_memory:
            return await self._in_memory.get(key)
        if self._redis is None:
            await self.connect()
        return await self._redis.get(key)

    async def set(self, key: str, value: str, expire_seconds: int | None = None) -> bool:
        """Set string value with optional expiration TTL in seconds."""
        if self._is_in_memory and self._in_memory:
            return await self._in_memory.set(key, value, ex=expire_seconds)
        if self._redis is None:
            await self.connect()
        res = await self._redis.set(key, value, ex=expire_seconds)
        return bool(res)

    async def delete(self, key: str) -> bool:
        """Delete key from Redis."""
        if self._is_in_memory and self._in_memory:
            return await self._in_memory.delete(key)
        if self._redis is None:
            await self.connect()
        res = await self._redis.delete(key)
        return bool(res > 0)

    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        if self._is_in_memory and self._in_memory:
            return await self._in_memory.exists(key)
        if self._redis is None:
            await self.connect()
        res = await self._redis.exists(key)
        return bool(res > 0)

    async def expire(self, key: str, seconds: int) -> bool:
        """Set TTL on an existing key."""
        if self._is_in_memory and self._in_memory:
            return await self._in_memory.expire(key, seconds)
        if self._redis is None:
            await self.connect()
        res = await self._redis.expire(key, seconds)
        return bool(res)

    # --------------------------------------------------------------------------
    # Presence Tracking
    # --------------------------------------------------------------------------

    async def set_presence(self, entity_id: str, status: str = "online", ttl_seconds: int = 60) -> bool:
        """Record presence heartbeat for an agent or user."""
        key = f"presence:{entity_id}"
        return await self.set(key, status, expire_seconds=ttl_seconds)

    async def get_presence(self, entity_id: str) -> str | None:
        """Get current presence status for an entity, or None if expired/offline."""
        key = f"presence:{entity_id}"
        return await self.get(key)

    async def remove_presence(self, entity_id: str) -> bool:
        """Remove presence for an entity explicitly on disconnect/logout."""
        key = f"presence:{entity_id}"
        return await self.delete(key)

    # --------------------------------------------------------------------------
    # Rate Limiting (Fixed-Window Counter)
    # --------------------------------------------------------------------------

    async def check_rate_limit(
        self,
        key: str,
        limit: int,
        window_seconds: int,
    ) -> tuple[bool, int, int]:
        """Check rate limit for a key.

        Returns:
            (allowed: bool, remaining: int, reset_seconds: int)
        """
        rl_key = f"ratelimit:{key}"
        if self._is_in_memory and self._in_memory:
            count = await self._in_memory.incr(rl_key)
            if count == 1:
                await self._in_memory.expire(rl_key, window_seconds)
            allowed = count <= limit
            remaining = max(0, limit - count)
            return allowed, remaining, window_seconds

        if self._redis is None:
            await self.connect()

        # Atomic pipeline
        pipe = self._redis.pipeline()
        pipe.incr(rl_key)
        pipe.ttl(rl_key)
        results = await pipe.execute()
        count = results[0]
        ttl = results[1]

        if ttl == -1:  # No expiry set yet
            await self._redis.expire(rl_key, window_seconds)
            ttl = window_seconds

        allowed = count <= limit
        remaining = max(0, limit - count)
        reset_seconds = ttl if ttl > 0 else window_seconds
        return allowed, remaining, reset_seconds

    # --------------------------------------------------------------------------
    # Ephemeral Distributed Locks
    # --------------------------------------------------------------------------

    async def acquire_lock(self, name: str, timeout_seconds: int = 10) -> str | None:
        """Acquire an ephemeral lock with a TTL.

        Returns token string if acquired, None if lock is already held.
        """
        token = str(uuid.uuid4())
        key = f"lock:{name}"

        if self._is_in_memory and self._in_memory:
            if await self._in_memory.exists(key):
                return None
            await self._in_memory.set(key, token, ex=timeout_seconds)
            return token

        if self._redis is None:
            await self.connect()

        # NX: Only set if not exists, EX: TTL in seconds
        acquired = await self._redis.set(key, token, ex=timeout_seconds, nx=True)
        if acquired:
            return token
        return None

    async def release_lock(self, name: str, token: str) -> bool:
        """Safely release lock only if the token matches the current holder."""
        key = f"lock:{name}"

        if self._is_in_memory and self._in_memory:
            current = await self._in_memory.get(key)
            if current == token:
                await self._in_memory.delete(key)
                return True
            return False

        if self._redis is None:
            await self.connect()

        # Lua script to ensure release is atomic and token matches
        lua_release = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        res = await self._redis.eval(lua_release, 1, key, token)
        return bool(res == 1)

    def lock(self, name: str, timeout_seconds: int = 10) -> EphemeralLock:
        """Context manager for acquiring and releasing an ephemeral lock."""
        return EphemeralLock(self, name, timeout_seconds)

    # --------------------------------------------------------------------------
    # Health Check
    # --------------------------------------------------------------------------

    async def health_check(self) -> dict[str, Any]:
        """Perform health probe and return latency status."""
        start = time.monotonic()
        try:
            is_ok = await self.ping()
            latency = round((time.monotonic() - start) * 1000, 2)
            if is_ok:
                return {"status": "up", "latency_ms": latency, "error": None}
            return {"status": "down", "latency_ms": None, "error": "Ping failed"}
        except Exception as exc:
            return {"status": "down", "latency_ms": None, "error": str(exc)}


_redis_client: RedisClient | None = None


def get_redis_client() -> RedisClient:
    """Return singleton RedisClient instance configured from application settings."""
    global _redis_client
    if _redis_client is None:
        from app.config import get_settings

        settings = get_settings()
        _redis_client = RedisClient(
            url=settings.redis_url,
            pool_size=settings.redis_pool_size,
            timeout=settings.redis_timeout,
        )
    return _redis_client


def set_redis_client(client: RedisClient | None) -> None:
    """Set global RedisClient instance (useful for test fixtures)."""
    global _redis_client
    _redis_client = client
