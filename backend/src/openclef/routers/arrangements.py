"""Arrangement uploads and Part management (TRD §5.1).

The HTTP request only validates the PDF, stores it, and writes the rows.
Thumbnail rendering (and, later, enrichment) happens in the worker, so
an upload returns as soon as the file is safely stored.
"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Annotated

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from openclef.auth.deps import get_current_user
from openclef.config import get_settings
from openclef.db import get_session
from openclef.models.enrichment import EnrichmentJob
from openclef.models.enums import EnrichmentJobStatus, PartType, UserRole
from openclef.models.library import Arrangement, Part
from openclef.models.user import User, UserSettings
from openclef.routers._deps import get_storage
from openclef.schemas import (
    ArrangementRead,
    ArrangementUploadMetadata,
    PartRead,
    UploadResponse,
)
from openclef.services.pdf_meta import InvalidPdfError
from openclef.services.uploads import (
    CheckedUpload,
    NotPdfError,
    UploadTooLargeError,
    check_upload,
    score_key,
    store_upload,
    thumbnail_key,
)
from openclef.storage import Storage
from openclef.workers.tasks import render_thumbnail

log = structlog.get_logger()
router = APIRouter(prefix="/api/v1/arrangements", tags=["arrangements"])

CurrentUser = Annotated[User, Depends(get_current_user)]
DbSession = Annotated[AsyncSession, Depends(get_session)]
StorageDep = Annotated[Storage, Depends(get_storage)]


async def _checked(file: UploadFile) -> CheckedUpload:
    settings = get_settings()
    try:
        return await check_upload(
            file,
            max_bytes=settings.max_upload_mb * 1024 * 1024,
            chunk_bytes=settings.upload_chunk_bytes,
        )
    except UploadTooLargeError:
        raise HTTPException(status_code=413, detail="upload_too_large") from None
    except NotPdfError:
        raise HTTPException(status_code=415, detail="not_a_pdf") from None
    except InvalidPdfError:
        raise HTTPException(status_code=415, detail="unreadable_pdf") from None


async def _store(file: UploadFile, storage: Storage, key: str) -> None:
    await store_upload(file, storage, key, chunk_bytes=get_settings().upload_chunk_bytes)


async def _delete_quietly(storage: Storage, *keys: str | None) -> None:
    for key in keys:
        if not key:
            continue
        try:
            await storage.delete(key)
        except Exception as exc:  # orphaned blob is harmless; a failed request isn't
            log.warning("openclef.storage.delete_failed", key=key, error=str(exc))


async def _enqueue_thumbnail(part_id: uuid.UUID) -> None:
    """Queue the render after the Part row is committed. A failed enqueue
    only means no thumbnail yet; the thumbnail endpoint 404s cleanly."""
    try:
        await run_in_threadpool(render_thumbnail.send, str(part_id))
    except Exception as exc:
        log.warning("openclef.thumbnail.enqueue_failed", part_id=str(part_id), error=str(exc))


async def _enrichment_default(db: AsyncSession, user: User) -> bool:
    enabled = (
        await db.execute(
            select(UserSettings.enrichment_default_enabled).where(UserSettings.user_id == user.id)
        )
    ).scalar_one_or_none()
    return bool(enabled)


def _part_label(label: str | None, instrument: str | None, part_type: PartType) -> str:
    label = (label or "").strip()
    if label:
        return label
    if instrument and instrument.strip():
        return instrument.strip()
    return part_type.value


@router.post("/upload", response_model=UploadResponse, status_code=201)
async def upload_arrangement(
    user: CurrentUser,
    db: DbSession,
    storage: StorageDep,
    file: Annotated[UploadFile, File()],
    metadata: Annotated[str | None, Form()] = None,
    part_type: Annotated[PartType, Form()] = PartType.FULL_SCORE,
    label: Annotated[str | None, Form()] = None,
    instrument: Annotated[str | None, Form()] = None,
    enrich: Annotated[bool | None, Form()] = None,
) -> UploadResponse:
    """Create an Arrangement with its first Part from one PDF.

    `metadata` is a JSON object of Arrangement fields; anything the user
    sets wins over what the PDF declares. Omitted `enrich` falls back to
    the user's enrichment default (off unless they turned it on).
    """
    try:
        meta = ArrangementUploadMetadata.model_validate_json(metadata or "{}")
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors(include_url=False)) from None
    checked = await _checked(file)

    fields = meta.model_dump(exclude_unset=True)
    origins = {name: "user" for name in fields}
    if not fields.get("title"):
        if checked.pdf.title:
            fields["title"], origins["title"] = checked.pdf.title, "pdf"
        else:
            fields["title"] = Path(file.filename or "").stem or "Untitled"
            origins["title"] = "filename"
    if not fields.get("composer") and checked.pdf.author:
        fields["composer"], origins["composer"] = [checked.pdf.author], "pdf"

    arrangement_id, part_id = uuid.uuid4(), uuid.uuid4()
    key = score_key(arrangement_id, part_id)
    await _store(file, storage, key)

    arrangement = Arrangement(
        id=arrangement_id,
        created_by=user.id,
        source_metadata_jsonb={"pdf_info": checked.pdf.raw} if checked.pdf.raw else None,
        field_origins_jsonb=origins,
        **fields,
    )
    part = Part(
        id=part_id,
        arrangement_id=arrangement_id,
        part_type=part_type,
        label=_part_label(label, instrument, part_type),
        instrument=(instrument or "").strip() or None,
        page_count=checked.pdf.page_count,
        file_size_bytes=checked.size_bytes,
        storage_key=key,
        file_hash_sha256=checked.sha256,
        uploaded_by=user.id,
    )
    db.add(arrangement)
    db.add(part)
    enrichment_job = None
    if enrich if enrich is not None else await _enrichment_default(db, user):
        # EnrichmentJob has no ORM relationship to Arrangement, so the unit
        # of work can't order the inserts by itself: flush the parent first.
        await db.flush()
        # Picked up by the enrichment worker (MusicBrainz) once it exists.
        enrichment_job = EnrichmentJob(
            arrangement_id=arrangement_id, status=EnrichmentJobStatus.PENDING
        )
        db.add(enrichment_job)
    try:
        await db.commit()
    except Exception:
        await _delete_quietly(storage, key)
        raise

    await _enqueue_thumbnail(part_id)
    await db.refresh(arrangement)
    await db.refresh(part)
    return UploadResponse(
        arrangement=ArrangementRead.model_validate(arrangement),
        part=PartRead.model_validate(part),
        enrichment_job_id=enrichment_job.id if enrichment_job else None,
    )


@router.post("/{arrangement_id}/parts", response_model=PartRead, status_code=201)
async def add_part(
    arrangement_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    storage: StorageDep,
    file: Annotated[UploadFile, File()],
    part_type: Annotated[PartType, Form()] = PartType.OTHER,
    label: Annotated[str | None, Form()] = None,
    instrument: Annotated[str | None, Form()] = None,
) -> PartRead:
    """Add another Part (e.g. the cello part) to an existing Arrangement."""
    exists = (
        await db.execute(select(Arrangement.id).where(Arrangement.id == arrangement_id))
    ).scalar_one_or_none()
    if exists is None:
        raise HTTPException(status_code=404, detail="arrangement_not_found")
    checked = await _checked(file)

    part_id = uuid.uuid4()
    key = score_key(arrangement_id, part_id)
    await _store(file, storage, key)
    part = Part(
        id=part_id,
        arrangement_id=arrangement_id,
        part_type=part_type,
        label=_part_label(label, instrument, part_type),
        instrument=(instrument or "").strip() or None,
        page_count=checked.pdf.page_count,
        file_size_bytes=checked.size_bytes,
        storage_key=key,
        file_hash_sha256=checked.sha256,
        uploaded_by=user.id,
    )
    db.add(part)
    try:
        await db.commit()
    except Exception:
        await _delete_quietly(storage, key)
        raise
    await _enqueue_thumbnail(part_id)
    await db.refresh(part)
    return PartRead.model_validate(part)


@router.delete("/{arrangement_id}/parts/{part_id}", status_code=204)
async def delete_part(
    arrangement_id: uuid.UUID,
    part_id: uuid.UUID,
    user: CurrentUser,
    db: DbSession,
    storage: StorageDep,
) -> Response:
    """Remove a Part and its files. Allowed for the uploader or an admin.
    The row goes first; a failed blob delete only leaves an orphan."""
    part = (
        await db.execute(
            select(Part).where(Part.id == part_id, Part.arrangement_id == arrangement_id)
        )
    ).scalar_one_or_none()
    if part is None:
        raise HTTPException(status_code=404, detail="part_not_found")
    if part.uploaded_by != user.id and user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="not_part_owner")
    keys = (part.storage_key, part.thumbnail_storage_key or thumbnail_key(part_id))
    await db.delete(part)
    await db.commit()
    await _delete_quietly(storage, *keys)
    return Response(status_code=204)
