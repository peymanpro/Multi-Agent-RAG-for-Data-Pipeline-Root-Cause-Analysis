"""Per-subject rate limiting with an atomic Redis backend for multi-worker deployments."""

from __future__ import annotations

import asyncio
import hashlib
import math
import os
import time
from importlib import import_module
from dataclasses import dataclass
from typing import Any, Protocol


class RateLimitBackendError(RuntimeError):
    """The configured rate-limit backend could not enforce the request budget."""


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    """Outcome of consuming one request from a fixed-window budget."""

    allowed: bool
    limit: int
    remaining: int
    retry_after_seconds: int


class RateLimitStore(Protocol):
    """Storage contract shared by local and distributed rate limiters."""

    is_distributed: bool

    async def consume(
        self,
        identity: str,
        *,
        limit: int,
        window_seconds: int,
    ) -> RateLimitDecision:
        """Atomically consume one request and return remaining budget."""
        ...


class InMemoryRateLimitStore:
    """Process-local fixed-window limiter for development and single-process tests only."""

    is_distributed = False

    def __init__(self, *, clock: Any = time.time) -> None:
        self._clock = clock
        self._counts: dict[tuple[str, int], int] = {}
        self._lock = asyncio.Lock()

    async def consume(
        self,
        identity: str,
        *,
        limit: int,
        window_seconds: int,
    ) -> RateLimitDecision:
        _validate_budget(limit, window_seconds)
        now = self._clock()
        window_id = int(now) // window_seconds
        key = (hashlib.sha256(identity.encode("utf-8")).hexdigest(), window_id)
        async with self._lock:
            self._counts = {
                stored_key: count
                for stored_key, count in self._counts.items()
                if stored_key[1] >= window_id - 1
            }
            count = self._counts.get(key, 0) + 1
            self._counts[key] = count
        retry_after = max(1, math.ceil((window_id + 1) * window_seconds - now))
        return RateLimitDecision(
            allowed=count <= limit,
            limit=limit,
            remaining=max(0, limit - count),
            retry_after_seconds=retry_after,
        )


class _RedisClient(Protocol):
    async def eval(self, script: str, numkeys: int, *keys_and_args: str | int) -> Any:
        """Run a Lua script atomically."""
        ...


class RedisRateLimitStore:
    """Fixed-window limiter using an atomic Lua script shared by every API worker."""

    is_distributed = True

    _SCRIPT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then
  redis.call('PEXPIRE', KEYS[1], ARGV[1])
end
local ttl = redis.call('PTTL', KEYS[1])
return {current, ttl}
"""

    def __init__(self, client: _RedisClient, *, key_prefix: str = "pipeline-rca:rate:v1") -> None:
        self._client = client
        self._key_prefix = key_prefix

    @classmethod
    def from_url(cls, redis_url: str) -> RedisRateLimitStore:
        """Create a Redis-backed store; requires the optional redis package."""
        if not redis_url:
            raise RateLimitBackendError("RCA_RATE_LIMIT_REDIS_URL is empty")
        try:
            redis_async = import_module("redis.asyncio")
        except ImportError as exc:
            raise RateLimitBackendError(
                'Redis rate limiting requires the optional dependency: pip install "pipeline-rca[api-redis]"'
            ) from exc
        try:
            client = redis_async.Redis.from_url(
                redis_url,
                encoding="utf-8",
                decode_responses=False,
            )
        except (TypeError, ValueError) as exc:
            raise RateLimitBackendError("RCA_RATE_LIMIT_REDIS_URL is invalid") from exc
        return cls(client)

    async def consume(
        self,
        identity: str,
        *,
        limit: int,
        window_seconds: int,
    ) -> RateLimitDecision:
        _validate_budget(limit, window_seconds)
        now = time.time()
        window_id = int(now) // window_seconds
        identity_hash = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        key = f"{self._key_prefix}:{identity_hash}:{window_id}"
        try:
            result = await self._client.eval(
                self._SCRIPT,
                1,
                key,
                window_seconds * 1_000,
            )
            count = int(result[0])
            ttl_ms = int(result[1])
        except Exception as exc:
            raise RateLimitBackendError(
                f"Redis rate-limit operation failed ({type(exc).__name__})"
            ) from exc
        retry_after = max(1, math.ceil(max(0, ttl_ms) / 1_000))
        return RateLimitDecision(
            allowed=count <= limit,
            limit=limit,
            remaining=max(0, limit - count),
            retry_after_seconds=retry_after,
        )

    async def close(self) -> None:
        """Close the asynchronous Redis connection pool during application shutdown."""
        close = getattr(self._client, "aclose", None)
        if close is not None:
            await close()


def _validate_budget(limit: int, window_seconds: int) -> None:
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("rate-limit request count must be a positive integer")
    if (
        isinstance(window_seconds, bool)
        or not isinstance(window_seconds, int)
        or window_seconds < 1
    ):
        raise ValueError("rate-limit window must be a positive integer")


def build_rate_limit_store(*, redis_url: str | None, production_mode: bool) -> RateLimitStore:
    """Use Redis when configured; fail closed instead of process-local limiting in production."""
    if redis_url:
        return RedisRateLimitStore.from_url(redis_url)
    if production_mode:
        raise RateLimitBackendError(
            "RCA_RATE_LIMIT_REDIS_URL is required when RCA_DEPLOYMENT_MODE=production"
        )
    return InMemoryRateLimitStore()


def positive_environment_int(name: str, default: int) -> int:
    """Parse a positive integer request-budget setting."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive integer") from exc
    if value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value
