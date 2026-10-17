"""Cascade thresholds, tuned per engagement on a labelled dev set.

Loaded from ``data/thresholds/<client>.json`` (falling back to ``default.json``
and then to untuned defaults) so runs are re-runnable per client.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

from ...settings import THRESHOLDS_DIR

DEFAULT_FILENAME = "default.json"


@dataclass
class Thresholds:
    """Gate parameters for the mapping cascade."""

    tau_e: float = 0.5       # min embedding similarity to auto-accept the top FSLI
    delta: float = 0.02      # min top-1 vs top-2 margin to auto-accept
    tau_l: float = 0.8       # min LLM confidence to auto-accept
    k: int = 5               # shortlist size handed to the LLM
    encoder: str = "tfidf"
    encoder_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    dict_mode: str = "full"  # full | heldout
    target_ap_emb: float = 0.97
    target_ap_llm: float = 0.95

    @classmethod
    def from_dict(cls, data: dict) -> "Thresholds":
        fields = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in fields})

    def to_dict(self) -> dict:
        return asdict(self)


def thresholds_path(client: Optional[str] = None) -> Path:
    name = f"{client}.json" if client else DEFAULT_FILENAME
    return THRESHOLDS_DIR / name


def load_thresholds(
    client: Optional[str] = None, path: str | Path | None = None
) -> tuple[Thresholds, bool]:
    """Load thresholds (client -> default -> untuned). Returns ``(thresholds, tuned)``."""
    candidates = [Path(path)] if path else [thresholds_path(client), thresholds_path(None)]
    for candidate in candidates:
        if candidate and candidate.exists():
            return Thresholds.from_dict(json.loads(candidate.read_text())), True
    return Thresholds(), False


def save_thresholds(thresholds: Thresholds, client: Optional[str] = None, path: str | Path | None = None) -> Path:
    target = Path(path) if path else thresholds_path(client)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(thresholds.to_dict(), indent=2))
    return target
