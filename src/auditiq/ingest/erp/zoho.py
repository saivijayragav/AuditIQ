"""Zoho Books trial-balance adapter.

Layout: ``Account | Account Code | Account Type | Debit | Credit``.
"""
from __future__ import annotations

from .base import TbRecord, _is_total_row, cell, find_header, is_blank, num, side_for

HEADER = "Account"


def read(rows: list[list]) -> list[TbRecord]:
    start = find_header(rows, HEADER) + 1
    out: list[TbRecord] = []
    for index, row in enumerate(rows[start:], start=start):
        name_value = cell(row, 0)
        if is_blank(name_value):
            continue
        name = str(name_value).strip()
        if _is_total_row(name):
            continue
        code = "" if is_blank(cell(row, 1)) else str(cell(row, 1)).strip()
        acc_type = "" if is_blank(cell(row, 2)) else str(cell(row, 2)).strip()
        amount = num(cell(row, 3)) - num(cell(row, 4))
        out.append(
            TbRecord(
                raw_code=code,
                raw_name=name,
                group=acc_type,
                erp_acc_type=acc_type,
                amount=amount,
                side=side_for(amount),
                source="zoho",
                source_row=index + 1,
            )
        )
    return out
