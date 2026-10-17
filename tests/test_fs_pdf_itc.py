"""Extraction smoke test against the real published ITC report.

The report lives in the legacy FRA checkout, which is gitignored in this repo, so
the test skips when it is absent. This checks extraction sanity — metadata
detection, statement segmentation and face-row extraction — not a tie-out.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("pymupdf")

from auditiq.ingest.fs.pdf.reader import PdfFsReader  # noqa: E402
from auditiq.ingest.fs.statements import extract_statements  # noqa: E402

PDF = (
    Path(__file__).resolve().parents[1]
    / "Financial_Report_Analysis_Agent"
    / "itc-r-and-a-consolidated-fin-statements-2026.pdf"
)


@pytest.mark.skipif(not PDF.exists(), reason="legacy ITC report PDF not present")
def test_itc_report_extraction_sanity():
    document = PdfFsReader(max_pages=6, extract_tables=False).read(PDF)

    assert document.company == "ITC Limited"
    assert document.period == "FY25-26"
    assert document.unit == "crores"
    assert document.basis == "Consolidated"

    statements = extract_statements(document)
    assert "bs" in statements and "pl" in statements

    bs_labels = {row.label for row in statements["bs"]}
    assert "Property, Plant and Equipment" in bs_labels
    assert "Trade receivables" in bs_labels
    assert any(row.is_subtotal for row in statements["bs"])
    assert any(row.is_subtotal for row in statements["pl"])
