"""Validate an uploaded PDF and stream it into storage.

Starlette has already spooled the multipart body to a temp file by the
time a handler runs, so the file is read from there: one pass checks the
magic bytes, enforces the size cap and computes the SHA-256, pypdf then
inspects the same file, and a second pass streams it to storage. Nothing
holds the whole PDF in memory, and nothing re-downloads it from storage.
"""
from __future__ import annotations

import hashlib
from collections.abc import AsyncIterator
from dataclasses import dataclass

from fastapi import UploadFile
from starlette.concurrency import run_in_threadpool

from openclef.services.pdf_meta import PdfInfo, inspect_pdf
from openclef.storage import Storage

PDF_MAGIC = b"%PDF-"


class NotPdfError(ValueError):
    """First bytes aren't the PDF signature."""


class UploadTooLargeError(ValueError):
    """Upload exceeds the configured cap."""


@dataclass(frozen=True)
class CheckedUpload:
    size_bytes: int
    sha256: str
    pdf: PdfInfo


async def check_upload(file: UploadFile, *, max_bytes: int, chunk_bytes: int) -> CheckedUpload:
    """Validate signature, size and structure. Raises NotPdfError,
    UploadTooLargeError or pdf_meta.InvalidPdfError."""
    await file.seek(0)
    digest = hashlib.sha256()
    size = 0
    first = True
    while chunk := await file.read(chunk_bytes):
        if first:
            if not chunk.startswith(PDF_MAGIC):
                raise NotPdfError("file does not start with %PDF-")
            first = False
        size += len(chunk)
        if size > max_bytes:
            raise UploadTooLargeError(f"upload exceeds {max_bytes} bytes")
        digest.update(chunk)
    if first:
        raise NotPdfError("empty file")
    pdf = await run_in_threadpool(inspect_pdf, file.file)
    return CheckedUpload(size_bytes=size, sha256=digest.hexdigest(), pdf=pdf)


async def store_upload(file: UploadFile, storage: Storage, key: str, *, chunk_bytes: int) -> None:
    """Stream the (already checked) upload into storage under `key`."""
    await file.seek(0)

    async def chunks() -> AsyncIterator[bytes]:
        while chunk := await file.read(chunk_bytes):
            yield chunk

    await storage.put(key, chunks())


def score_key(arrangement_id: object, part_id: object) -> str:
    return f"scores/{arrangement_id}/{part_id}.pdf"


def thumbnail_key(part_id: object) -> str:
    return f"thumbnails/{part_id}.png"
