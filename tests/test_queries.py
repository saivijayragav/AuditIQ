"""Engagement summary queries and exception disposition."""
from __future__ import annotations

import pytest

from _recon_fixture import add_fs_lines, add_tb, seed_engagement

from auditiq.store import db, init_db, session_scope
from auditiq.store.models import Engagement, ExceptionRecord
from auditiq.store.queries import (
    dispose_exception,
    engagement_summary,
    list_engagements,
    list_exceptions,
)


@pytest.fixture
def env(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'queries.db'}"
    monkeypatch.setattr(db, "DATABASE_URL", url)
    monkeypatch.setattr(db, "_engine", None)
    monkeypatch.setattr(db, "_session_factory", None)
    init_db(url)

    with session_scope(url) as session:
        engagement = seed_engagement(session, client_code="T01")
        add_tb(
            session,
            engagement,
            [
                {"name": "Sundry Debtors", "amount": 1000.0, "fsli": "AST_TR", "method": "dict"},
                {"name": "Mystery Payment", "amount": 250.0, "status": "pending_review", "method": "review"},
                {"name": "Unrecorded Ledger", "amount": 300.0, "status": "unmapped"},
            ],
        )
        add_fs_lines(
            session,
            engagement,
            [
                {"label": "Sundry Debtors", "value": 1000.0, "fsli": "AST_TR"},
                {"label": "Other Charges", "value": 120.0},
                {"label": "Other Charges", "value": 130.0, "period": "FY24-25", "is_current": False},
                {"label": "Total expenses", "value": 400.0, "fsli": "EXP_OTH", "is_subtotal": True},
            ],
        )
        session.add(
            ExceptionRecord(
                engagement_id=engagement.id,
                kind="tieout",
                fsli_code="AST_TR",
                severity="material",
                status="open",
                amount=999.0,
                note="AST_TR Trade receivables",
            )
        )
        engagement_id = engagement.id
    return url, engagement_id


def test_engagement_summary_counts(env):
    url, engagement_id = env
    summary = engagement_summary(engagement_id, url=url)
    assert summary.client_code == "T01"
    assert summary.period == "FY25-26"
    assert summary.tb_lines == 3
    assert summary.mappings == {"auto": 1, "pending_review": 1, "unmapped": 1}
    assert summary.resolved_lines == 1
    assert summary.pending_lines == 2
    assert summary.fs_lines == 4
    # "Other Charges" current + prior — both unmapped face rows.
    assert summary.fs_unmapped_rows == 2
    assert summary.fs_subtotals == 1
    assert summary.recon_status is None
    assert summary.open_exceptions == 1
    assert summary.intake_status == "in progress"


def test_list_engagements(env):
    url, engagement_id = env
    rows = list_engagements(url=url)
    assert [r.engagement_id for r in rows] == [engagement_id]
    assert rows[0].client_code == "T01"
    assert rows[0].resolved_lines == 1


def test_engagement_summary_unknown_id(env):
    url, _engagement_id = env
    with pytest.raises(ValueError, match="no engagement"):
        engagement_summary(9999, url=url)


def test_exception_list_and_dispose(env):
    url, engagement_id = env
    rows = list_exceptions(engagement_id, url=url)
    assert len(rows) == 1
    item = rows[0]
    assert item.exception_id == 1
    assert item.kind == "tieout"
    assert item.severity == "material"
    assert item.status == "open"
    assert item.fsli == "AST_TR"

    updated = dispose_exception(item.exception_id, "explained", note="timing difference", url=url)
    assert updated.status == "explained"
    assert updated.note == "timing difference"

    assert list_exceptions(engagement_id, status="open", url=url) == []
    assert len(list_exceptions(engagement_id, url=url)) == 1


def test_dispose_rejects_unknown_status(env):
    url, engagement_id = env
    with pytest.raises(ValueError, match="status"):
        dispose_exception(1, "closed", url=url)


def test_dispose_unknown_exception(env):
    url, engagement_id = env
    with pytest.raises(ValueError, match="no exception"):
        dispose_exception(9999, "accepted", url=url)
