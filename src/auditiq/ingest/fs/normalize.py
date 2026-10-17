"""Unit and period binding for extracted financial-statement rows.

Every reported figure is converted to absolute rupees and bound to a financial
year: the ``current`` column to the engagement period, the ``prior`` column to the
preceding year. This is what makes Side B comparable with the trial balance in
reconciliation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ...core.periods import normalize_fy, prior_fy
from ...core.units import normalize_unit, to_absolute
from .base import FsRow


@dataclass
class BoundValue:
    """A single reported figure, normalised to absolute rupees and dated."""

    fsli_code: Optional[str]
    statement: str
    measure: str
    period: str
    is_current: bool
    report_value: Optional[float]
    unit: str
    normalized_value: Optional[float]
    value_text: str = ""
    label: str = ""
    note_ref: Optional[str] = None
    is_subtotal: bool = False
    location: object = None
    layer: str = "review"


def resolve_unit(explicit: Optional[str], detected: Optional[str]) -> str:
    """Prefer an explicitly supplied unit over the detected one."""
    if explicit:
        return normalize_unit(explicit)
    return normalize_unit(detected)


def bind_row(
    row: FsRow,
    *,
    period: str,
    unit: str,
    fsli_code: Optional[str] = None,
    statement: str = "",
    layer: str = "review",
) -> list[BoundValue]:
    """Bind both columns of a row to absolute rupees and their financial year."""
    normalized_period = normalize_fy(period) or period
    prior_period = prior_fy(normalized_period) or ""
    bound: list[BoundValue] = []

    if row.current is not None:
        bound.append(
            BoundValue(
                fsli_code=fsli_code,
                statement=statement,
                measure=row.measure,
                period=normalized_period,
                is_current=True,
                report_value=row.current,
                unit=unit,
                normalized_value=to_absolute(row.current, unit),
                value_text=row.current_text,
                label=row.label,
                note_ref=row.note_ref,
                is_subtotal=row.is_subtotal,
                location=row.location,
                layer=layer,
            )
        )
    if row.prior is not None:
        bound.append(
            BoundValue(
                fsli_code=fsli_code,
                statement=statement,
                measure=row.measure,
                period=prior_period,
                is_current=False,
                report_value=row.prior,
                unit=unit,
                normalized_value=to_absolute(row.prior, unit),
                value_text=row.prior_text,
                label=row.label,
                note_ref=row.note_ref,
                is_subtotal=row.is_subtotal,
                location=row.location,
                layer=layer,
            )
        )
    return bound


__all__ = ["BoundValue", "bind_row", "resolve_unit"]
