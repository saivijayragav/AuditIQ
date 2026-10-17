"""Text normalisation shared by every matching layer.

Moved to ``core`` so both the mapping cascade (``ingest.prepare``) and the
reconciliation group layer (``core.groups``) can normalise keys identically
without ``core`` depending on ``ingest``.

Two levels, exactly as the legacy mapper:

* :func:`clean` — light normalisation for model input (embedding / LLM).
* :func:`nu` — aggressive normalisation for dictionary and cache keys.
"""
from __future__ import annotations

import re


def clean(value: object) -> str:
    """Light normalisation for model input (embedding / LLM)."""
    text = str(value or "").lower().replace("&", " and ")
    text = re.sub(r"\ba\s*/\s*c(s)?\b|\bacct\b", " account ", text)
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def nu(value: object) -> str:
    """Aggressive normalisation for dictionary and cache keys."""
    return " ".join(t for t in clean(value).split() if t not in ("account", "accounts"))


__all__ = ["clean", "nu"]
