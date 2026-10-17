"""CLI smoke tests for the reconciliation surface (isolated SQLite file)."""
from __future__ import annotations

import pytest
from typer.testing import CliRunner

from _recon_fixture import add_fs_lines, add_tb, seed_engagement, sign

from auditiq import cli
from auditiq.core import load_default_taxonomy
from auditiq.store import db, init_db, session_scope

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


@pytest.fixture
def cli_env(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'cli.db'}"
    monkeypatch.setattr(db, "DATABASE_URL", url)
    monkeypatch.setattr(db, "_engine", None)
    monkeypatch.setattr(db, "_session_factory", None)
    init_db(url)

    taxonomy = load_default_taxonomy()
    with session_scope(url) as session:
        engagement = seed_engagement(session)
        add_tb(
            session,
            engagement,
            [
                {
                    "name": taxonomy.name(code),
                    "amount": sign(taxonomy, code) * value,
                    "fsli": code,
                }
                for code, value in BASE.items()
            ],
        )
        add_fs_lines(
            session,
            engagement,
            [
                {"label": taxonomy.name(code), "value": value, "fsli": code}
                for code, value in BASE.items()
            ],
        )
        engagement_id = engagement.id
    return url, engagement_id


def _text(result) -> str:
    return (result.stdout or "") + (result.stderr or "")


def test_recon_run_requires_materiality(cli_env):
    _url, engagement_id = cli_env
    result = CliRunner().invoke(cli.app, ["recon", "run", "-e", str(engagement_id)])
    assert result.exit_code == 1
    assert "materiality" in _text(result).lower()


def test_materiality_set_then_run_show_explain(cli_env):
    _url, engagement_id = cli_env
    runner = CliRunner()

    result = runner.invoke(
        cli.app,
        ["materiality", "set", "-e", str(engagement_id), "-v", "100000", "--basis-name", "test"],
    )
    assert result.exit_code == 0, _text(result)
    assert "100,000.00" in _text(result)

    result = runner.invoke(cli.app, ["recon", "run", "-e", str(engagement_id)])
    assert result.exit_code == 0, _text(result)
    assert "clean" in _text(result)
    assert "tied 10" in _text(result)

    result = runner.invoke(cli.app, ["recon", "show", "-e", str(engagement_id)])
    assert result.exit_code == 0, _text(result)
    assert "AST_TR" in _text(result)
    assert "INC_REV_SALES" in _text(result)

    result = runner.invoke(cli.app, ["recon", "explain", "AST_TR", "-e", str(engagement_id)])
    assert result.exit_code == 0, _text(result)
    assert "side A" in _text(result)
    assert "1,000.00" in _text(result)


def test_materiality_suggest(cli_env):
    _url, engagement_id = cli_env
    result = CliRunner().invoke(cli.app, ["materiality", "suggest", "-e", str(engagement_id)])
    assert result.exit_code == 0, _text(result)
    assert "suggested" in _text(result)
    assert "10.00" in _text(result)  # 0.5% of revenue 2,000


def test_recon_show_without_run_errors(cli_env):
    _url, engagement_id = cli_env
    result = CliRunner().invoke(cli.app, ["recon", "show", "-e", str(engagement_id)])
    assert result.exit_code == 1
    assert "no reconciliation run" in _text(result)
