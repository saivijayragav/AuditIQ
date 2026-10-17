"""Reader registry: dispatch a financial-statement document to the right reader.

Mirrors ``ingest/erp/registry.py``. Readers are instantiated lazily so that heavy,
optional dependencies (``pymupdf`` / ``pdfplumber``, behind the ``[report]`` extra)
are only imported when a document is actually read.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

from .base import FsDocument, FsReader

# File suffix -> reader kind.
_SUFFIX_KIND = {
    ".pdf": "pdf",
    ".xlsx": "excel",
    ".xlsm": "excel",
    ".xls": "excel",
    ".csv": "excel",
}

_READERS: dict[str, FsReader] = {}


def _build() -> dict[str, FsReader]:
    from .excel.reader import ExcelFsReader
    from .pdf.reader import PdfFsReader

    return {"pdf": PdfFsReader(), "excel": ExcelFsReader()}


def readers() -> dict[str, FsReader]:
    """Return the available readers, keyed by kind (built once)."""
    global _READERS
    if not _READERS:
        _READERS = _build()
    return _READERS


def reader_kinds() -> list[str]:
    return sorted(readers())


def get_reader(kind: str) -> FsReader:
    try:
        return readers()[kind]
    except KeyError:
        raise ValueError(
            f"unknown reader kind '{kind}' (expected one of {reader_kinds()})"
        ) from None


def detect_reader(path: str | Path, kind: Optional[str] = None) -> str:
    """Resolve the reader kind for ``path`` (explicit ``kind`` wins)."""
    if kind:
        get_reader(kind)  # validate
        return kind
    suffix = Path(path).suffix.lower()
    resolved = _SUFFIX_KIND.get(suffix)
    if resolved is None:
        known = ", ".join(sorted(_SUFFIX_KIND))
        raise ValueError(
            f"cannot determine a reader for '{Path(path).name}' (known suffixes: {known})"
        )
    return resolved


def read_fs(path: str | Path, kind: Optional[str] = None) -> FsDocument:
    """Read a financial-statement document, auto-detecting the reader by suffix."""
    resolved = detect_reader(path, kind)
    return get_reader(resolved).read(path)


__all__ = [
    "detect_reader",
    "get_reader",
    "read_fs",
    "reader_kinds",
    "readers",
]
