"""The mapping review queue: list / resolve / reset / bulk + cache replay.

The queue closes the loop the cascade opens: pending_review rows (and lines with
no mapping row at all) are exposure; a reviewer resolution makes them (and every
line sharing the head) accepted, and re-running ``map`` replays the decision with
its provenance intact.
"""
from __future__ import annotations

import json

import pytest

from _recon_fixture import add_tb, seed_engagement

from auditiq.core import load_default_taxonomy
from auditiq.ingest.prepare import list_pending, reset_mapping, resolve_mapping
from auditiq.ingest.prepare import bulk_resolve
from auditiq.ingest.prepare import list_resolved
from auditiq.ingest.prepare.service import map_engagement
from auditiq.store import db, init_db, session_scope
from auditiq.store.models import Engagement, TbMapping


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Isolated SQLite store with one engagement and mixed mapping states."""
    url = f"sqlite:///{tmp_path / 'review.db'}"
    monkeypatch.setattr(db, "DATABASE_URL", url)
    monkeypatch.setattr(db, "_engine", None)
    monkeypatch.setattr(db, "_session_factory", None)
    init_db(url)

    with session_scope(url) as session:
        engagement = seed_engagement(session)
        add_tb(
            session,
            engagement,
            [
                {"name": "Sundry Debtors", "amount": 1000.0, "fsli": "AST_TR", "method": "dict"},
                {"name": "Mystery Payment", "amount": -250.0, "status": "pending_review", "method": "review"},
                {"name": "Mystery Payment", "amount": -750.0, "status": "pending_review", "method": "review"},
                {"name": "Unrecorded Ledger", "amount": 300.0, "status": "unmapped"},
            ],
        )
        engagement_id = engagement.id
    return url, engagement_id


def test_list_pending_groups_heads(env):
    url, engagement_id = env
    heads = list_pending(engagement_id)
    # The two Mystery Payment lines collapse into one head with summed exposure.
    names = [h.raw_name for h in heads]
    assert names == ["Mystery Payment", "Unrecorded Ledger"]  # largest exposure first
    mystery, unrecorded = heads
    assert mystery.abs_amount == 1000.0
    assert mystery.lines == 2
    assert mystery.status == "pending_review"
    assert unrecorded.abs_amount == 300.0
    assert unrecorded.lines == 1
    assert unrecorded.status == "unmapped"
    for head in heads:
        assert head.candidates == []


def test_resolve_applies_to_the_whole_head(env):
    url, engagement_id = env
    mystery = next(h for h in list_pending(engagement_id) if h.raw_name == "Mystery Payment")
    result = resolve_mapping(mystery.line_id, "AST_TR", reviewer="aman", url=url)

    assert result.fsli_code == "AST_TR"
    assert result.resolved_lines == 2
    heads = {h.raw_name for h in list_pending(engagement_id)}
    assert heads == {"Unrecorded Ledger"}

    with session_scope(url) as session:
        rows = (
            session.query(TbMapping)
            .filter(TbMapping.resolved_fsli == "AST_TR", TbMapping.status == "resolved")
            .all()
        )
        assert len(rows) == 2
        for row in rows:
            assert row.reviewer == "aman"
            assert row.resolved_at is not None


def test_resolve_unmapped_line_creates_the_mapping(env):
    url, engagement_id = env
    head = next(h for h in list_pending(engagement_id) if h.status == "unmapped")
    result = resolve_mapping(head.line_id, "AST_TR", url=url)
    assert result.resolved_lines == 1
    remaining = [h for h in list_pending(engagement_id)]
    assert [h.raw_name for h in remaining] == ["Mystery Payment"]
    with session_scope(url) as session:
        row = session.query(TbMapping).filter_by(line_id=head.line_id).one()
        assert row.status == "resolved"
        assert row.method == "review"


def test_reset_returns_head_to_queue(env):
    url, engagement_id = env
    mystery = next(h for h in list_pending(engagement_id) if h.raw_name == "Mystery Payment")
    resolve_mapping(mystery.line_id, "AST_TR", url=url)
    reset_mapping(mystery.line_id, url=url)

    heads = {h.raw_name: h.lines for h in list_pending(engagement_id)}
    assert heads == {"Mystery Payment": 2, "Unrecorded Ledger": 1}
    with session_scope(url) as session:
        rows = session.query(TbMapping).filter_by(status="pending_review").all()
        for row in rows:
            assert row.resolved_fsli is None
            assert row.reviewer is None


def test_resolve_rejects_unknown_fsli(env):
    url, engagement_id = env
    head = list_pending(engagement_id)[0]
    with pytest.raises(ValueError, match="unknown FSLI"):
        resolve_mapping(head.line_id, "NOT_A_CODE", url=url)


def test_resolve_rejects_empty_fsli(env):
    url, engagement_id = env
    head = list_pending(engagement_id)[0]
    with pytest.raises(ValueError, match="required"):
        resolve_mapping(head.line_id, "  ", url=url)


def test_resolve_unknown_line_fails(env):
    url, engagement_id = env
    with pytest.raises(ValueError, match="no trial-balance line"):
        resolve_mapping(99999, "AST_TR", url=url)


def test_bulk_resolve_reports_failures(env):
    url, engagement_id = env
    heads = {h.raw_name: h for h in list_pending(engagement_id)}
    results, failures = bulk_resolve(
        [
            (heads["Mystery Payment"].line_id, "AST_TR"),
            (heads["Unrecorded Ledger"].line_id, "NOT_A_CODE"),
        ],
        url=url,
    )
    assert len(results) == 1
    assert set(failures) == {heads["Unrecorded Ledger"].line_id}
    assert "unknown FSLI" in failures[heads["Unrecorded Ledger"].line_id]
    assert {h.raw_name for h in list_pending(engagement_id)} == {"Unrecorded Ledger"}


def test_list_resolved_audit_trail(env):
    url, engagement_id = env
    mystery = next(h for h in list_pending(engagement_id) if h.raw_name == "Mystery Payment")
    resolve_mapping(mystery.line_id, "AST_TR", reviewer="aman", url=url)
    resolved = list_resolved(engagement_id, url=url)
    assert len(resolved) == 1
    assert resolved[0].raw_name == "Mystery Payment"
    assert resolved[0].lines == 2
    assert resolved[0].candidates == ["AST_TR"]


def test_remap_replays_resolved_provenance(env):
    """A re-run of `map` must not downgrade reviewer decisions to auto."""
    url, engagement_id = env
    head = list_pending(engagement_id)[0]
    resolve_mapping(head.line_id, "AST_TR", reviewer="aman", url=url)

    summary = map_engagement(engagement_id, url=url, encoder_kind="none")
    assert summary.lines == 4
    assert summary.resolved == 3  # dict 1 + cache replay of the resolved head (2 lines)

    with session_scope(url) as session:
        resolved = session.query(TbMapping).filter_by(status="resolved").all()
        # Both lines of the approved head replay from the cache, provenance intact.
        assert len(resolved) == 2
        assert all(row.resolved_fsli == "AST_TR" for row in resolved)
        assert all(row.reviewer == "aman" for row in resolved)
        assert all(row.method == "cache" for row in resolved)
        auto = session.query(TbMapping).filter_by(status="auto").all()
        assert len(auto) == 1
        pending = session.query(TbMapping).filter_by(status="pending_review").all()
        assert len(pending) == 1


def test_map_persists_candidates_for_review(env, monkeypatch):
    """Heads the cascade cannot accept keep their embedding shortlist on disk."""
    if not _sku_available():
        pytest.skip("scikit-learn not installed")
    url, engagement_id = env
    with session_scope(url) as session:
        engagement = session.get(Engagement, engagement_id)
        add_tb(
            session,
            engagement,
            [
                {"name": "Blorp Zeppelin Trust Fund 9000", "amount": 111.0, "status": "unmapped"},
            ],
        )
    summary = map_engagement(engagement_id, url=url, encoder_kind="tfidf")
    assert summary.review >= 1

    with session_scope(url) as session:
        rows = session.query(TbMapping).filter(TbMapping.status == "pending_review").all()
        payloads = [r for r in rows if r.candidates_json]
        assert payloads, "expected a pending mapping with persisted candidates"
        payload = json.loads(payloads[0].candidates_json)
        assert payload["codes"], "candidate codes must be non-empty"
        assert payload["embed_score"] > 0.0


# -- helpers ---------------------------------------------------------------

def _sku_available() -> bool:
    try:
        import sklearn  # noqa: F401
        return True
    except Exception:
        return False
