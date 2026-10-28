"""Generated PDFs for tests. Never commit real scores to this repo."""
from __future__ import annotations

import io

from pypdf import PdfWriter


def make_pdf(pages: int = 1, title: str | None = None, author: str | None = None) -> bytes:
    writer = PdfWriter()
    for _ in range(pages):
        writer.add_blank_page(width=612, height=792)
    info = {}
    if title:
        info["/Title"] = title
    if author:
        info["/Author"] = author
    if info:
        writer.add_metadata(info)
    buffer = io.BytesIO()
    writer.write(buffer)
    return buffer.getvalue()
