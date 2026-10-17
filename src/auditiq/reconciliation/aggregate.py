"""Reconciliation Side A / Side B aggregation (sign-normalised).

Both sides are brought into **presentation space** using each FSLI's normal
balance::

    s(code)      = +1 when normal_balance is debit, else -1
    side_a(code) = s(code) * SUM(tb_line.normalized_amount)   # accepted mappings only
    side_b(code) =      SUM(fs_line.normalized_value)         # current, face rows

so a liability/equity/revenue line is positive on both sides. A variance is then
``side_a - side_b``; positive means the books exceed the financial statements.

Nothing here re-runs the mapping cascade: Side A reads the **persisted**
``tb_mapping`` and treats anything not accepted as *exposure* rather than summing
it into the books.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.taxonomy import Taxonomy
from ..store.models import FsLine, TbLine, TbMapping

ACCEPTED_STATUSES = ("auto", "resolved")
MEASURE_FACE = "face"


def sign_of(taxonomy: Taxonomy, code: Optional[str]) -> int:
    """``+1`` for debit-normal FSLIs, ``-1`` for credit-normal ones."""
    item = taxonomy.get(code)
    return 1 if (item is not None and item.is_debit) else -1


@dataclass
class ExposureLine:
    """A trial-balance line that is not part of the accepted books."""

    line_id: int
    raw_name: str
    group_name: str
    raw_code: str
    amount: float  # signed, debit-positive, absolute rupees
    status: str  # pending_review | unmapped
    method: str = ""
    candidate: Optional[str] = None  # code the cascade proposed, if any

    @property
    def abs_amount(self) -> float:
        return abs(self.amount)


@dataclass
class SideA:
    """The mapped trial balance, in presentation space, plus its exposure."""

    by_fsli: dict[str, float] = field(default_factory=dict)
    lines_by_fsli: dict[str, int] = field(default_factory=dict)
    ids_by_fsli: dict[str, list[int]] = field(default_factory=dict)
    raw_by_fsli: dict[str, float] = field(default_factory=dict)
    exposure: list[ExposureLine] = field(default_factory=list)
    total_lines: int = 0
    mapped_lines: int = 0
    unit: str = "absolute"

    @property
    def exposure_total(self) -> float:
        return sum(item.abs_amount for item in self.exposure)

    @property
    def net_exposure(self) -> float:
        return sum(item.amount for item in self.exposure)

    @property
    def net_books(self) -> float:
        """Signed sum of the accepted books; ~0 when the trial balance balances."""
        return sum(self.raw_by_fsli.values())

    def codes(self) -> set[str]:
        return set(self.by_fsli)


@dataclass
class FsExposureRow:
    """A face row on Side B that resolved to neither an FSLI nor a group."""

    line_id: int
    label: str
    statement: str
    value: Optional[float]
    period: str

    @property
    def amount(self) -> float:
        return float(self.value or 0.0)


@dataclass
class SubtotalRow:
    """A subtotal presented on Side B (excluded from tie-out, used to articulate)."""

    label: str
    statement: str
    value: float
    period: str


@dataclass
class SideB:
    """The client's draft financial statements, in presentation space."""

    by_fsli: dict[str, float] = field(default_factory=dict)
    rows_by_fsli: dict[str, int] = field(default_factory=dict)
    ids_by_fsli: dict[str, list[int]] = field(default_factory=dict)
    by_group: dict[str, float] = field(default_factory=dict)
    rows_by_group: dict[str, int] = field(default_factory=dict)
    ids_by_group: dict[str, list[int]] = field(default_factory=dict)
    unmapped: list[FsExposureRow] = field(default_factory=list)
    subtotals: list[SubtotalRow] = field(default_factory=list)
    unit: str = "absolute"
    periods: list[str] = field(default_factory=list)
    duplicate_fsli: dict[str, int] = field(default_factory=dict)

    @property
    def exposure_total(self) -> float:
        return sum(abs(row.amount) for row in self.unmapped)

    def codes(self) -> set[str]:
        return set(self.by_fsli) | set(self.by_group)


def _majority(values: Iterable[str]) -> str:
    counts = Counter(v for v in values if v)
    return counts.most_common(1)[0][0] if counts else "absolute"


def side_a(session: Session, engagement_id: int, taxonomy: Taxonomy) -> SideA:
    """Aggregate the engagement's accepted mappings into presentation-space FSLLIs."""
    rows = session.execute(
        select(TbLine, TbMapping)
        .outerjoin(TbMapping, TbMapping.line_id == TbLine.id)
        .where(TbLine.engagement_id == engagement_id)
    ).all()

    result = SideA()
    units: list[str] = []
    for line, mapping in rows:
        result.total_lines += 1
        units.append(line.unit or "absolute")

        status = mapping.status if mapping is not None else "unmapped"
        choice = None
        if mapping is not None and status in ACCEPTED_STATUSES:
            choice = mapping.resolved_fsli or mapping.fsli_code
        if choice and choice in taxonomy:
            amount = float(line.normalized_amount or 0.0)
            result.by_fsli[choice] = result.by_fsli.get(choice, 0.0) + sign_of(
                taxonomy, choice
            ) * amount
            result.raw_by_fsli[choice] = result.raw_by_fsli.get(choice, 0.0) + amount
            result.lines_by_fsli[choice] = result.lines_by_fsli.get(choice, 0) + 1
            result.ids_by_fsli.setdefault(choice, []).append(line.id)
            result.mapped_lines += 1
        else:
            result.exposure.append(
                ExposureLine(
                    line_id=line.id,
                    raw_name=line.raw_name,
                    group_name=line.group_name,
                    raw_code=line.raw_code,
                    amount=float(line.normalized_amount or 0.0),
                    status="pending_review" if status == "pending_review" else "unmapped",
                    method=mapping.method if mapping is not None else "unmapped",
                    candidate=(mapping.fsli_code if mapping is not None else None),
                )
            )
    result.unit = _majority(units)
    return result


def side_b(
    session: Session,
    engagement_id: int,
    taxonomy: Taxonomy,
    period: Optional[str] = None,
) -> SideB:
    """Aggregate the current-period face rows of the draft financial statements."""
    query = select(FsLine).where(
        FsLine.engagement_id == engagement_id,
        FsLine.is_current.is_(True),
        FsLine.measure == MEASURE_FACE,
    )
    if period:
        query = query.where(FsLine.period == period)
    rows = session.scalars(query.order_by(FsLine.id)).all()

    result = SideB()
    units: list[str] = []
    periods: Counter[str] = Counter()
    for row in rows:
        units.append(row.unit or "absolute")
        periods[row.period] = periods.get(row.period, 0) + 1

        if row.group_code:
            result.by_group[row.group_code] = result.by_group.get(
                row.group_code, 0.0
            ) + float(row.normalized_value or 0.0)
            result.rows_by_group[row.group_code] = (
                result.rows_by_group.get(row.group_code, 0) + 1
            )
            result.ids_by_group.setdefault(row.group_code, []).append(row.id)
        elif row.fsli_code:
            result.by_fsli[row.fsli_code] = result.by_fsli.get(
                row.fsli_code, 0.0
            ) + float(row.normalized_value or 0.0)
            result.rows_by_fsli[row.fsli_code] = (
                result.rows_by_fsli.get(row.fsli_code, 0) + 1
            )
            result.ids_by_fsli.setdefault(row.fsli_code, []).append(row.id)
        else:
            result.unmapped.append(
                FsExposureRow(
                    line_id=row.id,
                    label=row.source_ref or "",
                    statement=row.statement or "",
                    value=row.normalized_value,
                    period=row.period or "",
                )
            )

    # Subtotal rows are excluded from the tie-out but feed articulation.
    subtotal_query = select(FsLine).where(
        FsLine.engagement_id == engagement_id,
        FsLine.is_current.is_(True),
        FsLine.is_subtotal.is_(True),
    )
    if period:
        subtotal_query = subtotal_query.where(FsLine.period == period)
    for row in session.scalars(subtotal_query.order_by(FsLine.id)):
        result.subtotals.append(
            SubtotalRow(
                label=row.source_ref or "",
                statement=row.statement or "",
                value=float(row.normalized_value or 0.0),
                period=row.period or "",
            )
        )

    result.duplicate_fsli = {
        code: count for code, count in result.rows_by_fsli.items() if count > 1
    }
    result.duplicate_fsli.update(
        {code: count for code, count in result.rows_by_group.items() if count > 1}
    )
    result.unit = _majority(units)
    result.periods = sorted(periods)
    return result


__all__ = [
    "ACCEPTED_STATUSES",
    "ExposureLine",
    "FsExposureRow",
    "SideA",
    "SideB",
    "SubtotalRow",
    "side_a",
    "side_b",
    "sign_of",
]
