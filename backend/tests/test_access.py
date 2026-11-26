"""The sharing access rule (openclef#61, TRD section 3.5) across every endpoint.

One owner, one piece on one setlist, and a viewer in each relationship to
the owner. Each case checks every read and write path, including PDF and
thumbnail bytes, so a single endpoint that forgets the filter fails here.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass

import pytest
from sqlalchemy import select

from openclef.auth.hashing import hash_password
from openclef.models.enums import SharePermission, UserRole
from openclef.models.setlist import SetlistItem
from openclef.models.sharing import Partnership
from openclef.models.user import User
from tests.pdf_fixtures import make_pdf
from tests.sharing import make_group, share_arrangement, share_library, share_setlist

PASSWORD = "hunter2hunter2"


async def _user(kit, username, role=UserRole.USER) -> User:
    async with kit.sessionmaker() as s:
        user = User(username=username, password_hash=hash_password(PASSWORD), role=role)
        s.add(user)
        await s.commit()
        return user


async def _login(kit, username):
    r = await kit.client.post("/api/v1/auth/login", json={"username": username, "password": PASSWORD})
    assert r.status_code == 200, r.text


async def _upload(kit, title, composer="Composer"):
    r = await kit.client.post(
        "/api/v1/arrangements/upload",
        files={"file": ("score.pdf", make_pdf(pages=2), "application/pdf")},
        data={"metadata": json.dumps({"title": title, "composer": [composer]})},
    )
    assert r.status_code == 201, r.text
    return r.json()["arrangement"]["id"], r.json()["part"]["id"]


async def _setlist(kit, name, *pieces):
    r = await kit.client.post("/api/v1/setlists", json={"name": name})
    assert r.status_code == 201, r.text
    setlist_id = r.json()["id"]
    for piece in pieces:
        r = await kit.client.post(f"/api/v1/setlists/{setlist_id}/items", json={"arrangement_id": piece})
        assert r.status_code == 201, r.text
    return setlist_id


@dataclass
class World:
    owner: User
    piece: str
    part: str
    setlist: str


async def _world(kit) -> World:
    owner = await _user(kit, "owner")
    await _login(kit, "owner")
    piece, part = await _upload(kit, "Owner's Trio", composer="Owner Composer")
    setlist = await _setlist(kit, "Owner's recital", piece)
    return World(owner=owner, piece=piece, part=part, setlist=setlist)


async def _as_owner(kit, world): ...


async def _partner(kit, world, viewer):
    await share_library(kit, world.owner.id, viewer.id)


async def _reverse_partner(kit, world, viewer):
    # The viewer shares with the owner; that gives the viewer nothing.
    await share_library(kit, viewer.id, world.owner.id)


async def _partners_partner(kit, world, viewer):
    middle = await _user(kit, "middle")
    await share_library(kit, world.owner.id, middle.id)
    await share_library(kit, middle.id, viewer.id)


async def _group_member(kit, world, viewer):
    group = await make_group(kit, world.owner.id, viewer.id)
    await share_arrangement(kit, world.piece, group)


async def _other_group_member(kit, world, viewer):
    # Same group as the owner, but nothing shared with it.
    await make_group(kit, world.owner.id, world.owner.id, viewer.id)


async def _setlist_viewer(kit, world, viewer):
    await share_setlist(kit, world.setlist, user_id=viewer.id)


async def _setlist_group_member(kit, world, viewer):
    group = await make_group(kit, world.owner.id, viewer.id)
    await share_setlist(kit, world.setlist, group_id=group)


async def _stranger(kit, world, viewer): ...


# (name, how the viewer relates, sees the piece, sees the setlist, role)
CASES = [
    ("owner", _as_owner, True, True, UserRole.USER),
    ("partner", _partner, True, True, UserRole.USER),
    ("reverse_partner", _reverse_partner, False, False, UserRole.USER),
    ("partners_partner", _partners_partner, False, False, UserRole.USER),
    ("group_member", _group_member, True, False, UserRole.USER),
    ("member_of_group_with_nothing_shared", _other_group_member, False, False, UserRole.USER),
    ("setlist_shared_with_user", _setlist_viewer, True, True, UserRole.USER),
    ("setlist_shared_with_group", _setlist_group_member, True, True, UserRole.USER),
    ("stranger", _stranger, False, False, UserRole.USER),
    ("admin", _stranger, True, True, UserRole.ADMIN),
]
IDS = [case[0] for case in CASES]
# What the library page lists is narrower than what opens (openclef#62):
# pieces reached through a setlist, and the admin override, aren't listed.
LISTED = {"owner", "partner", "group_member"}


async def _viewer(kit, world, name, relate, role):
    if relate is _as_owner:
        return world.owner
    viewer = await _user(kit, f"viewer_{name}", role)
    await relate(kit, world, viewer)
    await _login(kit, viewer.username)
    return viewer


@pytest.mark.parametrize(("name", "relate", "sees_piece", "sees_setlist", "role"), CASES, ids=IDS)
async def test_reads_follow_the_access_rule(app_kit, name, relate, sees_piece, sees_setlist, role):
    kit = app_kit
    world = await _world(kit)
    await _viewer(kit, world, name, relate, role)
    client = kit.client

    listed = name in LISTED
    assert not listed or sees_piece  # never list what can't be opened
    library = (await client.get("/api/v1/arrangements")).json()
    assert ([item["id"] for item in library["items"]] == [world.piece]) is listed
    assert library["total"] == (1 if listed else 0)
    # Facet counts come from the same filter, so unlisted pieces aren't counted.
    composers = {facet["value"]: facet["count"] for facet in library["facets"]["composer"]}
    assert composers == ({"Owner Composer": 1} if listed else {})
    searched = (await client.get("/api/v1/arrangements", params={"q": "trio"})).json()
    assert searched["total"] == (1 if listed else 0)

    detail = await client.get(f"/api/v1/arrangements/{world.piece}")
    assert detail.status_code == (200 if sees_piece else 404)
    if sees_piece:
        # The piece's setlists only name setlists the viewer can see.
        assert [ref["id"] for ref in detail.json()["setlists"]] == ([world.setlist] if sees_setlist else [])

    pdf = await client.get(f"/api/v1/parts/{world.part}/file")
    assert pdf.status_code == (200 if sees_piece else 404)
    if sees_piece:
        assert pdf.content.startswith(b"%PDF")
    else:
        assert pdf.json()["detail"] == "part_not_found"
    thumbnail = await client.get(f"/api/v1/parts/{world.part}/thumbnail")
    if sees_piece:
        assert thumbnail.status_code == 200 or thumbnail.json()["detail"] != "part_not_found"
    else:
        assert (thumbnail.status_code, thumbnail.json()["detail"]) == (404, "part_not_found")

    setlists = (await client.get("/api/v1/setlists")).json()
    assert ([setlist["id"] for setlist in setlists] == [world.setlist]) is sees_setlist
    setlist = await client.get(f"/api/v1/setlists/{world.setlist}")
    assert setlist.status_code == (200 if sees_setlist else 404)
    if sees_setlist:
        entry = setlist.json()["items"][0]
        assert entry["available"] is sees_piece
        assert (entry["arrangement_id"] == world.piece) is sees_piece


@pytest.mark.parametrize(("name", "relate", "sees_piece", "sees_setlist", "role"), CASES, ids=IDS)
async def test_writes_follow_the_access_rule(app_kit, name, relate, sees_piece, sees_setlist, role):
    kit = app_kit
    world = await _world(kit)
    viewer = await _viewer(kit, world, name, relate, role)
    client = kit.client
    manages = viewer.id == world.owner.id or role == UserRole.ADMIN

    # Editing is open to anyone who can see the piece.
    edit = await client.patch(f"/api/v1/arrangements/{world.piece}", json={"notes": f"edited by {name}"})
    assert edit.status_code == (200 if sees_piece else 404), edit.text
    add_part = await client.post(
        f"/api/v1/arrangements/{world.piece}/parts",
        files={"file": ("part.pdf", make_pdf(pages=1), "application/pdf")},
        data={"instrument": "Cello"},
    )
    assert add_part.status_code == (201 if sees_piece else 404), add_part.text

    # Putting the piece on one's own setlist needs only that the viewer can see it.
    own = (await client.post("/api/v1/setlists", json={"name": "Mine"})).json()["id"]
    append = await client.post(f"/api/v1/setlists/{own}/items", json={"arrangement_id": world.piece})
    assert append.status_code == (201 if sees_piece else 422), append.text
    if not sees_piece:
        assert append.json()["detail"] == "arrangement_not_found"

    # Changing the owner's setlist: owner or admin; others get 403 if they
    # can see it, 404 if they can't.
    rename = await client.patch(f"/api/v1/setlists/{world.setlist}", json={"name": "Renamed"})
    assert rename.status_code == (200 if manages else 403 if sees_setlist else 404), rename.text

    # Deleting is for the owner or an admin, even with the piece on a
    # setlist: its entry stays there, marked deleted (openclef#64).
    delete_part = await client.delete(f"/api/v1/arrangements/{world.piece}/parts/{world.part}")
    assert delete_part.status_code == (204 if manages else 403 if sees_piece else 404), delete_part.text
    delete_piece = await client.delete(f"/api/v1/arrangements/{world.piece}")
    assert delete_piece.status_code == (204 if manages else 403 if sees_piece else 404), delete_piece.text


async def test_a_shared_setlist_passes_on_only_what_each_adder_owns(app_kit):
    """Decision 7/8 of openclef#60, and the partner edge case: a setlist's
    audience gets each piece only if whoever added it owns it."""
    kit = app_kit
    lender = await _user(kit, "lender")
    await _login(kit, "lender")
    lent, _ = await _upload(kit, "Lent piece")

    owner = await _user(kit, "owner")
    await share_library(kit, lender.id, owner.id)
    await _login(kit, "owner")
    own, _ = await _upload(kit, "Own piece")
    setlist = await _setlist(kit, "Recital", own, lent)

    contributor = await _user(kit, "contributor")
    await share_setlist(kit, setlist, user_id=contributor.id, permission=SharePermission.CONTRIBUTE)
    await _login(kit, "contributor")
    contributed, _ = await _upload(kit, "Contributed piece")
    async with kit.sessionmaker() as s:
        s.add(SetlistItem(setlist_id=setlist, position=2, arrangement_id=contributed, added_by=contributor.id))
        await s.commit()

    audience = await _user(kit, "audience")
    await share_setlist(kit, setlist, user_id=audience.id)
    owners_partner = await _user(kit, "owners_partner")
    await share_library(kit, owner.id, owners_partner.id)

    for viewer in ("audience", "owners_partner"):
        await _login(kit, viewer)
        items = (await kit.client.get(f"/api/v1/setlists/{setlist}")).json()["items"]
        assert [(item["title"], item["available"]) for item in items] == [
            ("Own piece", True),
            (None, False),  # the lent piece: never passed on, and nothing leaks
            ("Contributed piece", True),
        ], viewer
        assert items[1]["arrangement_id"] is None and items[1]["effective_part_id"] is None
        assert (await kit.client.get(f"/api/v1/arrangements/{lent}")).status_code == 404
        assert (await kit.client.get(f"/api/v1/arrangements/{contributed}")).status_code == 200

    # The owner still sees the lent piece through the lender's partnership.
    await _login(kit, "owner")
    items = (await kit.client.get(f"/api/v1/setlists/{setlist}")).json()["items"]
    assert all(item["available"] for item in items)


async def test_a_contributor_who_loses_the_setlist_stops_passing_on(app_kit):
    """openclef#64 acceptance: once a contributor's share ends, the pieces
    they added reach nobody, and say "no longer shared" to the owner."""
    kit = app_kit
    owner = await _user(kit, "owner")
    await _login(kit, "owner")
    own, _ = await _upload(kit, "Own piece")
    setlist = await _setlist(kit, "Recital", own)
    contributor = await _user(kit, "contributor")
    # The owner is a member too (make_group adds them): their own entries
    # must not stand in for the contributor's.
    choir = await make_group(kit, owner.id, contributor.id)
    await share_setlist(kit, setlist, group_id=choir, permission=SharePermission.CONTRIBUTE)
    audience = await _user(kit, "audience")
    await share_setlist(kit, setlist, user_id=audience.id)

    await _login(kit, "contributor")
    contributed, _ = await _upload(kit, "Contributed piece")
    r = await kit.client.post(f"/api/v1/setlists/{setlist}/items", json={"arrangement_id": contributed})
    assert r.status_code == 201, r.text

    async def seen_by(viewer):
        await _login(kit, viewer)
        _, item = (await kit.client.get(f"/api/v1/setlists/{setlist}")).json()["items"]
        opens = (await kit.client.get(f"/api/v1/arrangements/{contributed}")).status_code == 200
        return item["available"], item["removed"], item["title"], opens

    assert await seen_by("audience") == (True, None, "Contributed piece", True)
    # The contributor leaves the group the share went through.
    await _login(kit, "contributor")
    r = await kit.client.delete(f"/api/v1/groups/{choir}/members/{contributor.id}")
    assert r.status_code == 204
    assert await seen_by("audience") == (False, None, None, False)
    assert await seen_by("owner") == (False, "unshared", "Contributed piece", False)


async def test_reordering_keeps_who_added_each_piece(app_kit):
    kit = app_kit
    owner = await _user(kit, "owner")
    await _login(kit, "owner")
    own, _ = await _upload(kit, "Own piece")
    setlist = await _setlist(kit, "Recital", own)
    contributor = await _user(kit, "contributor")
    await share_library(kit, contributor.id, owner.id)
    await _login(kit, "contributor")
    contributed, _ = await _upload(kit, "Contributed piece")
    async with kit.sessionmaker() as s:
        s.add(SetlistItem(setlist_id=setlist, position=1, arrangement_id=contributed, added_by=contributor.id))
        await s.commit()

    await _login(kit, "owner")
    loaded = (await kit.client.get(f"/api/v1/setlists/{setlist}")).json()["items"]
    own_entry, contributed_entry = (entry["id"] for entry in loaded)
    r = await kit.client.put(
        f"/api/v1/setlists/{setlist}/items",
        json={"entries": [{"id": contributed_entry}, {"id": own_entry}, {"arrangement_id": own}]},
    )
    assert r.status_code == 200, r.text
    assert [entry["id"] for entry in r.json()["items"][:2]] == [contributed_entry, own_entry]
    async with kit.sessionmaker() as s:
        rows = (
            await s.execute(
                select(SetlistItem.arrangement_id, SetlistItem.added_by)
                .where(SetlistItem.setlist_id == setlist)
                .order_by(SetlistItem.position)
            )
        ).all()
    assert [(str(arrangement), adder) for arrangement, adder in rows] == [
        (contributed, contributor.id),
        (own, owner.id),
        (own, owner.id),  # a new copy is credited to the editor
    ]

    # The old body shape (every entry as a new piece) is refused rather than
    # re-crediting every piece to the editor.
    r = await kit.client.put(
        f"/api/v1/setlists/{setlist}/items", json={"items": [{"arrangement_id": contributed}]}
    )
    assert r.status_code == 422


async def test_entries_the_editor_cant_see_survive_a_save(app_kit):
    """The editor sends hidden entries back by id; they keep their piece and
    adder, can be moved or removed, but their part can't be changed."""
    kit = app_kit
    lender = await _user(kit, "lender")
    await _login(kit, "lender")
    lent, lent_part = await _upload(kit, "Lent piece")
    owner = await _user(kit, "owner")
    await share_library(kit, lender.id, owner.id)
    await _login(kit, "owner")
    own, _ = await _upload(kit, "Own piece")
    setlist = await _setlist(kit, "Recital", lent, own)

    async with kit.sessionmaker() as s:  # the lender stops sharing
        partnership = await s.get(Partnership, (lender.id, owner.id))
        await s.delete(partnership)
        await s.commit()

    loaded = (await kit.client.get(f"/api/v1/setlists/{setlist}")).json()["items"]
    hidden, mine = loaded
    # The owner put it there, so they're told what it was and who stopped sharing.
    assert (hidden["available"], hidden["removed"], hidden["title"], hidden["removed_by"]) == (
        False, "unshared", "Lent piece", "lender",
    )
    assert hidden["arrangement_id"] is None and hidden["effective_part_id"] is None

    url = f"/api/v1/setlists/{setlist}/items"
    r = await kit.client.put(url, json={"entries": [{"id": hidden["id"], "part_id": lent_part}]})
    assert (r.status_code, r.json()["detail"]) == (422, "item_hidden")
    r = await kit.client.put(url, json={"entries": [{"id": mine["id"]}, {"id": hidden["id"]}]})
    assert r.status_code == 200, r.text
    assert [entry["id"] for entry in r.json()["items"]] == [mine["id"], hidden["id"]]

    # Sharing again brings it back as it was.
    await share_library(kit, lender.id, owner.id)
    items = (await kit.client.get(f"/api/v1/setlists/{setlist}")).json()["items"]
    assert [(entry["title"], entry["available"]) for entry in items] == [("Own piece", True), ("Lent piece", True)]

    # An id from elsewhere, or one sent twice, is refused.
    r = await kit.client.put(url, json={"entries": [{"id": str(uuid.uuid4())}]})
    assert (r.status_code, r.json()["detail"]) == (422, "item_not_found")
    r = await kit.client.put(url, json={"entries": [{"id": mine["id"]}, {"id": mine["id"]}]})
    assert (r.status_code, r.json()["detail"]) == (422, "duplicate_item")

    # Leaving it out removes it.
    r = await kit.client.put(url, json={"entries": [{"id": mine["id"]}]})
    assert [entry["title"] for entry in r.json()["items"]] == ["Own piece"]


async def test_an_unshared_entry_tells_only_who_saw_it(app_kit):
    """Someone who never saw the piece learns nothing but its position."""
    kit = app_kit
    lender = await _user(kit, "lender")
    await _login(kit, "lender")
    lent, _ = await _upload(kit, "Lent piece")
    owner = await _user(kit, "owner")
    await share_library(kit, lender.id, owner.id)
    await _login(kit, "owner")
    setlist = await _setlist(kit, "Recital", lent)
    audience = await _user(kit, "audience")
    await share_setlist(kit, setlist, user_id=audience.id)

    await _login(kit, "audience")
    [entry] = (await kit.client.get(f"/api/v1/setlists/{setlist}")).json()["items"]
    assert entry["available"] is False
    assert (entry["removed"], entry["title"], entry["removed_by"]) == (None, None, None)
    assert "Lent piece" not in (await kit.client.get(f"/api/v1/setlists/{setlist}")).text
