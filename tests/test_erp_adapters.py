"""Tests for ERP trial-balance adapters and layout detection."""
from __future__ import annotations

from auditiq.ingest.erp import detect_source, read_records, read_with_source
from auditiq.ingest.erp.io import read_grid


def test_detect_tally(tally_rows):
    assert detect_source(tally_rows) == "tally"


def test_detect_sap(sap_rows):
    assert detect_source(sap_rows) == "sap"


def test_detect_zoho(zoho_rows):
    assert detect_source(zoho_rows) == "zoho"


def test_detect_generic(generic_rows):
    assert detect_source(generic_rows) == "generic"


def test_tally_adapter(tally_rows):
    records = read_records(tally_rows, "tally")
    by_name = {r.raw_name: r for r in records}

    # Group header rows are not counted as ledger lines.
    assert set(by_name) == {"Share Capital", "Sundry Debtors"}

    debtors = by_name["Sundry Debtors"]
    assert debtors.group == "Current Assets"
    assert debtors.amount == 500
    assert debtors.side == "Dr"

    capital = by_name["Share Capital"]
    assert capital.group == "Capital Account"
    assert capital.amount == -500
    assert capital.side == "Cr"


def test_sap_adapter(sap_rows):
    records = read_records(sap_rows, "sap")
    assert len(records) == 2
    by_code = {r.raw_code: r for r in records}
    assert by_code["10001"].raw_name == "Sundry Debtors"
    assert by_code["10001"].amount == 500
    assert by_code["20001"].amount == -500


def test_zoho_adapter(zoho_rows):
    records = read_records(zoho_rows, "zoho")
    assert len(records) == 2
    by_code = {r.raw_code: r for r in records}
    assert by_code["1200"].erp_acc_type == "Other Current Asset"
    assert by_code["1200"].group == "Other Current Asset"
    assert by_code["3000"].amount == -500


def test_generic_adapter(generic_rows):
    records = read_records(generic_rows, "generic")
    assert len(records) == 2
    by_name = {r.raw_name: r for r in records}
    assert by_name["Sundry Debtors"].raw_code == "1200"
    assert by_name["Sundry Debtors"].amount == 500
    assert by_name["Share Capital"].amount == -500


def test_read_with_source_xlsx_autodetect(tmp_path, write_xlsx, zoho_rows):
    path = write_xlsx(tmp_path / "tb.xlsx", zoho_rows)
    records, source = read_with_source(path)
    assert source == "zoho"
    assert len(records) == 2


def test_read_with_source_csv_autodetect(tmp_path, tally_rows):
    path = tmp_path / "tb.csv"
    lines = []
    for row in tally_rows:
        cells = ["" if c is None else str(c) for c in row]
        lines.append(",".join(cells))
    path.write_text("\n".join(lines), encoding="utf-8")

    grid = read_grid(path)
    assert detect_source(grid) == "tally"
    records, source = read_with_source(path, source=None)
    assert source == "tally"
    assert {r.raw_name for r in records} == {"Share Capital", "Sundry Debtors"}
