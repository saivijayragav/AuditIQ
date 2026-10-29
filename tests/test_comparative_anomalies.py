from pathlib import Path
import pytest
from auditiq.copilot.anomalies import detect_horizontal_anomalies
from auditiq.copilot.service import handle_document_upload
from auditiq.copilot.sql_store import get_records_by_session

MOCK_FILE = Path("data/exports/SAP_Comparative_Trial_Balance_2Year_FY23_FY24.xlsx")


def test_detect_horizontal_anomalies_materiality():
    records = [
        {
            "id": 1,
            "page_number": 1,
            "block_id": "sap-431050",
            "section": "Schedule III • EXP_OTHER",
            "line_item": "SAP #431050: Repairs & Maintenance - Machinery",
            "amount": 10000.0,
            "prior_amount": 88000.0,
            "raw_text": "Repairs & Maintenance - Machinery (431050)",
        },
        {
            "id": 2,
            "page_number": 1,
            "block_id": "sap-442010",
            "section": "Schedule III • EXP_OTHER",
            "line_item": "SAP #442010: Legal & Professional Advisory",
            "amount": 580000.0,
            "prior_amount": 45000.0,
            "raw_text": "Legal & Professional Advisory (442010)",
        },
        {
            "id": 3,
            "page_number": 1,
            "block_id": "sap-451020",
            "section": "Schedule III • EXP_OTHER",
            "line_item": "SAP #451020: Trade Fair & Global Exhibition",
            "amount": 0.0,
            "prior_amount": 150000.0,
            "raw_text": "Trade Fair & Global Exhibition (451020)",
        },
        {
            "id": 4,
            "page_number": 1,
            "block_id": "sap-463080",
            "section": "Schedule III • EXP_OTHER",
            "line_item": "SAP #463080: Cloud ERP Implementation",
            "amount": 420000.0,
            "prior_amount": 0.0,
            "raw_text": "Cloud ERP Implementation (463080)",
        },
        {
            "id": 5,
            "page_number": 1,
            "block_id": "sap-111000",
            "section": "Schedule III • AST_PPE",
            "line_item": "SAP #111000: Land & Freehold Site",
            "amount": 2500000.0,
            "prior_amount": 2500000.0,
            "raw_text": "Land (111000)",
        },
    ]

    # Test standard 30% materiality
    rep_30 = detect_horizontal_anomalies(records, critical_swing_pct=30.0)
    assert rep_30.summary.total_comparative_items == 4
    assert rep_30.summary.critical_count == 3  # Repairs drop, Legal spike, Trade fair vanished
    
    repairs_finding = next(f for f in rep_30.findings if "431050" in f.line_item)
    assert repairs_finding.anomaly_type == "CRITICAL_DROP"
    assert repairs_finding.severity == "CRITICAL"
    assert repairs_finding.variance == -78000.0
    assert round(repairs_finding.pct_change, 1) == -88.6


@pytest.mark.skipif(not MOCK_FILE.exists(), reason="Mock SAP comparative file not present")
def test_sap_comparative_excel_ingestion():
    file_bytes = MOCK_FILE.read_bytes()
    session = handle_document_upload(
        file_bytes=file_bytes,
        file_name=MOCK_FILE.name,
        session_id="test_sap_comp_pytest",
    )
    assert session.summary.get("is_trial_balance") is True
    assert session.summary.get("is_comparative") is True
    assert session.summary.get("balanced") is True

    records = get_records_by_session(session.session_id)
    assert len(records) == 27

    repairs = next(r for r in records if "431050" in r["line_item"])
    assert repairs["amount"] == 10000.0
    assert repairs["prior_amount"] == 88000.0

