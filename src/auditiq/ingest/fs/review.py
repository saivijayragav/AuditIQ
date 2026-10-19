"""Financial-statement side of the review queue.

A face row the cascading labelling resolved to neither an FSLI nor a presentation
group is *unmapped* exposure on Side B. :func:`list_unmapped_fs` lists those
labels; :func:`resolve_fs_line` records the reviewer's choice.

Reviewer decisions are not stored in a separate cache table. :func:`load_fs_cache`
replays them from the ``fs_line`` rows themselves, mirroring how trial-balance
mapping seeds its cache from resolved ``tb_mapping`` rows. A reset is written as
``method="reset"`` and acts as a tombstone, so an older draft cannot resurrect a
decision the reviewer has undone.

Resolving one label fixes **every** stored row of that label for the client —
stacked drafts, all period columns and prior engagements alike — matched on
``statement + normalised source_ref``, since mapping is a client-level decision.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from sqlalchemy import select

from ...core.groups import GroupIndex, load_default_groups
from ...core.taxonomy import Taxonomy, load_default_taxonomy
from ...core.text import nu
from ...store import init_db, session_scope
from ...store.models import Engagement, FsLine, SourceDocument
from .base import CachedLabel, STATEMENT_LABELS

MEASURE_FACE = "face"
RESET_METHOD = "reset"

_STATEMENT_KEY_BY_LABEL = {label: key for key, label in STATEMENT_LABELS.items()}


def _statement_key(label: str) -> str:
    """Map a stored statement label (``"P&L"``) back to its key (``"pl"``)."""
    return _STATEMENT_KEY_BY_LABEL.get(label, (label or "").lower())


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


def _label_rows(session, line: FsLine) -> list[FsLine]:
    """Every stored row of ``line``'s normalised label for the client.

    Mapping is a client-level decision (the cache is client-scoped), so a review
    action applies to stacked drafts and prior periods too, not just the document
    the representative line came from. Falls back to document scope for legacy
    rows without an engagement.
    """
    client_code = (
        session.scalar(
            select(Engagement.client_code).where(Engagement.id == line.engagement_id)
        )
        if line.engagement_id is not None
        else None
    )
    if client_code:
        candidates = session.scalars(
            select(FsLine)
            .join(Engagement, FsLine.engagement_id == Engagement.id)
            .where(
                Engagement.client_code == client_code,
                FsLine.statement == line.statement,
            )
        ).all()
    else:
        candidates = session.scalars(
            select(FsLine).where(
                FsLine.document_id == line.document_id,
                FsLine.statement == line.statement,
            )
        ).all()

    wanted = nu(line.source_ref or "")
    return [row for row in candidates if nu(row.source_ref or "") == wanted]


def load_fs_cache(
    client_code: Optional[str],
    url: Optional[str] = None,
) -> dict[tuple[str, str], CachedLabel]:
    """Replay reviewer decisions from the stored FS rows (no cache table).

    This mirrors the trial-balance cache, where ``tb_mapping`` rows are the source
    of truth: reviewer resolutions (``manual``) and earlier replays (``cache``)
    seed the cache, while a reset (``reset``) is a tombstone. Rows are replayed
    oldest-document first so the latest decision for a label wins.

    The key is ``(statement, nu(label))`` and the result is already scoped to the
    client, so cross-period drafts of the same client share decisions.
    """
    if not client_code:
        return {}

    init_db(url)
    cache: dict[tuple[str, str], CachedLabel] = {}
    with session_scope(url) as session:
        rows = session.execute(
            select(FsLine, SourceDocument.uploaded_at)
            .join(SourceDocument, FsLine.document_id == SourceDocument.id)
            .join(Engagement, FsLine.engagement_id == Engagement.id)
            .where(
                Engagement.client_code == client_code,
                FsLine.method.in_(("manual", "cache", RESET_METHOD)),
                FsLine.source_ref.isnot(None),
            )
            .order_by(SourceDocument.uploaded_at.asc(), FsLine.id.asc())
        ).all()

        for line, _uploaded_at in rows:
            label = (line.source_ref or "").strip()
            if not label:
                continue
            key = (_statement_key(line.statement), nu(label))
            if line.method == RESET_METHOD:
                cache.pop(key, None)
            elif line.fsli_code or line.group_code:
                cache[key] = CachedLabel(
                    fsli_code=line.fsli_code, group_code=line.group_code
                )
    return cache


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

    Applies to every stored row of the label for the client — stacked drafts, all
    period columns and prior engagements alike, because the cache is client-scoped.
    Providing both or neither — or an unknown code — fails loudly with
    ``ValueError``.
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

        siblings = _label_rows(session, line)

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
    """Send a resolved FS label back to the unmapped queue.

    A replayed decision (``cache``) can be undone just like a manual one. The
    reset is written as ``method="reset"`` and applied to every stored row of the
    same normalised label for the client, so an older draft cannot resurrect the
    decision on the next ingest.
    """
    init_db(url)
    with session_scope(url) as session:
        line = session.get(FsLine, line_id)
        if line is None:
            raise ValueError(f"no financial-statement line with id {line_id}")
        if line.method not in ("manual", "cache"):
            raise ValueError(
                f"line {line_id} was not resolved (method '{line.method}'); "
                "only a reviewer decision can be undone"
            )

        siblings = _label_rows(session, line)
        for row in siblings:
            row.fsli_code = None
            row.group_code = None
            row.category = ""
            row.method = RESET_METHOD
        return FsResolutionResult(
            line_id=line_id, label=line.source_ref or "", fsli_code=None,
            group_code=None, resolved_rows=len(siblings),
        )


__all__ = [
    "FsResolutionResult",
    "RESET_METHOD",
    "UnmappedLabel",
    "list_unmapped_fs",
    "load_fs_cache",
    "reset_fs_line",
    "resolve_fs_line",
]
