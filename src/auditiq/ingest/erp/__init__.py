"""ERP trial-balance ingestion (Tally / SAP / Zoho / generic)."""
from __future__ import annotations

from .base import TbRecord
from .detect import detect_source
from .registry import ADAPTERS, read_records, read_with_source
from .service import TbIngestResult, file_hash, ingest_tb

__all__ = [
    "ADAPTERS",
    "TbIngestResult",
    "TbRecord",
    "detect_source",
    "file_hash",
    "ingest_tb",
    "read_records",
    "read_with_source",
]
