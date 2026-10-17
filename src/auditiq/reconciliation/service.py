"""Run reconciliation for an engagement and persist the result.

Reads Side A (mapped trial balance) and Side B (client's draft financial
statements), ties them out, checks articulation, attributes the differences, and
writes a reproducible ``recon_run`` + ``recon_line`` set with material variances
escalated to the exception queue.

The draft FS is the default Side B. Analysing the published report remains a
separate, opt-in feature.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional, Sequence

from sqlalchemy import delete, select

from ..core.groups import GroupIndex, load_default_groups
from ..core.taxonomy import Taxonomy, load_default_taxonomy
from ..store import init_db, session_scope
from ..store.models import Engagement, ExceptionRecord, ReconLine, ReconRun
from ..ingest.prepare.aliases import load_alias
from .aggregate import SideA, SideB, side_a, side_b
from .articulation import Finding, articulate
from .attribution import Attribution, attribute
from .materiality import (
    DEFAULT_PM_RATIO,
    DEFAULT_ROUNDING_DECIMALS,
    MATERIAL,
    ReconConfig,
    build_config,
    suggest_materiality,
)
from .tieout import ReconLineResult, tieout


@dataclass
class ReconSummary:
    engagement_id: int
    run_id: Optional[int]
    period: str
    basis: str
    unit: str
    materiality: float
    performance_materiality: float
    rounding_decimals: int
    tolerance: float
    statements: tuple[str, ...]
    materiality_basis: str = ""
    units: int = 0
    tied: int = 0
    rounding: int = 0
    minor: int = 0
    watch: int = 0
    material: int = 0
    exposure_a: float = 0.0
    exposure_a_lines: int = 0
    exposure_b: float = 0.0
    exposure_b_rows: int = 0
    attributed: int = 0
    findings: list[Finding] = field(default_factory=list)
    worst: list[ReconLineResult] = field(default_factory=list)

    @property
    def reconciled(self) -> bool:
        return self.material == 0

    @property
    def status(self) -> str:
        if self.material:
            return "material differences"
        if self.watch:
            return "watch items"
        if self.minor or self.exposure_a_lines or self.exposure_b_rows:
            return "minor residual"
        return "clean"


def _load_materiality(
    session, engagement: Engagement, override: Optional[float]
) -> tuple[Optional[float], str]:
    value = override if override is not None else engagement.materiality_value
    return (float(value) if value is not None else None, engagement.materiality_basis or "")


def _guard_inputs(side_a_result: SideA, side_b_result: SideB, engagement_id: int) -> None:
    if side_a_result.total_lines == 0:
        raise ValueError(
            f"engagement #{engagement_id} has no trial-balance lines; run "
            "`auditiq ingest tb` first"
        )
    pending = [e for e in side_a_result.exposure if e.status == "pending_review"]
    if side_a_result.mapped_lines == 0 and not pending:
        raise ValueError(
            f"engagement #{engagement_id} has no trial-balance mappings; run "
            "`auditiq map` first"
        )
    if not side_b_result.codes() and not side_b_result.unmapped and not side_b_result.subtotals:
        raise ValueError(
            f"engagement #{engagement_id} has no draft financial statements; run "
            "`auditiq ingest fs` first"
        )


def _persist(
    session,
    engagement: Engagement,
    config: ReconConfig,
    results: list[ReconLineResult],
    attributions: dict[str, Attribution],
    side_a_result: SideA,
    side_b_result: SideB,
) -> int:
    # Idempotent re-run: one current run per engagement.
    prior = session.scalars(
        select(ReconRun.id).where(ReconRun.engagement_id == engagement.id)
    ).all()
    if prior:
        session.execute(delete(ReconLine).where(ReconLine.run_id.in_(prior)))
        session.execute(delete(ReconRun).where(ReconRun.id.in_(prior)))
    session.execute(
        delete(ExceptionRecord).where(
            ExceptionRecord.engagement_id == engagement.id,
            ExceptionRecord.kind == "tieout",
        )
    )

    counts = {"tied": 0, "rounding": 0, "minor": 0, "watch": 0, "material": 0}
    for result in results:
        counts[result.classification] = counts.get(result.classification, 0) + 1

    run = ReconRun(
        engagement_id=engagement.id,
        period=engagement.period,
        basis=engagement.basis,
        unit=config.unit,
        statements=",".join(config.statements),
        rounding_decimals=config.rounding_decimals,
        materiality=config.materiality,
        performance_materiality=config.performance_materiality,
        materiality_basis=config.materiality_basis,
        units_total=len(results),
        tied=counts["tied"],
        rounding=counts["rounding"],
        minor=counts["minor"],
        watch=counts["watch"],
        material=counts["material"],
        exposure_a=side_a_result.exposure_total,
        exposure_b=side_b_result.exposure_total,
        config_json=json.dumps(config.as_dict()),
    )
    session.add(run)
    session.flush()

    for result in results:
        attribution = attributions.get(result.code)
        session.add(
            ReconLine(
                run_id=run.id,
                unit_code=result.code,
                is_group=result.unit.is_group,
                statement=result.unit.statement,
                name=result.unit.name,
                side_a=result.side_a,
                side_b=result.side_b,
                variance=result.variance,
                variance_pct=result.variance_pct,
                a_lines=result.a_lines,
                b_rows=result.b_rows,
                classification=result.classification,
                severity=result.severity,
                refs_json=result.refs_json,
                attribution_json=json.dumps(
                    {
                        "explained": attribution.explained if attribution else 0.0,
                        "residual": attribution.residual if attribution else 0.0,
                        "candidates": [
                            {"kind": c.kind, "amount": c.amount, "detail": c.detail, "refs": c.refs}
                            for c in (attribution.candidates if attribution else [])
                        ],
                    }
                ),
            )
        )
        if result.severity == MATERIAL:
            session.add(
                ExceptionRecord(
                    engagement_id=engagement.id,
                    kind="tieout",
                    fsli_code=result.code[:32],
                    severity=MATERIAL,
                    status="open",
                    amount=result.variance,
                    detail=json.dumps(
                        {
                            "unit": result.code,
                            "name": result.unit.name,
                            "side_a": result.side_a,
                            "side_b": result.side_b,
                            "variance": result.variance,
                            "candidates": [
                                {"kind": c.kind, "amount": c.amount, "detail": c.detail}
                                for c in (attribution.candidates if attribution else [])
                            ],
                        }
                    ),
                    note=f"{result.code} {result.unit.name}",
                )
            )
    return run.id


def run_recon(
    engagement_id: int,
    url: Optional[str] = None,
    materiality: Optional[float] = None,
    pm_ratio: float = DEFAULT_PM_RATIO,
    rounding_decimals: int = DEFAULT_ROUNDING_DECIMALS,
    statements: Optional[Sequence[str]] = None,
    persist: bool = True,
    side_b_period: Optional[str] = None,
    taxonomy: Optional[Taxonomy] = None,
    groups: Optional[GroupIndex] = None,
) -> ReconSummary:
    """Reconcile an engagement's books against its draft financial statements."""
    taxonomy = taxonomy or load_default_taxonomy()
    groups = groups if groups is not None else load_default_groups(taxonomy=taxonomy)
    alias = load_alias(taxonomy=taxonomy)

    init_db(url)
    with session_scope(url) as session:
        engagement = session.get(Engagement, engagement_id)
        if engagement is None:
            raise ValueError(f"no engagement with id {engagement_id}")

        side_a_result = side_a(session, engagement_id, taxonomy)
        side_b_result = side_b(session, engagement_id, taxonomy, period=side_b_period)
        _guard_inputs(side_a_result, side_b_result, engagement_id)

        value, basis = _load_materiality(session, engagement, materiality)
        unit = side_b_result.unit or side_a_result.unit
        config = build_config(
            value,
            unit=unit,
            pm_ratio=pm_ratio,
            rounding_decimals=rounding_decimals,
            statements=tuple(statements) if statements is not None else None,
            materiality_basis=basis,
        )

        results = tieout(side_a_result, side_b_result, taxonomy, groups, config)
        findings = articulate(side_a_result, side_b_result, taxonomy, groups, config)
        attributions = attribute(
            results, side_a_result, side_b_result, taxonomy, groups, alias, config
        )

        summary = ReconSummary(
            engagement_id=engagement_id,
            run_id=None,
            period=engagement.period,
            basis=engagement.basis,
            unit=config.unit,
            materiality=config.materiality,
            performance_materiality=config.performance_materiality,
            rounding_decimals=config.rounding_decimals,
            tolerance=config.tolerance,
            statements=config.statements,
            materiality_basis=config.materiality_basis,
            units=len(results),
            tied=sum(1 for r in results if r.classification == "tied"),
            rounding=sum(1 for r in results if r.classification == "rounding"),
            minor=sum(1 for r in results if r.classification == "minor"),
            watch=sum(1 for r in results if r.classification == "watch"),
            material=sum(1 for r in results if r.classification == "material"),
            exposure_a=side_a_result.exposure_total,
            exposure_a_lines=len(side_a_result.exposure),
            exposure_b=side_b_result.exposure_total,
            exposure_b_rows=len(side_b_result.unmapped),
            attributed=sum(1 for r in results if r.code in attributions),
            findings=findings,
            worst=[
                r
                for r in sorted(results, key=lambda r: abs(r.variance), reverse=True)
                if r.severity in ("material", "watch")
            ],
        )

        if persist:
            summary.run_id = _persist(
                session, engagement, config, results, attributions, side_a_result, side_b_result
            )
        return summary


@dataclass
class StoredLine:
    """A persisted reconciliation line, decoded for display."""

    unit_code: str
    name: str
    statement: str
    is_group: bool
    side_a: float
    side_b: float
    variance: float
    variance_pct: Optional[float]
    a_lines: int
    b_rows: int
    classification: str
    severity: str
    attribution: dict = field(default_factory=dict)
    refs: dict = field(default_factory=dict)


@dataclass
class RunInfo:
    """A persisted run header, detached from the session."""

    run_id: int
    engagement_id: int
    period: str
    basis: str
    unit: str
    statements: str
    materiality: float
    performance_materiality: float
    rounding_decimals: int
    units_total: int
    tied: int
    rounding: int
    minor: int
    watch: int
    material: int
    exposure_a: float
    exposure_b: float


@dataclass
class EngagementInfo:
    """A persisted engagement, detached from the session."""

    engagement_id: int
    client_code: str
    period: str
    basis: str
    materiality_value: Optional[float] = None
    materiality_basis: Optional[str] = None


def _decode_line(row: ReconLine) -> StoredLine:
    try:
        attribution = json.loads(row.attribution_json or "{}")
    except ValueError:
        attribution = {}
    try:
        refs = json.loads(row.refs_json or "{}")
    except ValueError:
        refs = {}
    return StoredLine(
        unit_code=row.unit_code,
        name=row.name,
        statement=row.statement,
        is_group=row.is_group,
        side_a=row.side_a,
        side_b=row.side_b,
        variance=row.variance,
        variance_pct=row.variance_pct,
        a_lines=row.a_lines,
        b_rows=row.b_rows,
        classification=row.classification,
        severity=row.severity,
        attribution=attribution,
        refs=refs,
    )


def _run_info(run: ReconRun) -> RunInfo:
    return RunInfo(
        run_id=run.id,
        engagement_id=run.engagement_id,
        period=run.period,
        basis=run.basis,
        unit=run.unit,
        statements=run.statements,
        materiality=run.materiality,
        performance_materiality=run.performance_materiality,
        rounding_decimals=run.rounding_decimals,
        units_total=run.units_total,
        tied=run.tied,
        rounding=run.rounding,
        minor=run.minor,
        watch=run.watch,
        material=run.material,
        exposure_a=run.exposure_a,
        exposure_b=run.exposure_b,
    )


def latest_run(
    engagement_id: int, url: Optional[str] = None
) -> tuple[Optional[RunInfo], list[StoredLine]]:
    """Return the engagement's most recent run and its lines."""
    init_db(url)
    with session_scope(url) as session:
        run = session.scalars(
            select(ReconRun)
            .where(ReconRun.engagement_id == engagement_id)
            .order_by(ReconRun.id.desc())
        ).first()
        if run is None:
            return None, []
        lines = session.scalars(
            select(ReconLine).where(ReconLine.run_id == run.id).order_by(ReconLine.id)
        ).all()
        return _run_info(run), [_decode_line(row) for row in lines]


def explain_unit(
    engagement_id: int, unit_code: str, url: Optional[str] = None
) -> tuple[Optional[RunInfo], Optional[StoredLine]]:
    """Return the latest run and the line for one unit, if present."""
    run, lines = latest_run(engagement_id, url)
    if run is None:
        return None, None
    for line in lines:
        if line.unit_code == unit_code:
            return run, line
    return run, None


def set_materiality(
    engagement_id: int,
    value: float,
    basis: str = "",
    url: Optional[str] = None,
) -> EngagementInfo:
    """Store a materiality value (and basis) on the engagement."""
    if value is None or float(value) <= 0:
        raise ValueError("materiality must be a positive number")
    init_db(url)
    with session_scope(url) as session:
        engagement = session.get(Engagement, engagement_id)
        if engagement is None:
            raise ValueError(f"no engagement with id {engagement_id}")
        engagement.materiality_value = float(value)
        if basis:
            engagement.materiality_basis = basis
        session.flush()
        return EngagementInfo(
            engagement_id=engagement_id,
            client_code=engagement.client_code,
            period=engagement.period,
            basis=engagement.basis,
            materiality_value=engagement.materiality_value,
            materiality_basis=engagement.materiality_basis,
        )


def suggest_for_engagement(engagement_id: int, url: Optional[str] = None) -> dict:
    """Suggest a materiality from the engagement's draft financial statements."""
    taxonomy = load_default_taxonomy()
    groups = load_default_groups(taxonomy=taxonomy)
    init_db(url)
    with session_scope(url) as session:
        if session.get(Engagement, engagement_id) is None:
            raise ValueError(f"no engagement with id {engagement_id}")
        side_b_result = side_b(session, engagement_id, taxonomy)
        suggestion = suggest_materiality(side_b_result, taxonomy, groups)
        suggestion["unit"] = side_b_result.unit
        return suggestion


__all__ = [
    "EngagementInfo",
    "ReconSummary",
    "RunInfo",
    "StoredLine",
    "explain_unit",
    "latest_run",
    "run_recon",
    "set_materiality",
    "suggest_for_engagement",
]
