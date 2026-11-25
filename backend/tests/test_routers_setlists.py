"""/api/v1/setlists: shared running orders of pieces."""
from __future__ import annotations

import json
import uuid

from openclef.auth.hashing import hash_password
from openclef.models.enums import UserRole
from openclef.models.setlist import SetlistItem
from openclef.models.user import User
from tests.pdf_fixtures import make_pdf
from tests.sharing import share_library, share_setlist

PASSWORD = "hunter2hunter2"
BASE = "/api/v1/setlists"


async def _user(kit, username, role=UserRole.USER):
    async with kit.sessionmaker() as s:
        user = User(username=username, password_hash=hash_password(PASSWORD), role=role)
        s.add(user)
        await s.commit()
        return user


async def _login(kit, username):
    r = await kit.client.post("/api/v1/auth/login", json={"username": username, "password": PASSWORD})
    assert r.status_code == 200


async def _piece(kit, title, *, extra_part=None):
    """Upload a piece; optionally add a second part. Returns (arrangement_id, [part ids])."""
    r = await kit.client.post(
        "/api/v1/arrangements/upload",
        files={"file": ("score.pdf", make_pdf(pages=2), "application/pdf")},
        data={"metadata": json.dumps({"title": title, "composer": ["Composer"]})},
    )
    assert r.status_code == 201, r.text
    arrangement_id = r.json()["arrangement"]["id"]
    part_ids = [r.json()["part"]["id"]]
    if extra_part:
        r = await kit.client.post(
            f"/api/v1/arrangements/{arrangement_id}/parts",
            files={"file": ("part.pdf", make_pdf(pages=3), "application/pdf")},
            data={"instrument": extra_part},
        )
        assert r.status_code == 201, r.text
        part_ids.append(r.json()["id"])
    return arrangement_id, part_ids


async def _setlist(kit, name="Sunday"):
    r = await kit.client.post(BASE, json={"name": name})
    assert r.status_code == 201, r.text
    return r.json()


async def test_create_list_and_get(app_kit):
    await _user(app_kit, "owner")
    await _login(app_kit, "owner")
    created = await _setlist(app_kit, "  Sunday service  ")
    assert created["name"] == "Sunday service"
    assert created["owner_username"] == "owner"
    assert created["items"] == [] and created["can_edit"] is True

    listing = (await app_kit.client.get(BASE)).json()
    assert [(s["name"], s["item_count"]) for s in listing] == [("Sunday service", 0)]
    assert (await app_kit.client.get(f"{BASE}/{created['id']}")).json()["id"] == created["id"]
    assert (await app_kit.client.get(f"{BASE}/{uuid.uuid4()}")).status_code == 404


async def test_requires_sign_in(app_kit):
    assert (await app_kit.client.get(BASE)).status_code == 401


async def test_replace_items_orders_resolves_parts_and_allows_repeats(app_kit):
    await _user(app_kit, "owner")
    await _login(app_kit, "owner")
    hymn, _ = await _piece(app_kit, "Opening hymn")
    trio, (score, cello) = await _piece(app_kit, "Trio", extra_part="Cello")
    setlist = await _setlist(app_kit)

    r = await app_kit.client.put(
        f"{BASE}/{setlist['id']}/items",
        json={
            "entries": [
                {"arrangement_id": hymn},
                {"arrangement_id": trio, "part_id": cello},
                {"arrangement_id": hymn},
            ]
        },
    )
    assert r.status_code == 200, r.text
    items = r.json()["items"]
    assert [(i["position"], i["title"]) for i in items] == [
        (0, "Opening hymn"), (1, "Trio"), (2, "Opening hymn"),
    ]
    # No part chosen opens the cover; a chosen part opens that part.
    assert items[0]["part_id"] is None and items[0]["part_label"] == "Full Score"
    assert items[1]["effective_part_id"] == cello and items[1]["part_label"] == "Cello"
    assert items[1]["page_count"] == 3

    # Reorder by saving again: the old rows are replaced, not merged.
    r = await app_kit.client.put(
        f"{BASE}/{setlist['id']}/items",
        json={"entries": [{"arrangement_id": trio, "part_id": score}, {"arrangement_id": hymn}]},
    )
    assert [i["title"] for i in r.json()["items"]] == ["Trio", "Opening hymn"]
    assert (await app_kit.client.get(BASE)).json()[0]["item_count"] == 2


async def test_append_adds_to_the_end(app_kit):
    await _user(app_kit, "owner")
    await _login(app_kit, "owner")
    first, _ = await _piece(app_kit, "First")
    second, _ = await _piece(app_kit, "Second")
    setlist = await _setlist(app_kit)
    for arrangement_id in (first, second, first):
        r = await app_kit.client.post(f"{BASE}/{setlist['id']}/items", json={"arrangement_id": arrangement_id})
        assert r.status_code == 201, r.text
    assert [i["title"] for i in r.json()["items"]] == ["First", "Second", "First"]
    assert [i["position"] for i in r.json()["items"]] == [0, 1, 2]


async def test_rejects_unknown_piece_and_foreign_part(app_kit):
    await _user(app_kit, "owner")
    await _login(app_kit, "owner")
    piece, _ = await _piece(app_kit, "Mine")
    other, (other_part,) = await _piece(app_kit, "Other")
    setlist = await _setlist(app_kit)
    url = f"{BASE}/{setlist['id']}/items"

    r = await app_kit.client.put(url, json={"entries": [{"arrangement_id": str(uuid.uuid4())}]})
    assert (r.status_code, r.json()["detail"]) == (422, "arrangement_not_found")
    r = await app_kit.client.put(url, json={"entries": [{"arrangement_id": piece, "part_id": other_part}]})
    assert (r.status_code, r.json()["detail"]) == (422, "part_not_in_arrangement")
    r = await app_kit.client.put(url, json={"entries": [{"arrangement_id": piece, "surprise": 1}]})
    assert r.status_code == 422
    assert (await app_kit.client.get(f"{BASE}/{setlist['id']}")).json()["items"] == []


async def test_partners_can_read_but_only_owner_or_admin_can_change(app_kit):
    owner = await _user(app_kit, "owner")
    await _login(app_kit, "owner")
    piece, _ = await _piece(app_kit, "Piece")
    setlist = await _setlist(app_kit)
    sid = setlist["id"]

    member = await _user(app_kit, "member")
    await share_library(app_kit, owner.id, member.id)
    await _login(app_kit, "member")
    seen = (await app_kit.client.get(f"{BASE}/{sid}")).json()
    assert seen["name"] == "Sunday" and seen["can_edit"] is False
    assert (await app_kit.client.patch(f"{BASE}/{sid}", json={"name": "Mine now"})).status_code == 403
    assert (await app_kit.client.put(f"{BASE}/{sid}/items", json={"entries": []})).status_code == 403
    assert (await app_kit.client.post(f"{BASE}/{sid}/items", json={"arrangement_id": piece})).status_code == 403
    assert (await app_kit.client.delete(f"{BASE}/{sid}")).status_code == 403

    await _user(app_kit, "boss", role=UserRole.ADMIN)
    await _login(app_kit, "boss")
    assert (await app_kit.client.get(f"{BASE}/{sid}")).json()["can_edit"] is True
    r = await app_kit.client.patch(f"{BASE}/{sid}", json={"name": "Renamed by admin"})
    assert r.status_code == 200 and r.json()["name"] == "Renamed by admin"
    assert (await app_kit.client.delete(f"{BASE}/{sid}")).status_code == 204
    assert (await app_kit.client.get(f"{BASE}/{sid}")).status_code == 404


async def test_stale_version_is_rejected(app_kit):
    await _user(app_kit, "owner")
    await _login(app_kit, "owner")
    piece, _ = await _piece(app_kit, "Piece")
    loaded = await _setlist(app_kit)
    sid, version = loaded["id"], loaded["updated_at"]

    # Another tab saves first, which moves the version on.
    r = await app_kit.client.put(f"{BASE}/{sid}/items", json={"entries": [{"arrangement_id": piece}], "expected_updated_at": version})
    assert r.status_code == 200, r.text
    assert r.json()["updated_at"] != version

    stale = await app_kit.client.put(f"{BASE}/{sid}/items", json={"entries": [], "expected_updated_at": version})
    assert (stale.status_code, stale.json()["detail"]) == (409, "setlist_changed")
    stale = await app_kit.client.patch(f"{BASE}/{sid}", json={"name": "X", "expected_updated_at": version})
    assert stale.status_code == 409
    assert len((await app_kit.client.get(f"{BASE}/{sid}")).json()["items"]) == 1


async def test_deleted_part_falls_back_to_cover(app_kit):
    await _user(app_kit, "owner")
    await _login(app_kit, "owner")
    trio, (_, cello) = await _piece(app_kit, "Trio", extra_part="Cello")
    setlist = await _setlist(app_kit)
    await app_kit.client.put(f"{BASE}/{setlist['id']}/items", json={"entries": [{"arrangement_id": trio, "part_id": cello}]})

    assert (await app_kit.client.delete(f"/api/v1/arrangements/{trio}/parts/{cello}")).status_code == 204
    item = (await app_kit.client.get(f"{BASE}/{setlist['id']}")).json()["items"][0]
    assert item["part_id"] is None and item["part_label"] == "Full Score"


async def test_deleting_a_piece_leaves_a_deleted_entry(app_kit):
    owner = await _user(app_kit, "owner")
    await _login(app_kit, "owner")
    piece, (part,) = await _piece(app_kit, "Piece")
    keep, _ = await _piece(app_kit, "Keep")
    setlist = await _setlist(app_kit, "Recital")
    url = f"{BASE}/{setlist['id']}/items"
    await app_kit.client.post(url, json={"arrangement_id": piece, "part_id": part})
    await app_kit.client.post(url, json={"arrangement_id": keep})

    detail = (await app_kit.client.get(f"/api/v1/arrangements/{piece}")).json()
    assert detail["setlists"] == [{"id": setlist["id"], "name": "Recital"}]
    # The title recorded is the one it has when deleted.
    await app_kit.client.patch(f"/api/v1/arrangements/{piece}", json={"title": "Renamed piece"})
    assert (await app_kit.client.delete(f"/api/v1/arrangements/{piece}")).status_code == 204

    gone, kept = (await app_kit.client.get(f"{BASE}/{setlist['id']}")).json()["items"]
    assert (gone["available"], gone["removed"], gone["title"], gone["removed_by"]) == (
        False, "deleted", "Renamed piece", "owner",
    )
    assert gone["arrangement_id"] is None and gone["part_id"] is None
    assert kept["title"] == "Keep" and kept["available"]
    async with app_kit.sessionmaker() as s:
        row = await s.get(SetlistItem, (uuid.UUID(setlist["id"]), 0))
        assert (row.deleted_by, row.piece_owner_id, row.deleted_at is not None) == (owner.id, owner.id, True)

    # A deleted entry can be moved, can't take a part, and goes when left out.
    r = await app_kit.client.put(url, json={"entries": [{"id": kept["id"]}, {"id": gone["id"]}]})
    assert [entry["removed"] for entry in r.json()["items"]] == [None, "deleted"]
    r = await app_kit.client.put(url, json={"entries": [{"id": gone["id"], "part_id": None}]})
    assert (r.status_code, r.json()["detail"]) == (422, "item_hidden")
    r = await app_kit.client.put(url, json={"entries": [{"id": kept["id"]}]})
    assert [entry["title"] for entry in r.json()["items"]] == ["Keep"]


async def test_a_deleted_entry_is_named_only_to_those_who_saw_it(app_kit):
    """The audience saw a piece the setlist's owner added from their own
    library; a piece lent to the owner never reached them."""
    lender = await _user(app_kit, "lender")
    await _login(app_kit, "lender")
    lent, _ = await _piece(app_kit, "Lent piece")
    owner = await _user(app_kit, "owner")
    await share_library(app_kit, lender.id, owner.id)
    await _login(app_kit, "owner")
    own, _ = await _piece(app_kit, "Own piece")
    setlist = await _setlist(app_kit, "Recital")
    for piece in (own, lent):
        await app_kit.client.post(f"{BASE}/{setlist['id']}/items", json={"arrangement_id": piece})
    audience = await _user(app_kit, "audience")
    await share_setlist(app_kit, uuid.UUID(setlist["id"]), user_id=audience.id)

    assert (await app_kit.client.delete(f"/api/v1/arrangements/{own}")).status_code == 204
    await _login(app_kit, "lender")
    assert (await app_kit.client.delete(f"/api/v1/arrangements/{lent}")).status_code == 204

    await _login(app_kit, "audience")
    r = await app_kit.client.get(f"{BASE}/{setlist['id']}")
    own_entry, lent_entry = r.json()["items"]
    assert (own_entry["removed"], own_entry["title"], own_entry["removed_by"]) == ("deleted", "Own piece", "owner")
    assert (lent_entry["removed"], lent_entry["title"], lent_entry["removed_by"]) == (None, None, None)
    assert "Lent piece" not in r.text and "lender" not in r.text

    await _login(app_kit, "owner")
    lent_entry = (await app_kit.client.get(f"{BASE}/{setlist['id']}")).json()["items"][1]
    assert (lent_entry["removed"], lent_entry["title"], lent_entry["removed_by"]) == ("deleted", "Lent piece", "lender")


async def test_an_add_in_flight_is_marked_by_the_delete(app_kit):
    """An add that hasn't committed when the delete starts: the delete waits
    for it (its lock on the piece), then marks that entry too, instead of
    failing on the RESTRICT key."""
    import asyncio

    owner = await _user(app_kit, "owner")
    await _login(app_kit, "owner")
    piece, _ = await _piece(app_kit, "Piece")
    setlist = await _setlist(app_kit)

    async with app_kit.sessionmaker() as adding:
        adding.add(
            SetlistItem(
                setlist_id=uuid.UUID(setlist["id"]), position=0, arrangement_id=uuid.UUID(piece), added_by=owner.id
            )
        )
        await adding.flush()  # holds a key-share lock on the piece, not committed
        deleting = asyncio.create_task(app_kit.client.delete(f"/api/v1/arrangements/{piece}"))
        await asyncio.sleep(0.5)
        assert not deleting.done()
        await adding.commit()
    assert (await deleting).status_code == 204
    [entry] = (await app_kit.client.get(f"{BASE}/{setlist['id']}")).json()["items"]
    assert (entry["removed"], entry["title"]) == ("deleted", "Piece")


async def test_a_rename_in_flight_is_the_title_recorded(app_kit):
    """The title is read from the locked row, so a rename that commits while
    the delete waits is the one its entries keep."""
    import asyncio

    from sqlalchemy import text

    await _user(app_kit, "owner")
    await _login(app_kit, "owner")
    piece, _ = await _piece(app_kit, "Old title")
    setlist = await _setlist(app_kit)
    await app_kit.client.post(f"{BASE}/{setlist['id']}/items", json={"arrangement_id": piece})

    async with app_kit.sessionmaker() as renaming:
        await renaming.execute(text("UPDATE arrangements SET title = 'New title' WHERE id = :id"), {"id": piece})
        deleting = asyncio.create_task(app_kit.client.delete(f"/api/v1/arrangements/{piece}"))
        await asyncio.sleep(0.5)
        await renaming.commit()
    assert (await deleting).status_code == 204
    [entry] = (await app_kit.client.get(f"{BASE}/{setlist['id']}")).json()["items"]
    assert entry["title"] == "New title"


async def test_item_limit(app_kit):
    await _user(app_kit, "owner")
    await _login(app_kit, "owner")
    piece, _ = await _piece(app_kit, "Piece")
    setlist = await _setlist(app_kit)
    url = f"{BASE}/{setlist['id']}/items"
    r = await app_kit.client.put(url, json={"entries": [{"arrangement_id": piece}] * 201})
    assert r.status_code == 422
    assert (await app_kit.client.put(url, json={"entries": [{"arrangement_id": piece}] * 200})).status_code == 200
    r = await app_kit.client.post(url, json={"arrangement_id": piece})
    assert (r.status_code, r.json()["detail"]) == (422, "setlist_full")


async def test_concurrent_appends_get_distinct_positions(app_kit):
    """The row lock serializes appends; without it both would claim one position."""
    import asyncio

    await _user(app_kit, "owner")
    await _login(app_kit, "owner")
    piece, _ = await _piece(app_kit, "Piece")
    setlist = await _setlist(app_kit)
    url = f"{BASE}/{setlist['id']}/items"
    responses = await asyncio.gather(
        *(app_kit.client.post(url, json={"arrangement_id": piece}) for _ in range(5))
    )
    assert sorted(r.status_code for r in responses) == [201] * 5
    items = (await app_kit.client.get(f"{BASE}/{setlist['id']}")).json()["items"]
    assert [i["position"] for i in items] == [0, 1, 2, 3, 4]
