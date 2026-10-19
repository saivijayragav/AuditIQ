"""CLI: ``auditiq api schema`` exports the contract without starting a server."""
from __future__ import annotations

import json

from typer.testing import CliRunner

from auditiq import cli


def test_api_schema_prints_to_stdout():
    result = CliRunner().invoke(cli.app, ["api", "schema"])
    assert result.exit_code == 0, result.stderr
    spec = json.loads(result.stdout)
    assert "/api/engagements" in spec["paths"]
    assert "ErrorOut" in spec["components"]["schemas"]


def test_api_schema_writes_a_nested_file(tmp_path):
    out = tmp_path / "nested" / "openapi.json"
    result = CliRunner().invoke(cli.app, ["api", "schema", "--out", str(out)])
    assert result.exit_code == 0, result.stderr
    assert "wrote" in result.stdout

    spec = json.loads(out.read_text(encoding="utf-8"))
    assert spec["openapi"].startswith("3.")
    assert all(path.startswith("/") for path in spec["paths"])


def test_api_schema_is_byte_stable():
    """Codegen diffs stay meaningful only if the document is deterministic."""
    first = CliRunner().invoke(cli.app, ["api", "schema", "--indent", "0"]).stdout
    second = CliRunner().invoke(cli.app, ["api", "schema", "--indent", "0"]).stdout
    assert first == second
    assert first.strip()
