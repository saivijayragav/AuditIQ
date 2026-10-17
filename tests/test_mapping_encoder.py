"""Embedding / service / tuning tests. Skipped when scikit-learn is unavailable."""
from __future__ import annotations

import pytest

pytest.importorskip("sklearn")

from sqlalchemy import select

from auditiq.core import load_default_taxonomy
from auditiq.ingest.erp import ingest_tb
from auditiq.ingest.prepare import (
    LabelledHead,
    LedgerHead,
    Mapper,
    Thresholds,
    load_alias,
    make_encoder,
    map_engagement,
    tune_thresholds,
)
from auditiq.store import session_scope
from auditiq.store.models import TbLine, TbMapping


def _mapper(taxonomy, **cfg):
    alias = load_alias(taxonomy=taxonomy)
    encoder = make_encoder("tfidf", Thresholds().encoder_model, taxonomy)
    return Mapper(taxonomy, alias, encoder=encoder, llm=None, cfg=Thresholds(**cfg))


def test_embed_returns_valid_candidates(taxonomy):
    mapper = _mapper(taxonomy, k=5)
    top, score, margin, shortlist = mapper.embed("Share Capital", "Equity")
    assert top in taxonomy.codes
    assert len(shortlist) == 5
    assert all(code in taxonomy.codes for code in shortlist)
    assert isinstance(score, float) and isinstance(margin, float)


def test_dict_layer_takes_priority_over_embedding(taxonomy):
    mapper = _mapper(taxonomy, tau_e=0.0, delta=0.0)
    result = mapper.map(LedgerHead(raw_name="Sundry Debtors", source="zoho"))
    assert result.layer == "dict"
    assert result.fsli_code == "AST_TR"


def test_cascade_auto_accepts_known_heads(taxonomy):
    mapper = _mapper(taxonomy, tau_e=0.3, delta=0.0)
    result = mapper.map(LedgerHead(raw_name="Trade Receivables", source="sap"))
    assert result.fsli_code is not None
    assert result.layer in ("dict", "emb")


def test_map_engagement_dict_only(tmp_path, write_xlsx, zoho_rows):
    path = write_xlsx(tmp_path / "tb.xlsx", zoho_rows)
    url = f"sqlite:///{tmp_path / 'map.db'}"
    ingested = ingest_tb(path, client_code="T00", period="FY25-26", url=url)

    summary = map_engagement(ingested.engagement_id, url=url, encoder_kind="none")

    assert summary.lines == 2
    assert summary.encoder == "none"
    assert summary.resolved == 2
    assert summary.review == 0
    assert summary.by_layer == {"dict": 2}

    with session_scope(url) as session:
        mappings = session.scalars(select(TbMapping)).all()
        assert len(mappings) == 2
        assert {m.method for m in mappings} == {"dict"}
        assert {m.status for m in mappings} == {"auto"}
        assert {m.fsli_code for m in mappings} == {"AST_TR", "EQ_SC"}


def test_map_engagement_is_idempotent(tmp_path, write_xlsx, zoho_rows):
    path = write_xlsx(tmp_path / "tb.xlsx", zoho_rows)
    url = f"sqlite:///{tmp_path / 'map.db'}"
    ingested = ingest_tb(path, client_code="T00", period="FY25-26", url=url)

    map_engagement(ingested.engagement_id, url=url, encoder_kind="none")
    map_engagement(ingested.engagement_id, url=url, encoder_kind="none")

    with session_scope(url) as session:
        assert len(session.scalars(select(TbLine)).all()) == 2
        assert len(session.scalars(select(TbMapping)).all()) == 2


def test_map_engagement_tfidf_resolves_at_least_dict(tmp_path, write_xlsx, zoho_rows):
    path = write_xlsx(tmp_path / "tb.xlsx", zoho_rows)
    url = f"sqlite:///{tmp_path / 'map.db'}"
    ingested = ingest_tb(path, client_code="T00", period="FY25-26", url=url)

    dict_only = map_engagement(ingested.engagement_id, url=url, encoder_kind="none")
    with_embed = map_engagement(ingested.engagement_id, url=url, encoder_kind="tfidf")

    assert with_embed.encoder == "tfidf"
    assert with_embed.resolved >= dict_only.resolved


def test_tune_thresholds_on_taxonomy_names(taxonomy):
    dev = [
        LabelledHead(raw_name=i.name, group=i.category, source="sap", gold=i.code)
        for i in taxonomy
    ]
    thresholds, report = tune_thresholds(dev, taxonomy=taxonomy, encoder_kind="tfidf", k=5)

    assert thresholds.encoder == "tfidf"
    assert 0.2 <= thresholds.tau_e <= 0.95
    assert thresholds.delta in (0.0, 0.01, 0.02, 0.05, 0.1)
    assert thresholds.k == 5
    assert report["dev_heads"] == len(dev)
    assert "embedding" in report


def test_tune_thresholds_heldout_mode(taxonomy):
    dev = [
        LabelledHead(raw_name=i.name, group=i.category, source="tally", gold=i.code)
        for i in taxonomy
    ]
    thresholds, report = tune_thresholds(
        dev, taxonomy=taxonomy, encoder_kind="tfidf", dict_mode="heldout"
    )
    assert report["dict_mode"] == "heldout"
    assert thresholds.dict_mode == "heldout"
