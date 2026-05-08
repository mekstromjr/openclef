"""Per-username login rate limit.

Token bucket: bucket holds up to `max_tokens`, refills at 1 token per
`refill_seconds`. Each failed login attempt decrements one token; when
the bucket hits 0, further attempts are rejected until refill.

Implemented as a single Redis Lua script so check + decrement is
atomic — without that, two simultaneous failed logins for the same
user could each see "5 tokens left" and both succeed.

Successful login *does not* refill the bucket — the bucket exists to
slow down brute-force, not to reward correct guesses.
"""
from __future__ import annotations

from dataclasses import dataclass

from redis.asyncio import Redis

from openclef.config import get_settings


# KEYS[1] = bucket key, ARGV[1] = max tokens, ARGV[2] = refill seconds, ARGV[3] = now (unix seconds).
# Returns: {tokens_remaining, retry_after_seconds_or_zero}.
_LUA_TOKEN_BUCKET = """
local bucket_key = KEYS[1]
local max_tokens = tonumber(ARGV[1])
local refill_seconds = tonumber(ARGV[2])
local now = tonumber(ARGV[3])

local data = redis.call("HMGET", bucket_key, "tokens", "last_refill")
local tokens = tonumber(data[1])
local last_refill = tonumber(data[2])

if tokens == nil then
    tokens = max_tokens
    last_refill = now
end

local elapsed = now - last_refill
if elapsed > 0 then
    local refilled = math.floor(elapsed / refill_seconds)
    if refilled > 0 then
        tokens = math.min(max_tokens, tokens + refilled)
        last_refill = last_refill + (refilled * refill_seconds)
    end
end

if tokens > 0 then
    tokens = tokens - 1
    redis.call("HSET", bucket_key, "tokens", tokens, "last_refill", last_refill)
    redis.call("EXPIRE", bucket_key, refill_seconds * (max_tokens + 1))
    return {tokens, 0}
else
    local retry_after = refill_seconds - (now - last_refill)
    return {0, retry_after}
end
"""


@dataclass
class RateLimitResult:
    allowed: bool
    tokens_remaining: int
    retry_after_seconds: int


def _bucket_key(scope: str, identity: str) -> str:
    return f"ratelimit:{scope}:{identity}"


async def check_and_consume(
    redis: Redis,
    scope: str,
    identity: str,
    *,
    max_tokens: int | None = None,
    refill_seconds: int | None = None,
    now_seconds: int | None = None,
) -> RateLimitResult:
    """Atomic check-and-consume. `allowed=False` means the caller is
    rate-limited; the returned `retry_after_seconds` is the time until
    the bucket gains its next token.
    """
    s = get_settings()
    max_tokens = max_tokens if max_tokens is not None else s.login_rate_limit_max
    refill_seconds = (
        refill_seconds if refill_seconds is not None else s.login_rate_limit_refill_seconds
    )
    if now_seconds is None:
        import time

        now_seconds = int(time.time())

    raw = await redis.eval(
        _LUA_TOKEN_BUCKET,
        1,
        _bucket_key(scope, identity),
        max_tokens,
        refill_seconds,
        now_seconds,
    )
    tokens, retry_after = int(raw[0]), int(raw[1])
    return RateLimitResult(
        allowed=retry_after == 0,
        tokens_remaining=tokens,
        retry_after_seconds=retry_after,
    )


async def reset(redis: Redis, scope: str, identity: str) -> None:
    """Wipe a bucket — used by admin tools and tests, not by normal flow."""
    await redis.delete(_bucket_key(scope, identity))
