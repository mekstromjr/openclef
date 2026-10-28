"""PDF inspection at upload time: page count + embedded metadata.

Pure, synchronous functions over a binary file object. Callers run them
in a thread (pypdf is CPU-bound and would block the event loop on a
large score).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import BinaryIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError


class InvalidPdfError(ValueError):
    """The file starts like a PDF but pypdf can't parse it."""


@dataclass(frozen=True)
class PdfInfo:
    page_count: int
    title: str | None = None
    author: str | None = None
    # Every Info-dictionary string, kept verbatim for provenance
    # (stored in arrangements.source_metadata_jsonb).
    raw: dict[str, str] = field(default_factory=dict)


def _clean(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def inspect_pdf(file: BinaryIO) -> PdfInfo:
    """Read page count and Info metadata. Raises InvalidPdfError."""
    file.seek(0)
    try:
        reader = PdfReader(file)
        page_count = len(reader.pages)
        info = reader.metadata or {}
    except (PdfReadError, ValueError, KeyError, TypeError) as exc:
        raise InvalidPdfError(str(exc)) from exc
    if page_count < 1:
        raise InvalidPdfError("PDF has no pages")
    raw = {str(key).lstrip("/"): text for key, value in info.items() if (text := _clean(value))}
    return PdfInfo(
        page_count=page_count,
        title=raw.get("Title"),
        author=raw.get("Author"),
        raw=raw,
    )
