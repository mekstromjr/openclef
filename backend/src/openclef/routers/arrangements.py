"""Arrangement uploads and Part management (TRD §5.1).

The HTTP request only validates the PDF, stores it, and writes the rows.
Thumbnail rendering (and, later, enrichment) happens in the worker, so
an upload returns as soon as the file is safely stored.
"""
from __future__ import annotations

import uuid
from enum import Enum
from pathlib import Path
from typing import Annotated, Literal

import structlog
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile
from pydantic import ValidationError
from sqlalchemy import and_, func, select
from sqlalchemy import delete as sql_delete
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from openclef.auth.deps import get_current_user
from openclef.config import get_settings
from openclef.db import get_session
from openclef.models.enrichment import EnrichmentJob
from openclef.models.enums import EnrichmentJobStatus, KeySignature, PartType, Period, UserRole
from openclef.models.library import Arrangement, ArrangementTag, Part, Tag
from openclef.models.setlist import SetlistItem
from openclef.models.user import User, UserSettings
from openclef.routers._deps import get_storage
from openclef.schemas import (
    ArrangementDetail,
    ArrangementList,
    ArrangementRead,
    ArrangementSummary,
    ArrangementUpdate,
    FacetCount,
    ArrangementUploadMetadata,
    PartRead,
    UploadResponse,
)
from openclef.services.library_search import LibraryFilters, facet_queries, order_by
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


def _facet_value(value: object) -> str:
    return value.value if isinstance(value, Enum) else str(value)


@router.get("", response_model=ArrangementList)
async def list_arrangements(
    _user: CurrentUser,
    db: DbSession,
    q: Annotated[str | None, Query(max_length=200)] = None,
    instrument: Annotated[list[str], Query()] = [],  # noqa: B006 (FastAPI copies it)
    composer: str | None = None,
    key: KeySignature | None = None,
    period: Period | None = None,
    difficulty: Annotated[int | None, Query(ge=1, le=5)] = None,
    tag: str | None = None,
    sort: Literal["relevance", "title", "recent"] = "relevance",
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 24,
) -> ArrangementList:
    """The library: search, filter, and facet counts for the sidebar.
    Default order is search relevance when searching, newest otherwise."""
    filters = LibraryFilters(
        q=q, instrument=instrument, composer=composer, key=key,
        period=period, difficulty=difficulty, tag=tag,
    )
    where = and_(True, *filters.conditions())
    total = (await db.execute(select(func.count()).select_from(Arrangement).where(where))).scalar_one()
    rows = (
        await db.execute(
            select(Arrangement)
            .where(where)
            .order_by(*order_by(filters, sort))
            .limit(page_size)
            .offset((page - 1) * page_size)
        )
    ).scalars().all()

    parts_by_arrangement: dict[uuid.UUID, list[tuple]] = {}
    if rows:
        part_rows = await db.execute(
            select(Part.arrangement_id, Part.id, Part.thumbnail_storage_key)
            .where(Part.arrangement_id.in_([row.id for row in rows]))
            .order_by(Part.created_at, Part.id)
        )
        for arrangement_id, part_id, thumb in part_rows:
            parts_by_arrangement.setdefault(arrangement_id, []).append((part_id, thumb))

    items = []
    for row in rows:
        parts = parts_by_arrangement.get(row.id, [])
        cover = parts[0] if parts else None
        items.append(
            ArrangementSummary(
                id=row.id, title=row.title, subtitle=row.subtitle,
                composer=row.composer, arranger=row.arranger,
                instrumentation=row.instrumentation, key_signature=row.key_signature,
                period=row.period, difficulty=row.difficulty, created_at=row.created_at,
                part_count=len(parts),
                cover_part_id=cover[0] if cover else None,
                cover_thumbnail_ready=bool(cover and cover[1]),
            )
        )

    facets = {}
    for name, query in facet_queries(filters).items():
        facets[name] = [
            FacetCount(value=_facet_value(value), count=count)
            for value, count in (await db.execute(query)).all()
        ]
    return ArrangementList(items=items, total=total, page=page, page_size=page_size, facets=facets)


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


async def _load_arrangement(db: AsyncSession, arrangement_id: uuid.UUID) -> Arrangement:
    arrangement = await db.get(Arrangement, arrangement_id)
    if arrangement is None:
        raise HTTPException(status_code=404, detail="arrangement_not_found")
    return arrangement


async def _detail(db: AsyncSession, arrangement: Arrangement) -> ArrangementDetail:
    parts = (
        await db.execute(
            select(Part)
            .where(Part.arrangement_id == arrangement.id)
            .order_by(Part.created_at, Part.id)
        )
    ).scalars().all()
    tags = (
        await db.execute(
            select(Tag.name)
            .join(ArrangementTag, ArrangementTag.tag_id == Tag.id)
            .where(ArrangementTag.arrangement_id == arrangement.id)
            .order_by(Tag.name)
        )
    ).scalars().all()
    return ArrangementDetail(
        **ArrangementRead.model_validate(arrangement).model_dump(),
        parts=[PartRead.model_validate(part) for part in parts],
        tags=list(tags),
    )


@router.get("/{arrangement_id}", response_model=ArrangementDetail)
async def get_arrangement(
    arrangement_id: uuid.UUID, _user: CurrentUser, db: DbSession
) -> ArrangementDetail:
    return await _detail(db, await _load_arrangement(db, arrangement_id))


@router.patch("/{arrangement_id}", response_model=ArrangementDetail)
async def update_arrangement(
    arrangement_id: uuid.UUID, payload: ArrangementUpdate, _user: CurrentUser, db: DbSession
) -> ArrangementDetail:
    """Edit metadata. Any member may: the library is shared, and fixing a
    typo shouldn't need the uploader. Edited fields are marked as user-set
    so later enrichment never overwrites them."""
    arrangement = await _load_arrangement(db, arrangement_id)
    changes = payload.model_dump(exclude_unset=True)
    if "title" in changes and not changes["title"]:
        raise HTTPException(status_code=422, detail="title_required")
    for name, value in changes.items():
        setattr(arrangement, name, value)
    if changes:
        origins = dict(arrangement.field_origins_jsonb or {})
        origins.update({name: "user" for name in changes})
        arrangement.field_origins_jsonb = origins
    await db.commit()
    await db.refresh(arrangement)
    return await _detail(db, arrangement)


@router.delete("/{arrangement_id}", status_code=204)
async def delete_arrangement(
    arrangement_id: uuid.UUID, user: CurrentUser, db: DbSession, storage: StorageDep
) -> Response:
    """Delete a piece, all its parts and their files. Allowed for whoever
    added it, or an admin. Rows go first; a failed blob delete only orphans."""
    arrangement = await _load_arrangement(db, arrangement_id)
    if arrangement.created_by != user.id and user.role != UserRole.ADMIN:
        raise HTTPException(status_code=403, detail="not_arrangement_owner")
    on_setlist = (
        await db.execute(
            select(SetlistItem.setlist_id).where(SetlistItem.arrangement_id == arrangement_id).limit(1)
        )
    ).first()
    if on_setlist:
        raise HTTPException(status_code=409, detail="on_a_setlist")
    keys = [
        key
        for storage_key, part_id, thumb in (
            await db.execute(
                select(Part.storage_key, Part.id, Part.thumbnail_storage_key).where(
                    Part.arrangement_id == arrangement_id
                )
            )
        ).all()
        for key in (storage_key, thumb or thumbnail_key(part_id))
    ]
    # A SQL DELETE, not session.delete(): Arrangement.parts is lazy="raise",
    # and the FKs already cascade parts, tags and enrichment jobs in Postgres.
    await db.execute(sql_delete(Arrangement).where(Arrangement.id == arrangement_id))
    try:
        await db.commit()
    except IntegrityError:
        # Raced with a setlist add after the check above.
        raise HTTPException(status_code=409, detail="on_a_setlist") from None
    await _delete_quietly(storage, *keys)
    return Response(status_code=204)
