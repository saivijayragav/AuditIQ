"""SA 520 analytical procedures: anomaly detection via ratio analysis.

Flags computed ratios against configurable thresholds:

* **year-on-year swing** — a ratio that moved >15 % from the prior year.
* **absolute red-flag** — a value outside a safe range (e.g. current ratio < 1).
* **cross-validation** — two ratios that are inconsistent with each other.

Every finding carries a severity (``material`` / ``watch`` / ``info``) and a
plain-English explanation, so the auditor can decide whether to investigate.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from .ratios import RatioResult, RATIO_DEFINITIONS


# ── Configurable thresholds ──────────────────────────────────────────────────

DEFAULT_SWING_THRESHOLD = 15.0  # % year-on-year change that triggers a flag
DEFAULT_MATERIAL_SWING = 25.0   # % change that upgrades to "material"

# Absolute red-flag bounds: (lower, upper).  None means no bound on that side.
ABSOLUTE_BOUNDS: dict[str, tuple[Optional[float], Optional[float]]] = {
    "current_ratio":          (1.0, None),
    "quick_ratio":            (0.75, None),
    "debt_equity":            (None, 2.0),
    "interest_coverage":      (1.5, None),
    "gross_profit_margin":    (0.0, None),   # negative GP is a red flag
    "net_profit_margin":      (None, None),  # no hard bound; swing matters more
    "debt_service_coverage":  (1.0, None),
}

# Cross-validation rules: if both conditions are true, flag it.
CROSS_CHECKS: list[tuple[str, str, str]] = [
    # (condition_description, ratio_a_code, ratio_b_code)
    # Checked programmatically below.
]


# ── Severities ───────────────────────────────────────────────────────────────

SEVERITY_MATERIAL = "material"
SEVERITY_WATCH = "watch"
SEVERITY_INFO = "info"
SEVERITY_NONE = "none"


@dataclass
class AnalyticalFinding:
    """One flagged anomaly from an analytical procedure."""

    ratio_code: str
    ratio_name: str
    family: str
    severity: str
    flag_type: str  # "swing" | "absolute" | "cross_check" | "data_gap"
    message: str
    current_value: Optional[float] = None
    prior_value: Optional[float] = None
    change_pct: Optional[float] = None
    threshold: Optional[float] = None

    def to_dict(self) -> dict:
        return {
            "ratio_code": self.ratio_code,
            "ratio_name": self.ratio_name,
            "family": self.family,
            "severity": self.severity,
            "flag_type": self.flag_type,
            "message": self.message,
            "current_value": self.current_value,
            "prior_value": self.prior_value,
            "change_pct": self.change_pct,
            "threshold": self.threshold,
        }


@dataclass
class AnalyticalProcedureConfig:
    """Thresholds for the analytical procedures engine."""

    swing_threshold: float = DEFAULT_SWING_THRESHOLD
    material_swing: float = DEFAULT_MATERIAL_SWING
    absolute_bounds: dict[str, tuple[Optional[float], Optional[float]]] = field(
        default_factory=lambda: dict(ABSOLUTE_BOUNDS)
    )


@dataclass
class AnalyticalReport:
    """Full SA 520 analytical procedures report."""

    engagement_id: int
    period: str
    ratios: list[RatioResult]
    findings: list[AnalyticalFinding]
    client_code: str = ""
    basis: str = ""
    has_prior: bool = False
    statutory_count: int = 0
    computed_count: int = 0
    flagged_count: int = 0

    @property
    def status(self) -> str:
        material = sum(1 for f in self.findings if f.severity == SEVERITY_MATERIAL)
        watch = sum(1 for f in self.findings if f.severity == SEVERITY_WATCH)
        if material:
            return "material findings"
        if watch:
            return "watch items"
        if self.findings:
            return "minor observations"
        return "clean"

    @property
    def material_findings(self) -> list[AnalyticalFinding]:
        return [f for f in self.findings if f.severity == SEVERITY_MATERIAL]

    @property
    def watch_findings(self) -> list[AnalyticalFinding]:
        return [f for f in self.findings if f.severity == SEVERITY_WATCH]

    def to_dict(self) -> dict:
        return {
            "engagement_id": self.engagement_id,
            "client_code": self.client_code,
            "period": self.period,
            "basis": self.basis,
            "status": self.status,
            "has_prior": self.has_prior,
            "statutory_count": self.statutory_count,
            "computed_count": self.computed_count,
            "flagged_count": self.flagged_count,
            "ratios": [r.to_dict() for r in self.ratios],
            "findings": [f.to_dict() for f in self.findings],
        }


def analyse(
    ratios: list[RatioResult],
    config: Optional[AnalyticalProcedureConfig] = None,
) -> list[AnalyticalFinding]:
    """Run all analytical procedures on a set of computed ratios."""
    config = config or AnalyticalProcedureConfig()
    findings: list[AnalyticalFinding] = []

    for ratio in ratios:
        findings.extend(_check_swing(ratio, config))
        findings.extend(_check_absolute(ratio, config))
        findings.extend(_check_data_gap(ratio))

    findings.extend(_cross_validate(ratios, config))

    # Sort: material first, then watch, then info.
    severity_order = {SEVERITY_MATERIAL: 0, SEVERITY_WATCH: 1, SEVERITY_INFO: 2}
    findings.sort(key=lambda f: severity_order.get(f.severity, 3))

    return findings


def _check_swing(ratio: RatioResult, config: AnalyticalProcedureConfig) -> list[AnalyticalFinding]:
    """Flag year-on-year swings above the threshold."""
    if ratio.change_pct is None:
        return []

    abs_change = abs(ratio.change_pct)
    if abs_change < config.swing_threshold:
        return []

    direction = "increased" if ratio.change_pct > 0 else "decreased"
    severity = SEVERITY_MATERIAL if abs_change >= config.material_swing else SEVERITY_WATCH

    return [AnalyticalFinding(
        ratio_code=ratio.code,
        ratio_name=ratio.name,
        family=ratio.family,
        severity=severity,
        flag_type="swing",
        message=(
            f"{ratio.name} {direction} by {abs_change:.1f}% "
            f"(from {_fmt(ratio.prior, ratio.unit)} to {_fmt(ratio.current, ratio.unit)}). "
            f"Investigate the underlying cause per SA 520."
        ),
        current_value=ratio.current,
        prior_value=ratio.prior,
        change_pct=ratio.change_pct,
        threshold=config.swing_threshold,
    )]


def _check_absolute(ratio: RatioResult, config: AnalyticalProcedureConfig) -> list[AnalyticalFinding]:
    """Flag ratios outside safe absolute bounds."""
    if ratio.current is None:
        return []

    bounds = config.absolute_bounds.get(ratio.code)
    if bounds is None:
        return []

    lower, upper = bounds
    findings: list[AnalyticalFinding] = []

    if lower is not None and ratio.current < lower:
        findings.append(AnalyticalFinding(
            ratio_code=ratio.code,
            ratio_name=ratio.name,
            family=ratio.family,
            severity=SEVERITY_MATERIAL,
            flag_type="absolute",
            message=(
                f"{ratio.name} is {_fmt(ratio.current, ratio.unit)}, "
                f"below the safe threshold of {_fmt(lower, ratio.unit)}. "
                f"This may indicate {'liquidity' if ratio.family == 'liquidity' else 'financial'} stress."
            ),
            current_value=ratio.current,
            threshold=lower,
        ))

    if upper is not None and ratio.current > upper:
        findings.append(AnalyticalFinding(
            ratio_code=ratio.code,
            ratio_name=ratio.name,
            family=ratio.family,
            severity=SEVERITY_WATCH,
            flag_type="absolute",
            message=(
                f"{ratio.name} is {_fmt(ratio.current, ratio.unit)}, "
                f"above the reference of {_fmt(upper, ratio.unit)}. "
                f"Verify this is appropriate for the entity's industry and scale."
            ),
            current_value=ratio.current,
            threshold=upper,
        ))

    return findings


def _check_data_gap(ratio: RatioResult) -> list[AnalyticalFinding]:
    """Flag statutory ratios that could not be computed (missing data)."""
    if ratio.current is not None:
        return []
    if not ratio.statutory:
        return []
    return [AnalyticalFinding(
        ratio_code=ratio.code,
        ratio_name=ratio.name,
        family=ratio.family,
        severity=SEVERITY_INFO,
        flag_type="data_gap",
        message=(
            f"{ratio.name} could not be computed — required FSLI data is missing. "
            f"This ratio is mandatory per Companies (Accounts) Rules."
        ),
    )]


def _cross_validate(
    ratios: list[RatioResult], config: AnalyticalProcedureConfig
) -> list[AnalyticalFinding]:
    """Flag cross-ratio inconsistencies."""
    findings: list[AnalyticalFinding] = []
    by_code = {r.code: r for r in ratios}

    revenue_growth = by_code.get("debtors_turnover")
    debtor_turn = by_code.get("debtors_turnover")

    # Revenue growing but debtors turnover declining → collection problem.
    if debtor_turn and debtor_turn.change_pct is not None and debtor_turn.change_pct < -10:
        net_margin = by_code.get("net_profit_margin")
        if net_margin and net_margin.change_pct is not None and net_margin.change_pct > 5:
            findings.append(AnalyticalFinding(
                ratio_code="debtors_turnover",
                ratio_name="Trade Receivables Turnover vs Net Profit Margin",
                family="cross_check",
                severity=SEVERITY_WATCH,
                flag_type="cross_check",
                message=(
                    f"Net profit margin improved by {net_margin.change_pct:.1f}% "
                    f"but debtors turnover declined by {abs(debtor_turn.change_pct):.1f}%. "
                    f"This may indicate aggressive revenue recognition or collection issues."
                ),
                current_value=debtor_turn.current,
                change_pct=debtor_turn.change_pct,
            ))

    # Gross margin declining while revenue growing → pricing pressure.
    gp = by_code.get("gross_profit_margin")
    asset_turn = by_code.get("asset_turnover")
    if (
        gp and gp.change_pct is not None and gp.change_pct < -5
        and asset_turn and asset_turn.change_pct is not None and asset_turn.change_pct > 10
    ):
        findings.append(AnalyticalFinding(
            ratio_code="gross_profit_margin",
            ratio_name="Gross Margin vs Asset Turnover",
            family="cross_check",
            severity=SEVERITY_WATCH,
            flag_type="cross_check",
            message=(
                f"Asset turnover improved by {asset_turn.change_pct:.1f}% "
                f"but gross margin declined by {abs(gp.change_pct):.1f}%. "
                f"The entity may be growing volume at the expense of margins."
            ),
            current_value=gp.current,
            change_pct=gp.change_pct,
        ))

    # Debt-equity spiking while interest coverage falling → solvency risk.
    de = by_code.get("debt_equity")
    ic = by_code.get("interest_coverage")
    if (
        de and de.change_pct is not None and de.change_pct > 20
        and ic and ic.change_pct is not None and ic.change_pct < -15
    ):
        findings.append(AnalyticalFinding(
            ratio_code="debt_equity",
            ratio_name="Debt-Equity vs Interest Coverage",
            family="cross_check",
            severity=SEVERITY_MATERIAL,
            flag_type="cross_check",
            message=(
                f"Debt-equity ratio increased by {de.change_pct:.1f}% "
                f"while interest coverage fell by {abs(ic.change_pct):.1f}%. "
                f"Evaluate going-concern risk per SA 570."
            ),
            current_value=de.current,
            change_pct=de.change_pct,
        ))

    return findings


def _fmt(value: Optional[float], unit: str) -> str:
    if value is None:
        return "n/a"
    if unit == "%":
        return f"{value:.1f}%"
    if unit == "x":
        return f"{value:.2f}x"
    if unit == "days":
        return f"{value:.0f} days"
    return f"{value:,.2f}"


__all__ = [
    "SEVERITY_INFO",
    "SEVERITY_MATERIAL",
    "SEVERITY_NONE",
    "SEVERITY_WATCH",
    "AnalyticalFinding",
    "AnalyticalProcedureConfig",
    "AnalyticalReport",
    "analyse",
]
