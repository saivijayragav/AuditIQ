"""CLI smoke tests for the review / fs-review / exceptions surface."""
from __future__ import annotations

import pytest
from typer.testing import CliRunner

from _recon_fixture import add_fs_lines, add_tb, seed_engagement

from auditiq import cli
from auditiq.core import load_default_taxonomy
from auditiq.store import db, init_db, session_scope
from auditiq.store.models import ExceptionRecord, FsLine, TbLine


def _text(result) -> str:
    return (result.stdout or "") + (result.stderr or "")


@pytest.fixture
def cli_env(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'review-cli.db'}"
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
                {"name": "Mystery Payment", "amount": -800.0, "status": "pending_review", "method": "review"},
                {"name": "Mystery Payment", "amount": -200.0, "status": "pending_review", "method": "review"},
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
            ],
        )
        session.add(
            ExceptionRecord(
                engagement_id=engagement.id,
                kind="tieout",
                fsli_code="AST_TR",
                severity="material",
                status="open",
                amount=500.0,
                note="AST_TR Trade receivables",
            )
        )
        engagement_id = engagement.id
    return url, engagement_id


def _line_id(url, raw_name: str) -> int:
    with session_scope(url) as session:
        row = session.query(TbLine).filter_by(raw_name=raw_name).first()
        assert row is not None
        return row.id


def _fs_line_id(url, label: str, is_current: bool = True) -> int:
    with session_scope(url) as session:
        row = (
            session.query(FsLine)
            .filter_by(source_ref=label, is_current=is_current, measure="face")
            .first()
        )
        assert row is not None
        return row.id


def test_review_list_and_resolve(cli_env):
    url, engagement_id = cli_env
    runner = CliRunner()

    result = runner.invoke(cli.app, ["review", "list", "-e", str(engagement_id)])
    assert result.exit_code == 0, _text(result)
    text = _text(result)
    assert "2 pending head(s)" in text
    assert "Mystery Payment" in text
    assert "Unrecorded Ledger" in text

    line_id = _line_id(url, "Mystery Payment")
    result = runner.invoke(
        cli.app,
        ["review", "resolve", str(line_id), "--fsli", "AST_TR", "--reviewer", "aman"],
    )
    assert result.exit_code == 0, _text(result)
    assert "resolved" in _text(result)
    assert "2 line(s)" in _text(result)

    result = runner.invoke(cli.app, ["review", "list", "-e", str(engagement_id)])
    text = _text(result)
    assert "Unrecorded Ledger" in text
    assert "Mystery Payment" not in text


def test_review_resolve_invalid_fsli_errors(cli_env):
    url, engagement_id = cli_env
    line_id = _line_id(url, "Mystery Payment")
    result = CliRunner().invoke(
        cli.app, ["review", "resolve", str(line_id), "--fsli", "NOT_A_CODE"]
    )
    assert result.exit_code == 1
    assert "unknown FSLI" in _text(result)


def test_review_reset_undo(cli_env):
    url, engagement_id = cli_env
    runner = CliRunner()
    line_id = _line_id(url, "Mystery Payment")
    resolve = runner.invoke(
        cli.app, ["review", "resolve", str(line_id), "--fsli", "AST_TR"]
    )
    assert resolve.exit_code == 0, _text(resolve)

    reset = runner.invoke(cli.app, ["review", "reset", str(line_id)])
    assert reset.exit_code == 0, _text(reset)

    listing = runner.invoke(cli.app, ["review", "list", "-e", str(engagement_id)])
    text = _text(listing)
    assert "Mystery Payment" in text
    assert "2 pending head(s)" in text


def test_review_list_requires_engagement(cli_env):
    result = CliRunner().invoke(cli.app, ["review", "list"])
    assert result.exit_code == 1
    assert "engagement" in _text(result).lower()


def test_fs_review_list_and_resolve(cli_env):
    url, engagement_id = cli_env
    runner = CliRunner()

    result = runner.invoke(cli.app, ["fs-review", "list", "-e", str(engagement_id)])
    assert result.exit_code == 0, _text(result)
    text = _text(result)
    assert "1 unmapped label(s)" in text
    assert "Other Charges" in text

    line_id = _fs_line_id(url, "Other Charges")
    result = runner.invoke(
        cli.app, ["fs-review", "resolve", str(line_id), "--fsli", "EXP_OTH"]
    )
    assert result.exit_code == 0, _text(result)
    assert "resolved" in _text(result)
    assert "2 row(s)" in _text(result)

    result = runner.invoke(cli.app, ["fs-review", "list", "-e", str(engagement_id)])
    assert "no unmapped financial-statement labels" in _text(result)

    with session_scope(url) as session:
        rows = session.query(FsLine).filter_by(source_ref="Other Charges").all()
        assert len(rows) == 2
        for row in rows:
            assert row.fsli_code == "EXP_OTH"
            assert row.method == "manual"


def test_fs_review_both_targets_rejected(cli_env):
    url, engagement_id = cli_env
    line_id = _fs_line_id(url, "Other Charges")
    result = CliRunner().invoke(
        cli.app,
        ["fs-review", "resolve", str(line_id), "--fsli", "AST_OTH", "--group", "REV_OPERATIONS"],
    )
    assert result.exit_code == 1
    assert "not both" in _text(result)


def test_exceptions_list_and_dispose(cli_env):
    url, engagement_id = cli_env
    runner = CliRunner()

    result = runner.invoke(cli.app, ["exceptions", "list", "-e", str(engagement_id)])
    assert result.exit_code == 0, _text(result)
    text = _text(result)
    assert "1 exception(s)" in text
    assert "tieout" in text
    assert "open" in text

    result = runner.invoke(
        cli.app,
        ["exceptions", "dispose", "1", "--status", "explained", "--note", "timing difference"],
    )
    assert result.exit_code == 0, _text(result)
    assert "explained" in _text(result)

    result = runner.invoke(
        cli.app, ["exceptions", "list", "-e", str(engagement_id), "--status", "open"]
    )
    assert result.exit_code == 0, _text(result)
    assert "no exceptions" in _text(result)


def test_exceptions_requires_engagement(cli_env):
    result = CliRunner().invoke(cli.app, ["exceptions", "list"])
    text = _text(result)
    assert "provide --engagement" in text or "engagement" in text.lower()


def test_exceptions_dispose_invalid_status_errors(cli_env):
    result = CliRunner().invoke(cli.app, ["exceptions", "dispose", "1", "--status", "closed"])
    assert result.exit_code == 1
    assert "status must be one of" in _text(result)


def test_fs_coverage_cli(tmp_path):
    """`fs coverage` reports via the shared fs_coverage service helper."""
    from _draft_fs import schedule_iii_rows, write_fs_pdf

    bs_rows, pl_rows = schedule_iii_rows(
        {"AST_TR": 1000.0, "AST_CASH": 400.0}, load_default_taxonomy()
    )
    pl_rows = list(pl_rows) + [("Whimsical Disbursements", None, 99.0, None)]
    pdf = write_fs_pdf(tmp_path / "fs.pdf", bs_rows=bs_rows, pl_rows=pl_rows)

    result = CliRunner().invoke(cli.app, ["fs", "coverage", str(pdf)])
    assert result.exit_code == 0, _text(result)
    text = _text(result)
    assert "rows          3" in text
    assert "unmapped" in text
    assert "Whimsical Disbursements" in text  # listed under unmapped
