"""Tally Prime trial-balance adapter.

Layout: ``Particulars | Debit | Credit``. Group rows are unindented and carry
subtotals (never counted); ledger rows are indented with a leading space.
"""
from __future__ import annotations

from .base import TbRecord, _is_total_row, cell, find_header, is_blank, num, side_for

HEADER = "Particulars"


def read(rows: list[list]) -> list[TbRecord]:
    start = find_header(rows, HEADER) + 1
    out: list[TbRecord] = []
    group = ""
    for index, row in enumerate(rows[start:], start=start):
        value = cell(row, 0)
        if is_blank(value):
            continue
        name = str(value)
        if _is_total_row(name):
            continue
        if not name.startswith(" "):
            # Unindented => a parent group header; remember it, never count it.
            group = name.strip()
            continue
        amount = num(cell(row, 1)) - num(cell(row, 2))
        out.append(
            TbRecord(
                raw_code="",
                raw_name=name.strip(),
                group="" if group.lower() == "primary" else group,
                amount=amount,
                side=side_for(amount),
                source="tally",
                source_row=index + 1,
            )
        )
    return out
