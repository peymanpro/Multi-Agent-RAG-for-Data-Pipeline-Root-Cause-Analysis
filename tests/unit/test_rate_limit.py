"""Unit tests for local and Redis-backed rate limiting contracts."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from pipeline_rca.api.rate_limit import (
    InMemoryRateLimitStore,
    RateLimitBackendError,
    RedisRateLimitStore,
    build_rate_limit_store,
)


class FakeRedis:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int, tuple[str | int, ...]]] = []
        self.count = 0

    async def eval(self, script: str, numkeys: int, *keys_and_args: str | int) -> Any:
        self.calls.append((script, numkeys, keys_and_args))
        self.count += 1
        return [self.count, 45_000]


def test_in_memory_limiter_enforces_a_fixed_window() -> None:
    async def scenario() -> None:
        now = [120.0]
        store = InMemoryRateLimitStore(clock=lambda: now[0])

        first = await store.consume("subject:alice", limit=2, window_seconds=60)
        second = await store.consume("subject:alice", limit=2, window_seconds=60)
        third = await store.consume("subject:alice", limit=2, window_seconds=60)

        assert first.allowed is True
        assert second.allowed is True
        assert third.allowed is False
        assert third.remaining == 0
        assert third.retry_after_seconds == 60

        now[0] = 180.0
        reset = await store.consume("subject:alice", limit=2, window_seconds=60)
        assert reset.allowed is True
        assert reset.remaining == 1

    asyncio.run(scenario())


def test_redis_limiter_uses_atomic_script_and_hashed_identity() -> None:
    async def scenario() -> None:
        client = FakeRedis()
        store = RedisRateLimitStore(client)

        first = await store.consume("subject:private-user", limit=1, window_seconds=60)
        second = await store.consume("subject:private-user", limit=1, window_seconds=60)

        assert first.allowed is True
        assert second.allowed is False
        assert len(client.calls) == 2
        script, numkeys, args = client.calls[0]
        assert "INCR" in script and "PEXPIRE" in script
        assert numkeys == 1
        assert "private-user" not in str(args[0])
        assert len(str(args[0]).split(":")[-2]) == 64
        assert args[1] == 60_000
        assert second.retry_after_seconds == 45

    asyncio.run(scenario())


def test_production_mode_requires_distributed_rate_limit_backend() -> None:
    with pytest.raises(RateLimitBackendError, match="required"):
        build_rate_limit_store(redis_url=None, production_mode=True)


def test_development_mode_can_use_process_local_rate_limiter() -> None:
    store = build_rate_limit_store(redis_url=None, production_mode=False)

    assert isinstance(store, InMemoryRateLimitStore)
    assert store.is_distributed is False
