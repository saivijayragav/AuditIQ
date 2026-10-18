"""UI harness smoke tests: server-rendered pages and HTMX fragments.

No browser: these verify pages render and every fragment endpoint behaves —
upload, map, review actions, materiality, recon, exceptions, fs-review.
"""
from __future__ import annotations

import re

import pytest
from fastapi.testclient import TestClient

from _draft_fs import schedule_iii_rows, write_fs_pdf

from auditiq.api import create_app
from auditiq.core import load_default_taxonomy
from auditiq.store import db, init_db

from test_api_e2e import PRESENTED, _tb_xlsx_bytes


@pytest.fixture
def ui(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'ui.db'}"
    monkeypatch.setattr(db, "DATABASE_URL", url)
    monkeypatch.setattr(db, "_engine", None)
    monkeypatch.setattr(db, "_session_factory", None)
    init_db(url)
    client = TestClient(create_app())
    r = client.post(
        "/ui",
        data={"client_code": "T09", "period": "FY25-26", "client_name": "Harness Co"},
        follow_redirects=False,
    )
    assert r.status_code == 303, r.text
    eid = int(re.search(r"/ui/engagements/(\d+)", r.headers["location"]).group(1))
    return client, eid, tmp_path


def test_ui_engagement_list_and_workspace(ui):
    client, eid, _ = ui
    r = client.get("/ui")
    assert r.status_code == 200 and "Engagements" in r.text
    assert "T09" in r.text and "Harness Co" in r.text
    assert "intake" in r.text

    r = client.get(f"/ui/engagements/{eid}")
    assert r.status_code == 200
    assert "TB: 0 lines" in r.text
    for label in ("Ingest", "Map FSLIs", "Review queue", "Materiality", "Reconcile", "Exceptions"):
        assert label in r.text
    assert 'hx-get="/ui/engagements/1/tabs/ingest"' in r.text

    assert client.get("/ui/engagements/9999").status_code == 200  # alert fragment
    assert "no engagement with id 9999" in client.get("/ui/engagements/9999").text


def test_ui_ingest_map_review_materiality_recon(ui):
    client, eid, tmp_path = ui

    # TB upload (multipart, like a real browser)
    r = client.post(
        f"/ui/engagements/{eid}/ingest/tb",
        files={"file": ("tb.xlsx", _tb_xlsx_bytes(), "application/vnd.openxmlformats")},
    )
    assert r.status_code == 200 and "TB ingested" in r.text and "balanced" in r.text

    # map (dictionary only)
    r = client.post(f"/ui/engagements/{eid}/map", data={"encoder": "none"})
    assert r.status_code == 200
    assert "accepted" in r.text and "2 pending review" in r.text
    assert "go to the review queue (2 pending)" in r.text

    # review queue lists both mystery heads with candidate chips
    r = client.get(f"/ui/engagements/{eid}/tabs/review")
    assert "Zzz Mystery Ledger A" in r.text and "Zzz Mystery Ledger B" in r.text
    assert "no candidate shortlist" in r.text  # dictionary-only run w/o embeddings

    # resolve leave B pending
    r = client.post(
        f"/ui/engagements/{eid}/tabs/review" and f"/ui/engagements/{eid}/review/resolve",
        data={"line_id": "1", "fsli": "NOT_A_CODE"},
    )
    # line 1 is "Sundry Debtors" — resolving to an unknown code errors safely
    assert r.status_code == 200 and "unknown FSLI" in r.text
    assert "2 head(s)" in r.text  # fragment re-rendered, both still pending

    # invalid tab fragment
    r = client.get(f"/ui/engagements/{eid}/tabs/bogus")
    assert "unknown tab" in r.text

    # recon fails loudly while materiality is unset
    r = client.post(f"/ui/engagements/{eid}/recon/run", data={"statements": "all"})
    assert "materiality" in r.text

    # materiality tab offers a suggestion only after the draft FS exists
    r = client.get(f"/ui/engagements/{eid}/tabs/materiality")
    assert "not set" in r.text
    assert "Ingest a draft FS" in r.text

    # --- draft FS from the presented books; upload via fragments -----------
    taxonomy = load_default_taxonomy()
    bs_rows, pl_rows = schedule_iii_rows(PRESENTED, taxonomy)
    pdf = write_fs_pdf(tmp_path / "draft.pdf", bs_rows=bs_rows, pl_rows=pl_rows)
    r = client.post(
        f"/ui/engagements/{eid}/ingest/fs",
        files={"file": ("draft.pdf", open(pdf, "rb").read(), "application/pdf")},
    )
    assert r.status_code == 200 and "Draft FS ingested" in r.text

    r = client.get(f"/ui/engagements/{eid}/tabs/materiality")
    assert "Suggested" in r.text and "use suggestion" in r.text

    # set it through the form
    r = client.post(f"/ui/engagements/{eid}/materiality", data={"value": "100", "basis": "test"})
    assert "Current" in r.text

    # baseline recon through the UI fragment
    r = client.post(f"/ui/engagements/{eid}/recon/run", data={"statements": "all"})
    assert "8 tied" in r.text and "0 material" in r.text
    assert "exposure A 246.00" in r.text

    # results grid + explain drawer endpoint
    r = client.get(f"/ui/engagements/{eid}/tabs/results")
    assert "Run reconciliation" in r.text
    r = client.get(f"/ui/engagements/{eid}/results/explain/AST_TR")
    assert "AST_TR" in r.text and "books (A)" in r.text
    r = client.get(f"/ui/engagements/{eid}/results/explain/NOT_HERE")
    assert "is not in the latest run" in r.text

    # exceptions tab: clean baseline has no escalations
    r = client.get(f"/ui/engagements/{eid}/tabs/exceptions")
    assert "No exception records" in r.text

    # fs-review tab: the deterministic draft has nothing unmapped
    r = client.get(f"/ui/engagements/{eid}/tabs/fsreview")
    assert "Side B carries no unmapped rows" in r.text


def test_ui_review_resolve_and_bulk(ui):
    client, eid, _ = ui

    client.post(
        f"/ui/engagements/{eid}/ingest/tb",
        files={"file": ("tb.xlsx", _tb_xlsx_bytes(), "application/vnd.openxmlformats")},
    )
    client.post(f"/ui/engagements/{eid}/map", data={"encoder": "none"})

    r = client.post(
        f"/ui/engagements/{eid}/review/resolve",
        data={"line_id": "9", "fsli": "AST_TR", "reviewer": "harness"},
    )
    assert r.status_code == 200
    assert "1 head(s)" in r.text  # A resolved; B remains

    # bulk approve the rest with top candidate (none available w/o encoder)
    r = client.post(f"/ui/engagements/{eid}/review/bulk", data={"reviewer": "harness"})
    assert r.status_code == 200
    assert "Nothing pending" in r.text or "head(s)" in r.text

    # resolve form validation: unknown FSLI error surfaces in the fragment
    r = client.post(
        f"/ui/engagements/{eid}/review/resolve",
        data={"line_id": "1", "fsli": "NOT_A_CODE", "reviewer": "harness"},
    )
    assert "unknown FSLI" in r.text
