"""Tests for FS-label -> FSLI labelling via the shared cascade."""
from __future__ import annotations

from auditiq.ingest.fs.base import CachedLabel, FsRow
from auditiq.ingest.fs.labels import build_fs_mapper, label_row, label_rows, summarise
from auditiq.ingest.prepare.aliases import load_alias
from auditiq.ingest.prepare.normalize import nu


def test_every_taxonomy_name_resolves_uniquely(taxonomy):
    alias = load_alias(taxonomy=taxonomy)
    unresolved = [item.name for item in taxonomy if not alias.resolves_uniquely(item.name)]
    assert unresolved == []


def test_alias_dictionary_has_no_ambiguous_keys(taxonomy):
    alias = load_alias(taxonomy=taxonomy)
    # Every key must resolve to exactly one code (multi-code entries defeat the
    # unique-resolution rule of the cascade).
    ambiguous = {name: codes for name, codes in alias._map.items() if len(codes) > 1}
    assert ambiguous == {}


def test_label_row_uses_dictionary(taxonomy):
    mapper, _cfg, kind, _tuned = build_fs_mapper(taxonomy=taxonomy, encoder_kind="none")
    assert kind == "none"
    row = FsRow(label="Trade Receivables", current=100.0)
    labelled = label_row(row, mapper, statement="bs")
    assert labelled.fsli_code == "AST_TR"
    assert labelled.layer == "dict"


def test_label_rows_and_summary(taxonomy):
    mapper, _cfg, kind, tuned = build_fs_mapper(taxonomy=taxonomy, encoder_kind="none")
    rows = {
        "bs": [
            FsRow(label="Share Capital", current=500.0),
            FsRow(label="Total Assets", current=500.0, is_subtotal=True),
        ],
        "pl": [FsRow(label="Finance Costs", current=20.0)],
    }
    labelled = label_rows(rows, mapper, client="T00")
    codes = {item.row.label: item.fsli_code for item in labelled}
    assert codes["Share Capital"] == "EQ_SC"
    assert codes["Finance Costs"] == "EXP_FIN"
    assert codes["Total Assets"] is None  # subtotal label, not in the dictionary

    summary = summarise(labelled, kind, tuned)
    assert summary.rows == 3
    assert summary.mapped == 2
    assert summary.unmapped == 1
    assert summary.by_layer["dict"] == 2


def test_cache_precedes_dictionary(taxonomy):
    """A reviewer decision beats the deterministic dictionary."""
    mapper, _cfg, _kind, _tuned = build_fs_mapper(taxonomy=taxonomy, encoder_kind="none")
    rows = {"bs": [FsRow(label="Trade Receivables", current=100.0)]}
    cache = {("bs", nu("Trade Receivables")): CachedLabel(fsli_code="AST_INV")}

    labelled = label_rows(rows, mapper, client="T00", cache=cache)

    assert labelled[0].fsli_code == "AST_INV"
    assert labelled[0].layer == "cache"


def test_cache_can_carry_a_presentation_group(taxonomy):
    """Reviewers may tie a face line out as a group, so the cache must too."""
    mapper, _cfg, _kind, _tuned = build_fs_mapper(taxonomy=taxonomy, encoder_kind="none")
    rows = {"pl": [FsRow(label="Revenue from Operations", current=100.0)]}
    cache = {
        ("pl", nu("Revenue from Operations")): CachedLabel(group_code="REV_OPERATIONS")
    }

    labelled = label_rows(rows, mapper, client="T00", cache=cache)

    assert labelled[0].group_code == "REV_OPERATIONS"
    assert labelled[0].fsli_code is None
    assert labelled[0].layer == "cache"


def test_cache_is_disabled_when_the_layer_is_off(taxonomy):
    mapper, _cfg, _kind, _tuned = build_fs_mapper(taxonomy=taxonomy, encoder_kind="none")
    rows = {"bs": [FsRow(label="Trade Receivables", current=100.0)]}
    cache = {("bs", nu("Trade Receivables")): CachedLabel(fsli_code="AST_INV")}

    labelled = label_rows(rows, mapper, client="T00", cache=cache, layers=("dict",))

    assert labelled[0].fsli_code == "AST_TR"
    assert labelled[0].layer == "dict"


def test_mapper_accepts_an_optional_llm(taxonomy):
    llm = object()
    mapper, _cfg, _kind, _tuned = build_fs_mapper(
        taxonomy=taxonomy, encoder_kind="none", llm=llm
    )
    assert mapper.llm is llm
