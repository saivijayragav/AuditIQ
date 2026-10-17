"""Tests for the committed Schedule III FSLI taxonomy."""
from __future__ import annotations

from auditiq.core import load_default_taxonomy


def test_taxonomy_loads(taxonomy):
    assert len(taxonomy) > 30
    assert "EQ_SC" in taxonomy


def test_taxonomy_fields():
    tax = load_default_taxonomy()
    share_capital = tax.get("EQ_SC")
    assert share_capital is not None
    assert share_capital.name == "Share Capital"
    assert share_capital.statement == "Balance Sheet"
    assert share_capital.category == "Equity"
    assert share_capital.is_debit is False


def test_by_statement_filtering(taxonomy):
    balance_sheet = taxonomy.by_statement("Balance Sheet")
    assert balance_sheet
    assert all(i.statement == "Balance Sheet" for i in balance_sheet)


def test_name_lookup_and_missing(taxonomy):
    assert taxonomy.name("AST_TR")
    assert taxonomy.get("DOES_NOT_EXIST") is None
