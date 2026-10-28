"""Dramatiq actors. The API enqueues; `dramatiq openclef.workers.tasks` runs them.

Each job runs its async body under a fresh `asyncio.run()`, so the DB
engine and storage client are created inside that loop and disposed
before it closes. Never reuse `openclef.db.engine` here: asyncpg
connections belong to the loop that opened them.
"""
from __future__ import annotations

import asyncio
import tempfile
import uuid
from collections.abc import AsyncIterator

import dramatiq
import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from openclef import workers  # noqa: F401  (registers the broker first)
from openclef.config import get_settings
from openclef.models.library import Part
from openclef.services.uploads import thumbnail_key
from openclef.storage import KeyNotFoundError, build_storage
from openclef.workers.thumbnails import render_first_page_png

log = structlog.get_logger()


async def _single_chunk(payload: bytes) -> AsyncIterator[bytes]:
    yield payload


async def generate_thumbnail(part_id: uuid.UUID) -> bool:
    """Render and store the part's thumbnail. Returns False when the part
    (or its PDF) no longer exists, which is not an error worth retrying."""
    settings = get_settings()
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
    storage = build_storage()
    try:
        async with AsyncSession(engine) as session:
            storage_key = (
                await session.execute(select(Part.storage_key).where(Part.id == part_id))
            ).scalar_one_or_none()
            if storage_key is None:
                log.info("openclef.thumbnail.part_gone", part_id=str(part_id))
                return False
            try:
                body = await storage.get(storage_key)
            except KeyNotFoundError:
                log.warning("openclef.thumbnail.pdf_missing", part_id=str(part_id))
                return False
            with tempfile.NamedTemporaryFile(suffix=".pdf") as tmp:
                async for chunk in body:
                    tmp.write(chunk)
                tmp.flush()
                png = render_first_page_png(tmp.name, settings.thumbnail_width_px)

            key = thumbnail_key(part_id)
            await storage.put(key, _single_chunk(png))
            result = await session.execute(
                update(Part).where(Part.id == part_id).values(thumbnail_storage_key=key)
            )
            await session.commit()
            if result.rowcount == 0:
                # Part deleted while rendering: don't leave an unreachable PNG.
                await storage.delete(key)
                return False
        log.info("openclef.thumbnail.done", part_id=str(part_id), bytes=len(png))
        return True
    finally:
        await engine.dispose()


@dramatiq.actor(queue_name="thumbnails", max_retries=3, time_limit=120_000)
def render_thumbnail(part_id: str) -> None:
    asyncio.run(generate_thumbnail(uuid.UUID(part_id)))
