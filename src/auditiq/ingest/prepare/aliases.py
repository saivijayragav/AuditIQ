"""Alias dictionary: normalised alias -> the FSLI code(s) it may denote.

Ported from the legacy ``load_alias``. ``exclude`` supports held-out evaluation
(removing aliases that collide with the heads under test).
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from ...core.taxonomy import Taxonomy
from ...settings import ALIASES_PATH
from .normalize import nu


class AliasDictionary:
    """A normalised alias -> set[fsli_code] lookup built from ``aliases.csv``."""

    def __init__(self, mapping: dict[str, set[str]]):
        self._map = mapping

    def get(self, key: str, default: set[str] | None = None) -> set[str]:
        return self._map.get(key, default if default is not None else set())

    def codes_for(self, raw_name: object) -> set[str]:
        return self._map.get(nu(raw_name), set())

    def resolves_uniquely(self, raw_name: object) -> bool:
        return len(self.codes_for(raw_name)) == 1

    def __len__(self) -> int:
        return len(self._map)

    def __contains__(self, key: object) -> bool:
        return key in self._map


def load_alias(
    path: str | Path | None = None,
    taxonomy: Taxonomy | None = None,
    exclude: Iterable[str] = (),
) -> AliasDictionary:
    """Load the alias dictionary, validating codes against the taxonomy."""
    path = Path(path or ALIASES_PATH)
    known = set(taxonomy.codes) if taxonomy is not None else None
    excluded = set(exclude)
    out: dict[str, set[str]] = {}

    with path.open(newline="", encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            alias = row.get("alias") or ""
            code = (row.get("fsli_code") or "").strip()
            key = nu(alias)
            if not key or key in excluded:
                continue
            if known is not None and code not in known:
                raise ValueError(f"alias '{alias}' uses unknown FSLI code '{code}'")
            out.setdefault(key, set()).add(code)

    return AliasDictionary(out)
