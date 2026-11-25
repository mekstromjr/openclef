"""Groups: members, sharing pieces into them, and the group page (openclef#63).

Opening a group-shared piece follows services.access.visible_arrangements
(test_access covers it with seeded rows). These tests drive the API.
"""
from __future__ import annotations

import pytest

from openclef.models.enums import UserRole
from tests.test_access import _login, _upload, _user
from tests.test_partners import _ids


async def _group(kit, name="Choir") -> dict:
    r = await kit.client.post("/api/v1/groups", json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()


async def _add(kit, group, member) -> None:
    r = await kit.client.post(f"/api/v1/groups/{group['id']}/members", json={"user_id": str(member.id)})
    assert r.status_code == 201, r.text


async def _share(kit, piece, *groups) -> dict:
    r = await kit.client.put(
        f"/api/v1/arrangements/{piece}/shares", json={"group_ids": [g["id"] for g in groups]}
    )
    assert r.status_code == 200, r.text
    return r.json()


async def _opens(kit, piece) -> bool:
    return (await kit.client.get(f"/api/v1/arrangements/{piece}")).status_code == 200


async def _choir(kit):
    """Alice owns the Choir with Bob in it; Carol is outside."""
    alice = await _user(kit, "alice")
    bob = await _user(kit, "bob")
    carol = await _user(kit, "carol")
    await _login(kit, "alice")
    choir = await _group(kit)
    await _add(kit, choir, bob)
    return alice, bob, carol, choir


# --- the group itself ------------------------------------------------------


@pytest.mark.asyncio
async def test_creator_owns_and_belongs(app_kit):
    alice, bob, _, choir = await _choir(app_kit)
    assert choir["owner"] == {"id": str(alice.id), "username": "alice"}
    r = await app_kit.client.get("/api/v1/groups")
    [listed] = r.json()
    assert listed["name"] == "Choir"
    assert [m["username"] for m in listed["members"]] == ["alice", "bob"]

    # The owner sees what members share, through the membership row.
    await _login(app_kit, "bob")
    bobs, _ = await _upload(app_kit, "Bob's Anthem")
    await _share(app_kit, bobs, choir)
    await _login(app_kit, "alice")
    assert await _opens(app_kit, bobs)
    assert bobs in await _ids(app_kit)


@pytest.mark.asyncio
async def test_names_are_trimmed_and_required(app_kit):
    await _user(app_kit, "alice")
    await _login(app_kit, "alice")
    assert (await _group(app_kit, "  Band  "))["name"] == "Band"
    for name in ["", "   ", "x" * 101]:
        r = await app_kit.client.post("/api/v1/groups", json={"name": name})
        assert r.status_code == 422, name
    # Duplicate names are fine.
    await _group(app_kit, "Band")


@pytest.mark.asyncio
async def test_only_the_owner_manages(app_kit):
    alice, bob, carol, choir = await _choir(app_kit)
    gid = choir["id"]
    r = await app_kit.client.post(f"/api/v1/groups/{gid}/members", json={"user_id": str(bob.id)})
    assert (r.status_code, r.json()["detail"]) == (409, "already_member")
    tombstone = await _user(app_kit, "__deleted__")
    r = await app_kit.client.post(f"/api/v1/groups/{gid}/members", json={"user_id": str(tombstone.id)})
    assert (r.status_code, r.json()["detail"]) == (422, "user_not_found")
    r = await app_kit.client.patch(f"/api/v1/groups/{gid}", json={"name": "Chamber Choir"})
    assert r.json()["name"] == "Chamber Choir"
    r = await app_kit.client.delete(f"/api/v1/groups/{gid}/members/{alice.id}")
    assert (r.status_code, r.json()["detail"]) == (422, "owner_cannot_leave")

    # A member can see the group but not change it.
    await _login(app_kit, "bob")
    r = await app_kit.client.patch(f"/api/v1/groups/{gid}", json={"name": "Mine now"})
    assert (r.status_code, r.json()["detail"]) == (403, "not_group_owner")
    r = await app_kit.client.post(f"/api/v1/groups/{gid}/members", json={"user_id": str(carol.id)})
    assert r.status_code == 403
    r = await app_kit.client.delete(f"/api/v1/groups/{gid}")
    assert r.status_code == 403

    # To an outsider, including an admin, the group doesn't exist.
    await _user(app_kit, "admin", role=UserRole.ADMIN)
    for outsider in ["carol", "admin"]:
        await _login(app_kit, outsider)
        assert (await app_kit.client.get("/api/v1/groups")).json() == []
        r = await app_kit.client.patch(f"/api/v1/groups/{gid}", json={"name": "x"})
        assert (r.status_code, r.json()["detail"]) == (404, "group_not_found")
        r = await app_kit.client.delete(f"/api/v1/groups/{gid}/members/{bob.id}")
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_endpoints_need_sign_in(app_kit):
    r = await app_kit.client.get("/api/v1/groups")
    assert r.status_code == 401


# --- sharing pieces into a group --------------------------------------------


@pytest.mark.asyncio
async def test_members_see_only_what_is_shared(app_kit):
    _, bob, carol, choir = await _choir(app_kit)
    shared, _ = await _upload(app_kit, "Ave Maria")
    private, _ = await _upload(app_kit, "Alice's Diary")
    body = await _share(app_kit, shared, choir)
    assert body["groups"] == [{"id": choir["id"], "name": "Choir"}]

    await _login(app_kit, "bob")
    assert await _opens(app_kit, shared) and not await _opens(app_kit, private)
    assert await _ids(app_kit) == {shared}
    assert await _ids(app_kit, group=choir["id"]) == {shared}
    # Group pieces are on the sharer's page too.
    assert await _ids(app_kit, shared_by=choir["owner"]["id"]) == {shared}
    # A member doesn't see which groups the piece is shared with.
    r = await app_kit.client.get(f"/api/v1/arrangements/{shared}")
    assert r.json()["groups"] == []

    await _login(app_kit, "carol")
    assert not await _opens(app_kit, shared)
    assert await _ids(app_kit, group=choir["id"]) == set()


@pytest.mark.asyncio
async def test_who_may_share(app_kit):
    _, bob, carol, choir = await _choir(app_kit)
    alices, _ = await _upload(app_kit, "Ave Maria")
    await _share(app_kit, alices, choir)

    # Carol's own piece, into a group she isn't in: not found.
    await _login(app_kit, "carol")
    carols, _ = await _upload(app_kit, "Carol's Song")
    r = await app_kit.client.put(f"/api/v1/arrangements/{carols}/shares", json={"group_ids": [choir["id"]]})
    assert (r.status_code, r.json()["detail"]) == (422, "group_not_found")

    # Bob can open Alice's piece but can't change where it's shared.
    await _login(app_kit, "bob")
    r = await app_kit.client.put(f"/api/v1/arrangements/{alices}/shares", json={"group_ids": []})
    assert (r.status_code, r.json()["detail"]) == (403, "not_arrangement_owner")

    # No admin override: an admin can't hand out someone's piece, nor see
    # the groups it's in.
    await _user(app_kit, "admin", role=UserRole.ADMIN)
    await _login(app_kit, "admin")
    r = await app_kit.client.put(f"/api/v1/arrangements/{carols}/shares", json={"group_ids": []})
    assert (r.status_code, r.json()["detail"]) == (403, "not_arrangement_owner")
    r = await app_kit.client.get(f"/api/v1/arrangements/{alices}")
    assert r.json()["groups"] == [] and "Choir" not in r.text


@pytest.mark.asyncio
async def test_unsharing_and_removal_hide_at_once(app_kit):
    _, bob, _, choir = await _choir(app_kit)
    piece, _ = await _upload(app_kit, "Ave Maria")
    await _share(app_kit, piece, choir)
    await _share(app_kit, piece)  # [] unshares
    await _login(app_kit, "bob")
    assert not await _opens(app_kit, piece)

    await _login(app_kit, "alice")
    await _share(app_kit, piece, choir)
    r = await app_kit.client.delete(f"/api/v1/groups/{choir['id']}/members/{bob.id}")
    assert r.status_code == 204
    await _login(app_kit, "bob")
    assert not await _opens(app_kit, piece)
    assert await _ids(app_kit) == set()
    assert (await app_kit.client.get("/api/v1/groups")).json() == []


@pytest.mark.asyncio
async def test_a_departing_members_shares_end(app_kit):
    """Leaving or being removed takes your pieces out of the group."""
    _, bob, carol, choir = await _choir(app_kit)
    await _add(app_kit, choir, carol)
    await _login(app_kit, "bob")
    bobs, _ = await _upload(app_kit, "Bob's Anthem")
    await _share(app_kit, bobs, choir)
    await _login(app_kit, "carol")
    carols, _ = await _upload(app_kit, "Carol's Song")
    await _share(app_kit, carols, choir)

    r = await app_kit.client.delete(f"/api/v1/groups/{choir['id']}/members/{carol.id}")
    assert r.status_code == 204  # Carol leaves
    await _login(app_kit, "alice")
    assert not await _opens(app_kit, carols)
    r = await app_kit.client.delete(f"/api/v1/groups/{choir['id']}/members/{bob.id}")
    assert r.status_code == 204  # Alice removes Bob
    assert not await _opens(app_kit, bobs)
    # Rejoining doesn't bring the old shares back.
    await _add(app_kit, choir, bob)
    assert not await _opens(app_kit, bobs)
    r = await app_kit.client.delete(f"/api/v1/groups/{choir['id']}/members/{carol.id}")
    assert (r.status_code, r.json()["detail"]) == (404, "member_not_found")


@pytest.mark.asyncio
async def test_deleting_a_group_keeps_the_pieces(app_kit):
    _, bob, _, choir = await _choir(app_kit)
    piece, _ = await _upload(app_kit, "Ave Maria")
    await _share(app_kit, piece, choir)
    r = await app_kit.client.delete(f"/api/v1/groups/{choir['id']}")
    assert r.status_code == 204
    assert await _opens(app_kit, piece)
    r = await app_kit.client.get(f"/api/v1/arrangements/{piece}")
    assert r.json()["groups"] == []
    await _login(app_kit, "bob")
    assert not await _opens(app_kit, piece)
