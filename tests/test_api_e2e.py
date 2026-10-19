"""API end-to-end: the full pipeline driven through HTTP on an isolated store.

Upload a Zoho-layout TB -> map (dictionary only) -> approve + reset mappings ->
upload/generate a draft FS -> materiality -> reconcile (twice) -> exceptions ->
fs-review. Mirrors the CLI e2e gate at the API level; no browser, no node.
"""
from __future__ import annotations

import sqlite3

import pytest
from fastapi.testclient import TestClient

from _draft_fs import schedule_iii_rows, write_fs_pdf
from _tb_writer import DEFAULT_HEADS, write_tb_bytes

from auditiq.api import create_app
from auditiq.core import load_default_taxonomy
from auditiq.store import db, init_db

# Deterministic vocabulary: these heads resolve through the alias dictionary.
PRESENTED = {
    "AST_TR": 1000.0,
    "AST_CASH": 500.0,
    "AST_INV": 700.0,
    "EXP_MAT": 1200.0,
    "EXP_OTH": 800.0,
    "INC_REV_SALES": 2000.0,
    "LIA_TP": 700.0,
    "EQ_SC": 1500.0,
}

# Two heads the cascade cannot accept — pending-review exposure, balanced against
# each other so the workbook itself still ties.
MYSTERY_HEADS = list(DEFAULT_HEADS) + [
    ("Zzz Mystery Ledger A", None, 123.0),
    ("Zzz Mystery Ledger B", None, -123.0),
]


def _draft_fs_pdf(tmp_path):
    taxonomy = load_default_taxonomy()
    bs_rows, pl_rows = schedule_iii_rows(PRESENTED, taxonomy)
    path = write_fs_pdf(tmp_path / "draft.png".replace("png", "pdf"), bs_rows=bs_rows, pl_rows=pl_rows)
    return path


@pytest.fixture
def client_api(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path / 'api.db'}"
    monkeypatch.setattr(db, "DATABASE_URL", url)
    monkeypatch.setattr(db, "_engine", None)
    monkeypatch.setattr(db, "_session_factory", None)
    monkeypatch.setattr("auditiq.settings.DATABASE_URL", url)
    # The harness reads files off disk in tests; the default is off for browsers.
    monkeypatch.setattr("auditiq.api.app.ALLOW_PATH_INGEST", True)
    init_db(url)
    return TestClient(create_app()), url, tmp_path


def test_api_full_pipeline(client_api):
    client, url, tmp_path = client_api

    # -- health + reference ------------------------------------------------
    r = client.get("/api/health")
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "ok"

    r = client.get("/api/erp-sources")
    assert "zoho" in r.json()["sources"]

    r = client.get("/api/taxonomy", params={"search": "cash"})
    assert r.status_code == 200 and r.json()

    # -- engagement --------------------------------------------------------
    r = client.post(
        "/api/engagements",
        json={"client_code": "T07", "period": "FY25-26", "client_name": "Test Co"},
    )
    assert r.status_code == 201, r.text
    eid = r.json()["engagement_id"]
    assert r.json()["intake_status"] == "intake"

    # -- ingest TB (upload) --------------------------------------------------
    r = client.post(
        f"/api/engagements/{eid}/ingest/tb",
        files={"file": ("tb.xlsx", write_tb_bytes(MYSTERY_HEADS), "application/vnd.openxmlformats")},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["lines"] == len(MYSTERY_HEADS)
    assert body["balanced"]

    # -- map (dictionary only) ----------------------------------------------
    r = client.post(f"/api/engagements/{eid}/map", json={"encoder": "none"})
    assert r.status_code == 200, r.text
    summary = r.json()
    assert summary["lines"] == len(MYSTERY_HEADS)
    assert summary["resolved"] == 8
    assert summary["review"] == 2
    summary_by_status = client.get(f"/api/engagements/{eid}").json()
    assert summary_by_status["mappings"] == {"auto": 8, "pending_review": 2}

    # -- review queue ---------------------------------------------------------
    r = client.get(f"/api/engagements/{eid}/mappings")
    assert r.status_code == 200, r.text
    pending = r.json()
    assert {p["raw_name"] for p in pending} == {"Zzz Mystery Ledger A", "Zzz Mystery Ledger B"}
    assert sorted(p["amount"] for p in pending) == [-123.0, 123.0]

    # bulk failure path stays visible
    r = client.post("/api/mappings/resolve-bulk", json={"pairs": [[pending[1]["line_id"], "NOT_A_CODE"]]})
    assert r.status_code == 200 and r.json()["failures"]

    # invalid target -> 422 with the uniform envelope
    r = client.post("/api/mappings/resolve", json={"line_id": pending[1]["line_id"], "fsli_code": "NOPE"})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_failed"
    assert "unknown FSLI" in r.json()["error"]["message"]

    # -- draft FS ------------------------------------------------------------
    draft = _draft_fs_pdf(tmp_path)
    r = client.post(f"/api/engagements/{eid}/ingest/fs", params={"path": str(draft)})
    assert r.status_code == 201, r.text
    ingest_body = r.json()
    assert ingest_body["mapped_weighted"] == len(PRESENTED)

    # fs-review queue is empty (all labels considered)
    assert client.get(f"/api/engagements/{eid}/fs-review").json() == []

    # -- materiality: recon fails loudly before it is set ----------------------
    r = client.post(f"/api/engagements/{eid}/recon/run", json={})
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "materiality_unset"
    assert "materiality" in r.json()["error"]["message"]

    r = client.get(f"/api/engagements/{eid}/materiality")
    suggestion = r.json()
    assert suggestion["suggestion"]["suggested"] > 0

    r = client.post(f"/api/engagements/{eid}/materiality", json={"value": 100.0, "basis": "test"})
    assert r.status_code == 200 and r.json()["materiality_value"] == 100.0

    # -- baseline recon: everything the client presented ties ----------------
    r = client.post(f"/api/engagements/{eid}/recon/run", json={})
    assert r.status_code == 201, r.text
    base = r.json()
    assert base["tied"] == 8
    assert base["material"] == 0
    assert base["exposure_a"] == pytest.approx(246.0)
    assert base["status"] == "minor residual"

    # -- reviewer approves head A: it moves into Side A, so a +123 variance ----
    target = next(p for p in pending if p["raw_name"] == "Zzz Mystery Ledger A")
    r = client.post(
        "/api/mappings/resolve",
        json={"line_id": target["line_id"], "fsli_code": "AST_TR", "reviewer": "aman"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["fsli_code"] == "AST_TR"

    r = client.get(f"/api/engagements/{eid}/mappings", params={"status": "resolved"})
    assert {h["raw_name"] for h in r.json()} == {"Zzz Mystery Ledger A"}

    # per-status counts (the UI's badge source)
    r = client.get(f"/api/engagements/{eid}/mappings", params={"status": "all"})
    assert r.status_code == 200
    assert r.json()["counts"] == {"auto": 8, "pending_review": 1, "resolved": 1}
    assert r.json()["total"] == len(MYSTERY_HEADS)

    # latest run retrieval
    r = client.get(f"/api/engagements/{eid}/recon")
    assert r.status_code == 200
    codes = {line["unit_code"] for line in r.json()["lines"]}
    assert {"AST_TR", "EXP_MAT", "INC_REV_SALES"} <= codes

    # -- the approved head moves into Side A: a 123 variance appears ----------
    r = client.post(f"/api/engagements/{eid}/recon/run", json={})
    assert r.json()["exposure_a"] == pytest.approx(123.0)
    assert r.json()["material"] == 1  # only AST_TR carries the +123
    run_line_ast = next(l for l in client.get(f"/api/engagements/{eid}/recon").json()["lines"] if l["unit_code"] == "AST_TR")
    assert run_line_ast["variance"] == pytest.approx(123.0)

    # exceptions escalated, then dispositioned
    r = client.get(f"/api/engagements/{eid}/exceptions", params={"status": "open"})
    assert len(r.json()) == 1
    r = client.post(f"/api/exceptions/{r.json()[0]['exception_id']}/dispose", json={"status": "explained", "note": "late posting"})
    assert r.json()["status"] == "explained"

    # explain endpoint picks up the variance unit
    r = client.get(f"/api/engagements/{eid}/recon/explain/AST_TR")
    assert r.status_code == 200 and r.json()["line"]["unit_code"] == "AST_TR"

    # -- undo the approval: back to tied -------------------------------------
    r = client.post(f"/api/mappings/{target['line_id']}/reset")
    assert r.status_code == 200, r.text

    r = client.post(f"/api/engagements/{eid}/recon/run", json={})
    final = r.json()
    assert final["tied"] == 8
    assert final["material"] == 0
    assert final["exposure_a"] == pytest.approx(246.0)

    # unknown unit explain -> 404
    assert client.get(f"/api/engagements/{eid}/recon/explain/NOT_HERE").status_code == 404


def test_api_engagement_404_and_bad_status(client_api):
    client, url, _ = client_api
    r = client.get("/api/engagements/9999")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"
    eid = client.post("/api/engagements", json={"client_code": "T08", "period": "FY25-26"}).json()["engagement_id"]
    bad = client.get(f"/api/engagements/{eid}/mappings", params={"status": "bogus"})
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "bad_request"


def test_api_documents_and_tb_lines(client_api):
    """The read endpoints: document inventory and paged ledger lines."""
    client, url, tmp_path = client_api
    eid = client.post(
        "/api/engagements", json={"client_code": "T10", "period": "FY25-26"}
    ).json()["engagement_id"]
    assert client.get(f"/api/engagements/{eid}/documents").json() == []

    client.post(
        f"/api/engagements/{eid}/ingest/tb",
        files={"file": ("tb.xlsx", write_tb_bytes(MYSTERY_HEADS), "application/vnd.openxmlformats")},
    )

    docs = client.get(f"/api/engagements/{eid}/documents").json()
    assert len(docs) == 1
    assert docs[0]["kind"] == "tb_erp" and docs[0]["system"] == "zoho"
    assert docs[0]["filename"].endswith("tb.xlsx")
    assert client.get(
        f"/api/engagements/{eid}/documents", params={"kind": "fs_document"}
    ).json() == []

    # paging: the total is independent of the window
    page = client.get(f"/api/engagements/{eid}/tb-lines", params={"limit": 3}).json()
    assert page["total"] == len(MYSTERY_HEADS)
    assert len(page["items"]) == 3 and page["limit"] == 3 and page["offset"] == 0
    nxt = client.get(f"/api/engagements/{eid}/tb-lines", params={"limit": 3, "offset": 3}).json()
    assert not ({i["line_id"] for i in nxt["items"]} & {i["line_id"] for i in page["items"]})

    # before mapping, every line is unmapped
    un = client.get(f"/api/engagements/{eid}/tb-lines", params={"status": "unmapped"}).json()
    assert un["total"] == len(MYSTERY_HEADS)

    client.post(f"/api/engagements/{eid}/map", json={"encoder": "none"})
    auto = client.get(f"/api/engagements/{eid}/tb-lines", params={"status": "auto"}).json()
    assert auto["total"] == 8
    assert all(i["mapping_status"] == "auto" for i in auto["items"])
    first = auto["items"][0]
    assert first["fsli_code"] and first["mapping_method"]
    assert client.get(
        f"/api/engagements/{eid}/tb-lines", params={"status": "unmapped"}
    ).json()["total"] == 0


def test_api_fs_review_resolve_and_reset(client_api):
    """Unmapped statement labels can be resolved and undone through the API."""
    client, _, tmp_path = client_api
    eid = client.post(
        "/api/engagements", json={"client_code": "T13", "period": "FY25-26"}
    ).json()["engagement_id"]

    bs_rows, pl_rows = schedule_iii_rows(PRESENTED, load_default_taxonomy())
    pl_rows = list(pl_rows) + [("Whimsical Disbursements", None, 99.0, None)]
    pdf = write_fs_pdf(tmp_path / "review.pdf", bs_rows=bs_rows, pl_rows=pl_rows)
    r = client.post(f"/api/engagements/{eid}/ingest/fs", params={"path": str(pdf)})
    assert r.status_code == 201, r.text
    assert r.json()["unmapped"] == 1

    queue = client.get(f"/api/engagements/{eid}/fs-review").json()
    assert len(queue) == 1
    item = queue[0]
    assert item["label"] == "Whimsical Disbursements"
    assert item["statement"] == "P&L"
    assert item["abs_total"] == pytest.approx(99.0)
    assert item["periods"]

    r = client.post(
        f"/api/fs-lines/{item['line_id']}/resolve", json={"fsli_code": "EXP_OTH"}
    )
    assert r.status_code == 200, r.text
    assert r.json()["fsli_code"] == "EXP_OTH"
    assert r.json()["resolved_rows"] >= 1
    assert client.get(f"/api/engagements/{eid}/fs-review").json() == []

    r = client.post(f"/api/fs-lines/{item['line_id']}/reset")
    assert r.status_code == 200, r.text
    assert r.json()["fsli_code"] is None
    assert len(client.get(f"/api/engagements/{eid}/fs-review").json()) == 1

    # resolving to both targets at once is rejected
    r = client.post(
        f"/api/fs-lines/{item['line_id']}/resolve",
        json={"fsli_code": "EXP_OTH", "group_code": "REV_OPERATIONS"},
    )
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_failed"


def test_api_fs_coverage_is_typed(client_api):
    """Coverage returns structured labels, not position-dependent tuples."""
    client, _, tmp_path = client_api
    eid = client.post(
        "/api/engagements", json={"client_code": "T12", "period": "FY25-26"}
    ).json()["engagement_id"]

    bs_rows, pl_rows = schedule_iii_rows(PRESENTED, load_default_taxonomy())
    pl_rows = list(pl_rows) + [("Whimsical Disbursements", None, 99.0, None)]
    pdf = write_fs_pdf(tmp_path / "coverage.pdf", bs_rows=bs_rows, pl_rows=pl_rows)

    r = client.post(
        f"/api/engagements/{eid}/fs/coverage",
        params={"path": str(pdf), "encoder": "none"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["rows"] > 0
    assert 0.0 < body["coverage"] <= 1.0
    assert body["unmapped"] == [{"statement": "P&L", "label": "Whimsical Disbursements"}]
    assert body["unmapped_rows"] == 1


def test_api_path_ingest_is_gated(client_api, monkeypatch):
    """A browser cannot make the server read arbitrary disk paths by default."""
    client, url, tmp_path = client_api
    monkeypatch.setattr("auditiq.api.app.ALLOW_PATH_INGEST", False)
    eid = client.post(
        "/api/engagements", json={"client_code": "T11", "period": "FY25-26"}
    ).json()["engagement_id"]
    r = client.post(f"/api/engagements/{eid}/ingest/tb", params={"path": "/etc/hostname"})
    assert r.status_code == 400
    assert r.json()["error"]["code"] == "bad_request"
    assert "AUDITIQ_ALLOW_PATH_INGEST" in r.json()["error"]["message"]


def test_api_validation_and_routing_errors_use_the_envelope(client_api):
    """FastAPI's own 422s and routing 404s are not special-cased for clients."""
    client, _, _ = client_api

    r = client.post("/api/engagements", json={})
    assert r.status_code == 422
    body = r.json()["error"]
    assert body["code"] == "validation_failed"
    assert body["details"]["errors"]

    r = client.get("/api/engagements/not-an-int")
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "validation_failed"

    r = client.get("/api/no-such-route")
    assert r.status_code == 404
    assert r.json()["error"]["code"] == "not_found"
    assert r.json()["error"]["message"]

    r = client.delete("/api/engagements")
    assert r.status_code == 405
    assert r.json()["error"]["code"] == "bad_request"


def test_api_cors_allows_local_dev_origins(client_api):
    """A Vite dev server on :5173 can call the API; anything else cannot."""
    client, _, _ = client_api

    r = client.options(
        "/api/engagements",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert r.status_code == 200
    assert r.headers["access-control-allow-origin"] == "http://localhost:5173"
    assert "POST" in r.headers["access-control-allow-methods"]

    r = client.get("/api/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in r.headers


def test_api_meta_vocabulary(client_api):
    """Clients read their enums from /api/meta rather than hardcoding them."""
    client, _, _ = client_api
    meta = client.get("/api/meta").json()
    assert meta["version"]
    assert "BS" in meta["statements"] and "P&L" in meta["statements"]
    assert meta["mapping_statuses"] == ["auto", "pending_review", "resolved"]
    assert set(meta["classifications"]) == {"tied", "rounding", "minor", "watch", "material"}
    assert "tb_erp" in meta["document_kinds"]
    assert "zoho" in meta["erp_sources"]
    assert meta["features"]["path_ingest"] is True


def test_api_reports_schema_drift(tmp_path, monkeypatch):
    """A stale database returns an actionable 503, not a bare OperationalError."""
    url = f"sqlite:///{tmp_path / 'drift.db'}"
    monkeypatch.setattr(db, "DATABASE_URL", url)
    monkeypatch.setattr(db, "_engine", None)
    monkeypatch.setattr(db, "_session_factory", None)
    monkeypatch.setattr(db, "_schema_checked", set())
    monkeypatch.setattr("auditiq.settings.DATABASE_URL", url)

    # A database created before the P3.1 columns: fs_line without group_code.
    with sqlite3.connect(tmp_path / "drift.db") as con:
        con.execute("CREATE TABLE fs_line (id INTEGER PRIMARY KEY, fsli_code VARCHAR)")

    client = TestClient(create_app())
    response = client.get("/api/engagements")

    assert response.status_code == 503
    body = response.json()["error"]
    assert body["code"] == "schema_drift"
    assert "fs_line.group_code" in body["message"]
    assert "store reset" in body["details"]["fix"]

