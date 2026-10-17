"""End-to-end reconciliation tests against a directly-seeded store.

Side A is a mapped trial balance and Side B a draft financial statement, both
written straight into the tables so the figures are exact.
"""
from __future__ import annotations

import pytest

from _recon_fixture import add_fs_lines, add_tb, seed_engagement, sign

from auditiq.core import load_default_taxonomy
from auditiq.reconciliation import (
    MaterialityError,
    explain_unit,
    latest_run,
    run_recon,
    set_materiality,
    suggest_for_engagement,
)
from auditiq.store import init_db, session_scope
from auditiq.store.models import ExceptionRecord

# A balanced Schedule III slice: assets = equity + liabilities and the P&L is
# self-funding (profit is zero), so a clean tie-out needs no explanations.
BASE = {
    "AST_PPE": 4000.0,
    "AST_TR": 1000.0,
    "AST_CASH": 500.0,
    "EQ_SC": 3000.0,
    "EQ_RS": 1500.0,
    "LIA_TP": 1000.0,
    "INC_REV_SALES": 2000.0,
    "EXP_MAT": 1200.0,
    "EXP_EMP": 600.0,
    "EXP_OTH": 200.0,
}

MATERIALITY = 100_000.0


def _url(tmp_path) -> str:
    return f"sqlite:///{tmp_path / 'recon.db'}"


def _seed(
    url,
    *,
    tb_presented=None,
    fs_presented=None,
    fs_rows=None,
    tb_extra=None,
    materiality=None,
):
    taxonomy = load_default_taxonomy()
    tb_presented = tb_presented if tb_presented is not None else BASE
    init_db(url)
    with session_scope(url) as session:
        engagement = seed_engagement(session)
        specs = [
            {"name": taxonomy.name(code), "amount": sign(taxonomy, code) * value, "fsli": code}
            for code, value in tb_presented.items()
        ]
        if tb_extra:
            specs += tb_extra
        add_tb(session, engagement, specs)

        if fs_rows is None:
            source = fs_presented if fs_presented is not None else tb_presented
            fs_rows = [
                {"label": taxonomy.name(code), "value": value, "fsli": code}
                for code, value in source.items()
            ]
        add_fs_lines(session, engagement, fs_rows)
        if materiality is not None:
            engagement.materiality_value = materiality
        return engagement.id


def _lines(url, engagement_id):
    run, lines = latest_run(engagement_id, url)
    return run, {line.unit_code: line for line in lines}


def test_clean_tieout(tmp_path):
    url = _url(tmp_path)
    engagement_id = _seed(url)

    summary = run_recon(engagement_id, url=url, materiality=MATERIALITY)

    assert summary.material == 0
    assert summary.watch == 0
    assert summary.minor == 0
    assert summary.tied == summary.units == len(BASE)
    assert summary.exposure_a_lines == 0
    assert summary.exposure_b_rows == 0
    assert summary.status == "clean"
    assert {f.severity for f in summary.findings} == {"none"}

    run, lines = _lines(url, engagement_id)
    assert run is not None and run.units_total == len(BASE)
    assert all(line.classification == "tied" for line in lines.values())
    with session_scope(url) as session:
        assert session.query(ExceptionRecord).count() == 0


def test_rounding_only_is_ignorable(tmp_path):
    url = _url(tmp_path)
    fs = dict(BASE, AST_TR=1000.0025)  # half the absolute-rupee tolerance
    engagement_id = _seed(url, fs_presented=fs)

    summary = run_recon(engagement_id, url=url, materiality=MATERIALITY)

    assert summary.material == 0
    assert summary.rounding == 1
    _, lines = _lines(url, engagement_id)
    assert lines["AST_TR"].classification == "rounding"
    assert lines["AST_TR"].severity == "none"
    with session_scope(url) as session:
        assert session.query(ExceptionRecord).count() == 0


def test_material_difference_escalates_to_exception(tmp_path):
    url = _url(tmp_path)
    fs = dict(BASE, AST_TR=201_000.0)  # variance = 1,000 - 201,000 = -200,000
    engagement_id = _seed(url, fs_presented=fs)

    summary = run_recon(engagement_id, url=url, materiality=MATERIALITY)

    assert summary.material == 1
    assert summary.status == "material differences"
    _, lines = _lines(url, engagement_id)
    assert lines["AST_TR"].classification == "material"
    assert lines["AST_TR"].variance == -200_000.0
    with session_scope(url) as session:
        exceptions = session.query(ExceptionRecord).all()
        assert len(exceptions) == 1
        assert exceptions[0].kind == "tieout"
        assert exceptions[0].severity == "material"
        assert exceptions[0].amount == -200_000.0


def test_presentation_group_ties_out(tmp_path):
    url = _url(tmp_path)
    tb = {code: value for code, value in BASE.items() if code != "INC_REV_SALES"}
    tb.update({"INC_REV_SALES": 1200.0, "INC_REV_SERV": 500.0, "INC_REV_OTH": 300.0})

    taxonomy = load_default_taxonomy()
    fs_rows = [
        {"label": taxonomy.name(code), "value": value, "fsli": code}
        for code, value in tb.items()
        if not code.startswith("INC_REV")
    ]
    fs_rows.append({"label": "Revenue from Operations", "value": 2000.0, "group": "REV_OPERATIONS"})
    engagement_id = _seed(url, tb_presented=tb, fs_rows=fs_rows)

    summary = run_recon(engagement_id, url=url, materiality=MATERIALITY)

    assert summary.tied == summary.units
    _, lines = _lines(url, engagement_id)
    assert "REV_OPERATIONS" in lines
    group_line = lines["REV_OPERATIONS"]
    assert group_line.is_group is True
    assert group_line.side_a == 2000.0
    assert group_line.side_b == 2000.0
    assert group_line.classification == "tied"
    # Members are suppressed as separate units once the group is presented.
    assert "INC_REV_SALES" not in lines
    assert set(group_line.refs["members"]) == {"INC_REV_SALES", "INC_REV_SERV", "INC_REV_OTH"}


def test_group_variances_report(tmp_path):
    url = _url(tmp_path)
    tb = {code: value for code, value in BASE.items() if code != "INC_REV_SALES"}
    tb.update({"INC_REV_SALES": 1200.0, "INC_REV_SERV": 500.0, "INC_REV_OTH": 300.0})

    taxonomy = load_default_taxonomy()
    fs_rows = [
        {"label": taxonomy.name(code), "value": value, "fsli": code}
        for code, value in tb.items()
        if not code.startswith("INC_REV")
    ]
    fs_rows.append({"label": "Revenue from Operations", "value": 1900.0, "group": "REV_OPERATIONS"})
    engagement_id = _seed(url, tb_presented=tb, fs_rows=fs_rows)

    run_recon(engagement_id, url=url, materiality=MATERIALITY)
    _, lines = _lines(url, engagement_id)
    assert lines["REV_OPERATIONS"].variance == 100.0


def test_only_a_and_only_b_units(tmp_path):
    url = _url(tmp_path)
    tb = dict(BASE, AST_CI=300.0)  # books have it, statements do not
    fs = dict(BASE, AST_INTG=700.0)  # statements show it, books do not
    engagement_id = _seed(url, tb_presented=tb, fs_presented=fs)

    run_recon(engagement_id, url=url, materiality=MATERIALITY)
    _, lines = _lines(url, engagement_id)

    assert lines["AST_CI"].side_a == 300.0 and lines["AST_CI"].side_b == 0.0
    assert lines["AST_CI"].variance == 300.0
    assert lines["AST_INTG"].side_b == 700.0 and lines["AST_INTG"].side_a == 0.0
    assert lines["AST_INTG"].variance == -700.0


def test_unmapped_exposure_is_attributed(tmp_path):
    url = _url(tmp_path)
    engagement_id = _seed(
        url,
        tb_extra=[
            {
                "name": "Sundry Debtors Suspense",
                "amount": 250.0,
                "status": "pending_review",
                "method": "review",
            }
        ],
    )

    summary = run_recon(engagement_id, url=url, materiality=MATERIALITY)
    assert summary.exposure_a_lines == 1
    assert summary.exposure_a == 250.0

    _, line = explain_unit(engagement_id, "AST_TR", url)
    kinds = {c["kind"]: c for c in line.attribution["candidates"]}
    assert "unmapped_exposure" in kinds
    assert kinds["unmapped_exposure"]["amount"] == 250.0


def test_mirror_pair_is_a_reclass(tmp_path):
    url = _url(tmp_path)
    tb = dict(BASE, AST_TR=800.0, AST_STLA=200.0)  # 200 mis-booked to STLA
    fs = dict(BASE, AST_TR=1000.0, AST_STLA=0.0)
    engagement_id = _seed(url, tb_presented=tb, fs_presented=fs)

    run_recon(engagement_id, url=url, materiality=MATERIALITY)

    _, tr = explain_unit(engagement_id, "AST_TR", url)
    _, stla = explain_unit(engagement_id, "AST_STLA", url)
    assert tr.variance == -200.0 and stla.variance == 200.0
    tr_kinds = {c["kind"] for c in tr.attribution["candidates"]}
    stla_kinds = {c["kind"] for c in stla.attribution["candidates"]}
    assert "reclass_pair" in tr_kinds
    assert "reclass_pair" in stla_kinds


def test_current_year_result_explains_equity_variance(tmp_path):
    url = _url(tmp_path)
    # Profit of 200 is still in the P&L books, not yet closed to reserves.
    tb = dict(BASE, EQ_RS=1300.0, EXP_EMP=500.0, EXP_OTH=100.0)
    fs = dict(BASE, EQ_RS=1500.0, EXP_EMP=500.0, EXP_OTH=100.0)
    engagement_id = _seed(url, tb_presented=tb, fs_presented=fs)

    summary = run_recon(engagement_id, url=url, materiality=MATERIALITY)
    assert summary.material == 0

    _, equity = explain_unit(engagement_id, "EQ_RS", url)
    assert equity.variance == pytest.approx(-200.0)
    kinds = {c["kind"]: c for c in equity.attribution["candidates"]}
    assert "profit_offset" in kinds
    assert kinds["profit_offset"]["amount"] == -200.0


def test_materiality_is_required(tmp_path):
    url = _url(tmp_path)
    engagement_id = _seed(url)
    try:
        run_recon(engagement_id, url=url)
    except MaterialityError:
        pass
    else:  # pragma: no cover
        raise AssertionError("expected MaterialityError")


def test_engagement_materiality_is_used(tmp_path):
    url = _url(tmp_path)
    engagement_id = _seed(url)
    set_materiality(engagement_id, MATERIALITY, basis="0.5% of revenue", url=url)
    summary = run_recon(engagement_id, url=url)
    assert summary.materiality == MATERIALITY
    assert summary.materiality_basis == "0.5% of revenue"


def test_suggest_materiality_uses_revenue(tmp_path):
    url = _url(tmp_path)
    engagement_id = _seed(url)
    suggestion = suggest_for_engagement(engagement_id, url)
    assert suggestion["revenue"] == 2000.0
    assert suggestion["basis"] == "revenue"
    assert suggestion["suggested"] == 10.0  # 0.5%


def test_map_first_guard(tmp_path):
    url = _url(tmp_path)
    init_db(url)
    with session_scope(url) as session:
        engagement = seed_engagement(session)
        add_tb(
            session,
            engagement,
            [{"name": "Unknown Head", "amount": 100.0, "status": "unmapped"}],
        )
        engagement_id = engagement.id
    try:
        run_recon(engagement_id, url=url, materiality=MATERIALITY)
    except ValueError as exc:
        assert "map" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")


def test_no_draft_fs_guard(tmp_path):
    url = _url(tmp_path)
    init_db(url)
    with session_scope(url) as session:
        engagement = seed_engagement(session)
        taxonomy = load_default_taxonomy()
        add_tb(
            session,
            engagement,
            [
                {
                    "name": taxonomy.name("AST_TR"),
                    "amount": 100.0,
                    "fsli": "AST_TR",
                }
            ],
        )
        engagement_id = engagement.id
    try:
        run_recon(engagement_id, url=url, materiality=MATERIALITY)
    except ValueError as exc:
        assert "draft financial statements" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("expected ValueError")
