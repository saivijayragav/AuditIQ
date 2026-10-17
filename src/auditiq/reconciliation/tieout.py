"""Tie-out: a full outer join of Side A and Side B over recon units.

A **unit** is either a single FSLI or a presentation group. When Side B presents a
group on the face, its member FSLIs are suppressed as separate units and their
Side A sums are rolled into the group — that is what lets a one-line face total
tie out against the three ledger accounts behind it.

The grid is a full outer join, so ``only_a`` (books have it, the statements do
not) and ``only_b`` (the statements show it, the books do not) are first-class
outcomes rather than silent zeros.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Optional

from ..core.groups import GroupIndex
from ..core.taxonomy import Taxonomy, statement_code
from .aggregate import SideA, SideB
from .materiality import ReconConfig, classify, variance_percent


@dataclass
class ReconUnit:
    """A single comparable line on both sides."""

    code: str
    name: str
    statement: str
    is_group: bool = False
    members: tuple[str, ...] = ()


@dataclass
class ReconLineResult:
    unit: ReconUnit
    side_a: float
    side_b: float
    variance: float
    variance_pct: Optional[float]
    a_lines: int
    b_rows: int
    classification: str
    severity: str
    a_line_ids: list[int] = field(default_factory=list)
    b_line_ids: list[int] = field(default_factory=list)

    @property
    def code(self) -> str:
        return self.unit.code

    @property
    def refs_json(self) -> str:
        return json.dumps(
            {
                "members": list(self.unit.members),
                "a_line_ids": self.a_line_ids,
                "b_line_ids": self.b_line_ids,
            }
        )


def build_units(side_a: SideA, side_b: SideB, taxonomy: Taxonomy, groups: GroupIndex) -> list[ReconUnit]:
    """The comparable units of a run, groups first, then individual FSLIs."""
    present_groups = [g for g in side_b.by_group if g in groups]
    suppressed: set[str] = set()
    for group_code in present_groups:
        suppressed.update(groups.members(group_code))

    units: list[ReconUnit] = []
    for group_code in sorted(present_groups):
        group = groups.get(group_code)
        units.append(
            ReconUnit(
                code=group_code,
                name=group.name if group else group_code,
                statement=(group.statement_code if group else ""),
                is_group=True,
                members=groups.members(group_code),
            )
        )

    universe = (set(side_a.by_fsli) | set(side_b.by_fsli)) - suppressed
    for code in sorted(universe):
        item = taxonomy.get(code)
        units.append(
            ReconUnit(
                code=code,
                name=item.name if item else code,
                statement=statement_code(item.statement) if item else "",
                is_group=False,
            )
        )
    return units


def tieout(
    side_a: SideA,
    side_b: SideB,
    taxonomy: Taxonomy,
    groups: GroupIndex,
    config: ReconConfig,
) -> list[ReconLineResult]:
    """Classify every in-scope unit under the rounding and materiality gates."""
    results: list[ReconLineResult] = []
    for unit in build_units(side_a, side_b, taxonomy, groups):
        if not config.in_scope(unit.statement):
            continue

        if unit.is_group:
            a = sum(side_a.by_fsli.get(m, 0.0) for m in unit.members)
            a_lines = sum(side_a.lines_by_fsli.get(m, 0) for m in unit.members)
            a_ids = [i for m in unit.members for i in side_a.ids_by_fsli.get(m, [])]
            b = side_b.by_group.get(unit.code, 0.0)
            b_rows = side_b.rows_by_group.get(unit.code, 0)
            b_ids = list(side_b.ids_by_group.get(unit.code, []))
        else:
            a = side_a.by_fsli.get(unit.code, 0.0)
            a_lines = side_a.lines_by_fsli.get(unit.code, 0)
            a_ids = list(side_a.ids_by_fsli.get(unit.code, []))
            b = side_b.by_fsli.get(unit.code, 0.0)
            b_rows = side_b.rows_by_fsli.get(unit.code, 0)
            b_ids = list(side_b.ids_by_fsli.get(unit.code, []))

        variance = a - b
        classification, severity = classify(variance, config)
        results.append(
            ReconLineResult(
                unit=unit,
                side_a=a,
                side_b=b,
                variance=variance,
                variance_pct=variance_percent(variance, b, config),
                a_lines=a_lines,
                b_rows=b_rows,
                classification=classification,
                severity=severity,
                a_line_ids=a_ids,
                b_line_ids=b_ids,
            )
        )
    return results


__all__ = ["ReconLineResult", "ReconUnit", "build_units", "tieout"]
