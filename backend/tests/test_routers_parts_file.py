"""GET /api/v1/parts/{id}/file and /thumbnail, plus the thumbnail worker."""
from __future__ import annotations

import uuid

import dramatiq
from sqlalchemy import select

from openclef.auth.hashing import hash_password
from openclef.models.library import Part
from openclef.models.user import User
from openclef.routers.parts import content_disposition
from openclef.workers import broker
from openclef.workers.tasks import generate_thumbnail
from tests.pdf_fixtures import make_pdf

PASSWORD = "hunter2hunter2"


async def _signed_in_upload(kit, pdf: bytes, **form):
    async with kit.sessionmaker() as s:
        s.add(User(username="member", password_hash=hash_password(PASSWORD)))
        await s.commit()
    r = await kit.client.post(
        "/api/v1/auth/login", json={"username": "member", "password": PASSWORD}
    )
    assert r.status_code == 200
    r = await kit.client.post(
        "/api/v1/arrangements/upload",
        files={"file": ("score.pdf", pdf, "application/pdf")},
        data={key: str(value) for key, value in form.items()},
    )
    assert r.status_code == 201, r.text
    return r.json()["part"]


async def test_file_streams_original_bytes_inline(app_kit):
    pdf = make_pdf(pages=2)
    part = await _signed_in_upload(app_kit, pdf)
    r = await app_kit.client.get(f"/api/v1/parts/{part['id']}/file")
    assert r.status_code == 200
    assert r.content == pdf
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"].startswith("inline;")


async def test_download_sets_attachment_with_utf8_name(app_kit):
    part = await _signed_in_upload(app_kit, make_pdf(), label="Für Elise")
    r = await app_kit.client.get(f"/api/v1/parts/{part['id']}/file", params={"download": "1"})
    assert r.status_code == 200
    disposition = r.headers["content-disposition"]
    assert disposition.startswith("attachment;")
    assert "filename*=UTF-8''F%C3%BCr%20Elise.pdf" in disposition


def test_content_disposition_strips_quotes_from_fallback():
    header = content_disposition("attachment", 'Say "Hi".pdf')
    assert 'filename="Say Hi.pdf"' in header


async def test_file_for_unknown_part_is_404(app_kit):
    await _signed_in_upload(app_kit, make_pdf())
    r = await app_kit.client.get(f"/api/v1/parts/{uuid.uuid4()}/file")
    assert r.status_code == 404


async def test_thumbnail_404_until_worker_runs_then_png(app_kit):
    part = await _signed_in_upload(app_kit, make_pdf(pages=3))
    r = await app_kit.client.get(f"/api/v1/parts/{part['id']}/thumbnail")
    assert r.status_code == 404
    assert r.json()["detail"] == "thumbnail_pending"

    assert await generate_thumbnail(uuid.UUID(part["id"])) is True

    r = await app_kit.client.get(f"/api/v1/parts/{part['id']}/thumbnail")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content.startswith(b"\x89PNG\r\n\x1a\n")
    async with app_kit.sessionmaker() as s:
        row = (await s.execute(select(Part))).scalar_one()
        assert row.thumbnail_storage_key == f"thumbnails/{part['id']}.png"


async def test_thumbnail_job_for_deleted_part_is_a_no_op(app_kit):
    await _signed_in_upload(app_kit, make_pdf())
    assert await generate_thumbnail(uuid.uuid4()) is False


async def test_queued_job_runs_through_dramatiq_worker(app_kit):
    part = await _signed_in_upload(app_kit, make_pdf())
    worker = dramatiq.Worker(broker, worker_threads=1, worker_timeout=100)
    worker.start()
    try:
        broker.join("thumbnails", fail_fast=True)
        worker.join()
    finally:
        worker.stop()
    async with app_kit.sessionmaker() as s:
        row = await s.get(Part, uuid.UUID(part["id"]))
        assert row.thumbnail_storage_key == f"thumbnails/{part['id']}.png"
    assert await app_kit.storage.exists(f"thumbnails/{part['id']}.png")
