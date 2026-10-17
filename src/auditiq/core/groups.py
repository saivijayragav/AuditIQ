"""Presentation groups: a face line that aggregates several FSLIs.

Schedule III Division I presents most lines 1:1 with the taxonomy, but a few
*aggregate* on the face — most importantly **Revenue from Operations**, which the
taxonomy splits into ``INC_REV_SALES`` + ``INC_REV_SERV`` + ``INC_REV_OTH``.
Groups give the mapping cascade a second, closed target namespace so that such a
face line resolves to one unit that reconciliation can tie out.

Groups are committed config, not a database table:

* ``fsli_groups.csv``   — ``group_code, group_name, statement, fsli_code`` (one
  row per member; membership must be **disjoint**).
* ``group_aliases.csv`` — ``alias, group_code`` (presentation labels).

A group is a *reporting* aggregate: on the trial-balance side a ledger head always
maps to a single FSLI, so groups only ever appear on Side B (the financial
statements).
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

from ..settings import FSLI_GROUPS_PATH, GROUP_ALIASES_PATH
from .taxonomy import Taxonomy, load_default_taxonomy, statement_code
from .text import nu


@dataclass(frozen=True)
class FsliGroup:
    """A presentation aggregate over two or more FSLIs."""

    code: str
    name: str
    statement: str
    members: tuple[str, ...]
    category: str = ""

    @property
    def statement_code(self) -> str:
        return statement_code(self.statement)


class GroupIndex:
    """In-memory view of the committed group config."""

    def __init__(
        self,
        groups: list[FsliGroup],
        aliases: Optional[dict[str, set[str]]] = None,
    ):
        self._groups: list[FsliGroup] = groups
        self._by_code: dict[str, FsliGroup] = {g.code: g for g in groups}
        self._by_member: dict[str, str] = {}
        for group in groups:
            for member in group.members:
                self._by_member[member] = group.code
        self._aliases: dict[str, set[str]] = aliases or {}

    # -- construction ----------------------------------------------------
    @classmethod
    def from_csv(
        cls,
        group_path: str | Path | None = None,
        alias_path: str | Path | None = None,
        taxonomy: Optional[Taxonomy] = None,
    ) -> "GroupIndex":
        """Load and validate the group config against the taxonomy."""
        taxonomy = taxonomy or load_default_taxonomy()
        group_path = Path(group_path or FSLI_GROUPS_PATH)

        members: dict[str, list[str]] = {}
        meta: dict[str, tuple[str, str]] = {}
        with group_path.open(newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                code = (row.get("group_code") or "").strip()
                if not code:
                    continue
                name = (row.get("group_name") or "").strip()
                statement = (row.get("statement") or "").strip()
                fsli = (row.get("fsli_code") or "").strip()
                if not fsli:
                    continue
                if fsli not in taxonomy:
                    raise ValueError(
                        f"group '{code}' references unknown FSLI '{fsli}'"
                    )
                if code in taxonomy:
                    raise ValueError(
                        f"group code '{code}' collides with an FSLI code"
                    )
                if code in meta and meta[code] != (name, statement):
                    raise ValueError(
                        f"group '{code}' has inconsistent name/statement rows"
                    )
                meta[code] = (name, statement)
                members.setdefault(code, []).append(fsli)

        groups: list[FsliGroup] = []
        seen_member: dict[str, str] = {}
        for code, fsli_codes in members.items():
            if len(fsli_codes) < 2:
                raise ValueError(
                    f"group '{code}' has {len(fsli_codes)} member(s); a group must "
                    "aggregate at least two FSLIs"
                )
            for fsli in fsli_codes:
                other = seen_member.get(fsli)
                if other is not None:
                    raise ValueError(
                        f"FSLI '{fsli}' is a member of both '{other}' and '{code}' "
                        "(group membership must be disjoint)"
                    )
                seen_member[fsli] = code
            name, statement = meta[code]
            groups.append(
                FsliGroup(
                    code=code,
                    name=name or code,
                    statement=statement,
                    members=tuple(fsli_codes),
                    category=_common_category(fsli_codes, taxonomy),
                )
            )

        aliases = _load_group_aliases(Path(alias_path or GROUP_ALIASES_PATH), set(meta))
        return cls(groups, aliases)

    # -- lookups ---------------------------------------------------------
    def get(self, code: Optional[str]) -> Optional[FsliGroup]:
        if not code:
            return None
        return self._by_code.get(code)

    def name(self, code: Optional[str]) -> str:
        group = self.get(code)
        return group.name if group else (code or "")

    def members(self, code: Optional[str]) -> tuple[str, ...]:
        group = self.get(code)
        return group.members if group else ()

    def groups_of(self, fsli_code: Optional[str]) -> tuple[str, ...]:
        """Groups that contain ``fsli_code`` (at most one; membership is disjoint)."""
        if not fsli_code:
            return ()
        group = self._by_member.get(fsli_code)
        return (group,) if group else ()

    def alias_codes_for(self, label: object) -> set[str]:
        return self._aliases.get(nu(label), set())

    def resolves_uniquely(self, label: object) -> bool:
        return len(self.alias_codes_for(label)) == 1

    def group_for(self, label: object) -> Optional[str]:
        """The single group a presentation label denotes, when unambiguous."""
        codes = self.alias_codes_for(label)
        return next(iter(codes)) if len(codes) == 1 else None

    def normal_balance(self, code: Optional[str], taxonomy: Taxonomy) -> str:
        """``Debit``/``Credit`` when all members agree, else empty."""
        balances = {
            (taxonomy.get(m).normal_balance if taxonomy.get(m) else "")
            for m in self.members(code)
        }
        balances.discard("")
        return next(iter(balances)) if len(balances) == 1 else ""

    # -- dunders ---------------------------------------------------------
    @property
    def codes(self) -> list[str]:
        return [g.code for g in self._groups]

    def __len__(self) -> int:
        return len(self._groups)

    def __iter__(self) -> Iterator[FsliGroup]:
        return iter(self._groups)

    def __contains__(self, code: object) -> bool:
        return code in self._by_code


def _common_category(fsli_codes: list[str], taxonomy: Taxonomy) -> str:
    categories = {
        (taxonomy.get(code).category if taxonomy.get(code) else "") for code in fsli_codes
    }
    categories.discard("")
    return next(iter(categories)) if len(categories) == 1 else ""


def _load_group_aliases(path: Path, known: set[str]) -> dict[str, set[str]]:
    out: dict[str, set[str]] = {}
    if not path.exists():
        return out
    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            alias = row.get("alias") or ""
            code = (row.get("group_code") or "").strip()
            key = nu(alias)
            if not key or not code:
                continue
            if code not in known:
                raise ValueError(f"group alias '{alias}' uses unknown group '{code}'")
            out.setdefault(key, set()).add(code)
    ambiguous = {k: v for k, v in out.items() if len(v) > 1}
    if ambiguous:
        raise ValueError(f"group aliases resolve ambiguously: {sorted(ambiguous)}")
    return out


def load_default_groups(
    taxonomy: Optional[Taxonomy] = None,
    path: str | Path | None = None,
    alias_path: str | Path | None = None,
) -> GroupIndex:
    """Load the committed group config, tolerating an absent file.

    A missing config yields an empty index so that FS ingestion still works on a
    stripped-down install; a *malformed* config raises.
    """
    target = Path(path or FSLI_GROUPS_PATH)
    if not target.exists():
        return GroupIndex([])
    return GroupIndex.from_csv(target, alias_path, taxonomy)


__all__ = ["FsliGroup", "GroupIndex", "load_default_groups"]
