"""Financial-statement side of the review queue.

A face row the cascading labelling resolved to neither an FSLI nor a presentation
group is *unmapped* exposure on Side B. :func:`list_unmapped_fs` lists those
labels; :func:`resolve_fs_line` records the reviewer's choice.

Resolving one label fixes **every** ``fs_line`` row of that face label — current
and prior columns alike — matched on ``document_id + statement + source_ref``,
since one presentation row yields one stored row per year column.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import select

from ...core.groups import GroupIndex, load_default_groups
from ...core.taxonomy import Taxonomy, load_default_taxonomy
from ...store import init_db, session_scope
from ...store.models import FsLine

MEASURE_FACE = "face"


@dataclass
class UnmappedLabel:
    """One unmapped face label (all its period rows grouped)."""

    line_id: int  # representative fs_line id the reviewer can act on
    label: str
    statement: str
    document_id: int
    rows: int = 0
    periods: list[str] = field(default_factory=list)
    total: float = 0.0  # absolute sum of the reported values across periods

    @property
    def abs_total(self) -> float:
        return abs(self.total)


@dataclass
class FsResolutionResult:
    """Outcome of resolving (or resetting) one FS label."""

    line_id: int
    label: str
    fsli_code: Optional[str]
    group_code: Optional[str]
    resolved_rows: int


def list_unmapped_fs(
    engagement_id: int,
    url: Optional[str] = None,
) -> list[UnmappedLabel]:
    """Unmapped face labels for an engagement, largest exposure first."""
    init_db(url)
    with session_scope(url) as session:
        rows = session.scalars(
            select(FsLine)
            .where(
                FsLine.engagement_id == engagement_id,
                FsLine.fsli_code.is_(None),
                FsLine.group_code.is_(None),
                FsLine.measure == MEASURE_FACE,
            )
            .order_by(FsLine.id)
        ).all()

        labels: dict[tuple, UnmappedLabel] = {}
        for row in rows:
            key = (row.document_id, row.statement, row.source_ref or "")
            entry = labels.get(key)
            if entry is None:
                entry = UnmappedLabel(
                    line_id=row.id,
                    label=row.source_ref or "",
                    statement=row.statement or "",
                    document_id=row.document_id,
                )
                labels[key] = entry
            entry.rows += 1
            if row.period and row.period not in entry.periods:
                entry.periods.append(row.period)
            entry.total += float(row.normalized_value or 0.0)
        result = list(labels.values())
    result.sort(key=lambda l: (-l.abs_total, l.line_id))
    return result


def resolve_fs_line(
    line_id: int,
    fsli_code: Optional[str] = None,
    group_code: Optional[str] = None,
    url: Optional[str] = None,
    taxonomy: Optional[Taxonomy] = None,
    groups: Optional[GroupIndex] = None,
) -> FsResolutionResult:
    """Resolve one FS label to an FSLI **or** a presentation group.

    Applies to every stored row of the label (all period columns). Providing both
    or neither — or an unknown code — fails loudly with ``ValueError``.
    """
    taxonomy = taxonomy or load_default_taxonomy()
    groups = groups if groups is not None else load_default_groups(taxonomy=taxonomy)

    fsli_code = (fsli_code or "").strip() or None
    group_code = (group_code or "").strip() or None
    if fsli_code and group_code:
        raise ValueError("pass either fsli_code or group_code, not both")
    if not fsli_code and not group_code:
        raise ValueError("a target is required: fsli_code or group_code")
    if fsli_code and fsli_code not in taxonomy:
        raise ValueError(f"unknown FSLI code '{fsli_code}'")
    if group_code and groups.get(group_code) is None:
        raise ValueError(f"unknown group code '{group_code}'")

    group = groups.get(group_code) if group_code else None

    init_db(url)
    with session_scope(url) as session:
        line = session.get(FsLine, line_id)
        if line is None:
            raise ValueError(f"no financial-statement line with id {line_id}")

        siblings = session.scalars(
            select(FsLine).where(
                FsLine.document_id == line.document_id,
                FsLine.statement == line.statement,
                FsLine.source_ref == line.source_ref,
            )
        ).all()

        for row in siblings:
            row.fsli_code = fsli_code
            row.group_code = group_code
            if fsli_code:
                item = taxonomy.get(fsli_code)
                row.category = item.category if item else ""
                row.method = "manual"
            else:
                row.category = group.category if group is not None else ""
                row.method = "manual"

        return FsResolutionResult(
            line_id=line_id,
            label=line.source_ref or "",
            fsli_code=fsli_code,
            group_code=group_code,
            resolved_rows=len(siblings),
        )


def reset_fs_line(
    line_id: int,
    url: Optional[str] = None,
) -> FsResolutionResult:
    """Send a manually resolved FS label back to the unmapped queue."""
    init_db(url)
    with session_scope(url) as session:
        line = session.get(FsLine, line_id)
        if line is None:
            raise ValueError(f"no financial-statement line with id {line_id}")
        if line.method != "manual":
            raise ValueError(
                f"line {line_id} was not manually resolved (method '{line.method}'); "
                "re-ingest the document to change it"
            )
        siblings = session.scalars(
            select(FsLine).where(
                FsLine.document_id == line.document_id,
                FsLine.statement == line.statement,
                FsLine.source_ref == line.source_ref,
            )
        ).all()
        for row in siblings:
            row.fsli_code = None
            row.group_code = None
            row.category = ""
            row.method = "review"
        return FsResolutionResult(
            line_id=line_id, label=line.source_ref or "", fsli_code=None,
            group_code=None, resolved_rows=len(siblings),
        )


__all__ = [
    "FsResolutionResult",
    "UnmappedLabel",
    "list_unmapped_fs",
    "reset_fs_line",
    "resolve_fs_line",
]
