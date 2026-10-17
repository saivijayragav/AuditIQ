"""PDF financial-statement reader.

Text is extracted with PyMuPDF; tables with pdfplumber. Both dependencies live in
the ``[report]`` extra and are imported lazily so the base install (and the
deterministic ingest/map paths) keep working without them.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from ..base import FsDocument, FsPage
from .document import detect_basis, detect_company, detect_period, detect_unit_from
from .tables import table_from_grid
from .words import visual_lines


class PdfFsReader:
    """Reads a financial-statement PDF into a reader-neutral :class:`FsDocument`."""

    kind = "pdf"
    suffixes = (".pdf",)

    def __init__(self, max_pages: Optional[int] = None, extract_tables: bool = True):
        self.max_pages = max_pages
        self.extract_tables = extract_tables

    def can_read(self, path: str | Path) -> bool:
        return Path(path).suffix.lower() == ".pdf"

    def read(self, path: str | Path) -> FsDocument:
        try:
            import pymupdf  # lazy: [report] extra
        except ImportError as exc:  # pragma: no cover - depends on environment
            raise RuntimeError(
                "reading PDFs requires the [report] extra: pip install 'auditiq[report]'"
            ) from exc

        path = Path(path)
        document = pymupdf.open(path)
        try:
            count = document.page_count
            limit = count if self.max_pages is None else min(self.max_pages, count)
            pages_text: list[str] = []
            pages_words: list[list[str]] = []
            for index in range(limit):
                page = document.load_page(index)
                pages_text.append(page.get_text("text"))
                pages_words.append(visual_lines(page))
        finally:
            document.close()

        grids_by_page = self._extract_tables(path, limit) if self.extract_tables else {}

        pages: list[FsPage] = []
        for index in range(limit):
            tables = [
                table_from_grid(grid, page=index + 1, index=position)
                for position, grid in enumerate(grids_by_page.get(index, []))
            ]
            pages.append(
                FsPage(
                    index=index,
                    page=index + 1,
                    text=pages_text[index],
                    tables=tables,
                    word_rows=pages_words[index],
                )
            )

        window = "\n".join(pages_text[: min(3, limit)])
        full_text = "\n".join(pages_text)
        return FsDocument(
            path=str(path),
            reader_kind=self.kind,
            company=detect_company(window) or detect_company(full_text),
            period=detect_period(window) or detect_period(full_text),
            unit=detect_unit_from(window),
            basis=detect_basis(window),
            pages=pages,
        )

    def _extract_tables(self, path: Path, limit: int) -> dict[int, list]:
        try:
            import pdfplumber  # lazy: [report] extra
        except ImportError:  # pragma: no cover - depends on environment
            return {}

        grids: dict[int, list] = {}
        with pdfplumber.open(path) as pdf:
            for index, page in enumerate(pdf.pages[:limit]):
                try:
                    found = page.extract_tables()
                except Exception:
                    found = []
                if found:
                    grids[index] = found
        return grids


__all__ = ["PdfFsReader"]
