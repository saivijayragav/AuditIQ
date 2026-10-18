"""Synthetic trial-balance workbook writer for ingestion tests.

Complements ``_draft_fs.py`` (Side B) with Side A: a Zoho-layout .xlsx whose
ledger heads are taken from the alias dictionary so the mapping cascade resolves
them deterministically. An optional list of ``(name, amount)`` pairs adds heads
the cascade will *not* resolve (pending-review exposure).
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Sequence

from openpyxl import Workbook

# Deterministic vocabulary: (ledger head, fsli or None, Dr-positive amount).
DEFAULT_HEADS: Sequence[tuple[str, Optional[str], float]] = (
    ("Sundry Debtors", "AST_TR", 1000.0),
    ("Inventory", "AST_INV", 700.0),
    ("Cash in Hand", "AST_CASH", 500.0),
    ("Cost of Materials Consumed", "EXP_MAT", 1200.0),
    ("Other Expenses", "EXP_OTH", 800.0),
    ("Sundry Creditors", "LIA_TP", -700.0),
    ("Share Capital", "EQ_SC", -1500.0),
    ("Revenue from Operations", "INC_REV_SALES", -2000.0),
)


def to_tb_amount(presented: dict[str, float]) -> dict[str, float]:
    """Map presented (natural-side positive) values to Dr-positive TB amounts."""
    from auditiq.core import load_default_taxonomy

    taxonomy = load_default_taxonomy()
    out = {}
    for code, value in presented.items():
        item = taxonomy.get(code)
        if item is None or not value:
            continue
        out[code] = value if item.is_debit else -value
    return out


def tb_rows(heads: Sequence[tuple[str, Optional[str], float]]) -> list[list]:
    """Zoho-layout rows: header block + one row per head + balancing total."""
    rows = [
        ["Test Co Limited"],
        ["Account", "Account Code", "Account Type", "Debit", "Credit"],
    ]
    for name, _fsli, amount in heads:
        if amount >= 0:
            rows.append([name, "", "", amount, None])
        else:
            rows.append([name, "", "", None, -amount])
    debit = sum(a for _, _, a in heads if a > 0)
    credit = sum(-a for _, _, a in heads if a < 0)
    rows.append(["Total", "", "", debit, credit])
    return rows


def write_tb(path: str | Path, heads: Sequence[tuple[str, Optional[str], float]] = DEFAULT_HEADS) -> Path:
    """Write a synthetic trial balance .xlsx and return its path."""
    workbook = Workbook()
    sheet = workbook.active
    for row in tb_rows(heads):
        sheet.append(list(row))
    path = Path(path)
    workbook.save(path)
    return path


def write_tb_bytes(heads: Sequence[tuple[str, Optional[str], float]] = DEFAULT_HEADS) -> bytes:
    """The same workbook as in-memory .xlsx bytes (for HTTP uploads)."""
    workbook = Workbook()
    sheet = workbook.active
    for row in tb_rows(heads):
        sheet.append(list(row))
    import io

    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()
