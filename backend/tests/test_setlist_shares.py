"""Shared setlists: shares, view vs contribute, the adding rules and the
dry run before sharing (openclef#64)."""
from __future__ import annotations

import uuid

from openclef.models.enums import UserRole
from tests.test_access import _login, _upload, _user
from tests.test_groups import _add, _group

BASE = "/api/v1/setlists"


async def _setlist(kit, name="Recital", *pieces) -> str:
    r = await kit.client.post(BASE, json={"name": name})
    assert r.status_code == 201, r.text
    setlist = r.json()["id"]
    for piece in pieces:
        r = await kit.client.post(f"{BASE}/{setlist}/items", json={"arrangement_id": piece})
        assert r.status_code == 201, r.text
    return setlist


async def _share(kit, setlist, *, user=None, group=None, permission="view"):
    body = {"permission": permission}
    if user is not None:
        body["user_id"] = str(user.id)
    if group is not None:
        body["group_id"] = group["id"]
    return await kit.client.post(f"{BASE}/{setlist}/shares", json=body)


async def _band(kit):
    """Alice owns a setlist shared with Bob (contribute) and Carol (view)."""
    alice = await _user(kit, "alice")
    bob = await _user(kit, "bob")
    carol = await _user(kit, "carol")
    await _login(kit, "alice")
    own, _ = await _upload(kit, "Alice's piece")
    setlist = await _setlist(kit, "Recital", own)
    assert (await _share(kit, setlist, user=bob, permission="contribute")).status_code == 201
    assert (await _share(kit, setlist, user=carol)).status_code == 201
    return alice, bob, carol, setlist, own


# --- the shares themselves -------------------------------------------------


async def test_owner_shares_with_people_and_groups(app_kit):
    alice, bob, carol, setlist, _ = await _band(app_kit)
    choir = await _group(app_kit)
    await _add(app_kit, choir, bob)
    r = await _share(app_kit, setlist, group=choir, permission="contribute")
    assert r.status_code == 201, r.text
    assert [(s["user"] and s["user"]["username"], s["group"] and s["group"]["name"], s["permission"]) for s in r.json()] == [
        ("bob", None, "contribute"),
        ("carol", None, "view"),
        (None, "Choir", "contribute"),
    ]
    assert (await app_kit.client.get(f"{BASE}/{setlist}/shares")).json() == r.json()

    r = await _share(app_kit, setlist, user=carol, permission="contribute")
    assert (r.status_code, r.json()["detail"]) == (409, "already_shared")
    for bad in ({"permission": "view"}, {"user_id": str(bob.id), "group_id": choir["id"], "permission": "view"}):
        r = await app_kit.client.post(f"{BASE}/{setlist}/shares", json=bad)
        assert (r.status_code, r.json()["detail"]) == (422, "one_target")
    r = await _share(app_kit, setlist, user=alice)
    assert (r.status_code, r.json()["detail"]) == (422, "user_not_found")
    tombstone = await _user(app_kit, "__deleted__")
    r = await _share(app_kit, setlist, user=tombstone)
    assert (r.status_code, r.json()["detail"]) == (422, "user_not_found")
    r = await app_kit.client.post(
        f"{BASE}/{setlist}/shares", json={"permission": "edit", "user_id": str(uuid.uuid4())}
    )
    assert r.status_code == 422

    # Permission changes and removal.
    carols = next(s for s in r_list(await app_kit.client.get(f"{BASE}/{setlist}/shares")) if s["user"] and s["user"]["username"] == "carol")
    r = await app_kit.client.patch(f"{BASE}/{setlist}/shares/{carols['id']}", json={"permission": "contribute"})
    assert next(s for s in r.json() if s["id"] == carols["id"])["permission"] == "contribute"
    assert (await app_kit.client.delete(f"{BASE}/{setlist}/shares/{carols['id']}")).status_code == 204
    r = await app_kit.client.delete(f"{BASE}/{setlist}/shares/{carols['id']}")
    assert (r.status_code, r.json()["detail"]) == (404, "share_not_found")
    await _login(app_kit, "carol")
    assert (await app_kit.client.get(f"{BASE}/{setlist}")).status_code == 404


def r_list(response):
    assert response.status_code == 200, response.text
    return response.json()


async def test_only_the_owner_shares(app_kit):
    _, bob, carol, setlist, _ = await _band(app_kit)
    # Bob can see the setlist but not manage its shares.
    await _login(app_kit, "bob")
    r = await app_kit.client.get(f"{BASE}/{setlist}/shares")
    assert (r.status_code, r.json()["detail"]) == (403, "not_setlist_owner")
    r = await _share(app_kit, setlist, user=carol, permission="contribute")
    assert r.status_code == 403
    # No admin override.
    await _user(app_kit, "admin", role=UserRole.ADMIN)
    await _login(app_kit, "admin")
    assert (await app_kit.client.get(f"{BASE}/{setlist}/shares")).status_code == 403
    # To someone who can't see the setlist, it doesn't exist.
    await _user(app_kit, "dave")
    await _login(app_kit, "dave")
    assert (await app_kit.client.get(f"{BASE}/{setlist}/shares")).status_code == 404


async def test_groups_must_be_the_owners(app_kit):
    alice, bob, _, setlist, _ = await _band(app_kit)
    await _login(app_kit, "bob")
    bobs_group = await _group(app_kit, "Bob's band")
    await _login(app_kit, "alice")
    r = await _share(app_kit, setlist, group=bobs_group)
    assert (r.status_code, r.json()["detail"]) == (422, "group_not_found")


async def test_leaving_a_group_ends_ones_setlist_shares_into_it(app_kit):
    alice, bob, _, _, _ = await _band(app_kit)
    choir = await _group(app_kit)  # Alice's
    await _add(app_kit, choir, bob)
    await _login(app_kit, "bob")
    bobs = await _setlist(app_kit, "Bob's list")
    assert (await _share(app_kit, bobs, group=choir)).status_code == 201
    await _login(app_kit, "alice")
    assert (await app_kit.client.get(f"{BASE}/{bobs}")).status_code == 200
    await _login(app_kit, "bob")
    assert (await app_kit.client.delete(f"/api/v1/groups/{choir['id']}/members/{bob.id}")).status_code == 204
    assert (await app_kit.client.get(f"{BASE}/{bobs}/shares")).json() == []
    await _login(app_kit, "alice")
    assert (await app_kit.client.get(f"{BASE}/{bobs}")).status_code == 404


# --- view and contribute ---------------------------------------------------


async def test_flags_say_what_each_person_may_do(app_kit):
    _, _, _, setlist, _ = await _band(app_kit)
    for viewer, edit, manage in (("alice", True, True), ("bob", True, False), ("carol", False, False)):
        await _login(app_kit, viewer)
        detail = (await app_kit.client.get(f"{BASE}/{setlist}")).json()
        [summary] = (await app_kit.client.get(BASE)).json()
        for body in (detail, summary):
            assert (body["can_edit"], body["can_manage"], body["shared"]) == (edit, manage, True), viewer


async def test_a_viewer_changes_nothing(app_kit):
    _, _, carol, setlist, _ = await _band(app_kit)
    await _login(app_kit, "carol")
    carols, _ = await _upload(app_kit, "Carol's piece")
    r = await app_kit.client.post(f"{BASE}/{setlist}/items", json={"arrangement_id": carols})
    assert (r.status_code, r.json()["detail"]) == (403, "cannot_contribute")
    r = await app_kit.client.put(f"{BASE}/{setlist}/items", json={"entries": []})
    assert r.status_code == 403
    r = await app_kit.client.patch(f"{BASE}/{setlist}", json={"name": "Mine"})
    assert (r.status_code, r.json()["detail"]) == (403, "not_setlist_owner")


async def test_a_contributor_adds_own_pieces_reorders_and_removes_their_own(app_kit):
    alice, bob, _, setlist, alices = await _band(app_kit)
    await _login(app_kit, "bob")
    bobs, _ = await _upload(app_kit, "Bob's piece")
    r = await app_kit.client.post(f"{BASE}/{setlist}/items", json={"arrangement_id": bobs})
    assert r.status_code == 201, r.text
    alice_entry, bob_entry = r.json()["items"]

    # Alice's piece reached Bob through the setlist, but it isn't his to add.
    r = await app_kit.client.post(f"{BASE}/{setlist}/items", json={"arrangement_id": alices})
    assert (r.status_code, r.json()["detail"]) == (422, "not_your_piece")
    r = await app_kit.client.put(
        f"{BASE}/{setlist}/items",
        json={"entries": [{"id": alice_entry["id"]}, {"id": bob_entry["id"]}, {"arrangement_id": alices}]},
    )
    assert (r.status_code, r.json()["detail"]) == (422, "not_your_piece")

    # Reordering is fine, and so is removing his own entry; not Alice's.
    url = f"{BASE}/{setlist}/items"
    r = await app_kit.client.put(url, json={"entries": [{"id": bob_entry["id"]}, {"id": alice_entry["id"]}]})
    assert [entry["title"] for entry in r.json()["items"]] == ["Bob's piece", "Alice's piece"]
    r = await app_kit.client.put(url, json={"entries": [{"id": bob_entry["id"]}]})
    assert (r.status_code, r.json()["detail"]) == (403, "not_your_entry")
    r = await app_kit.client.put(url, json={"entries": [{"id": alice_entry["id"]}]})
    assert [entry["title"] for entry in r.json()["items"]] == ["Alice's piece"]

    # Bob can't rename, delete or share it.
    assert (await app_kit.client.patch(f"{BASE}/{setlist}", json={"name": "x"})).status_code == 403
    assert (await app_kit.client.delete(f"{BASE}/{setlist}")).status_code == 403


async def test_the_owner_adds_only_own_pieces_once_shared(app_kit):
    """A private setlist takes anything its owner can see; once shared, only
    pieces they own, because nothing else would reach the audience."""
    from tests.sharing import share_library

    lender = await _user(app_kit, "lender")
    owner = await _user(app_kit, "owner")
    await share_library(app_kit, lender.id, owner.id)
    await _login(app_kit, "lender")
    lent, _ = await _upload(app_kit, "Lent piece")
    await _login(app_kit, "owner")
    setlist = await _setlist(app_kit, "Recital", lent)  # private: fine
    friend = await _user(app_kit, "friend")
    assert (await _share(app_kit, setlist, user=friend)).status_code == 201
    r = await app_kit.client.post(f"{BASE}/{setlist}/items", json={"arrangement_id": lent})
    assert (r.status_code, r.json()["detail"]) == (422, "not_your_piece")


# --- the dry run -----------------------------------------------------------


async def test_dry_run_lists_what_the_audience_wont_get(app_kit):
    from tests.sharing import share_library

    lender = await _user(app_kit, "lender")
    owner = await _user(app_kit, "owner")
    await share_library(app_kit, lender.id, owner.id)
    await _login(app_kit, "lender")
    lent, _ = await _upload(app_kit, "Lent piece")
    gone, _ = await _upload(app_kit, "Withdrawn piece")
    await _login(app_kit, "owner")
    own, _ = await _upload(app_kit, "Own piece")
    setlist = await _setlist(app_kit, "Recital", own, lent, gone, lent)
    friend = await _user(app_kit, "friend")
    # The lender stops sharing one piece with the owner: counted, not named.
    async with app_kit.sessionmaker() as s:
        from sqlalchemy import update

        from openclef.models.library import Arrangement

        await s.execute(update(Arrangement).where(Arrangement.id == uuid.UUID(gone)).values(owner_id=friend.id))
        await s.commit()

    r = await app_kit.client.post(
        f"{BASE}/{setlist}/shares?dry_run=true", json={"user_id": str(friend.id), "permission": "view"}
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"held_back": [{"arrangement_id": lent, "title": "Lent piece"}], "hidden_count": 1}
    assert (await app_kit.client.get(f"{BASE}/{setlist}/shares")).json() == []
    # Nothing held back: an empty list, so the page shares without asking.
    plain = await _setlist(app_kit, "Plain", own)
    r = await app_kit.client.post(
        f"{BASE}/{plain}/shares?dry_run=true", json={"user_id": str(friend.id), "permission": "view"}
    )
    assert r.json() == {"held_back": [], "hidden_count": 0}
