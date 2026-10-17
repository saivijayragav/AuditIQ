"""The layered ledger-head mapper.

Cascade: ``cache -> alias dictionary -> embedding gate -> constrained LLM -> review``.
Every layer is optional; a run with no encoder and no LLM is dictionary-only and
sends everything else to the review queue (deterministic, no network).
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional, Sequence

import numpy as np

from ...core.taxonomy import Taxonomy
from .aliases import AliasDictionary
from .encoder import Encoder, fsli_text
from .normalize import clean, nu
from .thresholds import Thresholds

ALL_LAYERS = ("cache", "dict", "emb", "llm")


@dataclass
class LedgerHead:
    """A single ledger head presented to the mapper."""

    raw_name: str
    group: str = ""
    source: str = ""
    side: str = ""
    raw_code: str = ""
    client: str = ""


@dataclass
class MapResult:
    """Outcome of mapping one head."""

    fsli_code: Optional[str]
    layer: str  # cache | dict | emb | llm | review
    confidence: float = 0.0
    llm_called: bool = False
    llm_invalid: bool = False
    candidates: list[str] = field(default_factory=list)
    embed_score: float = 0.0
    embed_margin: float = 0.0
    timings: dict[str, float] = field(default_factory=dict)

    @property
    def auto_accepted(self) -> bool:
        return self.fsli_code is not None


class Mapper:
    """Runs the layered cascade over ledger heads."""

    def __init__(
        self,
        taxonomy: Taxonomy,
        alias: AliasDictionary,
        encoder: Optional[Encoder] = None,
        llm: Optional[object] = None,
        cfg: Optional[Thresholds] = None,
    ):
        self.tax = taxonomy
        self.alias = alias
        self.enc = encoder
        self.llm = llm
        self.cfg = cfg or Thresholds()
        self.item_vecs = (
            encoder.encode([fsli_text(taxonomy, c) for c in taxonomy.codes])
            if encoder is not None
            else None
        )

    @staticmethod
    def key(head: LedgerHead) -> tuple:
        return (head.client, head.source, head.raw_code or nu(head.raw_name))

    def embed(self, name: str, group: str = "") -> tuple[str, float, float, list[str]]:
        """Return ``(top_code, top_score, margin, shortlist)`` from the embedding layer."""
        if self.item_vecs is None or self.enc is None:
            raise RuntimeError("embedding layer requested but no encoder is configured")
        query = clean(name) + (f" ({clean(group)})" if group else "")
        sims = self.item_vecs @ self.enc.encode([query])[0]
        order = np.argsort(-sims)
        codes = self.tax.codes
        shortlist = [codes[i] for i in order[: self.cfg.k]]
        return (
            codes[order[0]],
            float(sims[order[0]]),
            float(sims[order[0]] - sims[order[1]]),
            shortlist,
        )

    def map(
        self,
        head: LedgerHead,
        layers: Sequence[str] = ALL_LAYERS,
        cache: Optional[dict] = None,
        full_list: bool = False,
    ) -> MapResult:
        cfg = self.cfg
        timings: dict[str, float] = {}
        result = MapResult(fsli_code=None, layer="review", timings=timings)

        if "cache" in layers and cache is not None:
            t0 = time.perf_counter()
            hit = cache.get(self.key(head))
            timings["cache"] = time.perf_counter() - t0
            if hit:
                result.fsli_code = hit
                result.layer = "cache"
                result.confidence = 1.0
                return result

        if "dict" in layers:
            t0 = time.perf_counter()
            codes = self.alias.codes_for(head.raw_name)
            timings["dict"] = time.perf_counter() - t0
            if len(codes) == 1:
                result.fsli_code = next(iter(codes))
                result.layer = "dict"
                result.confidence = 1.0
                return result

        candidates: Optional[list[str]] = None
        if self.enc is not None and ("emb" in layers or ("llm" in layers and not full_list)):
            t0 = time.perf_counter()
            top, score, margin, shortlist = self.embed(head.raw_name, head.group)
            timings["emb"] = time.perf_counter() - t0
            result.embed_score = score
            result.embed_margin = margin
            result.candidates = shortlist
            if "emb" in layers and score >= cfg.tau_e and margin >= cfg.delta:
                result.fsli_code = top
                result.layer = "emb"
                result.confidence = score
                return result
            candidates = shortlist

        if "llm" in layers and self.llm is not None:
            if full_list:
                candidates = self.tax.codes
            assert candidates is not None, "LLM layer requires a candidate shortlist"
            entry = self.llm.ask(head, [(c, fsli_text(self.tax, c)) for c in candidates])
            timings["llm"] = entry["latency"]
            result.llm_called = True
            code, conf = entry["code"], entry["conf"]
            if code in candidates and conf >= cfg.tau_l:
                result.fsli_code = code
                result.layer = "llm"
                result.confidence = conf
            elif code != "UNKNOWN" and code not in candidates:
                result.llm_invalid = True

        return result
