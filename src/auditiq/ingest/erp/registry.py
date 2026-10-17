"""Adapter registry: dispatch a parsed grid to the right ERP adapter."""
from __future__ import annotations

from pathlib import Path

from . import generic, sap, tally, zoho
from .base import TbRecord
from .detect import detect_source
from .io import read_grid

ADAPTERS = {
    "tally": tally.read,
    "sap": sap.read,
    "zoho": zoho.read,
    "generic": generic.read,
}


def read_records(rows: list[list], source: str) -> list[TbRecord]:
    """Run the adapter for ``source`` over an already-parsed grid."""
    try:
        adapter = ADAPTERS[source]
    except KeyError:
        raise ValueError(
            f"unknown source '{source}' (expected one of {sorted(ADAPTERS)})"
        ) from None
    return adapter(rows)


def read_with_source(
    path: str | Path, source: str | None = None
) -> tuple[list[TbRecord], str]:
    """Read a TB file, auto-detecting the layout when ``source`` is not given.

    Returns ``(records, source)``.
    """
    rows = read_grid(path)
    resolved = source or detect_source(rows)
    return read_records(rows, resolved), resolved
