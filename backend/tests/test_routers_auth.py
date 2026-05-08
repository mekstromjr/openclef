"""End-to-end auth router tests.

Drives the FastAPI app via httpx ASGITransport against the test
Postgres + Redis containers. Covers the login → cookie → authed
request → logout cycle, rate limiting, and the setup wizard flow.
"""
from __future__ import annotations

from openclef.auth.hashing import hash_password
from openclef.models.enums import UserRole
from openclef.models.user import User


async def _seed_user(session, *, username="alice", password="hunter2hunter2", role=UserRole.USER):
    user = User(
        username=username,
        password_hash=hash_password(password),
        role=role,
    )
    session.add(user)
    await session.commit()
    return user


# --- /auth/login + /auth/me + /auth/logout ----------------------------


async def test_login_round_trip(app_kit):
    async with app_kit.sessionmaker() as s:
        await _seed_user(s, username="alice", password="hunter2hunter2")

    r = await app_kit.client.post(
        "/api/v1/auth/login",
        json={"username": "alice", "password": "hunter2hunter2"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["username"] == "alice"
    assert "openclef_session" in r.cookies

    me = await app_kit.client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json()["username"] == "alice"


async def test_login_rejects_wrong_password(app_kit):
    async with app_kit.sessionmaker() as s:
        await _seed_user(s, username="bob", password="correctpassword")
    r = await app_kit.client.post(
        "/api/v1/auth/login",
        json={"username": "bob", "password": "WRONG"},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid_credentials"


async def test_login_unknown_user_uses_same_response(app_kit):
    r = await app_kit.client.post(
        "/api/v1/auth/login",
        json={"username": "ghost", "password": "anything"},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid_credentials"


async def test_me_requires_session(app_kit):
    r = await app_kit.client.get("/api/v1/auth/me")
    assert r.status_code == 401


async def test_logout_revokes_session(app_kit):
    async with app_kit.sessionmaker() as s:
        await _seed_user(s, username="carol", password="hunter2hunter2")
    await app_kit.client.post(
        "/api/v1/auth/login",
        json={"username": "carol", "password": "hunter2hunter2"},
    )
    assert (await app_kit.client.get("/api/v1/auth/me")).status_code == 200

    r = await app_kit.client.post("/api/v1/auth/logout")
    assert r.status_code == 204

    me = await app_kit.client.get("/api/v1/auth/me")
    assert me.status_code == 401


async def test_logout_idempotent_with_no_session(app_kit):
    r = await app_kit.client.post("/api/v1/auth/logout")
    assert r.status_code == 204


async def test_login_rate_limited_after_n_failures(app_kit, monkeypatch):
    monkeypatch.setenv("OPENCLEF_LOGIN_RATE_LIMIT_MAX", "3")
    async with app_kit.sessionmaker() as s:
        await _seed_user(s, username="dave", password="hunter2hunter2")

    for _ in range(3):
        r = await app_kit.client.post(
            "/api/v1/auth/login",
            json={"username": "dave", "password": "WRONG"},
        )
        assert r.status_code == 401

    r = await app_kit.client.post(
        "/api/v1/auth/login",
        json={"username": "dave", "password": "WRONG"},
    )
    assert r.status_code == 429
    detail = r.json()["detail"]
    assert detail["error"] == "rate_limited"
    assert detail["retry_after_seconds"] > 0
    assert "Retry-After" in r.headers


async def test_successful_login_clears_rate_limit(app_kit, monkeypatch):
    monkeypatch.setenv("OPENCLEF_LOGIN_RATE_LIMIT_MAX", "3")
    async with app_kit.sessionmaker() as s:
        await _seed_user(s, username="erin", password="hunter2hunter2")

    # Two failures consume 2 tokens
    for _ in range(2):
        r = await app_kit.client.post(
            "/api/v1/auth/login",
            json={"username": "erin", "password": "WRONG"},
        )
        assert r.status_code == 401

    # Successful login resets the bucket
    r = await app_kit.client.post(
        "/api/v1/auth/login",
        json={"username": "erin", "password": "hunter2hunter2"},
    )
    assert r.status_code == 200

    # User can now fail 3 more times before being rate-limited
    await app_kit.client.post("/api/v1/auth/logout")
    for _ in range(3):
        r = await app_kit.client.post(
            "/api/v1/auth/login",
            json={"username": "erin", "password": "WRONG"},
        )
        assert r.status_code == 401


# --- /setup ------------------------------------------------------------


async def test_setup_status_when_empty(app_kit):
    r = await app_kit.client.get("/api/v1/setup/status")
    assert r.status_code == 200
    assert r.json() == {"users_exist": False}


async def test_setup_creates_first_admin(app_kit):
    r = await app_kit.client.post(
        "/api/v1/setup",
        json={
            "username": "operator",
            "password": "hunter2hunter2",
            "email": "op@example.test",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["username"] == "operator"
    assert body["role"] == "admin"
    assert "openclef_session" in r.cookies

    # Subsequent setup is rejected with 409
    r2 = await app_kit.client.post(
        "/api/v1/setup",
        json={"username": "second", "password": "hunter2hunter2"},
    )
    assert r2.status_code == 409
    assert r2.json()["detail"] == "setup_already_complete"


async def test_setup_status_after_admin_exists(app_kit):
    async with app_kit.sessionmaker() as s:
        await _seed_user(s, username="someone")
    r = await app_kit.client.get("/api/v1/setup/status")
    assert r.json() == {"users_exist": True}


async def test_setup_password_min_length_enforced(app_kit):
    r = await app_kit.client.post(
        "/api/v1/setup",
        json={"username": "operator", "password": "short"},
    )
    assert r.status_code == 422
