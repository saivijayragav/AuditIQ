"""Tests for the financial-statement reader registry."""
from __future__ import annotations

import pytest

from auditiq.ingest.fs import detect_reader, get_reader, reader_kinds
from auditiq.ingest.fs.excel import ExcelFsReader


def test_reader_kinds_include_pdf_and_excel():
    assert set(reader_kinds()) == {"excel", "pdf"}


@pytest.mark.parametrize(
    ("name", "kind"),
    [("fs.pdf", "pdf"), ("fs.xlsx", "excel"), ("fs.csv", "excel"), ("fs.xlsm", "excel")],
)
def test_detect_reader_by_suffix(name, kind):
    assert detect_reader(name) == kind


def test_detect_reader_explicit_kind_wins():
    assert detect_reader("fs.pdf", kind="pdf") == "pdf"


def test_detect_reader_unknown_suffix():
    with pytest.raises(ValueError):
        detect_reader("fs.docx")


def test_get_reader_unknown_kind():
    with pytest.raises(ValueError):
        get_reader("docx")


def test_excel_reader_is_a_declared_stub(tmp_path):
    path = tmp_path / "fs.xlsx"
    path.write_bytes(b"not really a workbook")
    reader = ExcelFsReader()
    assert reader.can_read(path)
    with pytest.raises(NotImplementedError):
        reader.read(path)
