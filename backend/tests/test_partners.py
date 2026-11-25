"""Partners, the people directory, and what the library lists (openclef#62).

Opening a piece follows services.access.visible_arrangements (tested in
test_access). These tests cover the narrower listing rule: own pieces,
partners shown in the library, and the "Only my music" / per-sharer views.
"""
from __future__ import annotations

import pytest

from openclef.models.enums import UserRole
from tests.sharing import share_setlist
from tests.test_access import _login, _setlist, _upload, _user


async def _ids(kit, **params) -> set[str]:
    r = await kit.client.get("/api/v1/arrangements", params=params)
    assert r.status_code == 200, r.text
    return {item["id"] for item in r.json()["items"]}


async def _partner(kit, partner_id) -> None:
    r = await kit.client.post("/api/v1/partners", json={"user_id": str(partner_id)})
    assert r.status_code == 201, r.text


# --- partners API ------------------------------------------------------


@pytest.mark.asyncio
async def test_sharing_is_one_way(app_kit):
    alice, bob = await _user(app_kit, "alice"), await _user(app_kit, "bob")
    await _login(app_kit, "bob")
    bobs, _ = await _upload(app_kit, "Bob's Etude")
    await _login(app_kit, "alice")
    alices, _ = await _upload(app_kit, "Alice's Waltz")
    await _partner(app_kit, bob.id)

    r = await app_kit.client.get("/api/v1/partners")
    assert r.json() == {"outgoing": [{"id": str(bob.id), "username": "bob"}], "incoming": []}
    assert await _ids(app_kit) == {alices}  # Alice still can't see Bob's

    await _login(app_kit, "bob")
    r = await app_kit.client.get("/api/v1/partners")
    assert r.json() == {
        "outgoing": [],
        "incoming": [{"id": str(alice.id), "username": "alice", "show_in_library": True}],
    }
    assert await _ids(app_kit) == {alices, bobs}


@pytest.mark.asyncio
async def test_partner_refusals(app_kit):
    alice = await _user(app_kit, "alice")
    bob = await _user(app_kit, "bob")
    await _login(app_kit, "alice")
    await _partner(app_kit, bob.id)

    r = await app_kit.client.post("/api/v1/partners", json={"user_id": str(bob.id)})
    assert (r.status_code, r.json()["detail"]) == (409, "already_partners")
    r = await app_kit.client.post("/api/v1/partners", json={"user_id": str(alice.id)})
    assert (r.status_code, r.json()["detail"]) == (422, "cannot_partner_self")
    tombstone = await _user(app_kit, "__deleted__")
    r = await app_kit.client.post("/api/v1/partners", json={"user_id": str(tombstone.id)})
    assert (r.status_code, r.json()["detail"]) == (422, "user_not_found")
    r = await app_kit.client.post(
        "/api/v1/partners", json={"user_id": "00000000-0000-0000-0000-000000000000"}
    )
    assert (r.status_code, r.json()["detail"]) == (422, "user_not_found")
    r = await app_kit.client.post("/api/v1/partners", json={"user_id": str(bob.id), "extra": 1})
    assert r.status_code == 422

    # Only the receiver toggles; Alice has no incoming partnership from Bob.
    r = await app_kit.client.patch(
        f"/api/v1/partners/incoming/{bob.id}", json={"show_in_library": False}
    )
    assert r.status_code == 404
    # Bob can't end Alice's share: only the sharer removes it.
    await _login(app_kit, "bob")
    r = await app_kit.client.delete(f"/api/v1/partners/{alice.id}")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_removing_a_partner_ends_access(app_kit):
    await _user(app_kit, "alice")
    bob = await _user(app_kit, "bob")
    await _login(app_kit, "alice")
    piece, _ = await _upload(app_kit, "Alice's Waltz")
    await _partner(app_kit, bob.id)
    r = await app_kit.client.delete(f"/api/v1/partners/{bob.id}")
    assert r.status_code == 204
    r = await app_kit.client.delete(f"/api/v1/partners/{bob.id}")
    assert r.status_code == 404

    await _login(app_kit, "bob")
    assert await _ids(app_kit) == set()
    r = await app_kit.client.get(f"/api/v1/arrangements/{piece}")
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_people_directory(app_kit):
    await _user(app_kit, "alice")
    bob = await _user(app_kit, "bob")
    await _user(app_kit, "__deleted__")
    await _login(app_kit, "alice")
    r = await app_kit.client.get("/api/v1/people")
    assert r.status_code == 200
    # No self, no tombstone, no email or role.
    assert r.json() == [{"id": str(bob.id), "username": "bob"}]


@pytest.mark.asyncio
async def test_endpoints_need_sign_in(app_kit):
    for method, path in [("get", "/api/v1/people"), ("get", "/api/v1/partners")]:
        r = await getattr(app_kit.client, method)(path)
        assert r.status_code == 401


# --- what the library lists ----------------------------------------------


async def _three_way(kit):
    """Alice shares with Bob. Each has one piece; Bob also has a setlist
    shared with him by Carol holding Carol's piece."""
    alice = await _user(kit, "alice")
    bob = await _user(kit, "bob")
    await _user(kit, "carol")
    await _login(kit, "carol")
    carols, _ = await _upload(kit, "Carol's Nocturne", composer="Chopin")
    carol_setlist = await _setlist(kit, "Carol's gig", carols)
    await share_setlist(kit, carol_setlist, user_id=bob.id)
    await _login(kit, "alice")
    alices, _ = await _upload(kit, "Alice's Waltz", composer="Strauss")
    await _partner(kit, bob.id)
    await _login(kit, "bob")
    bobs, _ = await _upload(kit, "Bob's Etude", composer="Czerny")
    return alice, alices, bobs, carols


@pytest.mark.asyncio
async def test_library_scopes(app_kit):
    alice, alices, bobs, carols = await _three_way(app_kit)

    # Setlist-only pieces open but aren't listed.
    assert await _ids(app_kit) == {alices, bobs}
    assert (await app_kit.client.get(f"/api/v1/arrangements/{carols}")).status_code == 200
    assert await _ids(app_kit, scope="mine") == {bobs}
    assert await _ids(app_kit, shared_by=str(alice.id)) == {alices}

    r = await app_kit.client.get("/api/v1/arrangements")
    by_id = {item["id"]: item for item in r.json()["items"]}
    assert by_id[alices]["owner_username"] == "alice"
    assert by_id[alices]["owner_id"] == str(alice.id)
    assert by_id[bobs]["owner_username"] == "bob"
    # Facets count only what's listed.
    composers = {f["value"]: f["count"] for f in r.json()["facets"]["composer"]}
    assert composers == {"Strauss": 1, "Czerny": 1}
    r = await app_kit.client.get("/api/v1/arrangements", params={"scope": "mine"})
    assert r.json()["total"] == 1
    assert {f["value"] for f in r.json()["facets"]["composer"]} == {"Czerny"}


@pytest.mark.asyncio
async def test_show_in_library_toggle(app_kit):
    alice, alices, bobs, _ = await _three_way(app_kit)
    r = await app_kit.client.patch(
        f"/api/v1/partners/incoming/{alice.id}", json={"show_in_library": False}
    )
    assert r.status_code == 200
    assert r.json() == {"id": str(alice.id), "username": "alice", "show_in_library": False}

    # Hidden from the main library, still on Alice's page and still openable.
    assert await _ids(app_kit) == {bobs}
    assert await _ids(app_kit, shared_by=str(alice.id)) == {alices}
    assert (await app_kit.client.get(f"/api/v1/arrangements/{alices}")).status_code == 200

    await app_kit.client.patch(f"/api/v1/partners/incoming/{alice.id}", json={"show_in_library": True})
    assert await _ids(app_kit) == {alices, bobs}


@pytest.mark.asyncio
async def test_shared_by_a_non_partner_lists_nothing(app_kit):
    _, _, _, carols = await _three_way(app_kit)
    r = await app_kit.client.get(f"/api/v1/arrangements/{carols}")
    carol_id = r.json()["owner_id"]
    # Carol's piece reaches Bob only through a setlist, so her page is empty.
    assert await _ids(app_kit, shared_by=carol_id) == set()


@pytest.mark.asyncio
async def test_admin_library_lists_own_and_shared_only(app_kit):
    await _user(app_kit, "admin", role=UserRole.ADMIN)
    await _user(app_kit, "alice")
    await _login(app_kit, "alice")
    alices, _ = await _upload(app_kit, "Alice's Waltz")
    await _login(app_kit, "admin")
    admins, _ = await _upload(app_kit, "Admin's March")
    assert await _ids(app_kit) == {admins}
    # The admin override still opens anything by its link.
    assert (await app_kit.client.get(f"/api/v1/arrangements/{alices}")).status_code == 200


# --- piece page ------------------------------------------------------------


@pytest.mark.asyncio
async def test_detail_counts_setlists_the_viewer_cant_see(app_kit):
    await _user(app_kit, "alice")
    bob = await _user(app_kit, "bob")
    await _login(app_kit, "alice")
    piece, _ = await _upload(app_kit, "Alice's Waltz")
    await _partner(app_kit, bob.id)
    await _setlist(app_kit, "Alice's own", piece)
    await _login(app_kit, "bob")
    bobs_setlist = await _setlist(app_kit, "Bob's recital", piece)

    await _login(app_kit, "alice")
    r = await app_kit.client.get(f"/api/v1/arrangements/{piece}")
    body = r.json()
    assert [s["name"] for s in body["setlists"]] == ["Alice's own"]
    assert body["hidden_setlist_count"] == 1
    assert body["owner_username"] == "alice"
    assert "Bob's recital" not in r.text and bobs_setlist not in r.text
