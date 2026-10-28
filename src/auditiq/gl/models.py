"""Data models for General Ledger and Journal Entry Testing (SA 240)."""
from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class VoucherLine:
    """A single debit or credit line within a voucher."""

    ledger_name: str
    amount: float
    drcr: str  # "Dr" or "Cr"
    narration: Optional[str] = None

    @property
    def is_debit(self) -> bool:
        return self.drcr.strip().lower() in ("dr", "debit")

    @property
    def is_credit(self) -> bool:
        return self.drcr.strip().lower() in ("cr", "credit")

    def to_dict(self) -> dict[str, Any]:
        return {
            "ledger_name": self.ledger_name,
            "amount": self.amount,
            "drcr": self.drcr,
            "narration": self.narration,
        }


@dataclass
class Voucher:
    """A complete multi-line accounting voucher."""

    voucher_number: str
    voucher_type: str
    date: datetime.date
    narration: str = ""
    lines: list[VoucherLine] = field(default_factory=list)

    @property
    def total_debit(self) -> float:
        return sum(line.amount for line in self.lines if line.is_debit)

    @property
    def total_credit(self) -> float:
        return sum(line.amount for line in self.lines if line.is_credit)

    @property
    def is_balanced(self) -> bool:
        return abs(self.total_debit - self.total_credit) < 0.01

    @property
    def amount(self) -> float:
        """The total monetary value of the voucher (debit sum)."""
        return max(self.total_debit, self.total_credit)

    @property
    def is_weekend(self) -> bool:
        return self.date.weekday() in (5, 6)  # Saturday (5) or Sunday (6)

    def to_dict(self) -> dict[str, Any]:
        return {
            "voucher_number": self.voucher_number,
            "voucher_type": self.voucher_type,
            "date": self.date.isoformat(),
            "narration": self.narration,
            "amount": self.amount,
            "lines": [line.to_dict() for line in self.lines],
        }


@dataclass
class JetFinding:
    """A single audit exception or risk flag on a voucher."""

    voucher_number: str
    voucher_type: str
    date: datetime.date
    amount: float
    risk_rule: str  # e.g. "weekend_posting", "round_sum", "period_end", "benford", "unusual_pairing"
    severity: str   # "high", "medium", "low"
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "voucher_number": self.voucher_number,
            "voucher_type": self.voucher_type,
            "date": self.date.isoformat(),
            "amount": self.amount,
            "risk_rule": self.risk_rule,
            "severity": self.severity,
            "message": self.message,
            "details": self.details,
        }


@dataclass
class BenfordResult:
    """Benford's Law first-digit analysis."""

    total_amounts: int
    digit_counts: dict[int, int]
    observed_pct: dict[int, float]
    expected_pct: dict[int, float]
    chi_square: float
    p_value_approx: float
    is_conforming: bool
    flagged_digits: list[int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_amounts": self.total_amounts,
            "observed_pct": self.observed_pct,
            "expected_pct": self.expected_pct,
            "chi_square": self.chi_square,
            "is_conforming": self.is_conforming,
            "flagged_digits": self.flagged_digits,
        }


@dataclass
class JetReport:
    """Full SA 240 Journal Entry Testing report."""

    total_vouchers: int
    total_lines: int
    date_range: tuple[str, str]
    voucher_type_counts: dict[str, int]
    findings: list[JetFinding]
    benford: Optional[BenfordResult] = None
    high_risk_count: int = 0
    medium_risk_count: int = 0
    low_risk_count: int = 0

    @property
    def status(self) -> str:
        if self.high_risk_count > 0:
            return "high risk"
        if self.medium_risk_count > 0:
            return "medium risk"
        if self.low_risk_count > 0:
            return "low risk"
        return "clean"

    def to_dict(self) -> dict[str, Any]:
        return {
            "total_vouchers": self.total_vouchers,
            "total_lines": self.total_lines,
            "date_range": list(self.date_range),
            "voucher_type_counts": self.voucher_type_counts,
            "status": self.status,
            "high_risk_count": self.high_risk_count,
            "medium_risk_count": self.medium_risk_count,
            "low_risk_count": self.low_risk_count,
            "findings_count": len(self.findings),
            "findings": [f.to_dict() for f in self.findings],
            "benford": self.benford.to_dict() if self.benford else None,
        }
