"""The two reconciliation gates: rounding tolerance and materiality.

They are deliberately separate.

* **Rounding** is the *only* ignorable difference. It is derived, not chosen: a
  figure presented to ``d`` decimals in a reporting unit has a quantum of
  ``UNIT_FACTORS[unit] * 10**-d``, so an extracted value can be off by at most
  half a quantum. Crores to two decimals -> a tolerance of Rs 50,000.
* **Materiality** never accepts a difference. It only grades severity and decides
  what escalates to the exception queue. A performance-materiality band
  (default 0.75 x materiality) separates "watch" from "minor".

Materiality must be supplied (engagement or CLI). There is no silent fallback;
:func:`suggest_materiality` proposes a value for a human to confirm.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..core.groups import GroupIndex
from ..core.taxonomy import Taxonomy, statement_code
from ..core.units import UNIT_FACTORS, normalize_unit

DEFAULT_PM_RATIO = 0.75
DEFAULT_ROUNDING_DECIMALS = 2
SUGGESTION_RATIO = 0.005  # 0.5% of revenue, a common Indian audit heuristic
DEFAULT_SCOPE: tuple[str, ...] = ("BS", "P&L")

# Classification / severity vocabulary.
TIED = "tied"
ROUNDING = "rounding"
MINOR = "minor"
WATCH = "watch"
MATERIAL = "material"

SEVERITY_NONE = "none"
SEVERITY_ORDER = {SEVERITY_NONE: 0, MINOR: 1, WATCH: 2, MATERIAL: 3}

REVENUE_FSLIS = ("INC_REV_SALES", "INC_REV_SERV", "INC_REV_OTH")


class MaterialityError(ValueError):
    """Raised when reconciliation is run without a usable materiality."""


def rounding_tolerance(unit: str, decimals: int = DEFAULT_ROUNDING_DECIMALS) -> float:
    """Half the smallest presentable increment, in absolute rupees."""
    factor = UNIT_FACTORS.get(normalize_unit(unit), 1.0)
    return factor * (10.0 ** -int(decimals)) / 2.0


@dataclass
class ReconConfig:
    """Everything that shapes a reconciliation run."""

    materiality: float
    performance_materiality: float
    rounding_decimals: int = DEFAULT_ROUNDING_DECIMALS
    statements: tuple[str, ...] = field(default=DEFAULT_SCOPE)
    unit: str = "absolute"
    materiality_basis: str = ""

    @property
    def tolerance(self) -> float:
        return rounding_tolerance(self.unit, self.rounding_decimals)

    @property
    def pm_ratio(self) -> float:
        return self.performance_materiality / self.materiality if self.materiality else 0.0

    def in_scope(self, statement: object) -> bool:
        if not self.statements:
            return True
        code = statement_code(statement)
        return code in self.statements

    def as_dict(self) -> dict:
        return {
            "materiality": self.materiality,
            "performance_materiality": self.performance_materiality,
            "pm_ratio": round(self.pm_ratio, 4),
            "rounding_decimals": self.rounding_decimals,
            "tolerance": self.tolerance,
            "statements": list(self.statements),
            "unit": self.unit,
            "materiality_basis": self.materiality_basis,
        }


def build_config(
    materiality: Optional[float],
    *,
    unit: str = "absolute",
    performance_materiality: Optional[float] = None,
    pm_ratio: float = DEFAULT_PM_RATIO,
    rounding_decimals: int = DEFAULT_ROUNDING_DECIMALS,
    statements: Optional[tuple[str, ...]] = None,
    materiality_basis: str = "",
) -> ReconConfig:
    """Build and sanity-check a run configuration.

    Raises :class:`MaterialityError` when materiality is absent or not sensible —
    reconciliation must not silently pick a threshold.
    """
    if materiality is None or float(materiality) <= 0:
        raise MaterialityError(
            "materiality is not set for this engagement; pass --materiality or "
            "run `auditiq materiality set` (see `auditiq materiality suggest`)"
        )
    materiality = float(materiality)

    if performance_materiality is not None:
        pm = float(performance_materiality)
    else:
        pm = materiality * float(pm_ratio)
    if pm <= 0:
        raise MaterialityError("performance materiality must be positive")

    scope = tuple(statements) if statements is not None else DEFAULT_SCOPE
    tolerance = rounding_tolerance(unit, rounding_decimals)
    if materiality <= tolerance:
        raise MaterialityError(
            f"materiality ({materiality:,.2f}) must exceed the rounding tolerance "
            f"({tolerance:,.2f}) for unit '{normalize_unit(unit)}' at "
            f"{rounding_decimals} decimals"
        )

    return ReconConfig(
        materiality=materiality,
        performance_materiality=pm,
        rounding_decimals=int(rounding_decimals),
        statements=scope,
        unit=normalize_unit(unit),
        materiality_basis=materiality_basis,
    )


def classify(variance: float, config: ReconConfig) -> tuple[str, str]:
    """Return ``(classification, severity)`` for a variance under two gates."""
    magnitude = abs(float(variance or 0.0))
    if magnitude == 0:
        return TIED, SEVERITY_NONE
    if magnitude <= config.tolerance:
        return ROUNDING, SEVERITY_NONE
    if magnitude >= config.materiality:
        return MATERIAL, MATERIAL
    if magnitude >= config.performance_materiality:
        return WATCH, WATCH
    return MINOR, MINOR


def variance_percent(variance: float, side_b: float, config: ReconConfig) -> Optional[float]:
    """Variance as a percentage of the reported figure, or ``None`` if meaningless.

    Suppressed when the base is below performance materiality, where a percentage
    would be numerically real but analytically noise.
    """
    if abs(float(side_b or 0.0)) < config.performance_materiality:
        return None
    return float(variance) / float(side_b) * 100.0


def suggest_materiality(
    side_b,
    taxonomy: Taxonomy,
    groups: Optional[GroupIndex] = None,
    ratio: float = SUGGESTION_RATIO,
) -> dict:
    """Propose a materiality from the draft FS (revenue basis, with fallbacks)."""
    groups = groups or GroupIndex([])

    revenue = 0.0
    for code in REVENUE_FSLIS:
        revenue += side_b.by_fsli.get(code, 0.0)
    for group_code, value in side_b.by_group.items():
        if set(groups.members(group_code)) & set(REVENUE_FSLIS):
            revenue += value

    total_assets = sum(
        value
        for code, value in side_b.by_fsli.items()
        if (taxonomy.get(code) is not None and taxonomy.get(code).category == "Asset")
    )

    basis = "revenue" if revenue else "total assets"
    base = revenue or total_assets
    return {
        "revenue": revenue,
        "total_assets": total_assets,
        "ratio": ratio,
        "basis": basis,
        "suggested": base * ratio,
    }


__all__ = [
    "DEFAULT_PM_RATIO",
    "DEFAULT_ROUNDING_DECIMALS",
    "DEFAULT_SCOPE",
    "MATERIAL",
    "MINOR",
    "MaterialityError",
    "ROUNDING",
    "ReconConfig",
    "SEVERITY_NONE",
    "SEVERITY_ORDER",
    "SUGGESTION_RATIO",
    "TIED",
    "WATCH",
    "build_config",
    "classify",
    "rounding_tolerance",
    "suggest_materiality",
    "variance_percent",
]
