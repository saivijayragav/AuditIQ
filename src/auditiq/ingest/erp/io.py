"""Grid reading and cell helpers for ERP export files."""
from __future__ import annotations

import csv
import math
from pathlib import Path

import pandas as pd

from ...core.units import parse_amount

_XLSX_SUFFIXES = {".xlsx", ".xlsm", ".xls"}
_CSV_SUFFIXES = {".csv", ".txt"}


def is_blank(value: object) -> bool:
    """True for ``None``, NaN and whitespace-only cells."""
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    return str(value).strip() == ""


def cell(row: list, index: int) -> object:
    """Return ``row[index]`` or ``None`` when the row is shorter."""
    if index < 0 or index >= len(row):
        return None
    return row[index]


def num(value: object) -> float:
    """Numeric value of a cell, treating blanks as ``0.0``."""
    parsed = parse_amount(value)
    return 0.0 if parsed is None else float(parsed)


def read_grid(path: str | Path) -> list[list]:
    """Read an ERP export (.xlsx or .csv) into a list of rows."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in _XLSX_SUFFIXES:
        frame = pd.read_excel(path, header=None, dtype=object)
        frame = frame.where(pd.notna(frame), None)
        return frame.values.tolist()
    if suffix in _CSV_SUFFIXES:
        # The stdlib reader tolerates ragged preamble rows (a common ERP export shape).
        with path.open(newline="", encoding="utf-8-sig") as handle:
            return [list(row) for row in csv.reader(handle)]
    raise ValueError(f"Unsupported file type '{suffix}' (expected .xlsx or .csv)")
