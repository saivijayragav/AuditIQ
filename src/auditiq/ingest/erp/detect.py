"""Detect which ERP layout a trial-balance export uses from its header row."""
from __future__ import annotations

from .io import is_blank


def _header_cells(rows: list[list], limit: int = 15) -> list[str]:
    cells: list[str] = []
    for row in rows[:limit]:
        for value in row:
            if not is_blank(value):
                cells.append(str(value).strip())
    return cells


def detect_source(rows: list[list]) -> str:
    """Return one of ``tally``, ``sap``, ``zoho`` or ``generic``."""
    cells = _header_cells(rows)
    cell_set = set(cells)
    lowered = [c.lower() for c in cells]

    if "Particulars" in cell_set:
        return "tally"
    if "G/L Account" in cell_set:
        return "sap"
    if "Account" in cell_set and "Account Code" in cell_set:
        return "zoho"
    if "Account Type" in cell_set:
        return "zoho"
    if any("debit" in c for c in lowered) and any("credit" in c for c in lowered):
        return "generic"
    return "generic"
