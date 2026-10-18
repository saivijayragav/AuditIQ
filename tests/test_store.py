"""Tests for the store schema and session helpers."""
from __future__ import annotations

import sqlite3

import pytest
from sqlalchemy import select

from auditiq.store import SchemaDriftError, init_db, reset_db, session_scope
from auditiq.store.models import Engagement, SourceDocument, TbLine


def _url(tmp_path) -> str:
    return f"sqlite:///{tmp_path / 'auditiq_test.db'}"


def test_create_and_query(tmp_path):
    url = _url(tmp_path)
    init_db(url)

    with session_scope(url) as session:
        engagement = Engagement(
            client_code="T00", client_name="Test Co", period="FY25-26", basis="Standalone"
        )
        session.add(engagement)
        session.flush()

        document = SourceDocument(
            engagement_id=engagement.id, kind="tb_erp", system="tally", filename="tb.xlsx"
        )
        session.add(document)
        session.flush()

        session.add(
            TbLine(
                document_id=document.id,
                engagement_id=engagement.id,
                client_code="T00",
                period="FY25-26",
                raw_name="Sundry Debtors",
                amount=1000.0,
                side="Dr",
                normalized_amount=1000.0,
            )
        )

    with session_scope(url) as session:
        lines = session.scalars(select(TbLine)).all()
        assert len(lines) == 1
        assert lines[0].raw_name == "Sundry Debtors"
        assert lines[0].side == "Dr"


def test_init_db_detects_missing_columns(tmp_path):
    """A database predating a model change fails loudly, naming the columns."""
    url = _url(tmp_path)
    # Simulate an old file: fs_line exists but without the later columns.
    with sqlite3.connect(tmp_path / "auditiq_test.db") as con:
        con.execute("CREATE TABLE fs_line (id INTEGER PRIMARY KEY, fsli_code VARCHAR)")

    with pytest.raises(SchemaDriftError) as excinfo:
        init_db(url)

    message = str(excinfo.value)
    assert "fs_line.group_code" in message
    assert "fs_line.method" in message
    assert "store reset" in message


def test_reset_db_rebuilds_schema(tmp_path):
    url = _url(tmp_path)
    init_db(url)
    with session_scope(url) as session:
        session.add(
            Engagement(
                client_code="T00", client_name="Test Co", period="FY25-26", basis="Standalone"
            )
        )

    reset_db(url)

    with session_scope(url) as session:
        assert session.query(Engagement).count() == 0
    # The schema is healthy again, so init_db no longer raises.
    init_db(url)

