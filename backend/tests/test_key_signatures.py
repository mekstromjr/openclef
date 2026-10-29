"""The key_signature DB enum and the Python enum stay identical, in order."""
from __future__ import annotations

import json

from sqlalchemy import text

from openclef.auth.hashing import hash_password
from openclef.models.enums import KeySignature
from openclef.models.user import User
from tests.pdf_fixtures import make_pdf


async def test_db_enum_matches_python_enum_in_order(session):
    labels = (
        await session.execute(text("SELECT unnest(enum_range(NULL::key_signature))::text"))
    ).scalars().all()
    assert labels == [key.value for key in KeySignature]
    assert len([key for key in KeySignature if key.value.endswith(("major", "minor"))]) == 30


async def test_upload_in_g_flat_major(app_kit):
    async with app_kit.sessionmaker() as s:
        s.add(User(username="member", password_hash=hash_password("hunter2hunter2")))
        await s.commit()
    r = await app_kit.client.post(
        "/api/v1/auth/login", json={"username": "member", "password": "hunter2hunter2"}
    )
    assert r.status_code == 200
    r = await app_kit.client.post(
        "/api/v1/arrangements/upload",
        files={"file": ("impromptu.pdf", make_pdf(), "application/pdf")},
        data={"metadata": json.dumps({"title": "Impromptu", "key_signature": "Gb major"})},
    )
    assert r.status_code == 201, r.text
    assert r.json()["arrangement"]["key_signature"] == "Gb major"
    listing = await app_kit.client.get("/api/v1/arrangements", params={"key": "Gb major"})
    assert [item["title"] for item in listing.json()["items"]] == ["Impromptu"]
