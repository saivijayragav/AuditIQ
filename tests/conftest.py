"""Shared pytest fixtures."""
from __future__ import annotations

import pytest
from openpyxl import Workbook

from auditiq.core import load_default_taxonomy


@pytest.fixture(scope="session")
def taxonomy():
    return load_default_taxonomy()


@pytest.fixture
def write_xlsx():
    """Return a helper that writes ``rows`` to an .xlsx file and returns the path."""

    def _write(path, rows):
        workbook = Workbook()
        sheet = workbook.active
        for row in rows:
            sheet.append(list(row))
        workbook.save(path)
        return path

    return _write


@pytest.fixture
def tally_rows():
    return [
        ["Test Co Ltd"],
        ["Trial Balance"],
        ["As at 31-Mar-2026"],
        ["Particulars", "Debit", "Credit"],
        ["Capital Account", None, 500],
        ["    Share Capital", None, 500],
        ["Current Assets", 500, None],
        ["    Sundry Debtors", 500, None],
        ["Grand Total", 500, 500],
    ]


@pytest.fixture
def sap_rows():
    return [
        ["Test Co Ltd"],
        ["G/L Account", "G/L Acct Long Text", "Debit", "Credit"],
        ["10001", "Sundry Debtors", 500, None],
        ["20001", "Share Capital", None, 500],
        ["Total", None, 500, 500],
    ]


@pytest.fixture
def zoho_rows():
    return [
        ["Test Co Ltd"],
        ["Account", "Account Code", "Account Type", "Debit", "Credit"],
        ["Sundry Debtors", "1200", "Other Current Asset", 500, None],
        ["Share Capital", "3000", "Equity", None, 500],
        ["Total", None, None, 500, 500],
    ]


@pytest.fixture
def generic_rows():
    return [
        ["Ledger Name", "Code", "Debit", "Credit"],
        ["Sundry Debtors", "1200", 500, None],
        ["Share Capital", "3000", None, 500],
        ["Total", None, 500, 500],
    ]
