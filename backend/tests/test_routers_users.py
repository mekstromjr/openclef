"""End-to-end tests for /api/v1/users (admin CRUD + /me/settings)."""
from __future__ import annotations


from openclef.auth.hashing import hash_password
from openclef.models.enums import UserRole
from openclef.models.library import Arrangement
from openclef.models.user import User


async def _seed_user(session, *, username, password="hunter2hunter2", role=UserRole.USER):
    user = User(
        username=username,
        password_hash=hash_password(password),
        role=role,
    )
    session.add(user)
    await session.commit()
    return user


async def _login(client, username, password="hunter2hunter2"):
    r = await client.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )
    assert r.status_code == 200, r.text


# --- Admin guard -----------------------------------------------------


async def test_list_users_requires_admin(app_kit):
    async with app_kit.sessionmaker() as s:
        await _seed_user(s, username="alice", role=UserRole.USER)
    await _login(app_kit.client, "alice")
    r = await app_kit.client.get("/api/v1/users")
    assert r.status_code == 403


async def test_list_users_as_admin(app_kit):
    async with app_kit.sessionmaker() as s:
        await _seed_user(s, username="boss", role=UserRole.ADMIN)
        await _seed_user(s, username="alice")
    await _login(app_kit.client, "boss")
    r = await app_kit.client.get("/api/v1/users")
    assert r.status_code == 200
    usernames = sorted(u["username"] for u in r.json())
    assert usernames == ["alice", "boss"]


# --- Create user ------------------------------------------------------


async def test_admin_creates_user(app_kit):
    async with app_kit.sessionmaker() as s:
        await _seed_user(s, username="boss", role=UserRole.ADMIN)
    await _login(app_kit.client, "boss")
    r = await app_kit.client.post(
        "/api/v1/users",
        json={
            "username": "newbie",
            "password_hash": "freshpassword",  # plaintext; route hashes
        },
    )
    assert r.status_code == 201, r.text
    assert r.json()["username"] == "newbie"

    # And the new user can actually log in with that password
    r2 = await app_kit.client.post(
        "/api/v1/auth/login",
        json={"username": "newbie", "password": "freshpassword"},
    )
    assert r2.status_code == 200


async def test_create_rejects_duplicate_username(app_kit):
    async with app_kit.sessionmaker() as s:
        await _seed_user(s, username="boss", role=UserRole.ADMIN)
    await _login(app_kit.client, "boss")
    await app_kit.client.post(
        "/api/v1/users",
        json={"username": "twin", "password_hash": "hunter2hunter2"},
    )
    r = await app_kit.client.post(
        "/api/v1/users",
        json={"username": "twin", "password_hash": "hunter2hunter2"},
    )
    assert r.status_code == 409


async def test_create_rejects_reserved_username(app_kit):
    async with app_kit.sessionmaker() as s:
        await _seed_user(s, username="boss", role=UserRole.ADMIN)
    await _login(app_kit.client, "boss")
    r = await app_kit.client.post(
        "/api/v1/users",
        json={"username": "__deleted__", "password_hash": "hunter2hunter2"},
    )
    assert r.status_code == 409
    assert r.json()["detail"] == "reserved_username"


# --- Patch user -------------------------------------------------------


async def test_admin_can_promote_user(app_kit):
    async with app_kit.sessionmaker() as s:
        await _seed_user(s, username="boss", role=UserRole.ADMIN)
        target = await _seed_user(s, username="alice")
    await _login(app_kit.client, "boss")
    r = await app_kit.client.patch(
        f"/api/v1/users/{target.id}",
        json={"role": "admin"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["role"] == "admin"


# --- Delete + anonymize ----------------------------------------------


async def test_delete_user_repoints_arrangements(app_kit):
    async with app_kit.sessionmaker() as s:
        await _seed_user(s, username="boss", role=UserRole.ADMIN)
        alice = await _seed_user(s, username="alice")
        # Alice owns an arrangement
        arr = Arrangement(title="Alice's Arrangement", created_by=alice.id)
        s.add(arr)
        await s.commit()
        arr_id = arr.id

    await _login(app_kit.client, "boss")
    r = await app_kit.client.delete(f"/api/v1/users/{alice.id}")
    assert r.status_code == 204

    async with app_kit.sessionmaker() as s:
        from sqlalchemy import select

        # Alice is gone
        gone = (await s.execute(select(User).where(User.id == alice.id))).scalar_one_or_none()
        assert gone is None

        # Arrangement survives, repointed to the tombstone user
        surviving = (
            await s.execute(select(Arrangement).where(Arrangement.id == arr_id))
        ).scalar_one()
        tombstone = (
            await s.execute(select(User).where(User.username == "__deleted__"))
        ).scalar_one()
        assert surviving.created_by == tombstone.id


async def test_admin_cannot_delete_self(app_kit):
    async with app_kit.sessionmaker() as s:
        boss = await _seed_user(s, username="boss", role=UserRole.ADMIN)
    await _login(app_kit.client, "boss")
    r = await app_kit.client.delete(f"/api/v1/users/{boss.id}")
    assert r.status_code == 409
    assert r.json()["detail"] == "cannot_delete_self"


async def test_delete_invalid_uuid(app_kit):
    async with app_kit.sessionmaker() as s:
        await _seed_user(s, username="boss", role=UserRole.ADMIN)
    await _login(app_kit.client, "boss")
    r = await app_kit.client.delete("/api/v1/users/not-a-uuid")
    assert r.status_code == 422


# --- /me/settings ----------------------------------------------------


async def test_get_settings_autocreates(app_kit):
    async with app_kit.sessionmaker() as s:
        await _seed_user(s, username="alice")
    await _login(app_kit.client, "alice")
    r = await app_kit.client.get("/api/v1/users/me/settings")
    assert r.status_code == 200
    body = r.json()
    assert body["theme"] == "system"
    assert body["enrichment_default_enabled"] is False


async def test_patch_settings_round_trip(app_kit):
    async with app_kit.sessionmaker() as s:
        await _seed_user(s, username="alice")
    await _login(app_kit.client, "alice")
    r = await app_kit.client.patch(
        "/api/v1/users/me/settings",
        json={"theme": "dark", "enrichment_default_enabled": True},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["theme"] == "dark"
    assert body["enrichment_default_enabled"] is True

    # Confirm persisted
    r2 = await app_kit.client.get("/api/v1/users/me/settings")
    assert r2.json()["theme"] == "dark"


async def test_settings_requires_session(app_kit):
    r = await app_kit.client.get("/api/v1/users/me/settings")
    assert r.status_code == 401
