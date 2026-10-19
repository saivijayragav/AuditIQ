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
    CachedLabel,
    FsDocument,
    FsLocation,
    FsPage,
    FsReader,
    FsRow,
    FsTable,
)
from .labels import (
    CACHE_LAYER,
    GROUP_LAYER,
    LabelSummary,
    LabelledRow,
    build_fs_mapper,
    build_group_index,
    label_row,
    label_rows,
    summarise,
)
from .normalize import BoundValue, bind_row, resolve_unit
from .registry import detect_reader, get_reader, read_fs, reader_kinds, readers
from .review import (
    RESET_METHOD,
    FsResolutionResult,
    UnmappedLabel,
    list_unmapped_fs,
    load_fs_cache,
    reset_fs_line,
    resolve_fs_line,
)
from .service import FsCoverageReport, FsIngestResult, file_hash, fs_coverage, ingest_fs
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
    "CACHE_LAYER",
    "GROUP_LAYER",
    "MEASURE_FACE",
    "MEASURE_NOTE_TOTAL",
    "MEASURE_SUBTOTAL",
    "RESET_METHOD",
    "STATEMENT_BS",
    "STATEMENT_CF",
    "STATEMENT_EQUITY",
    "STATEMENT_KEYS",
    "STATEMENT_LABELS",
    "STATEMENT_NOTES",
    "STATEMENT_PL",
    "BoundValue",
    "CachedLabel",
    "FsCoverageReport",
    "FsDocument",
    "FsIngestResult",
    "FsLocation",
    "FsPage",
    "FsReader",
    "FsResolutionResult",
    "FsRow",
    "FsTable",
    "LabelSummary",
    "LabelledRow",
    "UnmappedLabel",
    "ValidationIssue",
    "bind_row",
    "build_fs_mapper",
    "build_group_index",
    "classify_page",
    "detect_reader",
    "extract_statements",
    "file_hash",
    "fs_coverage",
    "get_reader",
    "ingest_fs",
    "label_row",
    "label_rows",
    "list_unmapped_fs",
    "load_fs_cache",
    "read_fs",
    "reader_kinds",
    "readers",
    "reset_fs_line",
    "resolve_fs_line",
    "resolve_unit",
    "row_from_line",
    "rows_from_page",
    "rows_from_table",
    "segment_pages",
    "summarise",
    "validate_document",
    "value_columns",
]
