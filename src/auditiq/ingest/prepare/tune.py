"""Tune the embedding and LLM gates on a labelled dev set.

Ported from the legacy ``tune.py``: choose ``tau_e``/``delta`` (embedding gate)
and ``tau_l`` (LLM gate) so that auto-accepted maps hit a precision target on the
dev split, maximising coverage subject to that target. Output is a per-client
``thresholds.json`` so the process is re-runnable for every new client.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

from ...core import load_default_taxonomy
from .aliases import load_alias
from .encoder import default_encoder_kind, make_encoder
from .mapper import LedgerHead, Mapper
from .normalize import nu
from .thresholds import Thresholds

_TAU_E_GRID = np.arange(0.2, 0.96, 0.01)
_DELTA_GRID = (0.0, 0.01, 0.02, 0.05, 0.1)
_TAU_L_GRID = np.arange(0.3, 0.99, 0.05)


@dataclass
class LabelledHead(LedgerHead):
    """A ledger head with its gold FSLI label."""

    gold: str = ""


def load_labelled_csv(path: str | Path, split: Optional[str] = None) -> list[LabelledHead]:
    """Load a gold-style CSV (``raw_name, group, gold, source, ...``).

    When ``split`` is given and the file has a ``split`` column, only matching
    rows are kept (the legacy tuner always tuned on the ``dev`` split).
    """
    out: list[LabelledHead] = []
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        has_split = bool(reader.fieldnames) and "split" in reader.fieldnames
        for row in reader:
            if split and has_split and (row.get("split") or "").strip() != split:
                continue
            gold = (row.get("gold") or row.get("gold_fsli_code") or "").strip()
            out.append(
                LabelledHead(
                    raw_name=(row.get("raw_name") or "").strip(),
                    group=(row.get("group") or row.get("group_hint") or "").strip(),
                    source=(row.get("source") or "").strip(),
                    side=(row.get("side") or "").strip(),
                    raw_code=(row.get("raw_code") or "").strip(),
                    client=(row.get("client") or "").strip(),
                    gold=gold,
                )
            )
    return out


def _embedding_stage(mapper: Mapper, alias, dev: Sequence[LabelledHead], target: float, k: int):
    rows = []
    for record in dev:
        if alias.resolves_uniquely(record.raw_name):
            continue
        top, score, margin, _ = mapper.embed(record.raw_name, record.group)
        rows.append((score, margin, top == record.gold))
    if not rows:
        return None, dict(coverage=0.0, precision=float("nan"), accepted=0)

    score, margin, ok = (np.array(x) for x in zip(*rows))
    best = None
    for tau_e in _TAU_E_GRID:
        for delta in _DELTA_GRID:
            accepted = (score >= tau_e) & (margin >= delta)
            if accepted.sum() < 10:
                continue
            precision = ok[accepted].mean()
            coverage = accepted.mean()
            if precision >= target and (best is None or coverage > best[0]):
                best = (coverage, float(tau_e), float(delta), float(precision))
    if best is None:
        fallback = (0.0, 0.9, 0.05, float("nan"))
        return fallback, dict(coverage=0.0, precision=float("nan"), accepted=0, fallback=True)
    return best, dict(coverage=best[0], precision=best[3], accepted=int(len(rows)))


def _llm_stage(mapper: Mapper, alias, dev: Sequence[LabelledHead], tau_e: float, delta: float, target: float):
    observations = []
    for record in dev:
        if alias.resolves_uniquely(record.raw_name):
            continue
        _, score, margin, shortlist = mapper.embed(record.raw_name, record.group)
        if score >= tau_e and margin >= delta:
            continue
        entry = mapper.llm.ask(record, [(c, mapper.tax.get(c).name if mapper.tax.get(c) else c) for c in shortlist])
        valid = entry["code"] in shortlist
        observations.append((entry["conf"], valid and entry["code"] == record.gold, valid))
    if not observations:
        return 0.8, dict(coverage=0.0, precision=float("nan"), observations=0)

    conf, good, valid = (np.array(x) for x in zip(*observations))
    best = None
    for tau_l in _TAU_L_GRID:
        accepted = (conf >= tau_l) & valid
        if accepted.sum() < 5:
            continue
        precision, coverage = good[accepted].mean(), accepted.mean()
        if precision >= target and (best is None or coverage > best[0]):
            best = (coverage, float(tau_l), float(precision))
    if best is None:
        return 0.9, dict(coverage=0.0, precision=float("nan"), observations=len(observations), fallback=True)
    return round(best[1], 2), dict(coverage=best[0], precision=best[2], observations=len(observations))


def tune_thresholds(
    dev: Sequence[LabelledHead],
    taxonomy=None,
    encoder_kind: Optional[str] = None,
    encoder_model: Optional[str] = None,
    llm=None,
    k: int = 5,
    target_ap_emb: float = 0.97,
    target_ap_llm: float = 0.95,
    dict_mode: str = "full",
) -> tuple[Thresholds, dict]:
    """Return tuned :class:`Thresholds` and a human-readable report."""
    taxonomy = taxonomy or load_default_taxonomy()
    encoder_model = encoder_model or Thresholds().encoder_model
    kind = encoder_kind or default_encoder_kind()

    exclude = {nu(r.raw_name) for r in dev} if dict_mode == "heldout" else set()
    alias = load_alias(taxonomy=taxonomy, exclude=exclude)
    encoder = make_encoder(kind, encoder_model, taxonomy)

    cfg = Thresholds(tau_e=9.0, delta=9.0, tau_l=0.0, k=k, encoder=kind, encoder_model=encoder_model)
    mapper = Mapper(taxonomy, alias, encoder=encoder, llm=llm, cfg=cfg)

    report: dict = dict(dev_heads=len(dev), encoder=kind, dict_mode=dict_mode)

    if encoder is None:
        report["embedding"] = dict(skipped="no encoder available")
        tau_e, delta = Thresholds().tau_e, Thresholds().delta
    else:
        best, stats = _embedding_stage(mapper, alias, dev, target_ap_emb, k)
        tau_e, delta = round(float(best[1]), 3), float(best[2])
        report["embedding"] = stats
        report["embedding"].update(tau_e=tau_e, delta=delta)

    tau_l = 0.8
    if llm is not None and encoder is not None:
        tau_l, stats = _llm_stage(mapper, alias, dev, tau_e, delta, target_ap_llm)
        report["llm"] = stats
        report["llm"].update(tau_l=tau_l)
    else:
        report["llm"] = dict(skipped="LLM layer not enabled")

    thresholds = Thresholds(
        tau_e=tau_e,
        delta=delta,
        tau_l=tau_l,
        k=k,
        encoder=kind,
        encoder_model=encoder_model,
        dict_mode=dict_mode,
        target_ap_emb=target_ap_emb,
        target_ap_llm=target_ap_llm,
    )
    return thresholds, report
