"""Tests for the deterministic cascade layers (normalise, aliases, mapper core)."""
from __future__ import annotations

import pytest

from auditiq.ingest.prepare import (
    LedgerHead,
    Mapper,
    Thresholds,
    clean,
    load_alias,
    nu,
    parse_answer,
)


class FakeLLM:
    """A duck-typed stand-in for the constrained LLM layer (no network)."""

    def __init__(self, code: str, conf: float = 0.9, latency: float = 0.01):
        self.code, self.conf, self.latency = code, conf, latency
        self.calls = 0
        self.seen_candidates: list[str] = []

    def ask(self, head, candidates):
        self.calls += 1
        self.seen_candidates = [c for c, _ in candidates]
        return dict(code=self.code, conf=self.conf, latency=self.latency, tin=0, tout=0, temp0=True, raw="")


def test_clean_and_nu():
    assert clean("Sundry A/C & Debtors") == "sundry account and debtors"
    assert nu("Sundry A/C & Debtors") == "sundry and debtors"
    assert nu("Trade Accounts Receivable") == "trade receivable"


def test_alias_dictionary(taxonomy):
    alias = load_alias(taxonomy=taxonomy)
    assert alias.codes_for("Sundry Debtors") == {"AST_TR"}
    assert alias.resolves_uniquely("Share Capital")
    assert not alias.resolves_uniquely("Inventories and something else")
    assert alias.codes_for("Not A Real Head") == set()


def test_alias_rejects_unknown_code(tmp_path, taxonomy):
    path = tmp_path / "bad.csv"
    path.write_text("alias,fsli_code\nFoo,BOGUS_CODE\n")
    with pytest.raises(ValueError):
        load_alias(path, taxonomy=taxonomy)


def test_alias_holdout(taxonomy):
    alias = load_alias(taxonomy=taxonomy, exclude={nu("Sundry Debtors")})
    assert alias.codes_for("Sundry Debtors") == set()


def test_load_labelled_csv_split_filter(tmp_path):
    from auditiq.ingest.prepare import load_labelled_csv

    path = tmp_path / "labelled.csv"
    path.write_text(
        "raw_name,group,gold,split\n"
        "Alpha,,AST_TR,dev\n"
        "Beta,,EQ_SC,test\n"
        "Gamma,,AST_INV,\n"
    )
    assert len(load_labelled_csv(path)) == 3
    assert [h.raw_name for h in load_labelled_csv(path, split="dev")] == ["Alpha"]
    assert [h.raw_name for h in load_labelled_csv(path, split="test")] == ["Beta"]


def test_mapper_dict_layer(taxonomy):
    alias = load_alias(taxonomy=taxonomy)
    mapper = Mapper(taxonomy, alias, encoder=None, llm=None, cfg=Thresholds())
    result = mapper.map(LedgerHead(raw_name="Sundry Debtors", source="zoho"))
    assert result.fsli_code == "AST_TR"
    assert result.layer == "dict"


def test_mapper_review_when_unresolved(taxonomy):
    alias = load_alias(taxonomy=taxonomy)
    mapper = Mapper(taxonomy, alias, encoder=None, llm=None, cfg=Thresholds())
    result = mapper.map(LedgerHead(raw_name="Zzz Mystery Ledger 42", source="tally"))
    assert result.fsli_code is None
    assert result.layer == "review"
    assert not result.auto_accepted


def test_mapper_cache_layer(taxonomy):
    alias = load_alias(taxonomy=taxonomy)
    mapper = Mapper(taxonomy, alias, encoder=None, llm=None, cfg=Thresholds())
    head = LedgerHead(raw_name="Some Unmapped Head", source="sap", client="T00")
    cache = {mapper.key(head): "AST_TR"}
    result = mapper.map(head, cache=cache)
    assert result.layer == "cache"
    assert result.fsli_code == "AST_TR"


def test_mapper_llm_layer_full_list(taxonomy):
    alias = load_alias(taxonomy=taxonomy)
    fake = FakeLLM("AST_TR", conf=0.95)
    mapper = Mapper(taxonomy, alias, encoder=None, llm=fake, cfg=Thresholds(tau_l=0.8))
    result = mapper.map(
        LedgerHead(raw_name="Trade Receivables Control", source="sap"),
        layers=("dict", "llm"),
        full_list=True,
    )
    assert result.llm_called
    assert result.layer == "llm"
    assert result.fsli_code == "AST_TR"
    assert fake.calls == 1


def test_mapper_llm_below_threshold_goes_to_review(taxonomy):
    alias = load_alias(taxonomy=taxonomy)
    fake = FakeLLM("AST_TR", conf=0.4)
    mapper = Mapper(taxonomy, alias, encoder=None, llm=fake, cfg=Thresholds(tau_l=0.8))
    result = mapper.map(
        LedgerHead(raw_name="Something Else", source="sap"),
        layers=("llm",),
        full_list=True,
    )
    assert result.layer == "review"
    assert result.llm_called


def test_mapper_llm_invalid_code_flagged(taxonomy):
    alias = load_alias(taxonomy=taxonomy)
    fake = FakeLLM("NOT_A_REAL_CODE", conf=0.99)
    mapper = Mapper(taxonomy, alias, encoder=None, llm=fake, cfg=Thresholds(tau_l=0.8))
    result = mapper.map(
        LedgerHead(raw_name="Something Else", source="sap"),
        layers=("llm",),
        full_list=True,
    )
    assert result.layer == "review"
    assert result.llm_invalid


def test_parse_answer():
    assert parse_answer('{"code": "AST_TR", "confidence": 0.87}') == ("AST_TR", 0.87)
    assert parse_answer('noise "code": "EQ_SC", "confidence": 1.5') == ("EQ_SC", 1.0)
    assert parse_answer("") == ("UNKNOWN", 0.0)
    assert parse_answer("garbage") == ("UNKNOWN", 0.0)


def test_thresholds_roundtrip(tmp_path):
    from auditiq.ingest.prepare import load_thresholds, save_thresholds

    path = tmp_path / "thresholds.json"
    save_thresholds(Thresholds(tau_e=0.63, delta=0.03, tau_l=0.85, k=7), path=path)
    loaded, tuned = load_thresholds(path=path)
    assert tuned
    assert loaded.tau_e == 0.63
    assert loaded.k == 7


def test_thresholds_untuned_fallback(tmp_path):
    from auditiq.ingest.prepare import load_thresholds

    loaded, tuned = load_thresholds(path=tmp_path / "missing.json")
    assert not tuned
    assert loaded.tau_e == Thresholds().tau_e
