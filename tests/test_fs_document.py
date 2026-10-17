"""Tests for PDF metadata detection (no PDF dependency required)."""
from __future__ import annotations

from auditiq.ingest.fs.pdf.document import (
    detect_basis,
    detect_company,
    detect_period,
    detect_unit_from,
)


def test_detect_company():
    text = "XYZ Industries Limited\nStandalone Financial Statements"
    assert detect_company(text) == "XYZ Industries Limited"


def test_detect_company_absent():
    assert detect_company("Balance Sheet as at") == ""


def test_detect_period_from_date():
    assert detect_period("Balance Sheet as at 31 March 2026") == "FY25-26"


def test_detect_period_from_range():
    assert detect_period("for the year 2025-26") == "FY25-26"


def test_detect_period_none():
    assert detect_period("nothing to see") is None


def test_detect_basis():
    assert detect_basis("Consolidated financial statements") == "Consolidated"
    assert detect_basis("Standalone Balance Sheet") == "Standalone"
    assert detect_basis("Financial statements") == ""


def test_detect_unit():
    assert detect_unit_from("(Amount in Rs. lakhs)") == "lakhs"
    assert detect_unit_from("(Rs. in crores)") == "crores"
    assert detect_unit_from("(Amount in Rs.)") == "absolute"
    assert detect_unit_from("no unit mentioned") == "absolute"
