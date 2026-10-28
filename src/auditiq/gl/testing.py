"""SA 240 / ISA 240 Journal Entry Testing (JET) and Fraud Detection Engine."""
from __future__ import annotations

import collections
import datetime
import math
import re
from typing import Optional

from .models import BenfordResult, JetFinding, JetReport, Voucher


# ── Configurable thresholds & keywords ────────────────────────────────────────

SUSPICIOUS_NARRATION_PATTERNS = [
    re.compile(r"\badjustment\b", re.I),
    re.compile(r"\brectification\b", re.I),
    re.compile(r"\bdummy\b", re.I),
    re.compile(r"\bmanagement\b", re.I),
    re.compile(r"\bcfo\b", re.I),
    re.compile(r"\breversal\b", re.I),
    re.compile(r"\bplug\b", re.I),
    re.compile(r"\btemp\b", re.I),
    re.compile(r"\bsuspense\b", re.I),
    re.compile(r"\bas per discussion\b", re.I),
    re.compile(r"\bas discussed\b", re.I),
    re.compile(r"\bspecial entry\b", re.I),
]

ROUND_SUM_THRESHOLDS = (100_000.0, 500_000.0, 1_000_000.0, 2_500_000.0)

# Expected Benford first-digit frequencies (1 to 9)
BENFORD_EXPECTED = {
    1: 0.301,
    2: 0.176,
    3: 0.125,
    4: 0.097,
    5: 0.079,
    6: 0.067,
    7: 0.058,
    8: 0.051,
    9: 0.046,
}


def analyze_journal_entries(
    vouchers: list[Voucher],
    fy_end_date: Optional[datetime.date] = None,
) -> JetReport:
    """Run all SA 240 Journal Entry Tests on a set of vouchers."""
    if not vouchers:
        return JetReport(
            total_vouchers=0,
            total_lines=0,
            date_range=("", ""),
            voucher_type_counts={},
            findings=[],
        )

    # Date bounds
    sorted_by_date = sorted(vouchers, key=lambda v: v.date)
    min_date = sorted_by_date[0].date
    max_date = sorted_by_date[-1].date
    effective_fy_end = fy_end_date or max_date

    # Voucher type breakdown
    type_counts = collections.Counter(v.voucher_type for v in vouchers)

    findings: list[JetFinding] = []

    # 1. Individual voucher tests
    for v in vouchers:
        findings.extend(_check_weekend_posting(v))
        findings.extend(_check_round_sum(v))
        findings.extend(_check_period_end_clustering(v, effective_fy_end))
        findings.extend(_check_suspicious_narration(v))
        findings.extend(_check_unusual_ledger_pairings(v))

    # 2. Cross-voucher pattern tests
    findings.extend(_check_threshold_avoidance(vouchers))
    findings.extend(_check_sequence_gaps(vouchers))

    # 3. Benford's Law analysis
    benford_res = _compute_benford(vouchers)
    if benford_res and not benford_res.is_conforming:
        for digit in benford_res.flagged_digits:
            obs = benford_res.observed_pct.get(digit, 0.0)
            exp = benford_res.expected_pct.get(digit, 0.0)
            findings.append(
                JetFinding(
                    voucher_number="ALL",
                    voucher_type="GL Summary",
                    date=max_date,
                    amount=0.0,
                    risk_rule="benford_law",
                    severity="high" if abs(obs - exp) > 8.0 else "medium",
                    message=(
                        f"Benford's Law anomaly on digit {digit}: observed {obs:.1f}% "
                        f"vs expected {exp:.1f}%. May indicate fabricated or manipulated amounts."
                    ),
                    details={"digit": digit, "observed": obs, "expected": exp},
                )
            )

    # Severity counters
    high = sum(1 for f in findings if f.severity == "high")
    med = sum(1 for f in findings if f.severity == "medium")
    low = sum(1 for f in findings if f.severity == "low")

    return JetReport(
        total_vouchers=len(vouchers),
        total_lines=sum(len(v.lines) for v in vouchers),
        date_range=(min_date.isoformat(), max_date.isoformat()),
        voucher_type_counts=dict(type_counts),
        findings=findings,
        benford=benford_res,
        high_risk_count=high,
        medium_risk_count=med,
        low_risk_count=low,
    )


# ── Individual Audit Check Rules ─────────────────────────────────────────────


def _check_weekend_posting(v: Voucher) -> list[JetFinding]:
    """Flag entries posted on Sundays (non-working day in India)."""
    if v.date.weekday() == 6:  # Sunday
        is_manual = v.voucher_type.strip().lower() in ("journal", "jv")
        severity = "high" if is_manual else "medium"
        return [
            JetFinding(
                voucher_number=str(v.voucher_number),
                voucher_type=v.voucher_type,
                date=v.date,
                amount=v.amount,
                risk_rule="weekend_posting",
                severity=severity,
                message=(
                    f"Voucher #{v.voucher_number} ({v.voucher_type}) of INR {v.amount:,.2f} "
                    f"was posted on a Sunday ({v.date.strftime('%A, %d-%b-%Y')}). "
                    f"Investigate business justification per SA 240."
                ),
                details={"weekday": "Sunday"},
            )
        ]
    return []


def _check_round_sum(v: Voucher) -> list[JetFinding]:
    """Flag round-sum transactions (e.g. exactly 5,00,000, 10,00,000)."""
    amt = v.amount
    if amt < 50_000.0:
        return []

    # Check if exact multiple of 50,000, 1,00,000, 5,00,000, etc.
    is_round = False
    if amt >= 500_000.0 and (amt % 100_000.0 == 0.0):
        is_round = True
    elif amt >= 100_000.0 and (amt % 50_000.0 == 0.0):
        is_round = True

    if is_round and v.voucher_type.strip().lower() in ("journal", "jv", "payment"):
        severity = "high" if amt >= 500_000.0 else "medium"
        return [
            JetFinding(
                voucher_number=str(v.voucher_number),
                voucher_type=v.voucher_type,
                date=v.date,
                amount=amt,
                risk_rule="round_sum",
                severity=severity,
                message=(
                    f"High-value round sum amount of INR {amt:,.2f} on {v.voucher_type} #{v.voucher_number}. "
                    f"Unusual for genuine commercial invoices with GST/cents."
                ),
                details={"amount": amt},
            )
        ]
    return []


def _check_period_end_clustering(v: Voucher, fy_end: datetime.date) -> list[JetFinding]:
    """Flag manual Journal vouchers created in the final week of the financial year."""
    if v.voucher_type.strip().lower() not in ("journal", "jv"):
        return []

    # Final 7 days of the fiscal year (typically March 25 - March 31)
    days_to_end = (fy_end - v.date).days
    if 0 <= days_to_end <= 6 and v.amount >= 100_000.0:
        return [
            JetFinding(
                voucher_number=str(v.voucher_number),
                voucher_type=v.voucher_type,
                date=v.date,
                amount=v.amount,
                risk_rule="period_end_clustering",
                severity="high",
                message=(
                    f"Manual Journal entry #{v.voucher_number} of INR {v.amount:,.2f} "
                    f"posted {days_to_end} day(s) before financial year-end ({v.date}). "
                    f"High risk of management override or window-dressing (SA 240)."
                ),
                details={"days_to_year_end": days_to_end},
            )
        ]
    return []


def _check_suspicious_narration(v: Voucher) -> list[JetFinding]:
    """Flag missing narrations or keywords indicating manual override/plug."""
    narr = v.narration.strip()
    is_manual = v.voucher_type.strip().lower() in ("journal", "jv")

    # 1. Completely blank narration on manual entry
    if not narr and is_manual and v.amount >= 50_000.0:
        return [
            JetFinding(
                voucher_number=str(v.voucher_number),
                voucher_type=v.voucher_type,
                date=v.date,
                amount=v.amount,
                risk_rule="suspicious_narration",
                severity="medium",
                message=(
                    f"Manual Journal entry #{v.voucher_number} of INR {v.amount:,.2f} "
                    f"has a BLANK narration. Lacks audit trail."
                ),
                details={"pattern": "blank"},
            )
        ]

    # 2. Suspicious keywords
    for pattern in SUSPICIOUS_NARRATION_PATTERNS:
        if pattern.search(narr):
            return [
                JetFinding(
                    voucher_number=str(v.voucher_number),
                    voucher_type=v.voucher_type,
                    date=v.date,
                    amount=v.amount,
                    risk_rule="suspicious_narration",
                    severity="high" if is_manual else "medium",
                    message=(
                        f"Suspicious narration in voucher #{v.voucher_number}: '{narr}'. "
                        f"Matches keyword '{pattern.pattern}'."
                    ),
                    details={"narration": narr, "matched": pattern.pattern},
                )
            ]
    return []


def _check_unusual_ledger_pairings(v: Voucher) -> list[JetFinding]:
    """Flag abnormal debit-credit ledger combinations."""
    ledgers_dr = [l.ledger_name.lower() for l in v.lines if l.is_debit]
    ledgers_cr = [l.ledger_name.lower() for l in v.lines if l.is_credit]

    findings = []

    # 1. Direct Cash debited with Sales credited in Journal (bypassing cash ceiling / sales register)
    has_cash_dr = any("cash in hand" in l or "petty cash" in l for l in ledgers_dr)
    has_sales_cr = any("sales" in l or "revenue" in l for l in ledgers_cr)
    if has_cash_dr and has_sales_cr and v.voucher_type.lower() in ("journal", "jv"):
        findings.append(
            JetFinding(
                voucher_number=str(v.voucher_number),
                voucher_type=v.voucher_type,
                date=v.date,
                amount=v.amount,
                risk_rule="unusual_pairing",
                severity="high",
                message=(
                    f"Voucher #{v.voucher_number} directly pairs Cash with Sales via a Journal voucher. "
                    f"Bypasses standard sales registers and cash limit controls."
                ),
            )
        )

    # 2. Capital Asset credited to Operating Expense debited
    has_asset_cr = any("plant & machinery" in l or "equipment" in l or "furniture" in l for l in ledgers_cr)
    has_exp_dr = any("stationery" in l or "repairs" in l or "rent" in l or "conveyance" in l for l in ledgers_dr)
    if has_asset_cr and has_exp_dr:
        findings.append(
            JetFinding(
                voucher_number=str(v.voucher_number),
                voucher_type=v.voucher_type,
                date=v.date,
                amount=v.amount,
                risk_rule="unusual_pairing",
                severity="high",
                message=(
                    f"Voucher #{v.voucher_number} writes off a Capital Asset directly to Operating Expense. "
                    f"Violates AS 10 / Ind AS 16 fixed asset derecognition standards."
                ),
            )
        )

    return findings


def _check_threshold_avoidance(vouchers: list[Voucher]) -> list[JetFinding]:
    """Flag multiple payments to same party on same date just below Section 269ST/40A(3) limits."""
    # Group payments by (date, party)
    by_date_party: dict[tuple[datetime.date, str], list[Voucher]] = collections.defaultdict(list)

    for v in vouchers:
        if v.voucher_type.lower() in ("payment", "contra"):
            # find the recipient party
            parties = [l.ledger_name for l in v.lines if l.is_debit]
            for p in parties:
                by_date_party[(v.date, p)].append(v)

    findings = []
    for (dt, party), group in by_date_party.items():
        if len(group) >= 3:
            # Check if amounts are clustered just below 50,000 (e.g. 45,000 to 49,999)
            sub_50k = [v for v in group if 40_000.0 <= v.amount < 50_000.0]
            if len(sub_50k) >= 3:
                total_split = sum(v.amount for v in sub_50k)
                findings.append(
                    JetFinding(
                        voucher_number=", ".join(str(v.voucher_number) for v in sub_50k[:4]),
                        voucher_type="Payment",
                        date=dt,
                        amount=total_split,
                        risk_rule="threshold_avoidance",
                        severity="high",
                        message=(
                            f"Detected {len(sub_50k)} split payments totaling INR {total_split:,.2f} "
                            f"to '{party}' on {dt}, each just below the INR 50,000 limit. "
                            f"Potential structuring to circumvent Section 40A(3) / 269ST cash restrictions."
                        ),
                        details={"party": party, "count": len(sub_50k), "total": total_split},
                    )
                )
    return findings


def _check_sequence_gaps(vouchers: list[Voucher]) -> list[JetFinding]:
    """Flag missing numbers in sequential voucher series."""
    by_type: dict[str, list[int]] = collections.defaultdict(list)
    for v in vouchers:
        try:
            val = int(v.voucher_number)
            by_type[v.voucher_type].append(val)
        except ValueError:
            continue

    findings = []
    for vtype, numbers in by_type.items():
        if len(numbers) < 10:
            continue
        sorted_nums = sorted(set(numbers))
        gaps = []
        for i in range(len(sorted_nums) - 1):
            diff = sorted_nums[i + 1] - sorted_nums[i]
            if 1 < diff <= 5:  # small gap
                for missing in range(sorted_nums[i] + 1, sorted_nums[i + 1]):
                    gaps.append(missing)

        if gaps:
            findings.append(
                JetFinding(
                    voucher_number=", ".join(str(g) for g in gaps[:5]),
                    voucher_type=vtype,
                    date=vouchers[-1].date,
                    amount=0.0,
                    risk_rule="sequence_gap",
                    severity="medium",
                    message=(
                        f"Missing sequential voucher number(s) in {vtype} series: {gaps[:8]}. "
                        f"Check if vouchers were deleted or backdated without authorization."
                    ),
                    details={"missing_numbers": gaps[:20]},
                )
            )
    return findings


# ── Benford's Law Analysis ───────────────────────────────────────────────────


def _compute_benford(vouchers: list[Voucher]) -> Optional[BenfordResult]:
    """Compute first-digit frequency and chi-square goodness of fit."""
    first_digits: list[int] = []

    for v in vouchers:
        for line in v.lines:
            amt = abs(line.amount)
            if amt >= 10.0:  # ignore tiny fractions
                d_str = str(f"{amt:.2f}").lstrip("0").replace(".", "")
                if d_str and d_str[0] in "123456789":
                    first_digits.append(int(d_str[0]))

    total = len(first_digits)
    if total < 50:
        return None

    counts = collections.Counter(first_digits)
    obs_pct = {d: (counts.get(d, 0) / total) * 100.0 for d in range(1, 10)}
    exp_pct = {d: BENFORD_EXPECTED[d] * 100.0 for d in range(1, 10)}

    chi_sq = 0.0
    flagged = []
    for d in range(1, 10):
        expected_cnt = total * BENFORD_EXPECTED[d]
        actual_cnt = counts.get(d, 0)
        chi_sq += ((actual_cnt - expected_cnt) ** 2) / expected_cnt

        diff_pct = abs(obs_pct[d] - exp_pct[d])
        if diff_pct > 6.0:  # significant deviation
            flagged.append(d)

    # df = 8: critical chi-square value at p = 0.05 is 15.507
    is_conforming = chi_sq < 20.0 and len(flagged) == 0

    return BenfordResult(
        total_amounts=total,
        digit_counts=dict(counts),
        observed_pct=obs_pct,
        expected_pct=exp_pct,
        chi_square=round(chi_sq, 2),
        p_value_approx=0.05 if chi_sq < 15.5 else 0.001,
        is_conforming=is_conforming,
        flagged_digits=flagged,
    )
