"""Tests for SA 520 analytical procedures and Schedule III ratio analysis."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from auditiq.analytics import (
    ABSOLUTE_BOUNDS,
    DEFAULT_MATERIAL_SWING,
    DEFAULT_SWING_THRESHOLD,
    SEVERITY_INFO,
    SEVERITY_MATERIAL,
    SEVERITY_WATCH,
    AnalyticalFinding,
    AnalyticalProcedureConfig,
    AnalyticalReport,
    RatioFamily,
    RATIO_BY_CODE,
    RATIO_DEFINITIONS,
    analyse,
    compute_ratios,
    run_analytics,
)
from auditiq.analytics.ratios import RatioResult, _safe_divide
from auditiq.api import create_app
from auditiq.cli import app as cli_app
from auditiq.store import init_db, session_scope
from auditiq.store.models import Engagement, FsLine, TbLine, TbMapping

try:
    from tests._recon_fixture import add_fs_lines, seed_engagement
except ImportError:
    # pyrefly: ignore[missing-import]
    from _recon_fixture import add_fs_lines, seed_engagement


# ── Ratio computation unit tests ──────────────────────────────────────────────


def test_safe_divide():
    assert _safe_divide(10.0, 2.0) == 5.0
    assert _safe_divide(10.0, 0.0) is None
    assert _safe_divide(0.0, 10.0) == 0.0
    assert _safe_divide(10.0, 1e-11) is None


def test_ratio_catalog_completeness():
    assert len(RATIO_DEFINITIONS) == 15
    statutory = [r for r in RATIO_DEFINITIONS if r.statutory]
    assert len(statutory) == 11
    assert "current_ratio" in RATIO_BY_CODE
    assert "debt_equity" in RATIO_BY_CODE
    assert "debt_service_coverage" in RATIO_BY_CODE
    assert "gross_profit_margin" in RATIO_BY_CODE
    assert "net_profit_margin" in RATIO_BY_CODE
    assert "return_on_equity" in RATIO_BY_CODE
    assert "return_on_capital_employed" in RATIO_BY_CODE
    assert "debtors_turnover" in RATIO_BY_CODE
    assert "inventory_turnover" in RATIO_BY_CODE
    assert "creditors_turnover" in RATIO_BY_CODE


def test_liquidity_ratios_computation():
    agg = {
        "AST_CASH": 200_000.0,
        "AST_TR": 300_000.0,
        "AST_INV": 500_000.0,
        "LIA_STB": 250_000.0,
        "LIA_TP": 250_000.0,
    }
    # Current Assets = 200k + 300k + 500k = 1,000,000
    # Current Liabilities = 250k + 250k = 500,000
    # Current Ratio = 1,000,000 / 500,000 = 2.0
    # Quick Assets = 1,000,000 - 500,000 = 500,000
    # Quick Ratio = 500,000 / 500,000 = 1.0
    results = {r.code: r for r in compute_ratios(agg)}

    cr = results["current_ratio"]
    assert cr.current == pytest.approx(2.0)
    assert cr.statutory is True

    qr = results["quick_ratio"]
    assert qr.current == pytest.approx(1.0)
    assert qr.statutory is False


def test_solvency_and_coverage_ratios():
    agg = {
        "EQ_SC": 500_000.0,
        "EQ_RS": 500_000.0,
        "LIA_LTB": 600_000.0,
        "LIA_STB": 400_000.0,
        "INC_REV_SALES": 2_000_000.0,
        "EXP_MAT": 1_000_000.0,
        "EXP_FIN": 100_000.0,
        "EXP_DEP": 50_000.0,
        "EXP_TAXC": 50_000.0,
    }
    # Equity = 1,000,000
    # Debt = 1,000,000 -> Debt/Equity = 1.0
    # Revenue = 2,000,000
    # Expenses = 1,000,000 + 100,000 + 50,000 = 1,150,000
    # Tax = 50,000
    # PAT = 2,000,000 - 1,150,000 - 50,000 = 800,000
    # EBIT = PAT + Tax + Finance = 800,000 + 50,000 + 100,000 = 950,000
    # Interest coverage = EBIT / Finance = 950,000 / 100,000 = 9.5
    results = {r.code: r for r in compute_ratios(agg)}

    de = results["debt_equity"]
    assert de.current == pytest.approx(1.0)

    ic = results["interest_coverage"]
    assert ic.current == pytest.approx(9.5)


def test_rev_operations_group_precedence():
    # If REV_OPERATIONS is provided (e.g. from presentation face)
    agg = {
        "REV_OPERATIONS": 5_000_000.0,
        "INC_REV_SALES": 5_000_000.0,  # simulate merged Side A without double-counting
        "EXP_MAT": 3_000_000.0,
    }
    results = {r.code: r for r in compute_ratios(agg)}
    gp = results["gross_profit_margin"]
    # (5m - 3m) / 5m * 100 = 40%
    assert gp.current == pytest.approx(40.0)


def test_yoy_comparison_and_swings():
    current_agg = {
        "AST_CASH": 100_000.0,
        "LIA_STB": 200_000.0,  # CR = 0.5
    }
    prior_agg = {
        "AST_CASH": 200_000.0,
        "LIA_STB": 200_000.0,  # CR = 1.0
    }
    results = {r.code: r for r in compute_ratios(current_agg, prior_agg)}
    cr = results["current_ratio"]
    assert cr.current == pytest.approx(0.5)
    assert cr.prior == pytest.approx(1.0)
    assert cr.change == pytest.approx(-0.5)
    assert cr.change_pct == pytest.approx(-50.0)


# ── Anomaly detection procedures tests ────────────────────────────────────────


def test_analyse_absolute_bound_violation():
    # Current ratio below 1.0 is a material liquidity violation
    current_agg = {"AST_CASH": 80_000.0, "LIA_STB": 100_000.0}
    ratios = compute_ratios(current_agg)
    findings = analyse(ratios)

    cr_findings = [f for f in findings if f.ratio_code == "current_ratio"]
    assert len(cr_findings) >= 1
    abs_f = [f for f in cr_findings if f.flag_type == "absolute"][0]
    assert abs_f.severity == SEVERITY_MATERIAL
    assert abs_f.current_value == pytest.approx(0.8)
    assert "below the safe threshold" in abs_f.message


def test_analyse_swing_severity_tiers():
    config = AnalyticalProcedureConfig(swing_threshold=15.0, material_swing=25.0)

    # 18% swing -> WATCH
    ratio_watch = RatioResult(
        definition=RATIO_BY_CODE["current_ratio"],
        current=1.18,
        prior=1.00,
        change=0.18,
        change_pct=18.0,
    )
    findings_watch = analyse([ratio_watch], config)
    swing_watch = [f for f in findings_watch if f.flag_type == "swing"]
    assert len(swing_watch) == 1
    assert swing_watch[0].severity == SEVERITY_WATCH

    # 30% swing -> MATERIAL
    ratio_mat = RatioResult(
        definition=RATIO_BY_CODE["current_ratio"],
        current=1.30,
        prior=1.00,
        change=0.30,
        change_pct=30.0,
    )
    findings_mat = analyse([ratio_mat], config)
    swing_mat = [f for f in findings_mat if f.flag_type == "swing"]
    assert len(swing_mat) == 1
    assert swing_mat[0].severity == SEVERITY_MATERIAL


def test_analyse_cross_check_debt_vs_interest_coverage():
    # Rising leverage + falling interest coverage
    de = RatioResult(
        definition=RATIO_BY_CODE["debt_equity"],
        current=2.5,
        prior=1.8,
        change=0.7,
        change_pct=38.8,
    )
    ic = RatioResult(
        definition=RATIO_BY_CODE["interest_coverage"],
        current=1.8,
        prior=2.5,
        change=-0.7,
        change_pct=-28.0,
    )
    findings = analyse([de, ic])
    cross = [f for f in findings if f.flag_type == "cross_check"]
    assert len(cross) >= 1
    assert any("SA 570" in f.message for f in cross)
    assert any(f.severity == SEVERITY_MATERIAL for f in cross)


def test_analytical_report_status_derivation():
    report_clean = AnalyticalReport(
        engagement_id=1, period="FY 2025-26", ratios=[], findings=[]
    )
    assert report_clean.status == "clean"

    report_watch = AnalyticalReport(
        engagement_id=1,
        period="FY 2025-26",
        ratios=[],
        findings=[
            AnalyticalFinding(
                ratio_code="cr",
                ratio_name="CR",
                family="liquidity",
                severity=SEVERITY_WATCH,
                flag_type="swing",
                message="watch item",
            )
        ],
    )
    assert report_watch.status == "watch items"

    report_mat = AnalyticalReport(
        engagement_id=1,
        period="FY 2025-26",
        ratios=[],
        findings=[
            AnalyticalFinding(
                ratio_code="cr",
                ratio_name="CR",
                family="liquidity",
                severity=SEVERITY_MATERIAL,
                flag_type="absolute",
                message="material item",
            )
        ],
    )
    assert report_mat.status == "material findings"


# ── Database & Service integration tests ──────────────────────────────────────


@pytest.fixture
def test_db_with_engagement(tmp_path):
    db_file = tmp_path / "test_analytics.db"
    url = f"sqlite:///{db_file}"
    init_db(url)

    with session_scope(url) as session:
        eng = seed_engagement(session, client_code="CLIENT_TEST", period="FY 2025-26", basis="Standalone")
        eng_id = eng.id

        # Current period (Side B)
        current_specs = [
            {"label": "Trade Receivables", "fsli": "AST_TR", "value": 400_000.0},
            {"label": "Inventories", "fsli": "AST_INV", "value": 200_000.0},
            {"label": "Cash and Cash Equivalents", "fsli": "AST_CASH", "value": 100_000.0},
            {"label": "Trade Payables", "fsli": "LIA_TP", "value": 350_000.0},
            {"label": "Short-term Borrowings", "fsli": "LIA_STB", "value": 150_000.0},
            {"label": "Revenue from Operations", "group": "REV_OPERATIONS", "value": 2_000_000.0},
            {"label": "Cost of Materials Consumed", "fsli": "EXP_MAT", "value": 1_200_000.0},
        ]
        add_fs_lines(session, eng, current_specs, period="FY 2025-26")

        # Prior period (Side B, is_current=False)
        prior_specs = [
            {"label": "Trade Receivables", "fsli": "AST_TR", "value": 300_000.0, "is_current": False, "period": "FY 2024-25"},
            {"label": "Cash and Cash Equivalents", "fsli": "AST_CASH", "value": 300_000.0, "is_current": False, "period": "FY 2024-25"},
            {"label": "Trade Payables", "fsli": "LIA_TP", "value": 300_000.0, "is_current": False, "period": "FY 2024-25"},
            {"label": "Revenue from Operations", "group": "REV_OPERATIONS", "value": 1_500_000.0, "is_current": False, "period": "FY 2024-25"},
        ]
        add_fs_lines(session, eng, prior_specs, period="FY 2024-25")

    return url, eng_id


def test_run_analytics_service(test_db_with_engagement):
    url, eng_id = test_db_with_engagement
    report = run_analytics(eng_id, url=url)

    assert report.engagement_id == eng_id
    assert report.client_code == "CLIENT_TEST"
    assert report.period == "FY 2025-26"
    assert report.has_prior is True
    assert report.computed_count > 0

    # Check that ratios include current_ratio
    by_code = {r.code: r for r in report.ratios}
    cr = by_code["current_ratio"]
    # CA = 400k (TR) + 200k (INV) + 100k (CASH) = 700k
    # CL = 350k (TP) + 150k (STB) = 500k
    # CR = 700k / 500k = 1.4
    assert cr.current == pytest.approx(1.4)
    # Prior: CA = 300k (TR) + 300k (CASH) = 600k, CL = 300k -> 2.0
    assert cr.prior == pytest.approx(2.0)
    assert cr.change_pct == pytest.approx(-30.0)

    # Check to_dict serialization
    d = report.to_dict()
    assert d["engagement_id"] == eng_id
    assert "ratios" in d
    assert "findings" in d


def test_run_analytics_not_found(test_db_with_engagement):
    url, _ = test_db_with_engagement
    with pytest.raises(ValueError, match="no engagement with id 99999"):
        run_analytics(99999, url=url)


# ── CLI & API route tests ─────────────────────────────────────────────────────


def test_cli_analytics_catalog():
    runner = CliRunner()
    result = runner.invoke(cli_app, ["analytics", "catalog", "--statutory-only"])
    assert result.exit_code == 0
    assert "AuditIQ Ratio Catalogue (11 ratios)" in result.stdout
    assert "current_ratio" in result.stdout
    assert "debt_equity" in result.stdout


def test_cli_analytics_run(test_db_with_engagement, monkeypatch):
    url, eng_id = test_db_with_engagement
    from auditiq import settings
    monkeypatch.setattr(settings, "DATABASE_URL", url)

    runner = CliRunner()
    result = runner.invoke(cli_app, ["analytics", "run", "-e", str(eng_id)])
    assert result.exit_code == 0
    assert "SA 520 Analytical Procedures" in result.stdout
    assert "CLIENT_TEST" in result.stdout

    # JSON output test
    result_json = runner.invoke(cli_app, ["analytics", "run", "-e", str(eng_id), "--json"])
    assert result_json.exit_code == 0
    import json
    data = json.loads(result_json.stdout)
    assert data["engagement_id"] == eng_id
    assert "ratios" in data


def test_api_analytics_endpoint(test_db_with_engagement, monkeypatch):
    url, eng_id = test_db_with_engagement
    from auditiq import settings
    from auditiq.store import db
    monkeypatch.setattr(settings, "DATABASE_URL", url)
    monkeypatch.setattr(db, "_engine", None)
    monkeypatch.setattr(db, "_session_factory", None)

    client = TestClient(create_app())
    resp = client.get(f"/api/engagements/{eng_id}/analytics")
    assert resp.status_code == 200
    data = resp.json()
    assert data["engagement_id"] == eng_id
    assert data["client_code"] == "CLIENT_TEST"
    assert data["period"] == "FY 2025-26"
    assert len(data["ratios"]) == 15
    assert data["has_prior"] is True

    # Test non-existent engagement returns 404
    resp_404 = client.get("/api/engagements/999999/analytics")
    assert resp_404.status_code == 404
    err = resp_404.json()
    assert err["error"]["code"] == "not_found"
