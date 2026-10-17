"""Tests for the store schema and session helpers."""
from __future__ import annotations

from sqlalchemy import select

from auditiq.store import init_db, session_scope
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
