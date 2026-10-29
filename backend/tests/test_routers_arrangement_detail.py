"""GET/PATCH/DELETE /api/v1/arrangements/{id}."""
from __future__ import annotations

import json
import uuid

from openclef.auth.hashing import hash_password
from openclef.models.enums import UserRole
from openclef.models.library import Part
from openclef.models.setlist import Setlist, SetlistItem
from openclef.models.user import User
from tests.pdf_fixtures import make_pdf

PASSWORD = "hunter2hunter2"


async def _user(kit, username, role=UserRole.USER):
    async with kit.sessionmaker() as s:
        user = User(username=username, password_hash=hash_password(PASSWORD), role=role)
        s.add(user)
        await s.commit()
        return user


async def _login(kit, username):
    r = await kit.client.post(
        "/api/v1/auth/login", json={"username": username, "password": PASSWORD}
    )
    assert r.status_code == 200


async def _upload(kit, title="Trio", **meta):
    r = await kit.client.post(
        "/api/v1/arrangements/upload",
        files={"file": ("score.pdf", make_pdf(pages=2), "application/pdf")},
        data={"metadata": json.dumps({"title": title, **meta})},
    )
    assert r.status_code == 201, r.text
    return r.json()


async def test_detail_includes_parts_in_upload_order(app_kit):
    await _user(app_kit, "member")
    await _login(app_kit, "member")
    body = await _upload(app_kit, instrumentation=["Piano", "Cello"])
    arrangement_id = body["arrangement"]["id"]
    r = await app_kit.client.post(
        f"/api/v1/arrangements/{arrangement_id}/parts",
        files={"file": ("cello.pdf", make_pdf(), "application/pdf")},
        data={"instrument": "Cello"},
    )
    assert r.status_code == 201

    detail = (await app_kit.client.get(f"/api/v1/arrangements/{arrangement_id}")).json()
    assert detail["title"] == "Trio"
    assert [part["label"] for part in detail["parts"]] == ["Full Score", "Cello"]
    assert detail["tags"] == []


async def test_detail_unknown_is_404(app_kit):
    await _user(app_kit, "member")
    await _login(app_kit, "member")
    r = await app_kit.client.get(f"/api/v1/arrangements/{uuid.uuid4()}")
    assert r.status_code == 404


async def test_any_member_can_edit_and_edits_are_marked_user(app_kit):
    await _user(app_kit, "uploader")
    await _login(app_kit, "uploader")
    arrangement_id = (await _upload(app_kit))["arrangement"]["id"]
    await _user(app_kit, "relative")
    await _login(app_kit, "relative")

    r = await app_kit.client.patch(
        f"/api/v1/arrangements/{arrangement_id}",
        json={"title": "Piano Trio No. 1", "key_signature": "Gb major", "difficulty": 4},
    )
    assert r.status_code == 200, r.text
    detail = r.json()
    assert detail["title"] == "Piano Trio No. 1"
    assert detail["key_signature"] == "Gb major"
    assert detail["difficulty"] == 4

    async with app_kit.sessionmaker() as s:
        from openclef.models.library import Arrangement

        row = await s.get(Arrangement, uuid.UUID(arrangement_id))
        assert row.field_origins_jsonb["key_signature"] == "user"


async def test_patch_rejects_bad_values(app_kit):
    await _user(app_kit, "member")
    await _login(app_kit, "member")
    arrangement_id = (await _upload(app_kit))["arrangement"]["id"]
    for bad in ({"title": ""}, {"difficulty": 7}, {"key_signature": "H major"}, {"nope": 1}):
        r = await app_kit.client.patch(f"/api/v1/arrangements/{arrangement_id}", json=bad)
        assert r.status_code == 422, (bad, r.text)


async def test_patch_can_clear_an_optional_field(app_kit):
    await _user(app_kit, "member")
    await _login(app_kit, "member")
    arrangement_id = (await _upload(app_kit, difficulty=3))["arrangement"]["id"]
    r = await app_kit.client.patch(f"/api/v1/arrangements/{arrangement_id}", json={"difficulty": None})
    assert r.status_code == 200
    assert r.json()["difficulty"] is None


async def test_delete_by_creator_removes_rows_and_files(app_kit):
    await _user(app_kit, "member")
    await _login(app_kit, "member")
    body = await _upload(app_kit)
    arrangement_id, part = body["arrangement"]["id"], body["part"]
    r = await app_kit.client.delete(f"/api/v1/arrangements/{arrangement_id}")
    assert r.status_code == 204
    assert (await app_kit.client.get(f"/api/v1/arrangements/{arrangement_id}")).status_code == 404
    assert not await app_kit.storage.exists(part["storage_key"])
    async with app_kit.sessionmaker() as s:
        assert await s.get(Part, uuid.UUID(part["id"])) is None


async def test_delete_by_other_member_is_forbidden_but_admin_may(app_kit):
    await _user(app_kit, "uploader")
    await _login(app_kit, "uploader")
    arrangement_id = (await _upload(app_kit))["arrangement"]["id"]
    await _user(app_kit, "relative")
    await _login(app_kit, "relative")
    assert (await app_kit.client.delete(f"/api/v1/arrangements/{arrangement_id}")).status_code == 403
    await _user(app_kit, "boss", UserRole.ADMIN)
    await _login(app_kit, "boss")
    assert (await app_kit.client.delete(f"/api/v1/arrangements/{arrangement_id}")).status_code == 204


async def test_delete_piece_on_a_setlist_is_409(app_kit):
    user = await _user(app_kit, "member")
    await _login(app_kit, "member")
    arrangement_id = (await _upload(app_kit))["arrangement"]["id"]
    async with app_kit.sessionmaker() as s:
        setlist = Setlist(name="Recital", owner_id=user.id)
        s.add(setlist)
        await s.flush()
        s.add(SetlistItem(setlist_id=setlist.id, arrangement_id=uuid.UUID(arrangement_id), position=1))
        await s.commit()
    r = await app_kit.client.delete(f"/api/v1/arrangements/{arrangement_id}")
    assert r.status_code == 409
    assert r.json()["detail"] == "on_a_setlist"
