"""PDF to text. Uses PyMuPDF (layout-aware, two-column aware) when installed, else pypdf."""
from __future__ import annotations

from pathlib import Path
from typing import Sequence

from ..errors import MissingDependency

# (x0, y0, x1, y1, text) as returned by PyMuPDF's page.get_text("blocks")
Block = Sequence


def order_blocks(blocks: list[Block], page_width: float) -> list[Block]:
    """Put text blocks into reading order, handling two-column layouts.

    Blocks wider than ~60% of the page (titles, wide figures, captions) act as separators. Between
    separators, the left column is read top to bottom before the right column.
    """
    if not blocks:
        return []
    middle = page_width / 2
    spanning = [b for b in blocks if (b[2] - b[0]) > 0.6 * page_width]
    narrow = [b for b in blocks if (b[2] - b[0]) <= 0.6 * page_width]
    ordered: list[Block] = []
    previous_y = float("-inf")
    for separator in sorted(spanning, key=lambda b: b[1]) + [None]:
        limit = separator[1] if separator is not None else float("inf")
        band = [b for b in narrow if previous_y <= b[1] < limit]
        band.sort(key=lambda b: (0 if b[0] < middle else 1, b[1], b[0]))
        ordered.extend(band)
        if separator is not None:
            ordered.append(separator)
            previous_y = separator[1]
    return ordered


def _extract_with_pymupdf(path: Path) -> str:
    import fitz  # PyMuPDF

    pages = []
    with fitz.open(path) as doc:
        for page in doc:
            blocks = [b for b in page.get_text("blocks") if len(b) > 6 and b[6] == 0]  # text blocks only
            ordered = order_blocks([(b[0], b[1], b[2], b[3], b[4]) for b in blocks], page.rect.width)
            pages.append("\n\n".join(str(b[4]).strip() for b in ordered if str(b[4]).strip()))
    return "\n\n".join(pages)


def _extract_with_pypdf(path: Path) -> str:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    return "\n\n".join((page.extract_text() or "") for page in reader.pages)


def extract_pdf_text(path: Path) -> str:
    """Extract text from a PDF file, preferring the layout-aware backend."""
    path = Path(path)
    try:
        return _extract_with_pymupdf(path)
    except ImportError:
        pass
    try:
        return _extract_with_pypdf(path)
    except ImportError as exc:
        raise MissingDependency("pymupdf", "pdf") from exc
