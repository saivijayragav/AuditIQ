"""Tests for SA 240 / ISA 240 Journal Entry Testing (JET) and fraud risk detection."""
from __future__ import annotations

import datetime
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from auditiq.api import create_app
from auditiq.cli import app as cli_app
from auditiq.gl import (
    BenfordResult,
    JetFinding,
    JetReport,
    Voucher,
    VoucherLine,
    ingest_vouchers,
    run_jet_file,
    analyze_journal_entries,
)

DATA_DIR = Path(r"c:\Users\jaswa\Downloads\AuditIQ\data\General Ledger (for Journal Entry Testing)")
SAMPLE_XLSX = DATA_DIR / "Tally_Prime_Daybook_FY2023_24.xlsx"
SAMPLE_CSV = DATA_DIR / "Tally_Prime_Daybook_FY2023_24.csv"


# ── Ingestion & Model Tests ───────────────────────────────────────────────────


def test_ingest_tally_excel_vouchers():
    assert SAMPLE_XLSX.exists(), "Sample generated Tally Excel must exist"
    vouchers = ingest_vouchers(SAMPLE_XLSX)
    assert len(vouchers) > 1000
    first = vouchers[0]
    assert first.voucher_number == "1001"
    assert first.voucher_type == "Sales"
    assert first.date == datetime.date(2023, 4, 1)
    assert len(first.lines) == 4
    assert first.is_balanced


def test_ingest_tally_csv_vouchers():
    assert SAMPLE_CSV.exists(), "Sample generated Tally CSV must exist"
    vouchers = ingest_vouchers(SAMPLE_CSV)
    assert len(vouchers) > 1000
    first = vouchers[0]
    assert first.voucher_number == "1001"
    assert first.voucher_type == "Sales"
    assert len(first.lines) == 4
    assert first.is_balanced


def test_voucher_balance_property():
    balanced_v = Voucher(
        voucher_number="1",
        voucher_type="Journal",
        date=datetime.date(2023, 5, 1),
        lines=[
            VoucherLine("Office Rent", 50000.0, "Dr"),
            VoucherLine("Bank", 50000.0, "Cr"),
        ],
    )
    assert balanced_v.is_balanced
    assert balanced_v.amount == 50000.0

    unbalanced_v = Voucher(
        voucher_number="2",
        voucher_type="Journal",
        date=datetime.date(2023, 5, 1),
        lines=[
            VoucherLine("Office Rent", 50000.0, "Dr"),
            VoucherLine("Bank", 40000.0, "Cr"),
        ],
    )
    assert not unbalanced_v.is_balanced


# ── Rule Detection Unit Tests ────────────────────────────────────────────────


def test_weekend_posting_rule():
    sunday_v = Voucher(
        voucher_number="6099",
        voucher_type="Journal",
        date=datetime.date(2023, 10, 15),  # Sunday
        lines=[
            VoucherLine("Consultancy", 10000.0, "Dr"),
            VoucherLine("Cash", 10000.0, "Cr"),
        ],
    )
    report = analyze_journal_entries([sunday_v])
    weekend_findings = [f for f in report.findings if f.risk_rule == "weekend_posting"]
    assert len(weekend_findings) == 1
    assert weekend_findings[0].severity == "high"


def test_round_sum_rule():
    round_v = Voucher(
        voucher_number="6016",
        voucher_type="Journal",
        date=datetime.date(2023, 9, 30),
        lines=[
            VoucherLine("Legal Fees", 500000.0, "Dr"),
            VoucherLine("Bank", 500000.0, "Cr"),
        ],
    )
    report = analyze_journal_entries([round_v])
    round_findings = [f for f in report.findings if f.risk_rule == "round_sum"]
    assert len(round_findings) == 1
    assert round_findings[0].amount == 500000.0


def test_period_end_clustering_rule():
    fy_end = datetime.date(2024, 3, 31)
    period_end_v = Voucher(
        voucher_number="6020",
        voucher_type="Journal",
        date=datetime.date(2024, 3, 30),  # 1 day before FY end
        lines=[
            VoucherLine("Office Rent", 150000.0, "Dr"),
            VoucherLine("Reserves", 150000.0, "Cr"),
        ],
    )
    report = analyze_journal_entries([period_end_v], fy_end_date=fy_end)
    pe_findings = [f for f in report.findings if f.risk_rule == "period_end_clustering"]
    assert len(pe_findings) == 1
    assert pe_findings[0].severity == "high"


def test_suspicious_narration_rule():
    v1 = Voucher(
        voucher_number="6030",
        voucher_type="Journal",
        date=datetime.date(2023, 6, 1),
        narration="being dummy reversal as discussed with CFO",
        lines=[
            VoucherLine("Expense", 20000.0, "Dr"),
            VoucherLine("Bank", 20000.0, "Cr"),
        ],
    )
    v2_blank = Voucher(
        voucher_number="6031",
        voucher_type="Journal",
        date=datetime.date(2023, 6, 1),
        narration="",
        lines=[
            VoucherLine("Expense", 60000.0, "Dr"),
            VoucherLine("Bank", 60000.0, "Cr"),
        ],
    )
    report = analyze_journal_entries([v1, v2_blank])
    narr_findings = [f for f in report.findings if f.risk_rule == "suspicious_narration"]
    assert len(narr_findings) == 2


def test_unusual_ledger_pairing_rule():
    # Direct cash debit with sales credit
    cash_sales_v = Voucher(
        voucher_number="6036",
        voucher_type="Journal",
        date=datetime.date(2023, 8, 14),
        lines=[
            VoucherLine("Cash in Hand", 350000.0, "Dr"),
            VoucherLine("Sales - Domestic", 350000.0, "Cr"),
        ],
    )
    report = analyze_journal_entries([cash_sales_v])
    pairings = [f for f in report.findings if f.risk_rule == "unusual_pairing"]
    assert len(pairings) == 1
    assert "Cash with Sales" in pairings[0].message


def test_threshold_avoidance_rule():
    dt = datetime.date(2023, 6, 22)
    split_vouchers = [
        Voucher(
            voucher_number=str(4200 + i),
            voucher_type="Payment",
            date=dt,
            lines=[
                VoucherLine("Om Paper Products", 49500.0, "Dr"),
                VoucherLine("Petty Cash", 49500.0, "Cr"),
            ],
        )
        for i in range(4)
    ]
    report = analyze_journal_entries(split_vouchers)
    thresh = [f for f in report.findings if f.risk_rule == "threshold_avoidance"]
    assert len(thresh) == 1
    assert "Section 40A(3)" in thresh[0].message


def test_sequence_gap_rule():
    # Sequential series with gap: 101, 102, 103, 105 (missing 104)
    vouchers = [
        Voucher(
            voucher_number=str(num),
            voucher_type="Journal",
            date=datetime.date(2023, 5, 1),
            lines=[VoucherLine("A", 1000.0, "Dr"), VoucherLine("B", 1000.0, "Cr")],
        )
        for num in [101, 102, 103, 105, 106, 107, 108, 109, 110, 111, 112]
    ]
    report = analyze_journal_entries(vouchers)
    seq_findings = [f for f in report.findings if f.risk_rule == "sequence_gap"]
    assert len(seq_findings) == 1
    assert 104 in seq_findings[0].details["missing_numbers"]


# ── Full End-to-End Dataset Execution Test ────────────────────────────────────


def test_run_jet_file_full_dataset():
    report = run_jet_file(SAMPLE_XLSX)
    assert report.total_vouchers > 1000
    assert report.high_risk_count > 0
    assert report.status == "high risk"
    assert report.benford is not None
    assert len(report.findings) > 20

    # Serialization test
    d = report.to_dict()
    assert d["total_vouchers"] == report.total_vouchers
    assert "findings" in d
    assert "benford" in d


# ── CLI & API Tests ───────────────────────────────────────────────────────────


def test_cli_jet_test_command():
    runner = CliRunner()
    result = runner.invoke(cli_app, ["jet", "test", str(SAMPLE_XLSX), "--severity", "high"])
    assert result.exit_code == 0
    assert "SA 240 Journal Entry Testing" in result.stdout
    assert "FLAGGED AUDIT EXCEPTIONS" in result.stdout
    assert "[HIGH]" in result.stdout

    # JSON test
    res_json = runner.invoke(cli_app, ["jet", "test", str(SAMPLE_CSV), "--json"])
    assert res_json.exit_code == 0
    import json
    data = json.loads(res_json.stdout)
    assert "total_vouchers" in data
    assert "findings" in data


def test_cli_jet_benford_command():
    runner = CliRunner()
    result = runner.invoke(cli_app, ["jet", "benford", str(SAMPLE_XLSX)])
    assert result.exit_code == 0
    assert "Benford's Law First-Digit Analysis" in result.stdout
    assert "Chi-Square Statistic" in result.stdout


def test_api_jet_analyze_endpoint():
    client = TestClient(create_app())
    with open(SAMPLE_CSV, "rb") as f:
        resp = client.post(
            "/api/jet/analyze",
            files={"file": ("vouchers.csv", f, "text/csv")},
        )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_vouchers"] > 1000
    assert "findings" in data
    assert data["high_risk_count"] > 0
