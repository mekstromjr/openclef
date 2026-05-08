"""Tests for openclef.auth.sessions.

Hits real Redis via the redis_client fixture for revocation tests.
Sign/parse tests are pure-Python and don't need Redis.
"""
from __future__ import annotations

import time
import uuid

import pytest

from openclef.auth.sessions import (
    SessionConfigError,
    is_revoked,
    issue_session,
    parse_session,
    revoke,
)


@pytest.fixture(autouse=True)
def signing_env(monkeypatch):
    monkeypatch.setenv("OPENCLEF_SECRET_KEY", "test-secret-do-not-use-in-prod")
    monkeypatch.setenv("OPENCLEF_ENV", "dev")
    monkeypatch.setenv("OPENCLEF_SESSION_MAX_AGE_DAYS", "30")


def test_issue_then_parse_round_trip():
    user_id = uuid.uuid4()
    cookie, payload = issue_session(user_id)
    parsed = parse_session(cookie)
    assert parsed is not None
    assert parsed.user_id == user_id
    assert parsed.session_id == payload.session_id


def test_parse_rejects_tampered_cookie():
    _, _ = issue_session(uuid.uuid4())
    parsed = parse_session("totally-not-a-valid-cookie")
    assert parsed is None


def test_parse_rejects_wrong_signing_key(monkeypatch):
    cookie, _ = issue_session(uuid.uuid4())
    monkeypatch.setenv("OPENCLEF_SECRET_KEY", "different-secret")
    assert parse_session(cookie) is None


def test_missing_secret_key_outside_dev(monkeypatch):
    monkeypatch.delenv("OPENCLEF_SECRET_KEY", raising=False)
    monkeypatch.setenv("OPENCLEF_ENV", "prod")
    with pytest.raises(SessionConfigError):
        issue_session(uuid.uuid4())


def test_missing_secret_key_allowed_in_dev(monkeypatch):
    monkeypatch.delenv("OPENCLEF_SECRET_KEY", raising=False)
    monkeypatch.setenv("OPENCLEF_ENV", "dev")
    cookie, payload = issue_session(uuid.uuid4())
    parsed = parse_session(cookie)
    assert parsed is not None
    assert parsed.session_id == payload.session_id


async def test_revocation_round_trip(redis_client):
    _, payload = issue_session(uuid.uuid4())
    assert await is_revoked(redis_client, payload.session_id) is False
    await revoke(redis_client, payload.session_id)
    assert await is_revoked(redis_client, payload.session_id) is True


async def test_revocation_ttl_set(redis_client):
    _, payload = issue_session(uuid.uuid4())
    await revoke(redis_client, payload.session_id)
    ttl = await redis_client.ttl(f"revoked:{payload.session_id}")
    # 30-day TTL in seconds = 2_592_000
    assert ttl > 2_500_000
    assert ttl <= 2_592_000
