"""Run the mapping cascade over an engagement's trial-balance lines.

Reads ``tb_line`` rows, maps each distinct ledger head through the cascade and
persists one ``tb_mapping`` row per line. Reviewer-resolved mappings from earlier
runs feed the cache layer, so repeated uploads resolve faster.
"""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Sequence

from sqlalchemy import delete, select

from ...core import load_default_taxonomy
from ...store import init_db, session_scope
from ...store.models import SourceDocument, TbLine, TbMapping
from ...store.sync import sync_taxonomy
from .aliases import load_alias
from .encoder import default_encoder_kind, make_encoder
from .mapper import ALL_LAYERS, LedgerHead, Mapper, MapResult
from .normalize import nu
from .thresholds import Thresholds, load_thresholds


@dataclass
class MappingSummary:
    engagement_id: int
    lines: int
    resolved: int
    review: int
    by_layer: dict[str, int] = field(default_factory=dict)
    llm_calls: int = 0
    tuned: bool = False
    encoder: str = "none"

    @property
    def resolution_rate(self) -> float:
        return self.resolved / self.lines if self.lines else 0.0


def _head_key(client_code: str, system: str, raw_code: str, raw_name: str) -> tuple:
    return (client_code, system, raw_code or nu(raw_name))


def _candidates_payload(result: MapResult) -> Optional[str]:
    """Persist the cascade shortlist (+embed scores) for the review queue."""
    if not result.candidates:
        return None
    return json.dumps(
        {
            "codes": list(result.candidates),
            "embed_score": result.embed_score,
            "embed_margin": result.embed_margin,
        }
    )


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def map_engagement(
    engagement_id: int,
    url: Optional[str] = None,
    client: Optional[str] = None,
    encoder_kind: Optional[str] = None,
    use_llm: bool = False,
    llm_cache: Optional[str] = None,
    layers: Sequence[str] = ALL_LAYERS,
) -> MappingSummary:
    """Map all trial-balance lines of an engagement and persist the results."""
    from .llm import LLM  # local import keeps the LLM layer truly optional

    from ...settings import LLM_MODEL

    taxonomy = load_default_taxonomy()
    thresholds, tuned = load_thresholds(client)

    kind = encoder_kind if encoder_kind is not None else thresholds.encoder
    if kind in (None, "none") and encoder_kind is None:
        kind = default_encoder_kind()
    encoder = make_encoder(kind, thresholds.encoder_model, taxonomy)
    alias = load_alias(taxonomy=taxonomy)

    llm = None
    if use_llm:
        llm = LLM(LLM_MODEL, llm_cache or "llm_cache.json")

    mapper = Mapper(taxonomy, alias, encoder=encoder, llm=llm, cfg=thresholds)

    init_db(url)
    with session_scope(url) as session:
        sync_taxonomy(session, taxonomy)

        rows = session.execute(
            select(TbLine, SourceDocument.system)
            .join(SourceDocument, TbLine.document_id == SourceDocument.id)
            .where(TbLine.engagement_id == engagement_id)
        ).all()

        # Reviewer-resolved mappings from earlier runs seed the cache layer.
        # ``cache_meta`` keeps their provenance so a re-run restores them as
        # ``resolved`` (reviewer choice intact), not a plain auto-match.
        cache: dict[tuple, str] = {}
        cache_meta: dict[tuple, dict] = {}
        resolved_rows = session.execute(
            select(
                TbLine,
                SourceDocument.system,
                TbMapping.fsli_code,
                TbMapping.resolved_fsli,
                TbMapping.reviewer,
                TbMapping.resolved_at,
            )
            .join(SourceDocument, TbLine.document_id == SourceDocument.id)
            .join(TbMapping, TbMapping.line_id == TbLine.id)
            .where(TbLine.engagement_id == engagement_id, TbMapping.status == "resolved")
        ).all()
        for line, system, fsli_code, resolved_fsli, reviewer, resolved_at in resolved_rows:
            choice = resolved_fsli or fsli_code
            if choice:
                key = _head_key(line.client_code, system, line.raw_code, line.raw_name)
                cache[key] = choice
                cache_meta[key] = {
                    "reviewer": reviewer,
                    "resolved_at": resolved_at,
                }

        if rows:
            line_ids = [line.id for line, _ in rows]
            session.execute(delete(TbMapping).where(TbMapping.line_id.in_(line_ids)))

        by_layer: Counter[str] = Counter()
        memo: dict[tuple, MapResult] = {}
        resolved_count = 0

        for line, system in rows:
            key = _head_key(line.client_code, system, line.raw_code, line.raw_name)
            result = memo.get(key)
            if result is None:
                head = LedgerHead(
                    raw_name=line.raw_name,
                    group=line.group_name,
                    source=system,
                    side=line.side,
                    raw_code=line.raw_code,
                    client=line.client_code,
                )
                result = mapper.map(head, layers=layers, cache=cache)
                memo[key] = result

            layer = result.layer
            by_layer[layer] += 1
            if result.auto_accepted:
                resolved_count += 1

            status = "auto" if result.auto_accepted else "pending_review"
            reviewer = None
            resolved_fsli = None
            resolved_at = None
            if layer == "cache" and key in cache_meta:
                # This auto-match replays a reviewer's earlier decision: keep it
                # as ``resolved`` with the original provenance instead of
                # downgrading it to ``auto``.
                meta = cache_meta[key]
                status = "resolved"
                reviewer = meta.get("reviewer")
                resolved_at = meta.get("resolved_at") or _utcnow()
                resolved_fsli = cache.get(key)

            session.add(
                TbMapping(
                    line_id=line.id,
                    fsli_code=result.fsli_code,
                    method=layer,
                    confidence=result.confidence,
                    status=status,
                    reviewer=reviewer,
                    resolved_fsli=resolved_fsli,
                    resolved_at=resolved_at,
                    candidates_json=_candidates_payload(result),
                )
            )

        summary = MappingSummary(
            engagement_id=engagement_id,
            lines=len(rows),
            resolved=resolved_count,
            review=len(rows) - resolved_count,
            by_layer=dict(by_layer),
            llm_calls=llm.calls if llm is not None else 0,
            tuned=tuned,
            encoder=kind,
        )
        if llm is not None:
            llm.flush()
        return summary
