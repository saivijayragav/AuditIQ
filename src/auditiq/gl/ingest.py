"""Ingestion parser for Tally Prime general ledger vouchers (Excel & CSV)."""
from __future__ import annotations

import csv
import datetime
from pathlib import Path
from typing import Any, Optional, Union
import openpyxl

from .models import Voucher, VoucherLine


def _clean_str(val: Any) -> str:
    if val is None:
        return ""
    return str(val).strip().replace("\xa0", " ")


def _parse_date(val: Any) -> Optional[datetime.date]:
    if val is None:
        return None
    if isinstance(val, datetime.datetime):
        return val.date()
    if isinstance(val, datetime.date):
        return val
    s = str(val).strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%Y/%m/%d", "%d-%b-%Y", "%d-%b-%y"):
        try:
            return datetime.datetime.strptime(s.split("T")[0], fmt).date()
        except ValueError:
            pass
    return None


def _parse_amount(val: Any) -> float:
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().replace(",", "").replace("\xa0", "")
    # Check for formulas like =0.09*E3 or text like 35.40$=3540
    if "=" in s:
        s = s.split("=")[-1].strip()
    if "$" in s:
        s = s.split("$")[-1].strip()
    try:
        return float(s)
    except ValueError:
        return 0.0


def ingest_tally_excel(file_path: Union[str, Path]) -> list[Voucher]:
    """Parse Tally Prime accounting vouchers from an Excel (.xlsx) export."""
    wb = openpyxl.load_workbook(file_path, data_only=True)
    # Check for sheet named 'Accounting Voucher' or use active sheet
    sheet = wb["Accounting Voucher"] if "Accounting Voucher" in wb.sheetnames else wb.active

    rows = list(sheet.iter_rows(values_only=True))
    if not rows:
        return []

    # Map header column indices
    header = [_clean_str(c).lower() for c in rows[0]]
    col_idx = {
        "date": -1,
        "type": -1,
        "vno": -1,
        "ledger": -1,
        "amount": -1,
        "drcr": -1,
        "narration": -1,
    }

    for i, h in enumerate(header):
        if "voucher date" in h or h == "date":
            col_idx["date"] = i
        elif "voucher type" in h or h == "type":
            col_idx["type"] = i
        elif "voucher number" in h or "voucher no" in h or h == "vno":
            col_idx["vno"] = i
        elif "ledger name" in h or h == "ledger" or h == "account":
            col_idx["ledger"] = i
        elif "dr/cr" in h or "drcr" in h or "side" in h:
            col_idx["drcr"] = i
        elif "ledger amount" in h or "amount" in h:
            col_idx["amount"] = i
        elif "narration" in h:
            col_idx["narration"] = i

    vouchers: list[Voucher] = []
    current_voucher: Optional[Voucher] = None

    for row in rows[1:]:
        if not any(row):
            continue

        raw_date = row[col_idx["date"]] if col_idx["date"] >= 0 else None
        raw_type = row[col_idx["type"]] if col_idx["type"] >= 0 else None
        raw_vno = row[col_idx["vno"]] if col_idx["vno"] >= 0 else None
        raw_ledger = row[col_idx["ledger"]] if col_idx["ledger"] >= 0 else None
        raw_amt = row[col_idx["amount"]] if col_idx["amount"] >= 0 else None
        raw_drcr = row[col_idx["drcr"]] if col_idx["drcr"] >= 0 else None
        raw_narr = row[col_idx["narration"]] if col_idx["narration"] >= 0 else None

        parsed_date = _parse_date(raw_date)
        parsed_type = _clean_str(raw_type)
        parsed_vno = _clean_str(raw_vno)
        parsed_ledger = _clean_str(raw_ledger)
        parsed_amt = _parse_amount(raw_amt)
        parsed_drcr = _clean_str(raw_drcr) or "Dr"
        parsed_narr = _clean_str(raw_narr)

        # In Tally multi-line layout:
        # A new voucher starts whenever Date or Voucher Number or Voucher Type is present
        is_new_voucher = parsed_date is not None or (parsed_type and parsed_vno)

        if is_new_voucher:
            if current_voucher is not None and current_voucher.lines:
                vouchers.append(current_voucher)

            current_voucher = Voucher(
                voucher_number=parsed_vno,
                voucher_type=parsed_type,
                date=parsed_date or datetime.date(2023, 4, 1),
                narration=parsed_narr,
                lines=[],
            )

        if current_voucher is not None and parsed_ledger:
            current_voucher.lines.append(
                VoucherLine(
                    ledger_name=parsed_ledger,
                    amount=parsed_amt,
                    drcr=parsed_drcr,
                    narration=parsed_narr if not is_new_voucher else None,
                )
            )

    if current_voucher is not None and current_voucher.lines:
        vouchers.append(current_voucher)

    return vouchers


def ingest_tally_csv(file_path: Union[str, Path]) -> list[Voucher]:
    """Parse Tally Prime accounting vouchers from a CSV export."""
    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        reader = list(csv.reader(f))
    if not reader:
        return []

    header = [_clean_str(c).lower() for c in reader[0]]
    col_idx = {
        "date": -1,
        "type": -1,
        "vno": -1,
        "ledger": -1,
        "amount": -1,
        "drcr": -1,
        "narration": -1,
    }

    for i, h in enumerate(header):
        if "voucher date" in h or h == "date":
            col_idx["date"] = i
        elif "voucher type" in h or h == "type":
            col_idx["type"] = i
        elif "voucher number" in h or "voucher no" in h or h == "vno":
            col_idx["vno"] = i
        elif "ledger name" in h or h == "ledger" or h == "account":
            col_idx["ledger"] = i
        elif "dr/cr" in h or "drcr" in h or "side" in h:
            col_idx["drcr"] = i
        elif "ledger amount" in h or "amount" in h:
            col_idx["amount"] = i
        elif "narration" in h:
            col_idx["narration"] = i

    vouchers: list[Voucher] = []
    current_voucher: Optional[Voucher] = None

    for row in reader[1:]:
        if not any(row):
            continue

        raw_date = row[col_idx["date"]] if col_idx["date"] >= 0 and col_idx["date"] < len(row) else None
        raw_type = row[col_idx["type"]] if col_idx["type"] >= 0 and col_idx["type"] < len(row) else None
        raw_vno = row[col_idx["vno"]] if col_idx["vno"] >= 0 and col_idx["vno"] < len(row) else None
        raw_ledger = row[col_idx["ledger"]] if col_idx["ledger"] >= 0 and col_idx["ledger"] < len(row) else None
        raw_amt = row[col_idx["amount"]] if col_idx["amount"] >= 0 and col_idx["amount"] < len(row) else None
        raw_drcr = row[col_idx["drcr"]] if col_idx["drcr"] >= 0 and col_idx["drcr"] < len(row) else None
        raw_narr = row[col_idx["narration"]] if col_idx["narration"] >= 0 and col_idx["narration"] < len(row) else None

        parsed_date = _parse_date(raw_date)
        parsed_type = _clean_str(raw_type)
        parsed_vno = _clean_str(raw_vno)
        parsed_ledger = _clean_str(raw_ledger)
        parsed_amt = _parse_amount(raw_amt)
        parsed_drcr = _clean_str(raw_drcr) or "Dr"
        parsed_narr = _clean_str(raw_narr)

        is_new_voucher = parsed_date is not None or (parsed_type and parsed_vno)

        if is_new_voucher:
            if current_voucher is not None and current_voucher.lines:
                vouchers.append(current_voucher)

            current_voucher = Voucher(
                voucher_number=parsed_vno,
                voucher_type=parsed_type,
                date=parsed_date or datetime.date(2023, 4, 1),
                narration=parsed_narr,
                lines=[],
            )

        if current_voucher is not None and parsed_ledger:
            current_voucher.lines.append(
                VoucherLine(
                    ledger_name=parsed_ledger,
                    amount=parsed_amt,
                    drcr=parsed_drcr,
                    narration=parsed_narr if not is_new_voucher else None,
                )
            )

    if current_voucher is not None and current_voucher.lines:
        vouchers.append(current_voucher)

    return vouchers


def ingest_vouchers(file_path: Union[str, Path]) -> list[Voucher]:
    """Auto-detect format (Excel or CSV) and parse general ledger vouchers."""
    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(f"Voucher file not found: {file_path}")
    if p.suffix.lower() in (".xlsx", ".xlsm", ".xltx"):
        return ingest_tally_excel(p)
    elif p.suffix.lower() in (".csv", ".txt"):
        return ingest_tally_csv(p)
    else:
        raise ValueError(f"Unsupported voucher format '{p.suffix}'; expected .xlsx or .csv")
