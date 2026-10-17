"""Tests for unit detection / normalisation and amount parsing."""
from __future__ import annotations

from auditiq.core import detect_unit, normalize_unit, parse_amount, to_crores


def test_detect_unit():
    assert detect_unit("Figures in Rs. Crores") == "crores"
    assert detect_unit("All amounts in Lakhs") == "lakhs"
    assert detect_unit("in millions") == "millions"
    assert detect_unit("") == "absolute"


def test_normalize_unit():
    assert normalize_unit(None) == "absolute"
    assert normalize_unit("Crores") == "crores"
    assert normalize_unit("Rs.") == "absolute"


def test_to_crores():
    assert to_crores(1, "crores") == 1
    assert to_crores(100, "lakhs") == 1  # 100 lakh = 1 crore
    assert to_crores(10_000_000, "absolute") == 1
    assert to_crores(10, "millions") == 1


def test_parse_amount():
    assert parse_amount("1,234.5") == 1234.5
    assert parse_amount("(2,500)") == -2500.0
    assert parse_amount("-350") == -350.0
    assert parse_amount("₹ 1,00,000") == 100000.0
    assert parse_amount("nil") is None
    assert parse_amount("-") is None
    assert parse_amount("") is None
    assert parse_amount(None) is None
    assert parse_amount(42.0) == 42.0
