"""Comprehensive tests for GST Reconciliation (GSTR-2B vs Books, Section 16(2)(aa), Section 17(5))."""

from __future__ import annotations

import datetime
from decimal import Decimal
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from auditiq.api import create_app
from auditiq.cli import app as cli_app
from auditiq.gst import (
    GstInvoice,
    GstMatchRecord,
    GstReconReport,
    MatchStatus,
    RiskLevel,
    run_gst_recon_files,
    run_gst_recon_invoices,
)
from auditiq.gst.generator import generate_gst_dataset
from auditiq.gst.ingest import (
    auto_load_books_file,
    auto_load_portal_file,
    load_portal_gstr2b_csv,
    load_portal_gstr2b_excel,
)
from auditiq.gst.normalize import (
    detect_blocked_credit_17_5,
    normalize_gstin,
    normalize_invoice_number,
    parse_date_safe,
    parse_decimal_safe,
    validate_gstin,
)
from auditiq.gst.reconcile import reconcile_itc

GST_DATA_DIR = Path("data/GST")
OFFICIAL_B2B_CSV = GST_DATA_DIR / "Section_wise_CSV_files" / "GSTR2" / "b2b.csv"
OFFICIAL_GSTR2_XLSX = GST_DATA_DIR / "GSTR2_Excel_Workbook_TemplateNew_V1.1.xlsx"
GENERATED_BOOKS_XLSX = GST_DATA_DIR / "Tally_Purchase_Register_FY2023_24.xlsx"
GENERATED_BOOKS_CSV = GST_DATA_DIR / "Tally_Purchase_Register_FY2023_24.csv"
GENERATED_PORTAL_XLSX = GST_DATA_DIR / "GSTR2B_Portal_FY2023_24.xlsx"
GENERATED_PORTAL_CSV = GST_DATA_DIR / "GSTR2B_Portal_FY2023_24.csv"


# ── Normalization & Statutory Detection Tests ─────────────────────────────────


def test_normalize_gstin():
    assert normalize_gstin(" 27aaacb0446n1zt ") == "27AAACB0446N1ZT"
    assert normalize_gstin("27 AAAC B0446N 1ZT") == "27AAACB0446N1ZT"
    assert normalize_gstin(None) == ""


def test_validate_gstin():
    assert validate_gstin("27AAACB0446N1ZT") is True
    assert validate_gstin("29AAACI4798H1ZN") is True
    assert validate_gstin("INVALID_GSTIN") is False
    assert validate_gstin("12345") is False


def test_normalize_invoice_number():
    assert normalize_invoice_number("INV/2023-24/0042") == "INV20232442"
    assert normalize_invoice_number("0001001") == "1001"
    assert normalize_invoice_number("INV-0089") == "INV89"
    assert normalize_invoice_number("Bill # 452") == "BILL452"
    assert normalize_invoice_number("1001") == "1001"
    assert normalize_invoice_number(None) == ""


def test_parse_date_safe():
    assert parse_date_safe("12-Jul-17") == datetime.date(2017, 7, 12)
    assert parse_date_safe("15/04/2023") == datetime.date(2023, 4, 15)
    assert parse_date_safe("2023-04-15") == datetime.date(2023, 4, 15)
    assert parse_date_safe(datetime.date(2023, 4, 15)) == datetime.date(2023, 4, 15)
    assert parse_date_safe(None) is None
    assert parse_date_safe("-") is None


def test_parse_decimal_safe():
    assert parse_decimal_safe("1,00,000.50") == Decimal("100000.50")
    assert parse_decimal_safe(45000) == Decimal("45000")
    assert parse_decimal_safe(None) == Decimal("0.0")
    assert parse_decimal_safe("-") == Decimal("0.0")


def test_detect_blocked_credit_17_5():
    # Motor vehicle (17(5)(a))
    assert detect_blocked_credit_17_5("Executive car insurance premium") is not None
    # Catering (17(5)(b)(i))
    assert detect_blocked_credit_17_5("Annual corporate party catering dinner") is not None
    # Club (17(5)(b)(ii))
    assert detect_blocked_credit_17_5("Gym and fitness club membership") is not None
    # Explicit Ineligible flag
    assert detect_blocked_credit_17_5(eligibility="Ineligible") is not None
    # Eligible normal commercial expense
    assert detect_blocked_credit_17_5("Raw material purchase steel coil") is None


# ── Ingestion Tests ───────────────────────────────────────────────────────────


def test_ingest_official_gstn_b2b_csv():
    assert OFFICIAL_B2B_CSV.exists()
    invoices = load_portal_gstr2b_csv(OFFICIAL_B2B_CSV)
    assert len(invoices) == 5
    first = invoices[0]
    assert first.gstin == "08AAACG1395D1ZU"
    assert first.invoice_number == "1001"
    assert first.taxable_value == Decimal("90000")
    assert first.total_tax == Decimal("11500")  # 10800 IGST + 700 Cess
    assert first.blocked_reason is not None  # marked Ineligible in sample


def test_ingest_official_gstn_excel_template():
    assert OFFICIAL_GSTR2_XLSX.exists()
    invoices = load_portal_gstr2b_excel(OFFICIAL_GSTR2_XLSX)
    assert len(invoices) == 5
    assert invoices[0].gstin == "12GDDPS5160PDZR"
    assert invoices[0].invoice_number == "1001"
    assert invoices[0].taxable_value == Decimal("90000")


def test_auto_load_both_excel_and_csv():
    invs_xlsx = auto_load_books_file(GENERATED_BOOKS_XLSX)
    invs_csv = auto_load_books_file(GENERATED_BOOKS_CSV)
    assert len(invs_xlsx) == len(invs_csv)
    assert len(invs_xlsx) > 50


# ── Reconciliation Matching Engine Tests ──────────────────────────────────────


def test_exact_match_within_tolerance():
    b_inv = GstInvoice(
        source="books",
        gstin="27AAACB0446N1ZT",
        party_name="Blue Dart Express",
        invoice_number="INV/1001",
        invoice_number_norm="INV1001",
        invoice_date=datetime.date(2023, 5, 10),
        taxable_value=Decimal("100000.00"),
        igst=Decimal("18000.00"),
        total_tax=Decimal("18000.00"),
        invoice_value=Decimal("118000.00"),
    )
    # Portal has Rs 2 rounding difference (within Rs 5 tolerance)
    p_inv = GstInvoice(
        source="portal",
        gstin="27AAACB0446N1ZT",
        invoice_number="INV/1001",
        invoice_number_norm="INV1001",
        invoice_date=datetime.date(2023, 5, 10),
        taxable_value=Decimal("100002.00"),
        igst=Decimal("18000.00"),
        total_tax=Decimal("18000.00"),
        invoice_value=Decimal("118002.00"),
    )

    report = run_gst_recon_invoices([b_inv], [p_inv], tolerance=5.0)
    assert report.summary.exact_match_count == 1
    assert report.summary.value_mismatch_count == 0
    assert report.summary.itc_compliance_ratio == 100.0
    rec = report.records[0]
    assert rec.match_status == MatchStatus.EXACT_MATCH
    assert rec.risk_level == RiskLevel.LOW


def test_probable_match_fuzzy_invoice_number():
    # Books recorded as '1042', Portal recorded as 'INV/1042'
    b_inv = GstInvoice(
        source="books",
        gstin="20AAACT2727Q1ZW",
        party_name="Tata Steel",
        invoice_number="1042",
        invoice_number_norm="1042",
        invoice_date=datetime.date(2023, 6, 1),
        taxable_value=Decimal("200000.00"),
        igst=Decimal("36000.00"),
        total_tax=Decimal("36000.00"),
        invoice_value=Decimal("236000.00"),
    )
    p_inv = GstInvoice(
        source="portal",
        gstin="20AAACT2727Q1ZW",
        invoice_number="INV/1042",
        invoice_number_norm="INV1042",
        invoice_date=datetime.date(2023, 6, 2),
        taxable_value=Decimal("200000.00"),
        igst=Decimal("36000.00"),
        total_tax=Decimal("36000.00"),
        invoice_value=Decimal("236000.00"),
    )

    report = run_gst_recon_invoices([b_inv], [p_inv])
    assert report.summary.probable_match_count == 1
    rec = report.records[0]
    assert rec.match_status == MatchStatus.PROBABLE_MATCH
    assert rec.confidence_score >= 0.80


def test_value_mismatch_excess_claim():
    # Books entered Rs 50,000 tax, vendor only filed Rs 40,000
    b_inv = GstInvoice(
        source="books",
        gstin="27AAACL0149P1ZY",
        invoice_number="INV/200",
        invoice_number_norm="INV200",
        taxable_value=Decimal("500000.00"),
        igst=Decimal("90000.00"),
        total_tax=Decimal("90000.00"),
    )
    p_inv = GstInvoice(
        source="portal",
        gstin="27AAACL0149P1ZY",
        invoice_number="INV/200",
        invoice_number_norm="INV200",
        taxable_value=Decimal("400000.00"),
        igst=Decimal("72000.00"),
        total_tax=Decimal("72000.00"),
    )

    report = run_gst_recon_invoices([b_inv], [p_inv])
    assert report.summary.value_mismatch_count == 1
    rec = report.records[0]
    assert rec.match_status == MatchStatus.VALUE_MISMATCH
    assert rec.tax_difference == Decimal("18000.00")
    assert rec.risk_level == RiskLevel.HIGH


def test_books_only_section_16_2_aa_risk():
    # Vendor never filed return
    b_inv = GstInvoice(
        source="books",
        gstin="27AAACA0823H1ZW",
        party_name="Defaulting Vendor",
        invoice_number="INV/999",
        invoice_number_norm="INV999",
        taxable_value=Decimal("150000.00"),
        total_tax=Decimal("27000.00"),
    )

    report = run_gst_recon_invoices([b_inv], [])
    assert report.summary.books_only_count == 1
    assert report.summary.books_only_itc == Decimal("27000.00")
    rec = report.records[0]
    assert rec.match_status == MatchStatus.BOOKS_ONLY
    assert rec.risk_level == RiskLevel.CRITICAL
    assert "Section 16(2)(aa)" in rec.statutory_reference


def test_section_17_5_blocked_credit_identification():
    b_inv = GstInvoice(
        source="books",
        gstin="27AAACH2702H1Z1",
        party_name="Car Insurance Corp",
        invoice_number="CAR/01",
        invoice_number_norm="CAR1",
        taxable_value=Decimal("50000.00"),
        total_tax=Decimal("9000.00"),
        blocked_reason="Section 17(5)(a) - Motor vehicles and conveyances",
    )

    report = run_gst_recon_invoices([b_inv], [])
    assert report.summary.blocked_credit_count == 1
    assert report.summary.blocked_credit_itc == Decimal("9000.00")
    rec = report.records[0]
    assert rec.match_status == MatchStatus.BLOCKED_CREDIT
    assert rec.risk_level == RiskLevel.HIGH


def test_portal_only_unrecorded_purchase():
    p_inv = GstInvoice(
        source="portal",
        gstin="29AAACI4798H1ZN",
        invoice_number="INV/505",
        invoice_number_norm="INV505",
        taxable_value=Decimal("80000.00"),
        total_tax=Decimal("14400.00"),
    )

    report = run_gst_recon_invoices([], [p_inv])
    assert report.summary.portal_only_count == 1
    assert report.summary.portal_only_taxable == Decimal("80000.00")
    rec = report.records[0]
    assert rec.match_status == MatchStatus.PORTAL_ONLY
    assert rec.risk_level == RiskLevel.MEDIUM


# ── Full Dataset Execution Test ───────────────────────────────────────────────


def test_full_dataset_reconciliation():
    report = run_gst_recon_files(GENERATED_BOOKS_XLSX, GENERATED_PORTAL_XLSX)
    s = report.summary
    assert s.books_invoice_count > 50
    assert s.portal_invoice_count > 50
    assert s.exact_match_count > 30
    assert s.probable_match_count > 0
    assert s.value_mismatch_count > 0
    assert s.books_only_count > 0
    assert s.portal_only_count > 0
    assert s.blocked_credit_count > 0
    assert 50.0 <= s.itc_compliance_ratio <= 100.0

    # Serialization test
    d = report.to_dict()
    assert "report_id" in d
    assert "summary" in d
    assert "records" in d
    assert len(d["records"]) == len(report.records)


# ── CLI Commands Tests ────────────────────────────────────────────────────────


def test_cli_gst_recon_command():
    runner = CliRunner()
    result = runner.invoke(
        cli_app,
        [
            "gst",
            "recon",
            "--books",
            str(GENERATED_BOOKS_XLSX),
            "--portal",
            str(GENERATED_PORTAL_XLSX),
        ],
    )
    assert result.exit_code == 0
    assert "GST Reconciliation" in result.stdout
    assert "ITC Compliance Ratio:" in result.stdout
    assert "Exact Matches:" in result.stdout
    assert "Books Only (S.16(2)):" in result.stdout


def test_cli_gst_inspect_command():
    runner = CliRunner()
    result = runner.invoke(
        cli_app,
        ["gst", "inspect", str(OFFICIAL_B2B_CSV), "--source", "portal"],
    )
    assert result.exit_code == 0
    assert "GST File Inspection -- b2b.csv" in result.stdout
    assert "08AAACG1395D1ZU" in result.stdout


def test_cli_gst_generate_demo_command(tmp_path):
    runner = CliRunner()
    result = runner.invoke(
        cli_app,
        ["gst", "generate-demo", "--output-dir", str(tmp_path), "--invoices", "20"],
    )
    assert result.exit_code == 0
    assert (tmp_path / "Tally_Purchase_Register_FY2023_24.xlsx").exists()
    assert (tmp_path / "GSTR2B_Portal_FY2023_24.xlsx").exists()


# ── API Endpoint Tests ────────────────────────────────────────────────────────


def test_api_gst_recon_endpoint():
    client = TestClient(create_app())
    with open(GENERATED_BOOKS_CSV, "rb") as b_f, open(GENERATED_PORTAL_CSV, "rb") as p_f:
        resp = client.post(
            "/api/gst/recon",
            files={
                "books_file": ("books.csv", b_f, "text/csv"),
                "portal_file": ("portal.csv", p_f, "text/csv"),
            },
            params={"tolerance": 5.0},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert "report_id" in data
    assert "summary" in data
    assert data["summary"]["exact_match_count"] > 30
    assert data["summary"]["itc_compliance_ratio"] > 50.0
    assert len(data["records"]) > 50
