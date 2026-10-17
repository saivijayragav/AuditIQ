"""Tests for the trial-balance ingestion service."""
from __future__ import annotations

from sqlalchemy import select

from auditiq.ingest.erp import ingest_tb
from auditiq.store import session_scope
from auditiq.store.models import Engagement, SourceDocument, TbLine


def _url(tmp_path) -> str:
    return f"sqlite:///{tmp_path / 'ingest.db'}"


def test_ingest_zoho(tmp_path, write_xlsx, zoho_rows):
    path = write_xlsx(tmp_path / "tb.xlsx", zoho_rows)
    url = _url(tmp_path)

    result = ingest_tb(path, client_code="T00", period="FY25-26", client_name="Test Co", url=url)

    assert result.source == "zoho"
    assert result.period == "FY25-26"
    assert result.lines == 2
    assert result.total_debit == 500
    assert result.total_credit == 500
    assert result.balanced

    with session_scope(url) as session:
        lines = session.scalars(select(TbLine)).all()
        assert len(lines) == 2
        assert {l.raw_name for l in lines} == {"Sundry Debtors", "Share Capital"}
        engagement = session.scalars(select(Engagement)).one()
        assert engagement.client_name == "Test Co"


def test_ingest_is_idempotent(tmp_path, write_xlsx, sap_rows):
    path = write_xlsx(tmp_path / "tb.xlsx", sap_rows)
    url = _url(tmp_path)

    first = ingest_tb(path, client_code="T00", period="FY25-26", url=url)
    second = ingest_tb(path, client_code="T00", period="FY25-26", url=url)

    assert first.engagement_id == second.engagement_id
    with session_scope(url) as session:
        assert session.scalars(select(TbLine)).all().__len__() == 2
        assert session.scalars(select(SourceDocument)).all().__len__() == 1
        assert session.scalars(select(Engagement)).all().__len__() == 1


def test_ingest_unit_conversion(tmp_path, write_xlsx, zoho_rows):
    path = write_xlsx(tmp_path / "tb.xlsx", zoho_rows)
    url = _url(tmp_path)

    result = ingest_tb(
        path, client_code="T00", period="FY25-26", unit="crores", url=url
    )
    assert result.unit == "crores"
    assert result.total_debit == 500 * 1e7

    with session_scope(url) as session:
        lines = session.scalars(select(TbLine)).all()
        debtors = next(l for l in lines if l.raw_name == "Sundry Debtors")
        assert debtors.amount == 500
        assert debtors.normalized_amount == 500 * 1e7


def test_ingest_period_normalisation(tmp_path, write_xlsx, zoho_rows):
    path = write_xlsx(tmp_path / "tb.xlsx", zoho_rows)
    url = _url(tmp_path)

    result = ingest_tb(path, client_code="T00", period="2025-26", url=url)
    assert result.period == "FY25-26"


def test_ingest_missing_file(tmp_path):
    import pytest

    with pytest.raises(FileNotFoundError):
        ingest_tb(tmp_path / "nope.xlsx", client_code="T00", period="FY25-26")
