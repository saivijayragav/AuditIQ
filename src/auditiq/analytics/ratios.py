"""Financial ratio definitions for SA 520 analytical procedures.

Each ratio is a named computation over FSLI-level aggregates. The definitions
reference Schedule III taxonomy codes directly, so they work on any engagement
that has been ingested and (for Side A ratios) mapped.

Ratios fall into five families:

* **Liquidity** — can the company pay near-term obligations?
* **Solvency** — long-term debt capacity and leverage.
* **Profitability** — operating efficiency and returns.
* **Activity** — how fast assets turn over.
* **Coverage** — ability to service debt from operations.

The *Companies (Accounts) Rules, 2014* (as amended) mandate certain ratios in
the notes to Division I / Division II financial statements.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class RatioFamily(str, Enum):
    LIQUIDITY = "liquidity"
    SOLVENCY = "solvency"
    PROFITABILITY = "profitability"
    ACTIVITY = "activity"
    COVERAGE = "coverage"


# ── FSLI code groups (keep in sync with config/taxonomy/fsli_schema.csv) ─────

# Current assets.
CURRENT_ASSET_CODES = (
    "AST_CI", "AST_INV", "AST_TR", "AST_CASH", "AST_STLA", "AST_OCA",
)

# Quick assets (current assets minus inventories).
QUICK_ASSET_CODES = tuple(c for c in CURRENT_ASSET_CODES if c != "AST_INV")

# Current liabilities.
CURRENT_LIABILITY_CODES = (
    "LIA_STB", "LIA_TP", "LIA_OCL", "LIA_STP",
)

# All asset codes (for total assets).
ALL_ASSET_CODES = (
    "AST_PPE", "AST_INTG", "AST_CWIP", "AST_IAUD", "AST_NCI", "AST_DTA",
    "AST_LTLA", "AST_ONCA",
) + CURRENT_ASSET_CODES

# Equity codes.
EQUITY_CODES = ("EQ_SC", "EQ_RS")

# Total borrowings (debt).
DEBT_CODES = ("LIA_LTB", "LIA_STB")

# All liability codes.
ALL_LIABILITY_CODES = (
    "LIA_LTB", "LIA_DTL", "LIA_OLTL", "LIA_LTP",
) + CURRENT_LIABILITY_CODES

# Revenue codes.
REVENUE_CODES = ("INC_REV_SALES", "INC_REV_SERV", "INC_REV_OTH")

# Cost of goods sold (materials consumed + purchases + inventory change).
COGS_CODES = ("EXP_MAT", "EXP_PUR", "EXP_INVCH")

# All expense codes (before tax).
OPERATING_EXPENSE_CODES = (
    "EXP_MAT", "EXP_PUR", "EXP_INVCH", "EXP_EMP", "EXP_FIN",
    "EXP_DEP", "EXP_OTH", "EXP_EXC",
)

# Tax expense.
TAX_CODES = ("EXP_TAXC", "EXP_TAXD")

# Finance costs.
FINANCE_COST_CODES = ("EXP_FIN",)

# Depreciation.
DEPRECIATION_CODES = ("EXP_DEP",)

# Trade receivables.
RECEIVABLE_CODES = ("AST_TR",)

# Inventories.
INVENTORY_CODES = ("AST_INV",)

# Trade payables.
PAYABLE_CODES = ("LIA_TP",)


@dataclass(frozen=True)
class RatioDefinition:
    """A named financial ratio."""

    code: str
    name: str
    family: RatioFamily
    description: str
    unit: str = ""            # %, x, days
    invert_is_better: bool = False  # True when a lower ratio is healthier
    statutory: bool = False   # required by Companies (Accounts) Rules


# ── Ratio catalogue ─────────────────────────────────────────────────────────

RATIO_DEFINITIONS: list[RatioDefinition] = [
    # Liquidity.
    RatioDefinition(
        code="current_ratio",
        name="Current Ratio",
        family=RatioFamily.LIQUIDITY,
        description="Current Assets / Current Liabilities",
        unit="x",
        statutory=True,
    ),
    RatioDefinition(
        code="quick_ratio",
        name="Quick Ratio (Acid Test)",
        family=RatioFamily.LIQUIDITY,
        description="(Current Assets - Inventories) / Current Liabilities",
        unit="x",
    ),

    # Solvency.
    RatioDefinition(
        code="debt_equity",
        name="Debt-Equity Ratio",
        family=RatioFamily.SOLVENCY,
        description="Total Borrowings / Shareholders' Equity",
        unit="x",
        invert_is_better=True,
        statutory=True,
    ),
    RatioDefinition(
        code="debt_service_coverage",
        name="Debt Service Coverage Ratio",
        family=RatioFamily.SOLVENCY,
        description="(PAT + Depreciation + Finance Costs) / (Finance Costs + LT Borrowings repayable in CY)",
        unit="x",
        statutory=True,
    ),

    # Profitability.
    RatioDefinition(
        code="gross_profit_margin",
        name="Gross Profit Margin",
        family=RatioFamily.PROFITABILITY,
        description="(Revenue - COGS) / Revenue * 100",
        unit="%",
        statutory=True,
    ),
    RatioDefinition(
        code="operating_profit_margin",
        name="Operating Profit Margin",
        family=RatioFamily.PROFITABILITY,
        description="EBIT / Revenue * 100",
        unit="%",
        statutory=True,
    ),
    RatioDefinition(
        code="net_profit_margin",
        name="Net Profit Margin",
        family=RatioFamily.PROFITABILITY,
        description="PAT / Revenue * 100",
        unit="%",
        statutory=True,
    ),
    RatioDefinition(
        code="return_on_equity",
        name="Return on Equity",
        family=RatioFamily.PROFITABILITY,
        description="PAT / Shareholders' Equity * 100",
        unit="%",
        statutory=True,
    ),
    RatioDefinition(
        code="return_on_capital_employed",
        name="Return on Capital Employed",
        family=RatioFamily.PROFITABILITY,
        description="EBIT / (Total Assets - Current Liabilities) * 100",
        unit="%",
        statutory=True,
    ),
    RatioDefinition(
        code="return_on_assets",
        name="Return on Assets",
        family=RatioFamily.PROFITABILITY,
        description="PAT / Total Assets * 100",
        unit="%",
    ),

    # Activity (turnover).
    RatioDefinition(
        code="debtors_turnover",
        name="Trade Receivables Turnover",
        family=RatioFamily.ACTIVITY,
        description="Revenue / Trade Receivables",
        unit="x",
        statutory=True,
    ),
    RatioDefinition(
        code="inventory_turnover",
        name="Inventory Turnover",
        family=RatioFamily.ACTIVITY,
        description="COGS / Inventories",
        unit="x",
        statutory=True,
    ),
    RatioDefinition(
        code="creditors_turnover",
        name="Trade Payables Turnover",
        family=RatioFamily.ACTIVITY,
        description="Purchases / Trade Payables",
        unit="x",
        statutory=True,
    ),
    RatioDefinition(
        code="asset_turnover",
        name="Total Asset Turnover",
        family=RatioFamily.ACTIVITY,
        description="Revenue / Total Assets",
        unit="x",
    ),

    # Coverage.
    RatioDefinition(
        code="interest_coverage",
        name="Interest Coverage Ratio",
        family=RatioFamily.COVERAGE,
        description="EBIT / Finance Costs",
        unit="x",
    ),
]

RATIO_BY_CODE: dict[str, RatioDefinition] = {r.code: r for r in RATIO_DEFINITIONS}


# ── Computation ──────────────────────────────────────────────────────────────


def _sum(agg: dict[str, float], codes: tuple[str, ...]) -> float:
    return sum(agg.get(c, 0.0) for c in codes)


@dataclass
class RatioResult:
    """One computed ratio, optionally with a prior-year comparison."""

    definition: RatioDefinition
    current: Optional[float] = None
    prior: Optional[float] = None
    change: Optional[float] = None       # current − prior
    change_pct: Optional[float] = None   # % change
    flag: str = ""                        # anomaly flag, if any

    @property
    def code(self) -> str:
        return self.definition.code

    @property
    def name(self) -> str:
        return self.definition.name

    @property
    def family(self) -> str:
        return self.definition.family.value

    @property
    def unit(self) -> str:
        return self.definition.unit

    @property
    def statutory(self) -> bool:
        return self.definition.statutory

    @property
    def formula_desc(self) -> str:
        return self.definition.description

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "name": self.name,
            "family": self.family,
            "statutory": self.statutory,
            "unit": self.unit,
            "current": self.current,
            "prior": self.prior,
            "change": self.change,
            "change_pct": self.change_pct,
            "formula_desc": self.formula_desc,
        }


def _safe_divide(numerator: float, denominator: float) -> Optional[float]:
    if abs(denominator) < 1e-10:
        return None
    return numerator / denominator


def compute_ratios(
    agg: dict[str, float],
    prior_agg: Optional[dict[str, float]] = None,
) -> list[RatioResult]:
    """Compute all ratios from FSLI-level aggregates.

    ``agg`` is a ``{fsli_code: presentation_value}`` dict for the current
    period.  ``prior_agg`` is the same for the prior year (if available).
    All values must be in **presentation space** (positive = natural
    direction for each FSLI, same convention as Side B).
    """
    results: list[RatioResult] = []

    for defn in RATIO_DEFINITIONS:
        current = _compute_single(defn, agg)
        prior = _compute_single(defn, prior_agg) if prior_agg else None

        change = None
        change_pct = None
        if current is not None and prior is not None:
            change = current - prior
            if abs(prior) > 1e-10:
                change_pct = (change / abs(prior)) * 100.0

        results.append(RatioResult(
            definition=defn,
            current=current,
            prior=prior,
            change=change,
            change_pct=change_pct,
        ))

    return results


def _compute_single(defn: RatioDefinition, agg: Optional[dict[str, float]]) -> Optional[float]:
    """Compute one ratio from an FSLI aggregation dict."""
    if agg is None:
        return None

    revenue = agg.get("REV_OPERATIONS")
    if not revenue:
        revenue = _sum(agg, REVENUE_CODES)
    cogs = _sum(agg, COGS_CODES)
    total_income = revenue + agg.get("INC_OTH", 0.0)
    total_expense = _sum(agg, OPERATING_EXPENSE_CODES)
    tax = _sum(agg, TAX_CODES)
    pat = total_income - total_expense - tax
    finance_costs = _sum(agg, FINANCE_COST_CODES)
    depreciation = _sum(agg, DEPRECIATION_CODES)
    ebit = pat + tax + finance_costs

    current_assets = _sum(agg, CURRENT_ASSET_CODES)
    current_liabilities = _sum(agg, CURRENT_LIABILITY_CODES)
    quick_assets = _sum(agg, QUICK_ASSET_CODES)
    total_assets = _sum(agg, ALL_ASSET_CODES)
    equity = _sum(agg, EQUITY_CODES)
    debt = _sum(agg, DEBT_CODES)
    receivables = _sum(agg, RECEIVABLE_CODES)
    inventory = _sum(agg, INVENTORY_CODES)
    payables = _sum(agg, PAYABLE_CODES)
    purchases = _sum(agg, ("EXP_PUR",))
    capital_employed = total_assets - current_liabilities

    code = defn.code

    if code == "current_ratio":
        return _safe_divide(current_assets, current_liabilities)
    elif code == "quick_ratio":
        return _safe_divide(quick_assets, current_liabilities)
    elif code == "debt_equity":
        return _safe_divide(debt, equity)
    elif code == "debt_service_coverage":
        # Simplified: denominator uses finance costs only (since we lack
        # principal-repayment detail from the Schedule III face).
        numerator = pat + depreciation + finance_costs
        return _safe_divide(numerator, finance_costs) if finance_costs else None
    elif code == "gross_profit_margin":
        return _safe_divide(revenue - cogs, revenue) * 100.0 if revenue else None
    elif code == "operating_profit_margin":
        return _safe_divide(ebit, revenue) * 100.0 if revenue else None
    elif code == "net_profit_margin":
        return _safe_divide(pat, revenue) * 100.0 if revenue else None
    elif code == "return_on_equity":
        return _safe_divide(pat, equity) * 100.0 if equity else None
    elif code == "return_on_capital_employed":
        return _safe_divide(ebit, capital_employed) * 100.0 if capital_employed else None
    elif code == "return_on_assets":
        return _safe_divide(pat, total_assets) * 100.0 if total_assets else None
    elif code == "debtors_turnover":
        return _safe_divide(revenue, receivables)
    elif code == "inventory_turnover":
        return _safe_divide(cogs, inventory) if inventory else None
    elif code == "creditors_turnover":
        # If no explicit purchases, fall back to COGS.
        denom = purchases if purchases else cogs
        return _safe_divide(denom, payables)
    elif code == "asset_turnover":
        return _safe_divide(revenue, total_assets)
    elif code == "interest_coverage":
        return _safe_divide(ebit, finance_costs)
    else:
        return None


__all__ = [
    "ALL_ASSET_CODES",
    "ALL_LIABILITY_CODES",
    "COGS_CODES",
    "CURRENT_ASSET_CODES",
    "CURRENT_LIABILITY_CODES",
    "DEBT_CODES",
    "EQUITY_CODES",
    "RATIO_BY_CODE",
    "RATIO_DEFINITIONS",
    "REVENUE_CODES",
    "RatioDefinition",
    "RatioFamily",
    "RatioResult",
    "compute_ratios",
]
