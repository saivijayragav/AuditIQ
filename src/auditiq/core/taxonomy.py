"""Schedule III FSLI taxonomy.

The taxonomy maps the ``fsli_code`` namespace shared by every AuditIQ component
to its statement, category and normal balance. It is the join key that makes
reconciliation and review possible.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator, Optional

from ..settings import FSLI_SCHEMA_PATH


@dataclass(frozen=True)
class Fsli:
    """A single Schedule III Financial Statement Line Item."""

    code: str
    statement: str
    category: str
    sub_category_1: str
    sub_category_2: str
    name: str
    normal_balance: str
    description: str

    @property
    def is_debit(self) -> bool:
        return self.normal_balance.strip().lower().startswith("debit")


class Taxonomy:
    """In-memory view of the FSLI schema."""

    def __init__(self, items: list[Fsli]):
        self._items: list[Fsli] = items
        self._by_code: dict[str, Fsli] = {i.code: i for i in items}

    @classmethod
    def from_csv(cls, path: str | Path) -> "Taxonomy":
        path = Path(path)
        items: list[Fsli] = []
        with path.open(newline="", encoding="utf-8-sig") as handle:
            for row in csv.DictReader(handle):
                code = (row.get("fsli_code") or "").strip()
                if not code:
                    continue
                items.append(
                    Fsli(
                        code=code,
                        statement=(row.get("statement") or "").strip(),
                        category=(row.get("category") or "").strip(),
                        sub_category_1=(row.get("sub_category_1") or "").strip(),
                        sub_category_2=(row.get("sub_category_2") or "").strip(),
                        name=(row.get("fsli") or "").strip(),
                        normal_balance=(row.get("normal_balance") or "").strip(),
                        description=(row.get("description") or "").strip(),
                    )
                )
        if not items:
            raise ValueError(f"no FSLI rows found in {path}")
        return cls(items)

    # -- lookups ---------------------------------------------------------
    def get(self, code: Optional[str]) -> Optional[Fsli]:
        if not code:
            return None
        return self._by_code.get(code)

    def name(self, code: Optional[str]) -> str:
        item = self.get(code)
        return item.name if item else (code or "")

    @property
    def codes(self) -> list[str]:
        return [i.code for i in self._items]

    def by_statement(self, statement: str) -> list[Fsli]:
        target = statement.strip().lower()
        return [i for i in self._items if i.statement.lower() == target]

    def by_category(self, category: str) -> list[Fsli]:
        target = category.strip().lower()
        return [i for i in self._items if i.category.lower() == target]

    def search(self, text: str) -> list[Fsli]:
        needle = text.strip().lower()
        return [i for i in self._items if needle in i.name.lower()]

    # -- dunders ---------------------------------------------------------
    def __len__(self) -> int:
        return len(self._items)

    def __iter__(self) -> Iterator[Fsli]:
        return iter(self._items)

    def __contains__(self, code: object) -> bool:
        return code in self._by_code


def load_default_taxonomy(path: str | Path | None = None) -> Taxonomy:
    """Load the taxonomy from the configured schema path."""
    return Taxonomy.from_csv(path or FSLI_SCHEMA_PATH)
