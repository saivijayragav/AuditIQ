"""Financial-statement label -> FSLI mapping.

Reuses the **same** layered cascade as trial-balance mapping
(``cache -> alias dictionary -> embedding gate -> constrained LLM -> review``).
A financial-statement presentation label is just another ledger-style head, so
the cascade needs no changes; the alias dictionary is extended with the stable
Schedule III face vocabulary and the embedding gate covers the remainder.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ...core.taxonomy import Taxonomy, load_default_taxonomy
from ..prepare.aliases import AliasDictionary, load_alias
from ..prepare.encoder import Encoder, default_encoder_kind, make_encoder
from ..prepare.mapper import ALL_LAYERS, LedgerHead, MapResult, Mapper
from ..prepare.thresholds import Thresholds, load_thresholds
from .base import FsRow


@dataclass
class LabelledRow:
    """An extracted face row plus the FSLI the cascade resolved it to."""

    row: FsRow
    fsli_code: Optional[str]
    statement: str = ""
    layer: str = "review"
    confidence: float = 0.0

    @property
    def mapped(self) -> bool:
        return self.fsli_code is not None


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
) -> tuple[Mapper, Thresholds, str, bool]:
    """Build a mapper configured like the ledger cascade.

    Returns ``(mapper, thresholds, encoder_kind, tuned)``.
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
    mapper = Mapper(taxonomy, alias, encoder=encoder, cfg=thresholds)
    return mapper, thresholds, kind, tuned


def label_row(row: FsRow, mapper: Mapper, statement: str = "", client: str = "") -> LabelledRow:
    """Resolve one face row to an FSLI through the cascade."""
    head = LedgerHead(raw_name=row.label, group=statement, client=client)
    result: MapResult = mapper.map(head)
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
    cache: Optional[dict] = None,
) -> list[LabelledRow]:
    """Label every extracted row, deduplicating identical labels via a memo."""
    memo: dict[tuple, MapResult] = {}
    labelled: list[LabelledRow] = []
    for statement, rows in rows_by_statement.items():
        for row in rows:
            key = (statement, row.label.lower())
            result = memo.get(key)
            if result is None:
                head = LedgerHead(raw_name=row.label, group=statement, client=client)
                result = mapper.map(head, layers=layers, cache=cache)
                memo[key] = result
            labelled.append(
                LabelledRow(
                    row=row,
                    fsli_code=result.fsli_code,
                    statement=statement,
                    layer=result.layer,
                    confidence=result.confidence,
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
    "LabelSummary",
    "LabelledRow",
    "build_fs_mapper",
    "label_row",
    "label_rows",
    "summarise",
]
