"""POST /api/v1/arrangements/upload, /{id}/parts, DELETE /{id}/parts/{part_id}."""
from __future__ import annotations

import json
import uuid

from sqlalchemy import select

from openclef.auth.hashing import hash_password
from openclef.models.enrichment import EnrichmentJob
from openclef.models.enums import UserRole
from openclef.models.library import Arrangement, Part
from openclef.models.user import User
from openclef.workers import broker
from tests.pdf_fixtures import make_pdf

PASSWORD = "hunter2hunter2"


async def _seed_user(kit, username, role=UserRole.USER):
    async with kit.sessionmaker() as s:
        user = User(username=username, password_hash=hash_password(PASSWORD), role=role)
        s.add(user)
        await s.commit()
        return user


async def _login(kit, username):
    r = await kit.client.post(
        "/api/v1/auth/login", json={"username": username, "password": PASSWORD}
    )
    assert r.status_code == 200, r.text


async def _signed_in(kit, username="member", role=UserRole.USER):
    user = await _seed_user(kit, username, role)
    await _login(kit, username)
    return user


async def _upload(kit, pdf: bytes, filename="score.pdf", **form):
    data = {key: (json.dumps(value) if key == "metadata" else str(value)) for key, value in form.items()}
    return await kit.client.post(
        "/api/v1/arrangements/upload",
        files={"file": (filename, pdf, "application/pdf")},
        data=data,
    )


def _queued_thumbnail_jobs() -> list[str]:
    queue = broker.queues.get("thumbnails")
    if queue is None:
        return []
    return [json.loads(message)["args"][0] for message in list(queue.queue)]


async def test_upload_requires_login(app_kit):
    r = await _upload(app_kit, make_pdf())
    assert r.status_code == 401


async def test_single_part_upload_uses_pdf_metadata(app_kit):
    user = await _signed_in(app_kit)
    pdf = make_pdf(pages=4, title="Nocturne in E-flat", author="A. Composer")
    r = await _upload(app_kit, pdf)
    assert r.status_code == 201, r.text
    body = r.json()

    arrangement, part = body["arrangement"], body["part"]
    assert arrangement["title"] == "Nocturne in E-flat"
    assert arrangement["composer"] == ["A. Composer"]
    assert arrangement["created_by"] == str(user.id)
    assert part["page_count"] == 4
    assert part["file_size_bytes"] == len(pdf)
    assert part["part_type"] == "Full Score"
    assert part["label"] == "Full Score"
    assert part["thumbnail_storage_key"] is None
    assert part["storage_key"] == f"scores/{arrangement['id']}/{part['id']}.pdf"
    assert body["enrichment_job_id"] is None

    stored = b"".join([chunk async for chunk in await app_kit.storage.get(part["storage_key"])])
    assert stored == pdf
    assert _queued_thumbnail_jobs() == [part["id"]]

    async with app_kit.sessionmaker() as s:
        row = (await s.execute(select(Arrangement))).scalar_one()
        assert row.field_origins_jsonb == {"title": "pdf", "composer": "pdf"}
        assert row.source_metadata_jsonb["pdf_info"]["Title"] == "Nocturne in E-flat"


async def test_user_metadata_wins_over_pdf(app_kit):
    await _signed_in(app_kit)
    r = await _upload(
        app_kit,
        make_pdf(title="Embedded Title", author="Embedded Author"),
        metadata={"title": "My Title", "composer": ["Someone Else"], "key_signature": "Eb major"},
        part_type="Piano Reduction",
        label="Piano",
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["arrangement"]["title"] == "My Title"
    assert body["arrangement"]["composer"] == ["Someone Else"]
    assert body["arrangement"]["key_signature"] == "Eb major"
    assert body["part"]["part_type"] == "Piano Reduction"
    assert body["part"]["label"] == "Piano"


async def test_title_falls_back_to_filename(app_kit):
    await _signed_in(app_kit)
    r = await _upload(app_kit, make_pdf(), filename="Carol of the Bells.pdf")
    assert r.status_code == 201, r.text
    assert r.json()["arrangement"]["title"] == "Carol of the Bells"


async def test_invalid_metadata_is_422(app_kit):
    await _signed_in(app_kit)
    r = await _upload(app_kit, make_pdf(), metadata={"difficulty": 9})
    assert r.status_code == 422


async def test_non_pdf_is_rejected_and_nothing_stored(app_kit):
    await _signed_in(app_kit)
    r = await _upload(app_kit, b"PK\x03\x04 a zip file", filename="score.pdf")
    assert r.status_code == 415
    assert r.json()["detail"] == "not_a_pdf"
    async with app_kit.sessionmaker() as s:
        assert (await s.execute(select(Arrangement))).first() is None


async def test_unparseable_pdf_is_rejected(app_kit):
    await _signed_in(app_kit)
    r = await _upload(app_kit, b"%PDF-1.7\nnot actually a pdf")
    assert r.status_code == 415
    assert r.json()["detail"] == "unreadable_pdf"


async def test_size_cap_enforced_on_actual_bytes(app_kit, monkeypatch):
    monkeypatch.setenv("OPENCLEF_MAX_UPLOAD_MB", "1")
    await _signed_in(app_kit)
    pdf = make_pdf() + b"\n%" + b"x" * (1024 * 1024)
    r = await _upload(app_kit, pdf)
    assert r.status_code == 413


async def test_enrich_true_creates_pending_job(app_kit):
    await _signed_in(app_kit)
    r = await _upload(app_kit, make_pdf(title="Ave Maria"), enrich="true")
    assert r.status_code == 201, r.text
    job_id = r.json()["enrichment_job_id"]
    assert job_id is not None
    async with app_kit.sessionmaker() as s:
        job = await s.get(EnrichmentJob, uuid.UUID(job_id))
        assert job.status.value == "pending"


async def test_add_part_to_existing_arrangement(app_kit):
    await _signed_in(app_kit)
    first = (await _upload(app_kit, make_pdf(title="Trio"))).json()
    arrangement_id = first["arrangement"]["id"]
    r = await app_kit.client.post(
        f"/api/v1/arrangements/{arrangement_id}/parts",
        files={"file": ("cello.pdf", make_pdf(pages=2), "application/pdf")},
        data={"instrument": "Cello"},
    )
    assert r.status_code == 201, r.text
    part = r.json()
    assert part["arrangement_id"] == arrangement_id
    assert part["part_type"] == "Other"
    assert part["label"] == "Cello"
    assert part["page_count"] == 2
    assert _queued_thumbnail_jobs() == [first["part"]["id"], part["id"]]


async def test_add_part_to_missing_arrangement_is_404(app_kit):
    await _signed_in(app_kit)
    r = await app_kit.client.post(
        f"/api/v1/arrangements/{uuid.uuid4()}/parts",
        files={"file": ("x.pdf", make_pdf(), "application/pdf")},
    )
    assert r.status_code == 404


async def test_delete_part_by_uploader_removes_row_and_blob(app_kit):
    await _signed_in(app_kit)
    body = (await _upload(app_kit, make_pdf())).json()
    arrangement_id, part = body["arrangement"]["id"], body["part"]
    r = await app_kit.client.delete(f"/api/v1/arrangements/{arrangement_id}/parts/{part['id']}")
    assert r.status_code == 204
    assert not await app_kit.storage.exists(part["storage_key"])
    async with app_kit.sessionmaker() as s:
        assert await s.get(Part, uuid.UUID(part["id"])) is None


async def test_delete_part_by_other_member_is_forbidden(app_kit):
    await _signed_in(app_kit, "uploader")
    body = (await _upload(app_kit, make_pdf())).json()
    await _seed_user(app_kit, "other")
    await _login(app_kit, "other")
    r = await app_kit.client.delete(
        f"/api/v1/arrangements/{body['arrangement']['id']}/parts/{body['part']['id']}"
    )
    assert r.status_code == 403


async def test_admin_can_delete_any_part(app_kit):
    await _signed_in(app_kit, "uploader")
    body = (await _upload(app_kit, make_pdf())).json()
    await _seed_user(app_kit, "boss", UserRole.ADMIN)
    await _login(app_kit, "boss")
    r = await app_kit.client.delete(
        f"/api/v1/arrangements/{body['arrangement']['id']}/parts/{body['part']['id']}"
    )
    assert r.status_code == 204


async def test_size_limit_middleware_rejects_on_content_length():
    from openclef.main import UploadSizeLimit

    reached = []

    async def inner(scope, receive, send):
        reached.append(scope["path"])

    middleware = UploadSizeLimit(inner, max_bytes=10)
    sent = []

    async def send(message):
        sent.append(message)

    async def receive():
        return {"type": "http.request", "body": b""}

    big = str(10 + UploadSizeLimit.OVERHEAD_BYTES + 1).encode()
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/arrangements/upload",
        "headers": [(b"content-length", big)],
    }
    await middleware(scope, receive, send)
    assert sent[0]["status"] == 413 and reached == []

    scope["headers"] = [(b"content-length", b"5")]
    await middleware(scope, receive, send)
    assert reached == ["/api/v1/arrangements/upload"]
