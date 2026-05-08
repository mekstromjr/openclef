"""Tests for openclef.auth.ratelimit.

Verifies the Lua token-bucket script against real Redis. The
synthetic `now_seconds` parameter lets tests advance "time" without
sleeping or mocking.
"""
from __future__ import annotations

import pytest

from openclef.auth.ratelimit import check_and_consume, reset


@pytest.fixture(autouse=True)
def reasonable_defaults(monkeypatch):
    # 5 tokens, 60s refill — fast for tests
    monkeypatch.setenv("OPENCLEF_LOGIN_RATE_LIMIT_MAX", "5")
    monkeypatch.setenv("OPENCLEF_LOGIN_RATE_LIMIT_REFILL_SECONDS", "60")


async def test_allows_up_to_max_then_blocks(redis_client):
    user = "alice"
    now = 1_000_000
    for i in range(5):
        result = await check_and_consume(
            redis_client, "login", user, now_seconds=now
        )
        assert result.allowed is True, f"attempt {i+1} should be allowed"
        assert result.tokens_remaining == 4 - i

    # 6th attempt is blocked
    blocked = await check_and_consume(redis_client, "login", user, now_seconds=now)
    assert blocked.allowed is False
    assert blocked.tokens_remaining == 0
    assert 0 < blocked.retry_after_seconds <= 60


async def test_refills_after_interval(redis_client):
    user = "bob"
    # Drain the bucket
    for _ in range(5):
        await check_and_consume(redis_client, "login", user, now_seconds=1_000_000)

    # 60s later: one token refilled, one attempt allowed
    result = await check_and_consume(
        redis_client, "login", user, now_seconds=1_000_060
    )
    assert result.allowed is True
    assert result.tokens_remaining == 0  # Just consumed the refilled one

    # Next attempt at the same instant is blocked again
    blocked = await check_and_consume(
        redis_client, "login", user, now_seconds=1_000_060
    )
    assert blocked.allowed is False


async def test_buckets_are_per_username(redis_client):
    # Drain alice's bucket
    for _ in range(5):
        await check_and_consume(
            redis_client, "login", "alice", now_seconds=1_000_000
        )
    # Bob is unaffected
    result = await check_and_consume(
        redis_client, "login", "bob", now_seconds=1_000_000
    )
    assert result.allowed is True
    assert result.tokens_remaining == 4


async def test_reset_restores_full_bucket(redis_client):
    user = "carol"
    for _ in range(5):
        await check_and_consume(redis_client, "login", user, now_seconds=1_000_000)
    await reset(redis_client, "login", user)
    result = await check_and_consume(
        redis_client, "login", user, now_seconds=1_000_000
    )
    assert result.allowed is True
    assert result.tokens_remaining == 4
