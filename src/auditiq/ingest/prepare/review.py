"""The mapping review queue: resolve what the cascade left for review.

``map_engagement`` writes one ``tb_mapping`` row per trial-balance line; rows the
cascade could not accept stay ``status="pending_review"`` and lines the cascade
never touched have no mapping row at all. Both are *exposure* to reconciliation.
This module closes the loop:

* :func:`list_pending` — the pending heads with their stored cascade candidates.
* :func:`resolve_mapping` — record the reviewer's FSLI choice. Resolution applies
  to **every ledger line sharing the head** (same client + ERP + code/name key),
  so one approval fixes the whole head.
* :func:`reset_mapping` — undo a resolution.
* :func:`bulk_resolve` — approve several heads in one call.

Approval is immediately visible to reconciliation (Side A reads the persisted
accepted rows); re-running ``map`` is not required, and when it is run the
reviewer-resolved rows seed the cache layer with their provenance intact.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Sequence

from sqlalchemy import select

from ...core.taxonomy import Taxonomy, load_default_taxonomy
from ...store import init_db, session_scope
from ...store.models import SourceDocument, TbLine, TbMapping
from .normalize import nu


def _head_key(client_code: str, system: str, raw_code: str, raw_name: str) -> tuple:
    """Same key space as the mapping cache (see ``prepare.service._head_key``)."""
    return (client_code, system, raw_code or nu(raw_name))


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


@dataclass
class PendingHead:
    """One ledger head (all its lines grouped) awaiting review.

    ``line_id`` is a representative line the reviewer can act on; resolving it
    resolves every line of the head. ``amount`` is the signed Dr-positive sum in
    absolute rupees across the head's lines.
    """

    line_id: int
    raw_name: str
    raw_code: str
    group_name: str
    status: str  # pending_review | unmapped (no mapping row)
    method: str
    confidence: Optional[float]
    amount: float
    lines: int
    candidates: list[str] = field(default_factory=list)
    embed_score: Optional[float] = None
    embed_margin: Optional[float] = None

    @property
    def abs_amount(self) -> float:
        return abs(self.amount)


@dataclass
class ResolutionResult:
    """Outcome of resolving (or resetting) one head."""

    line_id: int
    head: str
    fsli_code: Optional[str]
    resolved_lines: int
    reviewer: str = ""


def _decode_candidates(candidates_json: Optional[str]) -> tuple[list[str], Optional[float], Optional[float]]:
    if not candidates_json:
        return [], None, None
    import json

    try:
        payload = json.loads(candidates_json)
    except ValueError:
        return [], None, None
    codes = [c for c in payload.get("codes") or [] if c]
    score = payload.get("embed_score")
    margin = payload.get("embed_margin")
    return codes, score, margin


def list_pending(engagement_id: int, url: Optional[str] = None, taxonomy: Optional[Taxonomy] = None) -> list[PendingHead]:
    """Pending heads for an engagement, largest exposure first."""
    init_db(url)
    with session_scope(url) as session:
        rows = session.execute(
            select(TbLine, SourceDocument.system, TbMapping)
            .join(SourceDocument, TbLine.document_id == SourceDocument.id)
            .outerjoin(TbMapping, TbMapping.line_id == TbLine.id)
            .where(TbLine.engagement_id == engagement_id)
            .order_by(TbLine.id)
        ).all()

        heads: dict[tuple, tuple[PendingHead, list[str]]] = {}
        for line, system, mapping in rows:
            status = mapping.status if mapping is not None else "unmapped"
            if status not in ("pending_review", "unmapped"):
                continue
            key = _head_key(line.client_code, system, line.raw_code, line.raw_name)
            entry = heads.get(key)
            if entry is None:
                codes, score, margin = _decode_candidates(
                    mapping.candidates_json if mapping is not None else None
                )
                head = PendingHead(
                    line_id=line.id,
                    raw_name=line.raw_name,
                    raw_code=line.raw_code,
                    group_name=line.group_name,
                    status="unmapped" if mapping is None else status,
                    method=mapping.method if mapping is not None else "unmapped",
                    confidence=mapping.confidence if mapping is not None else None,
                    amount=float(line.normalized_amount or 0.0),
                    lines=1,
                    candidates=codes,
                    embed_score=score,
                    embed_margin=margin,
                )
                ids = [str(mapping.id) if mapping is not None else "0"]
                heads[key] = (head, ids)
            else:
                head, ids = entry
                head.amount += float(line.normalized_amount or 0.0)
                head.lines += 1
                ids.append(str(mapping.id) if mapping is not None else "0")
        result = [entry[0] for entry in heads.values()]
    result.sort(key=lambda h: (-h.abs_amount, h.line_id))
    return result


def resolve_mapping(
    line_id: int,
    fsli_code: str,
    reviewer: str = "",
    url: Optional[str] = None,
    taxonomy: Optional[Taxonomy] = None,
) -> ResolutionResult:
    """Record the reviewer's FSLI choice for a ledger head.

    ``line_id`` identifies any one line of the head; every trial-balance line of
    the engagement sharing the head key is resolved to the choice. Fails loudly
    (``ValueError``) on unknown lines or FSLIs.
    """
    fsli_code = (fsli_code or "").strip()
    if not fsli_code:
        raise ValueError("fsli_code is required")
    taxonomy = taxonomy or load_default_taxonomy()
    if fsli_code not in taxonomy:
        raise ValueError(f"unknown FSLI code '{fsli_code}'")

    init_db(url)
    with session_scope(url) as session:
        line = session.get(TbLine, line_id)
        if line is None:
            raise ValueError(f"no trial-balance line with id {line_id}")
        system = session.scalars(
            select(SourceDocument.system).where(SourceDocument.id == line.document_id)
        ).first() or ""
        key = _head_key(line.client_code, system, line.raw_code, line.raw_name)

        siblings = session.execute(
            select(TbLine, SourceDocument.system)
            .join(SourceDocument, TbLine.document_id == SourceDocument.id)
            .where(
                TbLine.engagement_id == line.engagement_id,
                TbLine.client_code == key[0],
                SourceDocument.system == key[1],
            )
        ).all()
        target_ids = [
            sib.id
            for sib, sib_system in siblings
            if _head_key(sib.client_code, sib_system, sib.raw_code, sib.raw_name) == key
        ]

        now = _utcnow()
        resolved = 0
        for row in session.scalars(
            select(TbMapping).where(TbMapping.line_id.in_(target_ids))
        ).all():
            row.resolved_fsli = fsli_code
            row.status = "resolved"
            row.reviewer = reviewer or None
            row.resolved_at = now
            resolved += 1
        for sibling_id in target_ids:
            if not session.scalars(
                select(TbMapping.id).where(TbMapping.line_id == sibling_id)
            ).first():
                session.add(
                    TbMapping(
                        line_id=sibling_id,
                        fsli_code=None,
                        method="review",
                        status="resolved",
                        reviewer=reviewer or None,
                        resolved_fsli=fsli_code,
                        resolved_at=now,
                    )
                )
                resolved += 1

        return ResolutionResult(
            line_id=line_id,
            head=line.raw_name,
            fsli_code=fsli_code,
            resolved_lines=resolved,
            reviewer=reviewer,
        )


def reset_mapping(line_id: int, url: Optional[str] = None) -> ResolutionResult:
    """Send a resolved head back to the review queue."""
    init_db(url)
    with session_scope(url) as session:
        line = session.get(TbLine, line_id)
        if line is None:
            raise ValueError(f"no trial-balance line with id {line_id}")
        system = session.scalars(
            select(SourceDocument.system).where(SourceDocument.id == line.document_id)
        ).first() or ""
        key = _head_key(line.client_code, system, line.raw_code, line.raw_name)

        siblings = session.execute(
            select(TbLine, SourceDocument.system)
            .join(SourceDocument, TbLine.document_id == SourceDocument.id)
            .where(
                TbLine.engagement_id == line.engagement_id,
                TbLine.client_code == key[0],
                SourceDocument.system == key[1],
            )
        ).all()
        target_ids = [
            sib.id
            for sib, sib_system in siblings
            if _head_key(sib.client_code, sib_system, sib.raw_code, sib.raw_name) == key
        ]

        for mapping in session.scalars(
            select(TbMapping).where(TbMapping.line_id.in_(target_ids))
        ).all():
            # Any row with ``resolved_fsli`` set owes that choice to the review
            # workflow (the cascade never writes it), so plain reset is safe.
            mapping.status = "pending_review"
            mapping.resolved_fsli = None
            mapping.reviewer = None
            mapping.resolved_at = None

        return ResolutionResult(
            line_id=line_id, head=line.raw_name, fsli_code=None, resolved_lines=0
        )


def bulk_resolve(
    pairs: Sequence[tuple[int, str]],
    reviewer: str = "",
    url: Optional[str] = None,
) -> tuple[list[ResolutionResult], dict[int, str]]:
    """Resolve several ``(line_id, fsli_code)`` pairs.

    Returns ``(results, failures)`` where ``failures`` maps the failing
    ``line_id`` to the error message; successful heads are committed.
    """
    results: list[ResolutionResult] = []
    failures: dict[int, str] = {}
    for line_id, fsli_code in pairs:
        try:
            results.append(resolve_mapping(line_id, fsli_code, reviewer=reviewer, url=url))
        except ValueError as exc:
            failures[line_id] = str(exc)
    return results, failures


def list_resolved(
    engagement_id: int, url: Optional[str] = None, limit: int = 0
) -> list[PendingHead]:
    """Reviewer-resolved heads (audit trail), newest first."""
    init_db(url)
    with session_scope(url) as session:
        rows = session.execute(
            select(TbLine, TbMapping)
            .join(TbMapping, TbMapping.line_id == TbLine.id)
            .where(TbLine.engagement_id == engagement_id, TbMapping.status == "resolved")
            .order_by(TbMapping.resolved_at.desc(), TbLine.id)
        ).all()

        heads: dict[str, PendingHead] = {}
        order: list[str] = []
        for line, mapping in rows:
            key = f"{line.client_code}|{line.raw_code or nu(line.raw_name)}|{mapping.resolved_fsli}"
            entry = heads.get(key)
            if entry is None:
                entry = PendingHead(
                    line_id=line.id,
                    raw_name=line.raw_name,
                    raw_code=line.raw_code,
                    group_name=line.group_name,
                    status="resolved",
                    method="review",
                    confidence=None,
                    amount=float(line.normalized_amount or 0.0),
                    lines=1,
                    candidates=[mapping.resolved_fsli or ""],
                )
                heads[key] = entry
                order.append(key)
            else:
                entry.amount += float(line.normalized_amount or 0.0)
                entry.lines += 1
        result = [heads[key] for key in order]
    result.sort(key=lambda h: (-h.abs_amount, h.line_id))
    if limit and len(result) > limit:
        result = result[:limit]
    return result


__all__ = [
    "PendingHead",
    "ResolutionResult",
    "bulk_resolve",
    "list_pending",
    "list_resolved",
    "reset_mapping",
    "resolve_mapping",
]
