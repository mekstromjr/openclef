"""Deleting an account: what's kept, for whom, and what goes (openclef#65)."""
from __future__ import annotations

import asyncio
import uuid

import pytest
from sqlalchemy import select

from openclef.models.enums import UserRole
from openclef.models.library import Arrangement, ArrangementTag, Part, Tag
from openclef.models.setlist import Setlist, SetlistItem
from openclef.models.sharing import Group, SetlistShare
from openclef.models.user import User
from openclef.services.uploads import thumbnail_key
from tests.pdf_fixtures import make_pdf
from tests.test_access import _login, _upload, _user
from tests.test_groups import _add, _group
from tests.test_groups import _share as _share_piece
from tests.test_partners import _partner
from tests.test_setlist_shares import _setlist
from tests.test_setlist_shares import _share as _share_setlist

pytestmark = pytest.mark.asyncio

USERS = "/api/v1/users"


async def _plan(kit, user) -> dict:
    r = await kit.client.get(f"{USERS}/{user.id}/deletion-plan")
    assert r.status_code == 200, r.text
    return r.json()


async def _delete(kit, user, **owners):
    body = {kind: {str(k): str(v) for k, v in picks.items()} for kind, picks in owners.items()}
    return await kit.client.request("DELETE", f"{USERS}/{user.id}", json=body or None)


async def _owner_of(kit, model, item_id) -> uuid.UUID | None:
    async with kit.sessionmaker() as s:
        row = (await s.execute(select(model.owner_id).where(model.id == uuid.UUID(str(item_id))))).first()
        return row[0] if row else None


async def _admin(kit):
    admin = await _user(kit, "admin", role=UserRole.ADMIN)
    await _login(kit, "admin")
    return admin


async def test_private_content_goes_with_its_files(app_kit):
    """Only the admin can see Alice's things, and that doesn't count."""
    alice = await _user(app_kit, "alice")
    await _login(app_kit, "alice")
    piece, part = await _upload(app_kit, "Diary")
    setlist = await _setlist(app_kit, "Practice", piece)
    just_me = await _group(app_kit, "Just me")
    await _share_piece(app_kit, piece, just_me)  # nobody else is in it
    async with app_kit.sessionmaker() as s:
        key = (await s.execute(select(Part.storage_key))).scalar_one()
    thumb = thumbnail_key(part)

    async def png():
        yield b"png"

    await app_kit.storage.put(thumb, png())

    admin = await _admin(app_kit)
    plan = await _plan(app_kit, alice)
    assert (plan["arrangements"], plan["setlists"], plan["groups"]) == ([], [], [])
    assert plan["deleted"] == {"arrangements": 1, "setlists": 1, "groups": 1}
    assert plan["user"] == {"id": str(alice.id), "username": "alice"}

    r = await _delete(app_kit, alice)
    assert r.status_code == 204, r.text
    assert await _owner_of(app_kit, Arrangement, piece) is None
    assert await _owner_of(app_kit, Setlist, setlist) is None
    assert not await app_kit.storage.exists(key)
    assert not await app_kit.storage.exists(thumb)
    async with app_kit.sessionmaker() as s:
        names = set((await s.execute(select(User.username))).scalars())
        assert names == {"admin"}  # no placeholder account
        assert (await s.execute(select(Group))).first() is None
    assert admin.id  # still here


async def test_a_partner_inherits_by_default(app_kit):
    alice = await _user(app_kit, "alice")
    bob = await _user(app_kit, "bob")
    await _user(app_kit, "carol")
    await _login(app_kit, "alice")
    await _partner(app_kit, bob.id)
    piece, part = await _upload(app_kit, "Anthem")
    setlist = await _setlist(app_kit, "Recital", piece)

    await _admin(app_kit)
    plan = await _plan(app_kit, alice)
    [kept] = plan["arrangements"]
    assert (kept["id"], kept["seen_by"], kept["suggested_owner"]["username"]) == (piece, ["partner", "setlist"], "bob")
    [kept_setlist] = plan["setlists"]
    assert (kept_setlist["seen_by"], kept_setlist["suggested_owner"]["username"]) == (["partner"], "bob")
    assert plan["deleted"] == {"arrangements": 0, "setlists": 0, "groups": 0}
    assert [p["username"] for p in plan["partners"]] == ["bob"]

    assert (await _delete(app_kit, alice)).status_code == 204
    assert await _owner_of(app_kit, Arrangement, piece) == bob.id
    assert await _owner_of(app_kit, Setlist, setlist) == bob.id
    async with app_kit.sessionmaker() as s:
        assert (await s.execute(select(Part.uploaded_by))).scalar_one() == bob.id
        entry = (await s.execute(select(SetlistItem))).scalar_one()
        assert (entry.arrangement_id, entry.added_by) == (uuid.UUID(piece), bob.id)
    await _login(app_kit, "bob")
    r = await app_kit.client.get(f"/api/v1/setlists/{setlist}")
    assert [e["title"] for e in r.json()["items"]] == ["Anthem"]


async def test_a_setlist_only_piece_goes_to_the_setlist_owner(app_kit):
    """Carol's setlist passes Alice's piece on to Bob. Carol already holds the
    setlist, so with her as the new owner Bob keeps it."""
    alice = await _user(app_kit, "alice")
    bob = await _user(app_kit, "bob")
    carol = await _user(app_kit, "carol")
    await _login(app_kit, "carol")
    setlist = await _setlist(app_kit, "Concert")
    await _share_setlist(app_kit, setlist, user=alice, permission="contribute")
    await _share_setlist(app_kit, setlist, user=bob)
    await _login(app_kit, "alice")
    piece, _ = await _upload(app_kit, "Anthem")
    r = await app_kit.client.post(f"/api/v1/setlists/{setlist}/items", json={"arrangement_id": piece})
    assert r.status_code == 201, r.text

    await _admin(app_kit)
    plan = await _plan(app_kit, alice)
    [kept] = plan["arrangements"]
    assert (kept["seen_by"], kept["suggested_owner"]["username"]) == (["setlist"], "carol")
    [via] = kept["setlists"]
    assert (via["name"], via["owner"]["username"], via["holders"]) == ("Concert", "carol", [str(bob.id)])
    assert plan["setlists"] == []

    assert (await _delete(app_kit, alice)).status_code == 204
    assert await _owner_of(app_kit, Arrangement, piece) == carol.id
    await _login(app_kit, "bob")
    assert (await app_kit.client.get(f"/api/v1/arrangements/{piece}")).status_code == 200


async def test_groups_move_to_a_member_and_keep_their_shares(app_kit):
    alice = await _user(app_kit, "alice")
    bob = await _user(app_kit, "bob")
    carol = await _user(app_kit, "carol")
    dave = await _user(app_kit, "dave")
    await _login(app_kit, "alice")
    choir = await _group(app_kit)
    await _add(app_kit, choir, bob)
    await _add(app_kit, choir, carol)
    alices, _ = await _upload(app_kit, "Ave Maria")
    await _share_piece(app_kit, alices, choir)
    await _login(app_kit, "bob")
    bobs, _ = await _upload(app_kit, "Bob's Anthem")
    await _share_piece(app_kit, bobs, choir)

    admin = await _admin(app_kit)
    plan = await _plan(app_kit, alice)
    [group] = plan["groups"]
    assert [m["username"] for m in group["members"]] == ["bob", "carol"]
    assert group["suggested_owner"]["username"] == "bob"
    [kept] = plan["arrangements"]
    assert (kept["seen_by"], kept["suggested_owner"]["username"]) == (["group"], "admin")

    r = await _delete(app_kit, alice, groups={choir["id"]: dave.id})
    assert (r.status_code, r.json()["detail"]) == (422, "not_a_member")
    r = await _delete(app_kit, alice, groups={choir["id"]: carol.id})
    assert r.status_code == 204, r.text
    assert await _owner_of(app_kit, Group, choir["id"]) == carol.id
    assert await _owner_of(app_kit, Arrangement, alices) == admin.id
    await _login(app_kit, "carol")
    for piece in (alices, bobs):
        assert (await app_kit.client.get(f"/api/v1/arrangements/{piece}")).status_code == 200


async def test_a_shared_setlist_goes_to_the_pick_and_drops_their_share(app_kit):
    alice = await _user(app_kit, "alice")
    bob = await _user(app_kit, "bob")
    await _login(app_kit, "alice")
    setlist = await _setlist(app_kit, "Recital")
    await _share_setlist(app_kit, setlist, user=bob)

    await _admin(app_kit)
    [kept] = (await _plan(app_kit, alice))["setlists"]
    assert (kept["seen_by"], kept["suggested_owner"]["username"]) == (["share"], "admin")
    assert (await _delete(app_kit, alice, setlists={setlist: bob.id})).status_code == 204
    assert await _owner_of(app_kit, Setlist, setlist) == bob.id
    async with app_kit.sessionmaker() as s:
        assert (await s.execute(select(SetlistShare))).first() is None


async def test_deleted_pieces_on_others_setlists_become_deleted_entries(app_kit):
    """Alice's piece stopped reaching Carol's setlist when Carol unshared it,
    so it's private and goes; Carol keeps a deleted entry and its title."""
    alice = await _user(app_kit, "alice")
    await _user(app_kit, "carol")
    await _login(app_kit, "carol")
    setlist = await _setlist(app_kit, "Concert")
    share = await _share_setlist(app_kit, setlist, user=alice, permission="contribute")
    await _login(app_kit, "alice")
    piece, _ = await _upload(app_kit, "Anthem")
    await app_kit.client.post(f"/api/v1/setlists/{setlist}/items", json={"arrangement_id": piece})
    await _login(app_kit, "carol")
    r = await app_kit.client.delete(f"/api/v1/setlists/{setlist}/shares/{share.json()[0]['id']}")
    assert r.status_code == 204, r.text

    await _admin(app_kit)
    assert (await _plan(app_kit, alice))["deleted"]["arrangements"] == 1
    assert (await _delete(app_kit, alice)).status_code == 204
    await _login(app_kit, "carol")
    [entry] = (await app_kit.client.get(f"/api/v1/setlists/{setlist}")).json()["items"]
    assert (entry["removed"], entry["title"], entry["removed_by"]) == ("deleted", "Anthem", None)


async def test_shared_after_the_plan_is_kept(app_kit):
    """The delete decides again: a piece the dialog called private but that
    was shared since is kept, with its default owner."""
    alice = await _user(app_kit, "alice")
    bob = await _user(app_kit, "bob")
    await _login(app_kit, "alice")
    piece, _ = await _upload(app_kit, "Anthem")
    await _admin(app_kit)
    assert (await _plan(app_kit, alice))["deleted"]["arrangements"] == 1

    await _login(app_kit, "alice")
    await _partner(app_kit, bob.id)
    await _login(app_kit, "admin")
    assert (await _delete(app_kit, alice)).status_code == 204
    assert await _owner_of(app_kit, Arrangement, piece) == bob.id


async def test_a_pick_keeps_a_private_piece(app_kit):
    alice = await _user(app_kit, "alice")
    await _login(app_kit, "alice")
    piece, _ = await _upload(app_kit, "Diary")
    admin = await _admin(app_kit)
    assert (await _delete(app_kit, alice, arrangements={piece: admin.id})).status_code == 204
    assert await _owner_of(app_kit, Arrangement, piece) == admin.id


async def test_a_piece_added_while_deleting_is_decided_after_it_lands(app_kit):
    """An add to Carol's shared setlist is in flight when the delete starts.
    The delete waits for it, then sees the piece reaches Bob and keeps it."""
    alice = await _user(app_kit, "alice")
    bob = await _user(app_kit, "bob")
    carol = await _user(app_kit, "carol")
    await _login(app_kit, "carol")
    setlist = await _setlist(app_kit, "Concert")
    await _share_setlist(app_kit, setlist, user=alice, permission="contribute")
    await _share_setlist(app_kit, setlist, user=bob)
    await _login(app_kit, "alice")
    piece, _ = await _upload(app_kit, "Anthem")
    await _admin(app_kit)

    async with app_kit.sessionmaker() as adding:
        adding.add(
            SetlistItem(
                setlist_id=uuid.UUID(setlist), position=0, arrangement_id=uuid.UUID(piece), added_by=alice.id
            )
        )
        await adding.flush()  # key-share locks on the piece and on Alice
        deleting = asyncio.create_task(_delete(app_kit, alice))
        await asyncio.sleep(0.5)
        assert not deleting.done()
        await adding.commit()
    assert (await deleting).status_code == 204
    assert await _owner_of(app_kit, Arrangement, piece) == carol.id


async def test_parts_and_tags_on_others_pieces_stay(app_kit):
    """Alice added a part and a tag to Bob's piece. They stay, credited to Bob.
    (The tag's key on its adder used to make the delete fail.)"""
    alice = await _user(app_kit, "alice")
    bob = await _user(app_kit, "bob")
    await _login(app_kit, "bob")
    await _partner(app_kit, alice.id)
    piece, _ = await _upload(app_kit, "Bob's Anthem")
    await _login(app_kit, "alice")
    r = await app_kit.client.post(
        f"/api/v1/arrangements/{piece}/parts",
        files={"file": ("cello.pdf", make_pdf(pages=1), "application/pdf")},
        data={"part_type": "Other", "instrument": "Cello"},
    )
    assert r.status_code == 201, r.text
    async with app_kit.sessionmaker() as s:
        tag = Tag(name="hymn")
        s.add(tag)
        await s.flush()
        s.add(ArrangementTag(arrangement_id=uuid.UUID(piece), tag_id=tag.id, added_by=alice.id))
        await s.commit()

    await _admin(app_kit)
    assert (await _delete(app_kit, alice)).status_code == 204
    async with app_kit.sessionmaker() as s:
        assert set((await s.execute(select(Part.uploaded_by))).scalars()) == {bob.id}
        assert (await s.execute(select(ArrangementTag.added_by))).scalar_one() == bob.id


async def test_refusals(app_kit, monkeypatch):
    alice = await _user(app_kit, "alice")
    bob = await _user(app_kit, "bob")
    root = await _user(app_kit, "root", role=UserRole.ADMIN)
    tombstone = await _user(app_kit, "__deleted__")
    await _login(app_kit, "bob")
    bobs, _ = await _upload(app_kit, "Bob's Anthem")
    r = await app_kit.client.get(f"{USERS}/{alice.id}/deletion-plan")
    assert r.status_code == 403
    assert (await _delete(app_kit, alice)).status_code == 403

    admin = await _admin(app_kit)
    for path in [f"{USERS}/{admin.id}/deletion-plan", f"{USERS}/{admin.id}"]:
        r = await app_kit.client.request("GET" if "plan" in path else "DELETE", path)
        assert (r.status_code, r.json()["detail"]) == (409, "cannot_delete_self")
    assert (await _delete(app_kit, tombstone)).status_code == 404
    monkeypatch.setenv("OPENCLEF_ADMIN_USER", "root")
    r = await _delete(app_kit, root)
    assert (r.status_code, r.json()["detail"]) == (409, "cannot_delete_break_glass")

    # Owners must be the account's items, going to real other accounts.
    r = await _delete(app_kit, alice, arrangements={bobs: admin.id})
    assert (r.status_code, r.json()["detail"]) == (422, "item_not_found")
    await _login(app_kit, "alice")
    piece, _ = await _upload(app_kit, "Anthem")
    await _login(app_kit, "admin")
    for new_owner in (alice.id, tombstone.id, uuid.uuid4()):
        r = await _delete(app_kit, alice, arrangements={piece: new_owner})
        assert (r.status_code, r.json()["detail"]) == (422, "user_not_found")
    r = await _delete(app_kit, alice, groups={uuid.uuid4(): bob.id})
    assert (r.status_code, r.json()["detail"]) == (422, "group_not_found")
    # Nothing happened.
    assert await _owner_of(app_kit, Arrangement, piece) == alice.id


async def test_a_piece_follows_the_pick_for_its_setlist(app_kit):
    """Alice's piece reaches Bob only through her own setlist. Picking Carol
    for the setlist and nothing for the piece sends the piece to Carol too,
    so Bob keeps it."""
    alice = await _user(app_kit, "alice")
    bob = await _user(app_kit, "bob")
    carol = await _user(app_kit, "carol")
    await _login(app_kit, "alice")
    piece, _ = await _upload(app_kit, "Anthem")
    setlist = await _setlist(app_kit, "Recital", piece)
    await _share_setlist(app_kit, setlist, user=bob)

    await _admin(app_kit)
    [kept] = (await _plan(app_kit, alice))["arrangements"]
    assert (kept["seen_by"], kept["suggested_owner"]["username"]) == (["setlist"], "admin")
    [via] = kept["setlists"]
    assert (via["owner"], via["holders"]) == (None, [str(bob.id)])
    assert (await _delete(app_kit, alice, setlists={setlist: carol.id})).status_code == 204
    assert await _owner_of(app_kit, Arrangement, piece) == carol.id
    await _login(app_kit, "bob")
    assert (await app_kit.client.get(f"/api/v1/arrangements/{piece}")).status_code == 200
