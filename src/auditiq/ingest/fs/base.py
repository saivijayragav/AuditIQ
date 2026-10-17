"""Reader contract and shared types for financial-statement ingestion.

Financial-statement ingestion is modular: every document type (PDF today; Excel,
HTML, DOCX later) implements :class:`FsReader` and returns a normalised
:class:`FsDocument`. Everything downstream — statement segmentation, FSLI
labelling, unit/period normalisation and persistence — is shared and reader
agnostic.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Protocol, runtime_checkable

# Canonical statement keys used in FsDocument.statements.
STATEMENT_BS = "bs"
STATEMENT_PL = "pl"
STATEMENT_CF = "cf"
STATEMENT_EQUITY = "equity"
STATEMENT_NOTES = "notes"
STATEMENT_KEYS = (STATEMENT_BS, STATEMENT_PL, STATEMENT_CF, STATEMENT_EQUITY, STATEMENT_NOTES)

# Human labels aligned with core.enums.Statement values.
STATEMENT_LABELS = {
    STATEMENT_BS: "BS",
    STATEMENT_PL: "P&L",
    STATEMENT_CF: "CF",
    STATEMENT_EQUITY: "Equity",
    STATEMENT_NOTES: "Notes",
}

# Row measures.
MEASURE_FACE = "face"
MEASURE_SUBTOTAL = "subtotal"
MEASURE_NOTE_TOTAL = "note_total"


@dataclass
class FsLocation:
    """Where an extracted value came from."""

    kind: str = ""
    page: Optional[int] = None
    bbox: Optional[tuple] = None  # (x0, y0, x1, y1)
    sheet: Optional[str] = None
    cell: Optional[str] = None
    table_ref: Optional[str] = None

    def ref(self) -> str:
        if self.sheet and self.cell:
            return f"{self.sheet}!{self.cell}"
        if self.page and self.cell:
            return f"p{self.page}:{self.cell}"
        if self.page:
            return f"p{self.page}"
        return self.table_ref or ""


@dataclass
class FsRow:
    """A candidate statement line: a label plus up to two figures."""

    label: str
    location: FsLocation = field(default_factory=FsLocation)
    note_ref: Optional[str] = None
    current: Optional[float] = None
    prior: Optional[float] = None
    current_text: str = ""
    prior_text: str = ""
    is_subtotal: bool = False
    raw_text: str = ""

    @property
    def measure(self) -> str:
        return MEASURE_SUBTOTAL if self.is_subtotal else MEASURE_FACE


@dataclass
class FsTable:
    """A table extracted from a document, with its raw grid and location."""

    title: str = ""
    headers: list[str] = field(default_factory=list)
    rows: list[list] = field(default_factory=list)
    location: FsLocation = field(default_factory=FsLocation)
    note_number: str = ""
    section: str = ""


@dataclass
class FsPage:
    """A single parsed page (PDF) or sheet region (future readers)."""

    index: int = 0  # 0-based source index
    page: int = 1  # report page number (1-based)
    text: str = ""
    tables: list[FsTable] = field(default_factory=list)
    word_rows: list[str] = field(default_factory=list)  # visual rows, when available


@dataclass
class FsDocument:
    """A parsed financial-statement document in reader-neutral form."""

    path: str
    reader_kind: str
    company: str = ""
    period: Optional[str] = None
    unit: str = "absolute"
    basis: str = ""
    pages: list[FsPage] = field(default_factory=list)
    text_blocks: list[str] = field(default_factory=list)
    statements: dict[str, list[FsRow]] = field(default_factory=dict)

    @property
    def tables(self) -> list[FsTable]:
        return [t for page in self.pages for t in page.tables]

    @property
    def page_count(self) -> int:
        return len(self.pages)

    def all_rows(self) -> list[FsRow]:
        return [row for rows in self.statements.values() for row in rows]


@runtime_checkable
class FsReader(Protocol):
    """Interface every document-type reader implements."""

    kind: str
    suffixes: tuple[str, ...]

    def can_read(self, path: str | Path) -> bool:  # pragma: no cover - trivial
        ...

    def read(self, path: str | Path) -> FsDocument:  # pragma: no cover - interface
        ...


__all__ = [
    "MEASURE_FACE",
    "MEASURE_NOTE_TOTAL",
    "MEASURE_SUBTOTAL",
    "STATEMENT_BS",
    "STATEMENT_CF",
    "STATEMENT_EQUITY",
    "STATEMENT_KEYS",
    "STATEMENT_LABELS",
    "STATEMENT_NOTES",
    "STATEMENT_PL",
    "FsDocument",
    "FsLocation",
    "FsPage",
    "FsReader",
    "FsRow",
    "FsTable",
]
