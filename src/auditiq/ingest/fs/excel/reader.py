"""Structured (Excel / CSV) financial-statement reader.

The interface is defined now so that structured-workbook ingestion slots in behind
the same :class:`~auditiq.ingest.fs.base.FsReader` contract; the implementation
lands in a later sub-phase. PDF is the only reader shipped today.
"""
from __future__ import annotations

from pathlib import Path

from ..base import FsDocument

SUFFIXES = (".xlsx", ".xlsm", ".xls", ".csv")


class ExcelFsReader:
    """Placeholder reader for spreadsheet financial statements."""

    kind = "excel"
    suffixes = SUFFIXES

    def can_read(self, path: str | Path) -> bool:
        return Path(path).suffix.lower() in self.suffixes

    def read(self, path: str | Path) -> FsDocument:
        raise NotImplementedError(
            "structured financial-statement ingestion (Excel/CSV) is not implemented "
            "yet; use the PDF reader. The reader interface is stable, so this slots in "
            "without changes to the shared pipeline."
        )


__all__ = ["SUFFIXES", "ExcelFsReader"]
