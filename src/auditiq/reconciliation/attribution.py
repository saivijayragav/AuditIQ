"""Attribution: *why* a unit does not tie out.

For every unit that fails the tie-out we try to explain its variance from data we
already have, deterministically and without any model call:

1. **Unmapped exposure** — trial-balance heads that never resolved, but whose name
   clearly belongs to this unit. This is the dominant real-world cause.
2. **Reclass pair** — another unit whose variance is equal and opposite, i.e. the
   amount was booked to the wrong bucket. Reported on *both* units.
3. **Current-year result** — for an equity unit, the unreclosed profit or loss.
4. **Residual** — whatever is left, flagged as "likely adjustment / not explained".

Matching is lexical against each unit's vocabulary (its name, description and
every committed alias). It is intentionally conservative: a head must share at
least two significant tokens, so single-word heads stay in the exposure report
rather than being force-fitted.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from ..core.groups import GroupIndex
from ..core.taxonomy import Taxonomy
from ..core.text import nu
from ..ingest.prepare.aliases import AliasDictionary
from .aggregate import ExposureLine, SideA, SideB
from .materiality import ReconConfig
from .tieout import ReconLineResult

UNMAPPED_EXPOSURE = "unmapped_exposure"
RECLASS_PAIR = "reclass_pair"
PROFIT_OFFSET = "profit_offset"
RESIDUAL = "residual"

MIN_OVERLAP_TOKENS = 2
MIN_CONTAINMENT = 0.5
STOPWORDS = {
    "and", "of", "the", "to", "for", "in", "on", "a", "an", "by", "with", "at",
    "from", "as", "is", "account", "accounts",
}


def tokens(text: object) -> set[str]:
    return {t for t in nu(text).split() if t not in STOPWORDS and len(t) > 1}


class UnitVocabulary:
    """Token pool per recon unit, from names, descriptions and committed aliases."""

    def __init__(self, taxonomy: Taxonomy, groups: GroupIndex, alias: AliasDictionary):
        self._tax = taxonomy
        self._groups = groups
        self._alias = alias
        self._by_code: dict[str, set[str]] = {}

        for item in taxonomy:
            pool = tokens(item.name) | tokens(item.description)
            self._by_code[item.code] = pool
        for key, codes in alias._map.items():
            for code in codes:
                pool = self._by_code.get(code)
                if pool is not None:
                    pool |= tokens(key)

    def for_unit(self, code: str, is_group: bool) -> set[str]:
        if not is_group:
            return set(self._by_code.get(code, set()))
        pool: set[str] = set()
        for member in self._groups.members(code):
            pool |= self._by_code.get(member, set())
        group = self._groups.get(code)
        if group:
            pool |= tokens(group.name)
        return pool

    def match(self, line: ExposureLine, code: str, is_group: bool) -> float:
        """Fraction of the head's tokens known to the unit (0 when too vague)."""
        head = tokens(line.raw_name) | tokens(line.group_name)
        if not head:
            return 0.0
        overlap = head & self.for_unit(code, is_group)
        if len(overlap) < MIN_OVERLAP_TOKENS:
            return 0.0
        score = len(overlap) / len(head)
        return score if score >= MIN_CONTAINMENT else 0.0


@dataclass
class Candidate:
    kind: str
    amount: float
    detail: str
    refs: list = field(default_factory=list)


@dataclass
class Attribution:
    unit_code: str
    variance: float
    explained: float = 0.0
    residual: float = 0.0
    candidates: list[Candidate] = field(default_factory=list)

    @property
    def explained_ratio(self) -> Optional[float]:
        if not self.variance:
            return None
        return self.explained / self.variance


def _unit_sign(code: str, is_group: bool, taxonomy: Taxonomy, groups: GroupIndex) -> int:
    if is_group:
        balance = groups.normal_balance(code, taxonomy)
    else:
        item = taxonomy.get(code)
        balance = item.normal_balance if item else ""
    return 1 if str(balance).strip().lower().startswith("debit") else -1


def _net_profit(side_b: SideB, taxonomy: Taxonomy, groups: GroupIndex) -> float:
    income = expense = 0.0
    for code, value in side_b.by_fsli.items():
        item = taxonomy.get(code)
        category = item.category if item else ""
        if category == "Income":
            income += value
        elif category == "Expense":
            expense += value
    for code, value in side_b.by_group.items():
        group = groups.get(code)
        if group and group.category == "Income":
            income += value
    return income - expense


def attribute(
    results: list[ReconLineResult],
    side_a: SideA,
    side_b: SideB,
    taxonomy: Taxonomy,
    groups: GroupIndex,
    alias: AliasDictionary,
    config: ReconConfig,
) -> dict[str, Attribution]:
    """Attribute every non-rounding recon line; rounding lines are skipped."""
    vocabulary = UnitVocabulary(taxonomy, groups, alias)
    tolerance = config.tolerance
    net_profit = _net_profit(side_b, taxonomy, groups)

    unmatched = [line for line in side_a.exposure]
    attributions: dict[str, Attribution] = {}

    def best_unit(line: ExposureLine) -> tuple[Optional[str], float, bool]:
        best: tuple[Optional[str], float, bool] = (None, 0.0, False)
        for result in results:
            score = vocabulary.match(line, result.code, result.unit.is_group)
            if score > best[1]:
                best = (result.code, score, result.unit.is_group)
        return best

    # 1. Unmapped exposure -> the unit it most likely belongs to.
    for line in unmatched:
        code, score, is_group = best_unit(line)
        if code is None:
            continue
        result = next(r for r in results if r.code == code)
        sign = _unit_sign(code, is_group, taxonomy, groups)
        attributions.setdefault(code, Attribution(code, result.variance))
        attributions[code].candidates.append(
            Candidate(
                kind=UNMAPPED_EXPOSURE,
                amount=sign * line.amount,
                detail=(
                    f"unmapped head '{line.raw_name or line.raw_code}' "
                    f"({line.amount:,.2f}, {line.status})"
                ),
                refs=[line.line_id],
            )
        )

    # 2. Reclass pairs: equal and opposite variances.
    for i, left in enumerate(results):
        if abs(left.variance) <= tolerance:
            continue
        for right in results[i + 1 :]:
            if abs(right.variance) <= tolerance:
                continue
            if abs(left.variance + right.variance) <= tolerance:
                attributions.setdefault(left.code, Attribution(left.code, left.variance))
                attributions.setdefault(right.code, Attribution(right.code, right.variance))
                attributions[left.code].candidates.append(
                    Candidate(
                        kind=RECLASS_PAIR,
                        amount=-right.variance,
                        detail=(
                            f"offset by {right.code} {right.unit.name} "
                            f"({right.variance:,.2f}); likely a mis-posting / reclass"
                        ),
                        refs=[right.code],
                    )
                )
                attributions[right.code].candidates.append(
                    Candidate(
                        kind=RECLASS_PAIR,
                        amount=-left.variance,
                        detail=(
                            f"offset by {left.code} {left.unit.name} "
                            f"({left.variance:,.2f}); likely a mis-posting / reclass"
                        ),
                        refs=[left.code],
                    )
                )

    # 3. Current-year result on equity units, then 4. whatever remains.
    for result in results:
        if abs(result.variance) <= tolerance:
            continue
        entry = attributions.setdefault(result.code, Attribution(result.code, result.variance))
        explained = sum(c.amount for c in entry.candidates)
        residual = result.variance - explained

        category = _unit_category(result, taxonomy, groups)
        if (
            category == "Equity"
            and abs(residual) > tolerance
            and abs(residual + net_profit) <= tolerance
        ):
            entry.candidates.append(
                Candidate(
                    kind=PROFIT_OFFSET,
                    amount=residual,
                    detail=(
                        f"current-year result {net_profit:,.2f} not yet closed to "
                        "this equity line"
                    ),
                )
            )
            explained += residual
            residual = 0.0

        entry.explained = explained
        entry.residual = residual
        if abs(residual) > tolerance:
            entry.candidates.append(
                Candidate(
                    kind=RESIDUAL,
                    amount=residual,
                    detail=(
                        "unexplained: likely a manual / statutory adjustment, a "
                        "rounding chain or a presentation difference"
                    ),
                )
            )

    return attributions


def _unit_category(result: ReconLineResult, taxonomy: Taxonomy, groups: GroupIndex) -> str:
    if result.unit.is_group:
        group = groups.get(result.code)
        return group.category if group else ""
    item = taxonomy.get(result.code)
    return item.category if item else ""


__all__ = [
    "Attribution",
    "Candidate",
    "MIN_CONTAINMENT",
    "MIN_OVERLAP_TOKENS",
    "PROFIT_OFFSET",
    "RECLASS_PAIR",
    "RESIDUAL",
    "UNMAPPED_EXPOSURE",
    "UnitVocabulary",
    "attribute",
    "tokens",
]
