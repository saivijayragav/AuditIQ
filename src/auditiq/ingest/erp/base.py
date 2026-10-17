"""Shared types and helpers for ERP trial-balance adapters."""
from __future__ import annotations

from dataclasses import dataclass, field

from .io import cell, is_blank, num


@dataclass
class TbRecord:
    """A single trial-balance ledger line in the common intermediate form."""

    raw_code: str
    raw_name: str
    group: str
    amount: float  # debit positive, credit negative
    side: str
    source: str
    erp_acc_type: str = ""
    source_row: int = 0
    warnings: list[str] = field(default_factory=list)


def side_for(amount: float) -> str:
    """Derive the accounting side from the signed amount."""
    return "Dr" if amount >= 0 else "Cr"


def find_header(rows: list[list], first_cell: str, limit: int | None = None) -> int:
    """Find the index of the header row whose first cell equals ``first_cell``."""
    scan = rows if limit is None else rows[:limit]
    for index, row in enumerate(scan):
        value = cell(row, 0)
        if not is_blank(value) and str(value).strip() == first_cell:
            return index
    raise ValueError(f"header row starting with '{first_cell}' not found")


def _is_total_row(name: str) -> bool:
    low = name.strip().lower()
    return low in ("grand total", "total") or low.startswith("total ")
