"""Run SA 520 analytical procedures for an engagement.

Reads the ingested financial statement data (Side B) for both the current and
prior period, computes all ratios, and runs the anomaly-detection procedures.
No new data ingestion is needed — this works on data already in the store from
``auditiq ingest fs`` and ``auditiq ingest tb`` + ``auditiq map``.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import select

from ..core.groups import GroupIndex, load_default_groups
from ..core.taxonomy import Taxonomy, load_default_taxonomy
from ..reconciliation.aggregate import SideA, SideB, side_a, side_b
from ..store import init_db, session_scope
from ..store.models import Engagement

from .procedures import (
    AnalyticalFinding,
    AnalyticalProcedureConfig,
    AnalyticalReport,
    analyse,
)
from .ratios import (
    ALL_ASSET_CODES,
    ALL_LIABILITY_CODES,
    COGS_CODES,
    CURRENT_ASSET_CODES,
    CURRENT_LIABILITY_CODES,
    DEBT_CODES,
    EQUITY_CODES,
    REVENUE_CODES,
    RatioResult,
    compute_ratios,
)


def _build_agg_from_side_b(side_b_result: SideB) -> dict[str, float]:
    """Convert a Side B aggregation to a flat FSLI dict for ratio computation."""
    agg: dict[str, float] = {}
    for code, value in side_b_result.by_fsli.items():
        agg[code] = agg.get(code, 0.0) + value
    # Groups: expand to their members if available, otherwise use group total
    # as a proxy.  For ratio computation the group totals are additive.
    for code, value in side_b_result.by_group.items():
        agg[code] = agg.get(code, 0.0) + value
    return agg


def _build_agg_from_side_a(
    side_a_result: SideA, taxonomy: Taxonomy
) -> dict[str, float]:
    """Convert a Side A aggregation to a flat FSLI dict for ratio computation."""
    return dict(side_a_result.by_fsli)


def _merge_agg(
    side_a_agg: dict[str, float],
    side_b_agg: dict[str, float],
) -> dict[str, float]:
    """Merge Side A (books) and Side B (FS) into a best-available aggregation.

    Preference: Side B for balance-sheet items (they are the presented figures),
    Side A for P&L items (if Side B is sparse).  In practice, if the FS has been
    fully ingested, Side B is the better source.
    """
    merged = dict(side_b_agg)
    for code, value in side_a_agg.items():
        if code not in merged:
            merged[code] = value
    return merged


def run_analytics(
    engagement_id: int,
    url: Optional[str] = None,
    swing_threshold: float = 15.0,
    material_swing: float = 25.0,
    taxonomy: Optional[Taxonomy] = None,
    groups: Optional[GroupIndex] = None,
) -> AnalyticalReport:
    """Run SA 520 analytical procedures for an engagement.

    Reads the current-period and prior-period data from the store, computes all
    ratios, and flags anomalies.

    Raises ``ValueError`` if the engagement does not exist or has no data.
    """
    taxonomy = taxonomy or load_default_taxonomy()
    groups = groups if groups is not None else load_default_groups(taxonomy=taxonomy)

    init_db(url)
    with session_scope(url) as session:
        engagement = session.get(Engagement, engagement_id)
        if engagement is None:
            raise ValueError(f"no engagement with id {engagement_id}")

        # Current period: prefer Side B (draft FS), supplement with Side A.
        side_b_current = side_b(session, engagement_id, taxonomy)
        side_a_current = side_a(session, engagement_id, taxonomy)

        current_agg = _build_agg_from_side_b(side_b_current)
        if side_a_current.mapped_lines > 0:
            books_agg = _build_agg_from_side_a(side_a_current, taxonomy)
            current_agg = _merge_agg(books_agg, current_agg)

        if not current_agg:
            raise ValueError(
                f"engagement #{engagement_id} has no financial data; "
                "run `auditiq ingest tb` and/or `auditiq ingest fs` first"
            )

        # Prior period: Side B only (from the "prior" column of the FS).
        prior_agg = _build_prior_agg(session, engagement_id, taxonomy)
        has_prior = bool(prior_agg)

        # Compute ratios.
        ratios = compute_ratios(current_agg, prior_agg)

        # Run anomaly detection.
        config = AnalyticalProcedureConfig(
            swing_threshold=swing_threshold,
            material_swing=material_swing,
        )
        findings = analyse(ratios, config)

        return AnalyticalReport(
            engagement_id=engagement_id,
            client_code=engagement.client_code,
            period=engagement.period,
            basis=engagement.basis,
            ratios=ratios,
            findings=findings,
            has_prior=has_prior,
            statutory_count=sum(1 for r in ratios if r.statutory),
            computed_count=sum(1 for r in ratios if r.current is not None),
            flagged_count=len(findings),
        )


def _build_prior_agg(
    session, engagement_id: int, taxonomy: Taxonomy
) -> Optional[dict[str, float]]:
    """Build a prior-year aggregation from the 'prior' column of ingested FS.

    The FS ingestion marks prior-year rows with ``is_current = False``. We
    aggregate those into a flat FSLI dict.
    """
    from ..store.models import FsLine

    rows = session.scalars(
        select(FsLine).where(
            FsLine.engagement_id == engagement_id,
            FsLine.is_current.is_(False),
            FsLine.measure == "face",
            FsLine.is_subtotal.is_(False),
        ).order_by(FsLine.id)
    ).all()

    if not rows:
        return None

    agg: dict[str, float] = {}
    for row in rows:
        if row.group_code:
            agg[row.group_code] = agg.get(row.group_code, 0.0) + float(
                row.normalized_value or 0.0
            )
        elif row.fsli_code:
            agg[row.fsli_code] = agg.get(row.fsli_code, 0.0) + float(
                row.normalized_value or 0.0
            )
    return agg if agg else None


__all__ = [
    "AnalyticalReport",
    "run_analytics",
]
