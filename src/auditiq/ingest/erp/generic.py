"""Best-effort adapter for trial balances that match none of the known layouts.

Locates the header row by looking for ``debit`` and ``credit`` columns, then
picks a description column, and optional code / group columns.
"""
from __future__ import annotations

from .base import TbRecord, _is_total_row, cell, is_blank, num, side_for

_SKIP_TOKENS = ("debit", "credit", "dr", "cr", "amount", "balance")


def _header_index(rows: list[list], limit: int = 40) -> int:
    for index, row in enumerate(rows[:limit]):
        lowered = [str(c).strip().lower() for c in row if not is_blank(c)]
        has_debit = any("debit" in c for c in lowered)
        has_credit = any("credit" in c for c in lowered)
        if has_debit and has_credit:
            return index
    raise ValueError("could not locate a Debit/Credit header row (generic adapter)")


def _column(header: list[str], *needles: str) -> int | None:
    for index, name in enumerate(header):
        low = name.lower()
        if all(n in low for n in needles):
            return index
    return None


def _first_plain(header: list[str]) -> int:
    for index, name in enumerate(header):
        low = name.lower()
        if not name:
            continue
        if any(token in low for token in _SKIP_TOKENS):
            continue
        if "code" in low or "type" in low or "group" in low:
            continue
        return index
    return 0


def read(rows: list[list]) -> list[TbRecord]:
    header_index = _header_index(rows)
    header = [("" if is_blank(c) else str(c).strip()) for c in rows[header_index]]

    debit_col = _column(header, "debit")
    credit_col = _column(header, "credit")
    name_col = _first_plain(header)
    code_col = _column(header, "code")
    group_col = _column(header, "type") or _column(header, "group")

    out: list[TbRecord] = []
    for index, row in enumerate(rows[header_index + 1 :], start=header_index + 1):
        name_value = cell(row, name_col)
        if is_blank(name_value):
            continue
        name = str(name_value).strip()
        if _is_total_row(name):
            continue
        amount = num(cell(row, debit_col)) - num(cell(row, credit_col))
        out.append(
            TbRecord(
                raw_code="" if code_col is None or is_blank(cell(row, code_col)) else str(cell(row, code_col)).strip(),
                raw_name=name,
                group="" if group_col is None or is_blank(cell(row, group_col)) else str(cell(row, group_col)).strip(),
                amount=amount,
                side=side_for(amount),
                source="generic",
                source_row=index + 1,
            )
        )
    return out
