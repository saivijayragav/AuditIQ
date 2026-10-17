"""SAP ECC / S4HANA trial-balance adapter.

Layout: ``G/L Account | G/L Acct Long Text | Debit | Credit``.
"""
from __future__ import annotations

from .base import TbRecord, _is_total_row, cell, find_header, is_blank, num, side_for

HEADER = "G/L Account"


def read(rows: list[list]) -> list[TbRecord]:
    start = find_header(rows, HEADER) + 1
    out: list[TbRecord] = []
    for index, row in enumerate(rows[start:], start=start):
        code = cell(row, 0)
        if is_blank(code):
            continue
        code_str = str(code).strip()
        if _is_total_row(code_str):
            continue
        name = "" if is_blank(cell(row, 1)) else str(cell(row, 1)).strip()
        amount = num(cell(row, 2)) - num(cell(row, 3))
        out.append(
            TbRecord(
                raw_code=code_str,
                raw_name=name,
                group="",
                amount=amount,
                side=side_for(amount),
                source="sap",
                source_row=index + 1,
            )
        )
    return out
