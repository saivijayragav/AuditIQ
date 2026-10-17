"""Articulation: does each statement hang together on its own?

The tie-out compares Side A with Side B line by line. Articulation checks the
*internal* consistency of the numbers we just read, which catches extraction
errors and presentation mistakes that a line-by-line tie-out can miss:

* the balance sheet balances (assets = equity + liabilities);
* the trial balance clears to zero on the accepted mappings;
* the face subtotals equal the sum of the face lines they total;
* no FSLI or group was collapsed into two separate face rows.

Subtotals are excluded from the tie-out; here they are exactly the evidence we
need.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..core.groups import GroupIndex
from ..core.taxonomy import Taxonomy, statement_code
from ..core.text import nu
from .aggregate import SideA, SideB
from .materiality import (
    SEVERITY_NONE,
    WATCH,
    ReconConfig,
    classify,
)

INCOME_KEYWORDS = ("total income", "total revenue", "total operating income")
EXPENSE_KEYWORDS = ("total expenses", "total expenditure")


@dataclass
class Finding:
    code: str
    statement: str
    severity: str
    message: str
    amount: float = 0.0


def _severity(difference: float, config: ReconConfig) -> str:
    return classify(difference, config)[1]


def _unit_category(code: str, is_group: bool, taxonomy: Taxonomy, groups: GroupIndex) -> str:
    if is_group:
        group = groups.get(code)
        return group.category if group else ""
    item = taxonomy.get(code)
    return item.category if item else ""


def _find_subtotal(side_b: SideB, statement: str, keywords: tuple[str, ...]) -> float | None:
    for row in side_b.subtotals:
        if statement_code(row.statement) != statement:
            continue
        label = nu(row.label)
        if any(keyword in label for keyword in keywords):
            return row.value
    return None


def articulate(
    side_a: SideA,
    side_b: SideB,
    taxonomy: Taxonomy,
    groups: GroupIndex,
    config: ReconConfig,
) -> list[Finding]:
    """Return internal-consistency findings for a run (may be empty)."""
    findings: list[Finding] = []

    # 1. Balance sheet balances.
    assets = liabilities = 0.0
    for code, value in side_b.by_fsli.items():
        category = _unit_category(code, False, taxonomy, groups)
        if category == "Asset":
            assets += value
        elif category in ("Liability", "Equity"):
            liabilities += value
    for code, value in side_b.by_group.items():
        category = _unit_category(code, True, taxonomy, groups)
        if category == "Asset":
            assets += value
        elif category in ("Liability", "Equity"):
            liabilities += value
    if assets or liabilities:
        difference = assets - liabilities
        findings.append(
            Finding(
                code="bs_balance",
                statement="BS",
                severity=_severity(difference, config),
                amount=difference,
                message=(
                    f"assets {assets:,.2f} vs equity + liabilities {liabilities:,.2f} "
                    f"(difference {difference:,.2f})"
                ),
            )
        )

    # 2. The trial balance clears on the accepted mappings.
    if side_a.mapped_lines:
        net = side_a.net_books
        findings.append(
            Finding(
                code="books_clear",
                statement="",
                severity=_severity(net, config),
                amount=net,
                message=(
                    f"accepted trial-balance lines net to {net:,.2f} "
                    f"(exposure of {side_a.exposure_total:,.2f} excluded)"
                ),
            )
        )

    # 3. Face subtotals equal the lines they total.
    income = sum(
        value
        for code, value in side_b.by_fsli.items()
        if _unit_category(code, False, taxonomy, groups) == "Income"
    )
    for code, value in side_b.by_group.items():
        if _unit_category(code, True, taxonomy, groups) == "Income":
            income += value
    expense = sum(
        value
        for code, value in side_b.by_fsli.items()
        if _unit_category(code, False, taxonomy, groups) == "Expense"
    )

    total_income = _find_subtotal(side_b, "P&L", INCOME_KEYWORDS)
    if total_income is not None:
        difference = total_income - income
        findings.append(
            Finding(
                code="pl_total_income",
                statement="P&L",
                severity=_severity(difference, config),
                amount=difference,
                message=(
                    f"presented total income {total_income:,.2f} vs income lines "
                    f"{income:,.2f} (difference {difference:,.2f})"
                ),
            )
        )
    total_expense = _find_subtotal(side_b, "P&L", EXPENSE_KEYWORDS)
    if total_expense is not None and expense:
        difference = total_expense - expense
        findings.append(
            Finding(
                code="pl_total_expenses",
                statement="P&L",
                severity=_severity(difference, config),
                amount=difference,
                message=(
                    f"presented total expenses {total_expense:,.2f} vs expense lines "
                    f"{expense:,.2f} (difference {difference:,.2f})"
                ),
            )
        )

    # 4. Hygiene: the same FSLI / group collapsed into several face rows.
    for code, count in sorted(side_b.duplicate_fsli.items()):
        findings.append(
            Finding(
                code="duplicate_fsli",
                statement="",
                severity=WATCH,
                amount=float(count),
                message=(
                    f"{code} appears on {count} face rows; the presentation "
                    "aggregates lines the taxonomy keeps separate"
                ),
            )
        )

    # 5. Unit mismatch between the two sides is informational only (both sides are
    #    already normalised to absolute rupees).
    if side_a.unit and side_b.unit and side_a.unit != side_b.unit:
        findings.append(
            Finding(
                code="unit_mismatch",
                statement="",
                severity=SEVERITY_NONE,
                message=(
                    f"trial balance reported in {side_a.unit}, statements in "
                    f"{side_b.unit} (both normalised to rupees)"
                ),
            )
        )

    return findings


__all__ = ["Finding", "articulate"]
