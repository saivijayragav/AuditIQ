"""ICAI SA 520 & SA 240 Year-on-Year (YoY) Anomaly & Fluctuation Engine.

Performs horizontal variance analysis across comparative financial line items:
- Absolute Variance: CY - PY
- Percentage Swing: ((CY - PY) / PY) * 100
- Detects Material Drops (e.g. 88k -> 10k: -88.6%), Massive Spikes, Vanished Accounts, and New Heads.
- Generates statutory audit risk descriptions under SA 520 (Analytical Procedures) and SA 240 (Fraud Risk).
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AnomalyFinding(BaseModel):
    """An individual line item flagged as an anomaly or significant fluctuation."""
    id: int
    page_number: int
    block_id: str
    section: str
    line_item: str
    cy_amount: float = Field(description="Current Year Amount")
    py_amount: float = Field(description="Prior Year Amount")
    variance: float = Field(description="CY - PY")
    pct_change: float = Field(description="Percentage swing from prior year")
    anomaly_type: str = Field(description="'CRITICAL_DROP', 'CRITICAL_SPIKE', 'MATERIAL_SWING', 'WATCH_SWING', 'VANISHED_HEAD', 'NEW_HEAD'")
    severity: str = Field(description="'CRITICAL', 'WARNING', 'WATCH'")
    audit_risk: str = Field(description="ICAI SA 520 / SA 240 Statutory audit explanation")
    suggested_inquiry: str = Field(description="Actionable auditor question for copilot investigation")


class AnomalySummary(BaseModel):
    """Aggregate statistics of YoY anomaly analysis."""
    total_comparative_items: int
    critical_count: int
    warning_count: int
    watch_count: int
    total_drop_count: int
    total_spike_count: int
    max_drop_pct: float
    max_drop_item: str
    max_spike_pct: float
    max_spike_item: str


class AnomalyReport(BaseModel):
    """Full report returned to UI and API."""
    summary: AnomalySummary
    findings: List[AnomalyFinding]


def detect_horizontal_anomalies(
    records: List[Dict[str, Any]],
    min_material_amount: float = 50.0,
    critical_swing_pct: float = 30.0,
    watch_swing_pct: float = 15.0,
) -> AnomalyReport:
    """Analyze all financial records in a session and extract significant YoY anomalies."""
    findings: List[AnomalyFinding] = []

    total_comparative = 0
    total_drops = 0
    total_spikes = 0
    max_drop_pct = 0.0
    max_drop_item = ""
    max_spike_pct = 0.0
    max_spike_item = ""

    for idx, r in enumerate(records):
        cy = float(r.get("amount") or 0.0)
        py = float(r.get("prior_amount") or 0.0)
        raw_text = r.get("raw_text", "")
        line_item = r.get("line_item", "")

        # Skip if both are zero
        if cy == 0.0 and py == 0.0:
            continue

        # Skip if amounts are identical or near identical
        if math.isclose(abs(cy), abs(py), rel_tol=1e-4):
            continue

        # Skip non-comparative noise:
        # e.g., if one amount is share face value (0.10, 1.0) and the other is share count (10,000,000+)
        # or if ratio exceeds 1,000x and one number is under 100 (percentage next to total)
        min_v = min(abs(cy), abs(py))
        max_v = max(abs(cy), abs(py))
        if min_v > 0 and (max_v / min_v) > 5000.0 and min_v < 100.0:
            continue

        # If both are below the minimum threshold, skip immaterial clutter
        if max(abs(cy), abs(py)) < min_material_amount:
            continue

        total_comparative += 1
        variance = cy - py
        abs_var = abs(variance)

        if py > 0.0:
            pct = (variance / py) * 100.0
        elif py == 0.0 and cy > 0.0:
            pct = 100.0
        elif py < 0.0:
            pct = (variance / abs(py)) * 100.0
        else:
            pct = -100.0

        # Track max drops and spikes
        if pct < max_drop_pct:
            max_drop_pct = pct
            max_drop_item = line_item[:35]
        if pct > max_spike_pct and pct < 5000.0:
            max_spike_pct = pct
            max_spike_item = line_item[:35]

        # Classification logic based on ICAI SA 520 & SA 240
        if py > min_material_amount and cy < (py * 0.25):
            # Dropped by > 75% (e.g. 88k -> 10k is -88.6%)
            anom_type = "CRITICAL_DROP"
            sev = "CRITICAL"
            risk = (
                f"Severe expense/balance reduction of {abs(pct):.1f}% (INR {abs_var:,.2f} drop). "
                "Audit Risk under SA 240 / SA 520: Potential suppression of expenses, unrecorded liabilities, "
                "or cut-off timing errors designed to artificially boost operating margin."
            )
            total_drops += 1

        elif py > min_material_amount and cy > (py * 2.25):
            # More than doubled (> +125% jump)
            anom_type = "CRITICAL_SPIKE"
            sev = "CRITICAL"
            risk = (
                f"Extraordinary surge of {pct:+.1f}% (INR {abs_var:,.2f} increase). "
                "Audit Risk under SA 500 / SA 240: Potential misclassification of capital expenditure as revenue, "
                "unbudgeted vendor commitments, or fictitious invoices."
            )
            total_spikes += 1

        elif py > 0.0 and cy == 0.0:
            anom_type = "VANISHED_HEAD"
            sev = "WARNING"
            risk = (
                f"Account head completely ceased (Prior: INR {py:,.2f} -> Current: INR 0). "
                "Audit Risk: Potential complete omission, unrecorded liability release, or hidden reclassification under general overheads."
            )
            total_drops += 1

        elif py == 0.0 and cy > (min_material_amount * 2):
            anom_type = "NEW_HEAD"
            sev = "WARNING"
            risk = (
                f"Newly created account head (Current: INR {cy:,.2f} vs Prior: INR 0). "
                "Audit Risk: Unbudgeted expense stream or new vendor relationship requiring board authorization and agreement review."
            )
            total_spikes += 1

        elif abs(pct) >= critical_swing_pct and abs_var >= min_material_amount:
            anom_type = "MATERIAL_SWING"
            sev = "CRITICAL" if abs_var > (min_material_amount * 5) else "WARNING"
            risk = (
                f"Material fluctuation of {pct:+.1f}% (INR {abs_var:,.2f} variance). "
                "Audit Risk under SA 520: Line item exceeds tolerable audit threshold; obtain corroborated management representation."
            )
            if pct < 0:
                total_drops += 1
            else:
                total_spikes += 1

        elif abs(pct) >= watch_swing_pct and abs_var >= (min_material_amount / 2):
            anom_type = "WATCH_SWING"
            sev = "WATCH"
            risk = (
                f"Moderate variation of {pct:+.1f}% (INR {abs_var:,.2f} variance). "
                "Monitor for cumulative trend divergence across quarterly results."
            )
            if pct < 0:
                total_drops += 1
            else:
                total_spikes += 1
        else:
            continue

        item_name = line_item or "Line Item"
        inquiry_prompt = (
            f"As Statutory Auditor under ICAI SA 520, investigate the significant anomaly in '{item_name}': "
            f"Current Year is INR {cy:,.2f} versus Prior Year INR {py:,.2f} (Variance: {variance:+,.2f}, Swing: {pct:+.1f}%). "
            f"Examine Notes to Financial Statements for Page {r.get('page_number', 0)}, explain whether this represents "
            f"genuine business volume changes, and identify statutory audit risks under SA 240."
        )

        findings.append(
            AnomalyFinding(
                id=r.get("id") or (idx + 1),
                page_number=r.get("page_number", 0),
                block_id=r.get("block_id", ""),
                section=r.get("section", "Financial Statements"),
                line_item=item_name,
                cy_amount=cy,
                py_amount=py,
                variance=variance,
                pct_change=pct,
                anomaly_type=anom_type,
                severity=sev,
                audit_risk=risk,
                suggested_inquiry=inquiry_prompt,
            )
        )

    # Sort: CRITICAL first, then WARNING, then WATCH, ordered by largest absolute variance
    sev_rank = {"CRITICAL": 0, "WARNING": 1, "WATCH": 2}
    findings.sort(key=lambda x: (sev_rank.get(x.severity, 3), -abs(x.variance)))

    crit_cnt = sum(1 for f in findings if f.severity == "CRITICAL")
    warn_cnt = sum(1 for f in findings if f.severity == "WARNING")
    watch_cnt = sum(1 for f in findings if f.severity == "WATCH")

    summary = AnomalySummary(
        total_comparative_items=total_comparative,
        critical_count=crit_cnt,
        warning_count=warn_cnt,
        watch_count=watch_cnt,
        total_drop_count=total_drops,
        total_spike_count=total_spikes,
        max_drop_pct=max_drop_pct,
        max_drop_item=max_drop_item or "None",
        max_spike_pct=max_spike_pct,
        max_spike_item=max_spike_item or "None",
    )

    return AnomalyReport(summary=summary, findings=findings)
