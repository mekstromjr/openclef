"""Serve a Part's PDF and thumbnail to any signed-in user."""
from __future__ import annotations

import uuid
from typing import Annotated
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from openclef.auth.deps import get_current_user
from openclef.db import get_session
from openclef.models.library import Part
from openclef.models.user import User
from openclef.routers._deps import get_storage
from openclef.storage import KeyNotFoundError, Storage

router = APIRouter(prefix="/api/v1/parts", tags=["parts"])


def content_disposition(kind: str, filename: str) -> str:
    """RFC 6266 header with an ASCII fallback plus the RFC 5987 UTF-8 name,
    so labels like "Für Elise" or ones containing quotes survive."""
    fallback = "".join(
        ch for ch in filename.encode("ascii", "ignore").decode() if ch not in '"\\'
    ).strip() or "score.pdf"
    return f"{kind}; filename=\"{fallback}\"; filename*=UTF-8''{quote(filename)}"


async def _load_part(db: AsyncSession, part_id: uuid.UUID) -> Part:
    part = (await db.execute(select(Part).where(Part.id == part_id))).scalar_one_or_none()
    if part is None:
        raise HTTPException(status_code=404, detail="part_not_found")
    return part


@router.get("/{part_id}/file")
async def get_part_file(
    part_id: uuid.UUID,
    _user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_session)],
    storage: Annotated[Storage, Depends(get_storage)],
    download: bool = False,
) -> StreamingResponse:
    part = await _load_part(db, part_id)
    try:
        body = await storage.get(part.storage_key)
    except KeyNotFoundError:
        raise HTTPException(status_code=404, detail="file_missing") from None
    filename = f"{part.label}.pdf"
    return StreamingResponse(
        body,
        media_type="application/pdf",
        headers={
            "Content-Length": str(part.file_size_bytes),
            "Content-Disposition": content_disposition(
                "attachment" if download else "inline", filename
            ),
        },
    )


@router.get("/{part_id}/thumbnail")
async def get_part_thumbnail(
    part_id: uuid.UUID,
    _user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_session)],
    storage: Annotated[Storage, Depends(get_storage)],
) -> StreamingResponse:
    part = await _load_part(db, part_id)
    if not part.thumbnail_storage_key:
        raise HTTPException(status_code=404, detail="thumbnail_pending")
    try:
        body = await storage.get(part.thumbnail_storage_key)
    except KeyNotFoundError:
        raise HTTPException(status_code=404, detail="thumbnail_missing") from None
    # A part's thumbnail never changes (new upload = new part id).
    return StreamingResponse(
        body, media_type="image/png", headers={"Cache-Control": "private, max-age=86400"}
    )
