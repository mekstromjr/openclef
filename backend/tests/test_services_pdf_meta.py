"""pypdf-backed inspection of uploaded PDFs."""
from __future__ import annotations

import io

import pytest

from openclef.services.pdf_meta import InvalidPdfError, inspect_pdf
from tests.pdf_fixtures import make_pdf


def test_reads_page_count_and_info_metadata():
    info = inspect_pdf(io.BytesIO(make_pdf(pages=3, title="Nocturne", author="A. Composer")))
    assert info.page_count == 3
    assert info.title == "Nocturne"
    assert info.author == "A. Composer"
    assert info.raw["Title"] == "Nocturne"


def test_missing_metadata_is_none():
    info = inspect_pdf(io.BytesIO(make_pdf()))
    assert info.page_count == 1
    assert info.title is None and info.author is None


def test_garbage_after_signature_is_invalid():
    with pytest.raises(InvalidPdfError):
        inspect_pdf(io.BytesIO(b"%PDF-1.7\nthis is not really a pdf"))
