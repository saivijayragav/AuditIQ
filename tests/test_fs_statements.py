"""Tests for statement segmentation and face-line extraction (no PDF required)."""
from __future__ import annotations

from auditiq.ingest.fs.base import (
    MEASURE_SUBTOTAL,
    STATEMENT_BS,
    STATEMENT_NOTES,
    STATEMENT_PL,
    FsDocument,
    FsPage,
    FsTable,
)
from auditiq.ingest.fs.statements import (
    classify_page,
    extract_statements,
    row_from_line,
    rows_from_table,
    value_columns,
)


# --------------------------------------------------------------------------- #
# text-line extraction
# --------------------------------------------------------------------------- #
def test_row_from_line_with_note_current_and_prior():
    row = row_from_line("Trade Receivables  4  1,234.00  1,000.00", page=1)
    assert row is not None
    assert row.label == "Trade Receivables"
    assert row.note_ref == "4"
    assert row.current == 1234.0
    assert row.prior == 1000.0
    assert row.is_subtotal is False


def test_row_from_line_without_prior():
    row = row_from_line("Cash and Cash Equivalents  5,000.00", page=2)
    assert row is not None
    assert row.current == 5000.0
    assert row.prior is None


def test_row_from_line_marks_subtotal():
    row = row_from_line("Total Assets  10,000.00  9,000.00", page=1)
    assert row is not None
    assert row.is_subtotal is True
    assert row.measure == MEASURE_SUBTOTAL


def test_row_from_line_negative_parenthesis():
    row = row_from_line("Other Expenses  (100.00)  (90.00)", page=3)
    assert row is not None
    assert row.current == -100.0
    assert row.prior == -90.0


def test_row_from_line_skips_titles_and_headers():
    assert row_from_line("Balance Sheet as at 31 March 2026", page=1) is None
    assert row_from_line("Particulars  Note  Current  Prior", page=1) is None
    assert row_from_line("Statement of Profit and Loss", page=2) is None
    assert row_from_line("", page=1) is None


def test_row_from_line_strips_roman_and_bullets():
    row = row_from_line("(i) Inventories  2  1,000.00", page=1)
    assert row is not None
    assert row.label == "Inventories"


# --------------------------------------------------------------------------- #
# segmentation
# --------------------------------------------------------------------------- #
def test_classify_page_balance_sheet():
    page = FsPage(page=1, text="Balance Sheet as at 31 March 2026\nAssets\n")
    assert classify_page(page) == STATEMENT_BS


def test_classify_page_profit_and_loss():
    page = FsPage(
        page=2,
        text="Statement of Profit and Loss for the year ended 31 March 2026\nRevenue\n",
    )
    assert classify_page(page) == STATEMENT_PL


def test_classify_page_notes():
    page = FsPage(page=9, text="Notes to the financial statements\n1. Basis of preparation\n")
    assert classify_page(page) == STATEMENT_NOTES


def test_classify_page_unrelated():
    page = FsPage(page=4, text="Auditor's Report\nWe have audited the accompanying...\n")
    assert classify_page(page) is None


# --------------------------------------------------------------------------- #
# table column binding
# --------------------------------------------------------------------------- #
def test_value_columns_current_then_prior():
    headers = ["Particulars", "Note", "31 March 2026", "31 March 2025"]
    assert value_columns(headers, "FY25-26") == (2, 3)


def test_value_columns_prior_first_is_still_bound_by_year():
    headers = ["Particulars", "Note", "31 March 2025", "31 March 2026"]
    current, prior = value_columns(headers, "FY25-26")
    assert current == 3  # FY25-26 column, regardless of position
    assert prior == 2  # prior year column


def test_value_columns_fallback_without_years():
    assert value_columns(["Particulars", "Note", "Amount"], None) == (1, 2)


def test_rows_from_table():
    table = FsTable(
        headers=["Particulars", "Note", "31 March 2026", "31 March 2025"],
        rows=[
            ["Particulars", "Note", "31 March 2026", "31 March 2025"],
            ["Trade Receivables", "4", "1,234", "1,000"],
            ["Trade Payables", "8", "500", "400"],
        ],
    )
    rows = rows_from_table(table, "FY25-26")
    assert [r.label for r in rows] == ["Trade Receivables", "Trade Payables"]
    assert rows[0].current == 1234.0
    assert rows[0].prior == 1000.0


# --------------------------------------------------------------------------- #
# document-level extraction
# --------------------------------------------------------------------------- #
def test_extract_statements_end_to_end():
    pages = [
        FsPage(
            page=1,
            text=(
                "Balance Sheet as at 31 March 2026\n"
                "Assets\n"
                "Trade Receivables  4  1,234.00  1,000.00\n"
                "Total Assets  1,234.00  1,000.00\n"
            ),
        ),
        FsPage(
            page=2,
            text=(
                "Statement of Profit and Loss for the year ended 31 March 2026\n"
                "Revenue from Sale of Products  1  2,000.00  1,800.00\n"
            ),
        ),
    ]
    document = FsDocument(path="x.pdf", reader_kind="pdf", pages=pages)
    statements = extract_statements(document)

    assert set(statements) == {STATEMENT_BS, STATEMENT_PL}
    assert [r.label for r in statements[STATEMENT_BS]] == [
        "Trade Receivables",
        "Total Assets",
    ]
    assert document.statements[STATEMENT_PL][0].current == 2000.0
