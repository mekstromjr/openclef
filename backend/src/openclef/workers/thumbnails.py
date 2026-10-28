"""First-page thumbnail rendering (pure; no storage or DB)."""
from __future__ import annotations

import io

import pypdfium2 as pdfium


def render_first_page_png(pdf_path: str, width_px: int) -> bytes:
    """Render page 1 of the PDF at `width_px` wide and return PNG bytes."""
    document = pdfium.PdfDocument(pdf_path)
    try:
        page = document[0]
        try:
            scale = width_px / page.get_width()
            image = page.render(scale=scale).to_pil()
        finally:
            page.close()
    finally:
        document.close()
    buffer = io.BytesIO()
    image.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
