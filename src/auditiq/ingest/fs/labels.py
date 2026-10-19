"""Financial-statement label -> FSLI (or group) mapping.

Reuses the **same** layered cascade as trial-balance mapping
(``cache -> alias dictionary -> embedding gate -> constrained LLM -> review``).
A financial-statement presentation label is just another ledger-style head, so
the cascade needs no changes.

Two FS-specific layers wrap the cascade:

* a reviewer-decision **cache** (seeded from the stored ``fs_line`` rows, exactly
  like the trial-balance cache) and
* a closed **group** dictionary (:mod:`auditiq.core.groups`).

A face line that aggregates several FSLIs — today "Revenue from Operations" —
resolves to a group code and is tied out as one unit instead of being forced onto
an arbitrary member. Groups only ever apply to financial statements: on the
trial-balance side a ledger head still maps to a single FSLI, which keeps the
mapping cascade (and its parity guarantee) untouched.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ...core.groups import GroupIndex, load_default_groups
from ...core.taxonomy import Taxonomy, load_default_taxonomy
from ..prepare.aliases import AliasDictionary, load_alias
from ..prepare.encoder import Encoder, default_encoder_kind, make_encoder
from ..prepare.mapper import ALL_LAYERS, LedgerHead, MapResult, Mapper
from ..prepare.normalize import nu
from ..prepare.thresholds import Thresholds, load_thresholds
from .base import CachedLabel, FsRow

GROUP_LAYER = "group"
CACHE_LAYER = "cache"


@dataclass
class LabelledRow:
    """An extracted face row plus the FSLI or group the cascade resolved it to."""

    row: FsRow
    fsli_code: Optional[str]
    group_code: Optional[str] = None
    statement: str = ""
    layer: str = "review"
    confidence: float = 0.0

    @property
    def code(self) -> Optional[str]:
        """The recon unit this row feeds: a group when it aggregates, else an FSLI."""
        return self.group_code or self.fsli_code

    @property
    def mapped(self) -> bool:
        return self.fsli_code is not None or self.group_code is not None


@dataclass
class LabelSummary:
    rows: int = 0
    mapped: int = 0
    unmapped: int = 0
    by_layer: dict[str, int] = field(default_factory=dict)
    encoder: str = "none"
    tuned: bool = False

    @property
    def coverage(self) -> float:
        return self.mapped / self.rows if self.rows else 0.0


def build_fs_mapper(
    taxonomy: Optional[Taxonomy] = None,
    client: Optional[str] = None,
    encoder_kind: Optional[str] = None,
    thresholds: Optional[Thresholds] = None,
    alias: Optional[AliasDictionary] = None,
    llm: Optional[object] = None,
) -> tuple[Mapper, Thresholds, str, bool]:
    """Build a mapper configured like the ledger cascade.

    ``llm`` is the same optional client used by trial-balance mapping; pass it
    only when a run explicitly opts in. Returns ``(mapper, thresholds,
    encoder_kind, tuned)``.
    """
    taxonomy = taxonomy or load_default_taxonomy()
    looked_up = thresholds is None
    if looked_up:
        thresholds, tuned = load_thresholds(client)
    else:
        tuned = False

    kind = encoder_kind if encoder_kind is not None else thresholds.encoder
    if kind in (None, "none") and encoder_kind is None:
        kind = default_encoder_kind()
    encoder: Optional[Encoder] = (
        make_encoder(kind, thresholds.encoder_model, taxonomy)
        if kind not in (None, "none")
        else None
    )
    alias = alias or load_alias(taxonomy=taxonomy)
    mapper = Mapper(taxonomy, alias, encoder=encoder, llm=llm, cfg=thresholds)
    return mapper, thresholds, kind, tuned


def build_group_index(taxonomy: Optional[Taxonomy] = None) -> GroupIndex:
    """Load the committed presentation-group config (empty when absent)."""
    return load_default_groups(taxonomy=taxonomy)


def label_row(
    row: FsRow,
    mapper: Mapper,
    statement: str = "",
    client: str = "",
    groups: Optional[GroupIndex] = None,
    cache: Optional[dict[tuple, CachedLabel]] = None,
    layers=ALL_LAYERS,
) -> LabelledRow:
    """Resolve one face row to a group or FSLI.

    A reviewer decision replayed from the FS cache wins over everything else, then
    the presentation-group dictionary is consulted, then the shared cascade. The
    cache is keyed by ``(statement, nu(label))`` and is already scoped to the
    client by :func:`auditiq.ingest.fs.review.load_fs_cache`.
    """
    if groups is None:
        groups = build_group_index()
    if cache is not None and CACHE_LAYER in layers:
        hit = cache.get((statement, nu(row.label)))
        if hit is not None:
            return LabelledRow(
                row=row,
                fsli_code=hit.fsli_code,
                group_code=hit.group_code,
                statement=statement,
                layer=CACHE_LAYER,
                confidence=1.0,
            )

    group_code = groups.group_for(row.label)
    if group_code is not None:
        return LabelledRow(
            row=row,
            fsli_code=None,
            group_code=group_code,
            statement=statement,
            layer=GROUP_LAYER,
            confidence=1.0,
        )

    head = LedgerHead(raw_name=row.label, group=statement, client=client)
    result: MapResult = mapper.map(head, layers=layers)
    return LabelledRow(
        row=row,
        fsli_code=result.fsli_code,
        statement=statement,
        layer=result.layer,
        confidence=result.confidence,
    )


def label_rows(
    rows_by_statement: dict[str, list[FsRow]],
    mapper: Mapper,
    client: str = "",
    layers=ALL_LAYERS,
    cache: Optional[dict[tuple, CachedLabel]] = None,
    groups: Optional[GroupIndex] = None,
) -> list[LabelledRow]:
    """Label every extracted row, deduplicating identical labels via a memo."""
    if groups is None:
        groups = build_group_index()
    memo: dict[tuple, LabelledRow] = {}
    labelled: list[LabelledRow] = []
    for statement, rows in rows_by_statement.items():
        for row in rows:
            key = (statement, nu(row.label))
            hit = memo.get(key)
            if hit is None:
                hit = label_row(
                    row,
                    mapper,
                    statement=statement,
                    client=client,
                    groups=groups,
                    cache=cache,
                    layers=layers,
                )
                memo[key] = hit
            labelled.append(
                LabelledRow(
                    row=row,
                    fsli_code=hit.fsli_code,
                    group_code=hit.group_code,
                    statement=hit.statement,
                    layer=hit.layer,
                    confidence=hit.confidence,
                )
            )
    return labelled


def summarise(labelled: list[LabelledRow], encoder: str, tuned: bool) -> LabelSummary:
    summary = LabelSummary(encoder=encoder, tuned=tuned)
    for item in labelled:
        summary.rows += 1
        summary.by_layer[item.layer] = summary.by_layer.get(item.layer, 0) + 1
        if item.mapped:
            summary.mapped += 1
        else:
            summary.unmapped += 1
    return summary


__all__ = [
    "CACHE_LAYER",
    "GROUP_LAYER",
    "LabelSummary",
    "LabelledRow",
    "build_fs_mapper",
    "build_group_index",
    "label_row",
    "label_rows",
    "summarise",
]
