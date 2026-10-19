"""Read-only engagement views shared by the CLI, the API and the UI.

These helpers return plain dataclasses (never ORM objects) so they survive the
session. They layer over ``reconciliation.service`` models where possible and add
the per-engagement counts a workspace needs.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from sqlalchemy import func, select

from . import init_db, session_scope
from .models import Engagement, ExceptionRecord, FsLine, ReconRun, SourceDocument, TbLine, TbMapping


@dataclass
class EngagementSummary:
    """Per-engagement status: raw counts, mapping state, latest recon run."""

    engagement_id: int
    client_code: str
    client_name: str
    period: str
    basis: str
    materiality_value: Optional[float] = None
    materiality_basis: Optional[str] = None
    tb_lines: int = 0
    tb_documents: int = 0
    fs_documents: int = 0
    fs_lines: int = 0
    fs_subtotals: int = 0
    fs_unmapped_rows: int = 0
    mappings: dict[str, int] = field(default_factory=dict)  # status -> line count
    resolved_lines: int = 0
    pending_lines: int = 0
    intake_status: str = "intake"
    recon_run_id: Optional[int] = None
    recon_status: Optional[str] = None
    recon_exposure_a: float = 0.0
    recon_exposure_b: float = 0.0
    open_exceptions: int = 0


@dataclass
class ExceptionInfo:
    """An exception awaiting (or holding) a disposition, detached."""

    exception_id: int
    engagement_id: Optional[int]
    kind: str
    severity: str
    status: str
    amount: Optional[float]
    fsli: Optional[str]
    note: str = ""
    detail: str = ""

    def as_text(self) -> str:
        amount = "-" if self.amount is None else f"{self.amount:,.2f}"
        return f"{self.kind:<8} {self.severity:<8} {amount:>16}  {self.note}"


def _engagement_summary(session, engagement: Engagement) -> EngagementSummary:
    e_id = engagement.id
    summary = EngagementSummary(
        engagement_id=e_id,
        client_code=engagement.client_code,
        client_name=engagement.client_name,
        period=engagement.period,
        basis=engagement.basis,
        materiality_value=engagement.materiality_value,
        materiality_basis=engagement.materiality_basis,
    )

    summary.tb_documents = session.scalar(
        select(func.count(SourceDocument.id)).select_from(SourceDocument).where(
            SourceDocument.engagement_id == e_id,
            SourceDocument.kind == "tb_erp",
        )
    )
    summary.fs_documents = session.scalar(
        select(func.count(SourceDocument.id)).select_from(SourceDocument).where(
            SourceDocument.engagement_id == e_id,
            SourceDocument.kind.in_(("fs_document", "fs_structured")),
        )
    )

    summary.tb_lines = session.scalar(
        select(func.count(TbLine.id)).where(TbLine.engagement_id == e_id)
    )

    # Mapping state per line: missing mapping row counts as unmapped.
    rows = session.execute(
        select(TbLine.id, TbMapping.status)
        .outerjoin(TbMapping, TbMapping.line_id == TbLine.id)
        .where(TbLine.engagement_id == e_id)
    ).all()
    for _line_id, status in rows:
        status = status or "unmapped"
        summary.mappings[status] = summary.mappings.get(status, 0) + 1
    summary.resolved_lines = summary.mappings.get("auto", 0) + summary.mappings.get("resolved", 0)
    summary.pending_lines = summary.mappings.get("pending_review", 0) + summary.mappings.get("unmapped", 0)

    summary.fs_lines = session.scalar(
        select(func.count(FsLine.id)).where(FsLine.engagement_id == e_id)
    )
    summary.fs_unmapped_rows = session.scalar(
        select(func.count(FsLine.id)).where(
            FsLine.engagement_id == e_id,
            FsLine.fsli_code.is_(None),
            FsLine.group_code.is_(None),
            FsLine.measure == "face",
        )
    )
    summary.fs_subtotals = session.scalar(
        select(func.count(FsLine.id)).where(
            FsLine.engagement_id == e_id, FsLine.is_subtotal.is_(True)
        )
    )

    run = session.scalars(
        select(ReconRun).where(ReconRun.engagement_id == e_id).order_by(ReconRun.id.desc())
    ).first()
    if run is not None:
        summary.recon_run_id = run.id
        summary.recon_exposure_a = run.exposure_a
        summary.recon_exposure_b = run.exposure_b
        summary.recon_status = (
            "material differences" if run.material
            else "watch items" if run.watch
            else "minor residual" if (run.minor or summary.recon_exposure_a or summary.recon_exposure_b)
            else "clean"
        )

    summary.open_exceptions = session.scalar(
        select(func.count(ExceptionRecord.id)).where(
            ExceptionRecord.engagement_id == e_id, ExceptionRecord.status == "open"
        )
    )
    if summary.tb_lines and summary.fs_lines and summary.resolved_lines == summary.tb_lines:
        summary.intake_status = "reconcilable"
    elif summary.tb_lines and summary.fs_documents:
        summary.intake_status = "in progress"
    return summary


def engagement_summary(engagement_id: int, url: Optional[str] = None) -> EngagementSummary:
    """Status for one engagement."""
    init_db(url)
    with session_scope(url) as session:
        engagement = session.get(Engagement, engagement_id)
        if engagement is None:
            raise ValueError(f"no engagement with id {engagement_id}")
        return _engagement_summary(session, engagement)


def create_engagement(
    client_code: str,
    period: str,
    basis: str = "Standalone",
    client_name: str = "",
    url: Optional[str] = None,
) -> EngagementSummary:
    """Create (or return the existing) engagement and report its status."""
    from ..core.periods import normalize_fy

    if not client_code or not period:
        raise ValueError("client_code and period are required")
    normalized = normalize_fy(period) or period
    init_db(url)
    with session_scope(url) as session:
        row = session.scalars(
            select(Engagement).where(
                Engagement.client_code == client_code.strip(),
                Engagement.period == normalized,
                Engagement.basis == basis,
            )
        ).one_or_none()
        if row is None:
            row = Engagement(
                client_code=client_code.strip(),
                client_name=client_name or client_code.strip(),
                period=normalized,
                basis=basis,
            )
            session.add(row)
            session.flush()
        elif client_name:
            row.client_name = client_name
        return _engagement_summary(session, row)


def list_engagements(url: Optional[str] = None) -> list[EngagementSummary]:
    """Every engagement with its status, newest id last."""
    init_db(url)
    with session_scope(url) as session:
        engagements = session.query(Engagement).order_by(Engagement.id).all()
        return [_engagement_summary(session, engagement) for engagement in engagements]


@dataclass
class DocumentInfo:
    """An ingested artefact, detached from the session."""

    document_id: int
    engagement_id: Optional[int]
    kind: str
    system: str
    filename: str
    file_hash: str
    uploaded_at: Optional[datetime]
    parse_stats: dict = field(default_factory=dict)


@dataclass
class TbLineInfo:
    """A raw ledger line with its current mapping, detached from the session."""

    line_id: int
    document_id: int
    raw_code: str
    raw_name: str
    group_name: str
    erp_acc_type: str
    amount: float
    side: str
    unit: str
    normalized_amount: float
    source_row: Optional[int]
    fsli_code: Optional[str] = None
    mapping_status: Optional[str] = None
    mapping_method: Optional[str] = None
    mapping_confidence: Optional[float] = None


@dataclass
class TbLinePage:
    """One page of ledger lines plus the unpaged total."""

    items: list[TbLineInfo]
    total: int
    limit: int
    offset: int


def list_documents(
    engagement_id: int,
    kind: Optional[str] = None,
    url: Optional[str] = None,
) -> list[DocumentInfo]:
    """Documents ingested for an engagement, oldest first."""
    init_db(url)
    with session_scope(url) as session:
        query = (
            select(SourceDocument)
            .where(SourceDocument.engagement_id == engagement_id)
            .order_by(SourceDocument.id)
        )
        if kind:
            query = query.where(SourceDocument.kind == kind.strip().lower())
        rows = session.scalars(query).all()
        out: list[DocumentInfo] = []
        for row in rows:
            try:
                stats = json.loads(row.parse_stats) if row.parse_stats else {}
            except ValueError:
                stats = {}
            out.append(
                DocumentInfo(
                    document_id=row.id,
                    engagement_id=row.engagement_id,
                    kind=row.kind,
                    system=row.system,
                    filename=row.filename,
                    file_hash=row.file_hash,
                    uploaded_at=row.uploaded_at,
                    parse_stats=stats,
                )
            )
        return out


def list_tb_lines(
    engagement_id: int,
    limit: int = 100,
    offset: int = 0,
    status: Optional[str] = None,
    url: Optional[str] = None,
) -> TbLinePage:
    """A page of ledger lines (oldest first) with their current mapping.

    ``status`` filters on the mapping status; ``unmapped`` selects lines with no
    mapping row at all.
    """
    init_db(url)
    limit = max(1, min(int(limit), 1000))
    offset = max(0, int(offset))
    with session_scope(url) as session:
        base = (
            select(TbLine, TbMapping)
            .outerjoin(TbMapping, TbMapping.line_id == TbLine.id)
            .where(TbLine.engagement_id == engagement_id)
        )
        if status:
            wanted = status.strip().lower()
            if wanted == "unmapped":
                base = base.where(TbMapping.id.is_(None))
            else:
                base = base.where(TbMapping.status == wanted)
        total = session.scalar(
            select(func.count()).select_from(base.subquery())
        )
        rows = session.execute(
            base.order_by(TbLine.id).limit(limit).offset(offset)
        ).all()
        items = [
            TbLineInfo(
                line_id=line.id,
                document_id=line.document_id,
                raw_code=line.raw_code,
                raw_name=line.raw_name,
                group_name=line.group_name,
                erp_acc_type=line.erp_acc_type,
                amount=line.amount,
                side=line.side,
                unit=line.unit,
                normalized_amount=line.normalized_amount,
                source_row=line.source_row,
                fsli_code=mapping.fsli_code if mapping else None,
                mapping_status=mapping.status if mapping else None,
                mapping_method=mapping.method if mapping else None,
                mapping_confidence=mapping.confidence if mapping else None,
            )
            for line, mapping in rows
        ]
        return TbLinePage(items=items, total=total or 0, limit=limit, offset=offset)


def mapping_counts(engagement_id: int, url: Optional[str] = None) -> dict[str, int]:
    """Mapping status -> line count, with missing rows counted as ``unmapped``."""
    init_db(url)
    with session_scope(url) as session:
        rows = session.execute(
            select(TbMapping.status, func.count(TbMapping.id))
            .join(TbLine, TbLine.id == TbMapping.line_id)
            .where(TbLine.engagement_id == engagement_id)
            .group_by(TbMapping.status)
        ).all()
        counts = {status or "unmapped": count for status, count in rows}
        total = session.scalar(
            select(func.count(TbLine.id)).where(TbLine.engagement_id == engagement_id)
        ) or 0
        mapped = sum(counts.values())
        if total > mapped:
            counts["unmapped"] = counts.get("unmapped", 0) + (total - mapped)
        return counts


def list_exceptions(
    engagement_id: Optional[int] = None,
    status: Optional[str] = None,
    url: Optional[str] = None,
) -> list["ExceptionInfo"]:
    """Exception records, optionally filtered, newest first."""
    init_db(url)
    with session_scope(url) as session:
        query = select(ExceptionRecord).order_by(ExceptionRecord.id.desc())
        if engagement_id is not None:
            query = query.where(ExceptionRecord.engagement_id == engagement_id)
        if status:
            query = query.where(ExceptionRecord.status == status.strip().lower())
        rows = session.scalars(query).all()
        return [
            ExceptionInfo(
                exception_id=row.id,
                engagement_id=row.engagement_id,
                kind=row.kind,
                severity=row.severity,
                status=row.status,
                amount=row.amount,
                fsli=row.fsli_code,
                note=row.note or "",
                detail=row.detail or "",
            )
            for row in rows
        ]


def dispose_exception(
    exception_id: int,
    status: str,
    note: str = "",
    url: Optional[str] = None,
) -> "ExceptionInfo":
    """Set an exception's disposition (``explained`` or ``accepted``) with a note."""
    status = (status or "").strip().lower()
    allowed = ("open", "explained", "accepted")
    if status not in allowed:
        raise ValueError(f"status must be one of: {', '.join(allowed)}")
    init_db(url)
    with session_scope(url) as session:
        row = session.get(ExceptionRecord, exception_id)
        if row is None:
            raise ValueError(f"no exception with id {exception_id}")
        row.status = status
        if note:
            row.note = note
        return ExceptionInfo(
            exception_id=row.id,
            engagement_id=row.engagement_id,
            kind=row.kind,
            severity=row.severity,
            status=row.status,
            amount=row.amount,
            fsli=row.fsli_code,
            note=row.note or "",
            detail=row.detail or "",
        )


__all__ = [
    "EngagementSummary",
    "ExceptionInfo",
    "create_engagement",
    "dispose_exception",
    "engagement_summary",
    "list_engagements",
    "list_exceptions",
]
