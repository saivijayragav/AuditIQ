"""Tests for financial-year normalisation."""
from __future__ import annotations

from auditiq.core import normalize_fy, prior_fy


def test_normalize_fy_variants():
    assert normalize_fy("FY25-26") == "FY25-26"
    assert normalize_fy("2025-26") == "FY25-26"
    assert normalize_fy("FY2025-2026") == "FY25-26"
    assert normalize_fy("FY26") == "FY25-26"
    assert normalize_fy("31 March 2026") == "FY25-26"
    assert normalize_fy("As at 31st March 2026") == "FY25-26"


def test_normalize_fy_unknown():
    assert normalize_fy("Unknown FY") is None
    assert normalize_fy(None) is None


def test_prior_fy():
    assert prior_fy("FY25-26") == "FY24-25"
    assert prior_fy("2026-27") == "FY25-26"
    assert prior_fy("Unknown") is None
