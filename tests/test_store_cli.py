"""CLI tests for the store commands: init, reset and the schema-drift guard."""
from __future__ import annotations

import sqlite3

import pytest
from typer.testing import CliRunner

from auditiq import cli
from auditiq.store import db, init_db, session_scope
from auditiq.store.models import Engagement


def _text(result) -> str:
    return (result.stdout or "") + (result.stderr or "")


@pytest.fixture
def cli_env(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'store-cli.db'}"
    monkeypatch.setattr(db, "DATABASE_URL", url)
    monkeypatch.setattr(db, "_engine", None)
    monkeypatch.setattr(db, "_session_factory", None)
    monkeypatch.setattr(db, "_schema_checked", set())
    init_db(url)
    return tmp_path / "store-cli.db"


def test_store_init_is_idempotent(cli_env):
    result = CliRunner().invoke(cli.app, ["store", "init"])
    assert result.exit_code == 0
    assert "Initialised database" in result.stdout


def test_store_init_reports_drift(cli_env):
    """A stale database gets an actionable error, not a raw traceback."""
    db._engine.dispose()
    with sqlite3.connect(cli_env) as con:
        con.execute("DROP TABLE fs_line")
        con.execute("CREATE TABLE fs_line (id INTEGER PRIMARY KEY, fsli_code VARCHAR)")
    db._engine = None
    db._session_factory = None
    db._schema_checked.clear()

    result = CliRunner().invoke(cli.app, ["store", "init"])

    assert result.exit_code == 1
    assert "fs_line.group_code" in _text(result)
    assert "store reset" in _text(result)


def test_store_reset_empties_database(cli_env):
    with session_scope(db.DATABASE_URL) as session:
        session.add(
            Engagement(
                client_code="T00", client_name="Test Co", period="FY25-26", basis="Standalone"
            )
        )

    result = CliRunner().invoke(cli.app, ["store", "reset", "--yes"])

    assert result.exit_code == 0
    assert "Reset database" in result.stdout
    with session_scope(db.DATABASE_URL) as session:
        assert session.query(Engagement).count() == 0


def test_store_reset_requires_confirmation(cli_env):
    result = CliRunner().invoke(cli.app, ["store", "reset"], input="n\n")

    assert result.exit_code == 1
    assert "Reset database" not in result.stdout
