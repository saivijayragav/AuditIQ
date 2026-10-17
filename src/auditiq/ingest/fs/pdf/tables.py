"""PDF table extraction helpers (pdfplumber grid -> :class:`FsTable`).

Deliberately small: the reader converts raw grid cells into :class:`FsTable`
objects, and the shared statement layer decides what each row and column means.
"""
from __future__ import annotations

import re
from typing import Optional

from ..base import FsLocation, FsTable

_YEAR = re.compile(r"(?:19|20)\d{2}")


def clean_cell(value: object) -> str:
    """Collapse whitespace in a raw grid cell and stringify it."""
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def table_from_grid(grid, *, page: int, index: int, title: str = "") -> FsTable:
    """Build an :class:`FsTable` from a pdfplumber ``extract_tables`` grid."""
    rows = [[clean_cell(cell) for cell in row] for row in (grid or [])]
    rows = [row for row in rows if any(cell for cell in row)]
    headers = list(rows[0]) if rows else []
    return FsTable(
        title=title,
        headers=headers,
        rows=rows,
        location=FsLocation(kind="pdf", page=page, table_ref=f"p{page}t{index}"),
    )


def looks_like_year(text: object) -> bool:
    """True when the text contains a four-digit year (e.g. a column header)."""
    return bool(_YEAR.search(str(text or "")))


def has_numbers(rows: list[list]) -> bool:
    """True when the grid has at least one cell containing a digit."""
    return any(ch.isdigit() for row in rows for cell in row for ch in str(cell))


__all__ = ["clean_cell", "has_numbers", "looks_like_year", "table_from_grid"]
