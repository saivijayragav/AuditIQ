"""End-to-end tests for financial-statement ingestion (PDF reader).

Requires the ``[report]`` extra (PyMuPDF). Skips cleanly when it is absent.
"""
from __future__ import annotations

import pytest
from sqlalchemy import func, select

pymupdf = pytest.importorskip("pymupdf")

from _draft_fs import write_fs_pdf  # noqa: E402

from auditiq.core import load_default_taxonomy  # noqa: E402
from auditiq.ingest.fs import (  # noqa: E402
    ingest_fs,
    list_unmapped_fs,
    reset_fs_line,
    resolve_fs_line,
)
from auditiq.reconciliation import side_b  # noqa: E402
from auditiq.store import session_scope  # noqa: E402
from auditiq.store.models import (  # noqa: E402
    Engagement,
    Evidence,
    FsLine,
    SourceDocument,
)

BS_ROWS = [
    ("Property, Plant and Equipment", 3, 350513.96, 300000.00),
    ("Capital Work-in-Progress", 4, 100000.00, 80000.00),
    ("Trade Receivables", 5, 646208.05, 600000.00),
    ("Cash and Cash Equivalents", 6, 100000.00, 90000.00),
    ("Share Capital", 7, 500000.00, 500000.00),
    ("Reserves and Surplus", None, 696722.01, 570000.00),
    ("Trade Payables", 8, 200000.00, 150000.00),
    ("Total Assets", None, 1296722.01, 1170000.00),
]
PL_ROWS = [
    ("Revenue from Sale of Products", 1, 1000000.00, 900000.00),
    ("Cost of Materials Consumed", 2, 400000.00, 380000.00),
    ("Employee Benefits Expense", 3, 200000.00, 180000.00),
    ("Finance Costs", 3, 20000.00, 25000.00),
    ("Depreciation and Amortisation Expense", 3, 30000.00, 30000.00),
    ("Other Expenses", 3, 100000.00, 90000.00),
    ("Current Tax", 4, 50000.00, 40000.00),
    ("Deferred Tax", 4, 10000.00, 8000.00),
    ("Total Expenses", None, 800000.00, 753000.00),
]


def _url(tmp_path) -> str:
    return f"sqlite:///{tmp_path / 'fs.db'}"


def _draft(tmp_path, **kwargs):
    defaults = dict(
        company="Test Co Limited",
        period="FY25-26",
        unit="absolute",
        basis="Standalone",
        bs_rows=BS_ROWS,
        pl_rows=PL_ROWS,
    )
    defaults.update(kwargs)
    return write_fs_pdf(tmp_path / "draft_fs.pdf", **defaults)


def test_ingest_draft_fs(tmp_path):
    path = _draft(tmp_path)
    url = _url(tmp_path)

    result = ingest_fs(
        path, client_code="T00", period="FY25-26", encoder_kind="none", url=url
    )

    assert result.reader == "pdf"
    assert result.company == "Test Co Limited"
    assert result.period == "FY25-26"
    assert result.prior_period == "FY24-25"
    assert result.unit == "absolute"
    assert result.rows == 17
    assert result.lines == 34  # current + prior for every face row
    assert result.mapped == 30  # 15 resolvable rows x 2 columns
    assert result.subtotals == 4  # "Total ..." rows x 2 columns
    assert result.by_statement == {"BS": 16, "P&L": 18}


def test_fs_line_values_periods_and_evidence(tmp_path):
    path = _draft(tmp_path)
    url = _url(tmp_path)
    ingest_fs(path, client_code="T00", period="FY25-26", encoder_kind="none", url=url)

    with session_scope(url) as session:
        current = session.scalars(
            select(FsLine).where(
                FsLine.fsli_code == "AST_TR", FsLine.is_current.is_(True)
            )
        ).one()
        assert current.normalized_value == pytest.approx(646208.05)
        assert current.period == "FY25-26"
        assert current.statement == "BS"
        assert current.category == "Asset"
        assert current.measure == "face"
        assert current.is_subtotal is False
        assert current.evidence_id is not None

        prior = session.scalars(
            select(FsLine).where(
                FsLine.fsli_code == "AST_TR", FsLine.is_current.is_(False)
            )
        ).one()
        assert prior.normalized_value == pytest.approx(600000.0)
        assert prior.period == "FY24-25"

        # Every persisted value has evidence.
        lines = session.scalar(select(func.count()).select_from(FsLine))
        evidence = session.scalar(select(func.count()).select_from(Evidence))
        assert lines == evidence == 34


def test_subtotal_rows_are_marked_and_excluded(tmp_path):
    path = _draft(tmp_path)
    url = _url(tmp_path)
    result = ingest_fs(
        path, client_code="T00", period="FY25-26", encoder_kind="none", url=url
    )

    with session_scope(url) as session:
        subtotals = session.scalars(
            select(FsLine).where(FsLine.is_subtotal.is_(True))
        ).all()
        assert len(subtotals) == 4
        assert {row.measure for row in subtotals} == {"subtotal"}

    # Reconciliation consumes mapped face values only.
    assert result.mapped_weighted == result.mapped - result.subtotals == 26


def test_ingest_is_idempotent(tmp_path):
    path = _draft(tmp_path)
    url = _url(tmp_path)

    first = ingest_fs(path, client_code="T00", period="FY25-26", encoder_kind="none", url=url)
    second = ingest_fs(path, client_code="T00", period="FY25-26", encoder_kind="none", url=url)

    assert first.engagement_id == second.engagement_id
    assert second.lines == first.lines == 34
    with session_scope(url) as session:
        assert session.scalar(select(func.count()).select_from(FsLine)) == 34
        assert session.scalar(select(func.count()).select_from(SourceDocument)) == 1
        assert session.scalar(select(func.count()).select_from(Engagement)) == 1


def test_unit_detection_and_conversion(tmp_path):
    rows = [("Trade Receivables", 5, 100.0, 90.0)]
    path = _draft(tmp_path, unit="lakhs", bs_rows=rows, pl_rows=[])
    url = _url(tmp_path)

    result = ingest_fs(path, client_code="T00", period="FY25-26", encoder_kind="none", url=url)
    assert result.unit == "lakhs"

    with session_scope(url) as session:
        line = session.scalars(select(FsLine)).first()
        assert line.report_value == pytest.approx(100.0)
        assert line.normalized_value == pytest.approx(100.0 * 1e5)


def test_explicit_unit_overrides_and_warns(tmp_path):
    rows = [("Trade Receivables", 5, 100.0, 90.0)]
    path = _draft(tmp_path, unit="lakhs", bs_rows=rows, pl_rows=[])
    url = _url(tmp_path)

    result = ingest_fs(
        path, client_code="T00", period="FY25-26", unit="absolute",
        encoder_kind="none", url=url,
    )
    assert result.unit == "absolute"
    assert any(issue.code == "unit_mismatch" for issue in result.issues)

    with session_scope(url) as session:
        line = session.scalars(select(FsLine)).first()
        assert line.normalized_value == pytest.approx(100.0)


def test_unmapped_label_goes_to_review(tmp_path):
    rows = BS_ROWS + [("Biological Assets Under Development", None, 5000.0, None)]
    path = _draft(tmp_path, bs_rows=rows)
    url = _url(tmp_path)

    result = ingest_fs(path, client_code="T00", period="FY25-26", encoder_kind="none", url=url)
    assert result.unmapped > 0

    with session_scope(url) as session:
        unmapped = session.scalars(
            select(FsLine).where(
                FsLine.source_ref == "Biological Assets Under Development"
            )
        ).all()
        assert unmapped
        assert all(row.fsli_code is None for row in unmapped)


def test_reviewer_decision_replays_on_reingest(tmp_path):
    """The FS cache is seeded from the stored rows, exactly like the TB cache."""
    mystery = "Whimsical Disbursements"
    bs_rows = [("Trade Receivables", 5, 100.0, 90.0), (mystery, None, 99.0, 88.0)]
    pl_rows = [("Finance Costs", 3, 20.0, 25.0)]
    path = _draft(tmp_path, bs_rows=bs_rows, pl_rows=pl_rows)
    url = _url(tmp_path)

    first = ingest_fs(
        path, client_code="T00", period="FY25-26", encoder_kind="none", url=url
    )
    assert first.unmapped == 2  # current + prior

    with session_scope(url) as session:
        line_id = session.scalars(
            select(FsLine).where(FsLine.source_ref == mystery)
        ).first().id
    resolve_fs_line(line_id, fsli_code="AST_INV", url=url)
    assert list_unmapped_fs(first.engagement_id, url=url) == []

    second = ingest_fs(
        path, client_code="T00", period="FY25-26", encoder_kind="none", url=url
    )
    assert second.unmapped == 0

    with session_scope(url) as session:
        replayed = session.scalars(
            select(FsLine).where(FsLine.source_ref == mystery)
        ).all()
        assert {row.fsli_code for row in replayed} == {"AST_INV"}
        assert {row.method for row in replayed} == {"cache"}


def test_cache_is_scoped_to_the_client(tmp_path):
    """A decision for one client must not leak into another client's draft."""
    mystery = "Whimsical Disbursements"
    bs_rows = [("Trade Receivables", 5, 100.0, 90.0), (mystery, None, 99.0, 88.0)]
    path = _draft(tmp_path, bs_rows=bs_rows, pl_rows=[])
    url = _url(tmp_path)

    first = ingest_fs(
        path, client_code="T00", period="FY25-26", encoder_kind="none", url=url
    )
    with session_scope(url) as session:
        line_id = session.scalars(
            select(FsLine).where(FsLine.source_ref == mystery)
        ).first().id
    resolve_fs_line(line_id, fsli_code="AST_INV", url=url)

    other = ingest_fs(
        path, client_code="T01", period="FY25-26", encoder_kind="none", url=url
    )
    assert other.engagement_id != first.engagement_id
    assert other.unmapped == 2
    with session_scope(url) as session:
        rows = session.scalars(
            select(FsLine).where(
                FsLine.engagement_id == other.engagement_id,
                FsLine.source_ref == mystery,
            )
        ).all()
        assert all(row.fsli_code is None for row in rows)


def test_reset_after_replay_is_a_tombstone(tmp_path):
    """A reset must survive the re-ingest that purges the reset rows."""
    mystery = "Whimsical Disbursements"
    bs_rows = [("Trade Receivables", 5, 100.0, 90.0), (mystery, None, 99.0, 88.0)]
    pl_rows = [("Finance Costs", 3, 20.0, 25.0)]
    path = _draft(tmp_path, bs_rows=bs_rows, pl_rows=pl_rows)
    url = _url(tmp_path)

    first = ingest_fs(
        path, client_code="T00", period="FY25-26", encoder_kind="none", url=url
    )
    with session_scope(url) as session:
        line_id = session.scalars(
            select(FsLine).where(FsLine.source_ref == mystery)
        ).first().id
    resolve_fs_line(line_id, fsli_code="AST_INV", url=url)
    ingest_fs(path, client_code="T00", period="FY25-26", encoder_kind="none", url=url)

    with session_scope(url) as session:
        replayed_id = session.scalars(
            select(FsLine).where(FsLine.source_ref == mystery)
        ).first().id
    reset_fs_line(replayed_id, url=url)
    assert len(list_unmapped_fs(first.engagement_id, url=url)) == 1

    third = ingest_fs(
        path, client_code="T00", period="FY25-26", encoder_kind="none", url=url
    )
    assert third.unmapped == 2

    with session_scope(url) as session:
        reset_rows = session.scalars(
            select(FsLine).where(FsLine.source_ref == mystery)
        ).all()
        assert all(row.fsli_code is None for row in reset_rows)
        assert {row.method for row in reset_rows} == {"review"}


def test_notes_rows_are_note_total_and_excluded_from_side_b(tmp_path):
    notes = [
        ("Inventories", 9, 12345.0, 10000.0),
        ("Whimsical Note Item", 9, 500.0, 400.0),
    ]
    path = _draft(tmp_path, notes_rows=notes)
    url = _url(tmp_path)

    result = ingest_fs(
        path, client_code="T00", period="FY25-26", encoder_kind="none", url=url
    )
    assert result.by_statement["Notes"] == 4

    with session_scope(url) as session:
        note_rows = session.scalars(
            select(FsLine).where(FsLine.statement == "Notes")
        ).all()
        assert len(note_rows) == 4
        assert {row.measure for row in note_rows} == {"note_total"}

        side = side_b(
            session,
            result.engagement_id,
            load_default_taxonomy(),
            period="FY25-26",
        )
        assert "AST_INV" not in side.by_fsli
        assert all(row.statement != "Notes" for row in side.unmapped)

    # Notes never reach the face review queue.
    assert all(
        entry.statement != "Notes"
        for entry in list_unmapped_fs(result.engagement_id, url=url)
    )


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        ingest_fs(tmp_path / "nope.pdf", client_code="T00", period="FY25-26")
