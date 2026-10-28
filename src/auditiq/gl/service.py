"""Service layer for Journal Entry Testing (SA 240)."""
from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

from .ingest import ingest_vouchers
from .models import BenfordResult, JetFinding, JetReport, Voucher, VoucherLine
from .testing import analyze_journal_entries


def run_jet_file(
    file_path: Union[str, Path],
    fy_end_date: Optional[str] = None,
) -> JetReport:
    """Read a Tally Prime voucher export file and run SA 240 Journal Entry Testing."""
    import datetime

    p = Path(file_path)
    if not p.exists():
        raise FileNotFoundError(f"Voucher file not found: {file_path}")

    vouchers = ingest_vouchers(p)
    if not vouchers:
        raise ValueError(f"No vouchers found in '{p.name}'")

    parsed_fy_end = None
    if fy_end_date:
        parsed_fy_end = datetime.datetime.strptime(fy_end_date, "%Y-%m-%d").date()

    return analyze_journal_entries(vouchers, fy_end_date=parsed_fy_end)


__all__ = [
    "BenfordResult",
    "JetFinding",
    "JetReport",
    "Voucher",
    "VoucherLine",
    "analyze_journal_entries",
    "ingest_vouchers",
    "run_jet_file",
]
