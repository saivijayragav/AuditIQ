"""Tests for the FS-side group layer (presentation aggregates)."""
from __future__ import annotations

import pytest

from auditiq.ingest.fs.base import FsRow
from auditiq.ingest.fs.labels import (
    GROUP_LAYER,
    build_fs_mapper,
    label_row,
    label_rows,
    summarise,
)

pymupdf = pytest.importorskip("pymupdf")

from _draft_fs import write_fs_pdf  # noqa: E402

from auditiq.ingest.fs import ingest_fs  # noqa: E402
from auditiq.store import init_db, session_scope  # noqa: E402
from auditiq.store.models import FsLine  # noqa: E402


def test_group_label_resolves_before_cascade(taxonomy):
    mapper, _cfg, _kind, _tuned = build_fs_mapper(taxonomy=taxonomy, encoder_kind="none")
    row = FsRow(label="Revenue from Operations", current=1000.0)
    labelled = label_row(row, mapper, statement="pl")
    assert labelled.group_code == "REV_OPERATIONS"
    assert labelled.fsli_code is None
    assert labelled.layer == GROUP_LAYER
    assert labelled.code == "REV_OPERATIONS"
    assert labelled.mapped


def test_finer_revenue_label_still_maps_to_fsli(taxonomy):
    mapper, _cfg, _kind, _tuned = build_fs_mapper(taxonomy=taxonomy, encoder_kind="none")
    row = FsRow(label="Revenue from Sale of Products", current=1000.0)
    labelled = label_row(row, mapper, statement="pl")
    assert labelled.fsli_code == "INC_REV_SALES"
    assert labelled.group_code is None


def test_summary_counts_groups_as_mapped(taxonomy):
    mapper, _cfg, kind, tuned = build_fs_mapper(taxonomy=taxonomy, encoder_kind="none")
    rows = {
        "pl": [
            FsRow(label="Revenue from Operations", current=1000.0),
            FsRow(label="Other Expenses", current=100.0),
        ]
    }
    labelled = label_rows(rows, mapper, client="T00")
    summary = summarise(labelled, kind, tuned)
    assert summary.mapped == 2
    assert summary.by_layer[GROUP_LAYER] == 1


def test_ingest_persists_group_code(tmp_path):
    path = write_fs_pdf(
        tmp_path / "draft.pdf",
        bs_rows=[
            ("Share Capital", None, 100.0, None),
            ("Trade Receivables", None, 100.0, None),
        ],
        pl_rows=[
            ("Revenue from Operations", None, 500.0, None),
            ("Other Expenses", None, 100.0, None),
        ],
    )
    url = f"sqlite:///{tmp_path / 'fs.db'}"
    result = ingest_fs(path, client_code="T00", period="FY25-26", encoder_kind="none", url=url)
    assert result.mapped == 4  # two BS + revenue (group) + other expenses

    init_db(url)
    with session_scope(url) as session:
        group_row = (
            session.query(FsLine)
            .filter(FsLine.source_ref == "Revenue from Operations")
            .one()
        )
        assert group_row.group_code == "REV_OPERATIONS"
        assert group_row.fsli_code is None
        assert group_row.statement == "P&L"
        assert group_row.category == "Income"
