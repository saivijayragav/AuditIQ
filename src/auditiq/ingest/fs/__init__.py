"""Financial-statement ingestion (reconciliation Side B).

Modular by design: document-type readers implement :class:`FsReader` and return a
reader-neutral :class:`FsDocument`; segmentation, FSLI labelling, unit/period
normalisation, validation and persistence are shared across readers. PDF is the
only reader implemented today; Excel/CSV/HTML/DOCX slot in behind the same
interface.
"""
from __future__ import annotations

from .base import (
    MEASURE_FACE,
    MEASURE_NOTE_TOTAL,
    MEASURE_SUBTOTAL,
    STATEMENT_BS,
    STATEMENT_CF,
    STATEMENT_EQUITY,
    STATEMENT_KEYS,
    STATEMENT_LABELS,
    STATEMENT_NOTES,
    STATEMENT_PL,
    FsDocument,
    FsLocation,
    FsPage,
    FsReader,
    FsRow,
    FsTable,
)
from .labels import (
    LabelSummary,
    LabelledRow,
    build_fs_mapper,
    label_row,
    label_rows,
    summarise,
)
from .normalize import BoundValue, bind_row, resolve_unit
from .registry import detect_reader, get_reader, read_fs, reader_kinds, readers
from .service import FsIngestResult, file_hash, ingest_fs
from .statements import (
    classify_page,
    extract_statements,
    row_from_line,
    rows_from_page,
    rows_from_table,
    segment_pages,
    value_columns,
)
from .validation import ValidationIssue, validate_document

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
    "BoundValue",
    "FsDocument",
    "FsIngestResult",
    "FsLocation",
    "FsPage",
    "FsReader",
    "FsRow",
    "FsTable",
    "LabelSummary",
    "LabelledRow",
    "ValidationIssue",
    "bind_row",
    "build_fs_mapper",
    "classify_page",
    "detect_reader",
    "extract_statements",
    "file_hash",
    "get_reader",
    "ingest_fs",
    "label_row",
    "label_rows",
    "read_fs",
    "reader_kinds",
    "readers",
    "resolve_unit",
    "row_from_line",
    "rows_from_page",
    "rows_from_table",
    "segment_pages",
    "summarise",
    "validate_document",
    "value_columns",
]
