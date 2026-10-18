"""API end-to-end: the full pipeline driven through HTTP on an isolated store.

Upload a Zoho-layout TB -> map (dictionary only) -> approve + reset mappings ->
upload/generate a draft FS -> materiality -> reconcile (twice) -> exceptions ->
fs-review. Mirrors the CLI e2e gate at the API level; no browser, no node.
"""
from __future__ import annotations

import io

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook

from _draft_fs import schedule_iii_rows, write_fs_pdf

from auditiq.api import create_app
from auditiq.core import load_default_taxonomy
from auditiq.store import db, init_db

# Deterministic vocabulary: these heads resolve through the alias dictionary.
BASE = {
    "Sundry Debtors": ("AST_TR", 1000.0),          # Dr
    "Inventory": ("AST_INV", 700.0),               # Dr
    "Cash in Hand": ("AST_CASH", 500.0),           # Dr
    "Cost of Materials Consumed": ("EXP_MAT", 1200.0),  # Dr
    "Other Expenses": ("EXP_OTH", 800.0),          # Dr
    "Sundry Creditors": ("LIA_TP", -700.0),        # Cr
    "Share Capital": ("EQ_SC", -1500.0),           # Cr
    "Revenue from Operations": ("INC_REV_SALES", -2000.0),  # Cr
    # Two heads the cascade cannot accept; balanced against each other.
    "Zzz Mystery Ledger A": (None, 123.0),         # Dr
    "Zzz Mystery Ledger B": (None, -123.0),        # Cr
}
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


def _tb_xlsx_bytes() -> bytes:
    rows = [["Test Co Limited"], ["Account", "Account Code", "Account Type", "Debit", "Credit"]]
    for name, (_code, amount) in BASE.items():
        if amount >= 0:
            row = [name, "", "", amount, None]
        else:
            row = [name, "", "", None, -amount]
        rows.append(row)
    debit = sum(a for _, a in BASE.values() if a > 0)
    credit = sum(-a for _, a in BASE.values() if a < 0)
    rows.append(["Total", "", "", debit, credit])
    workbook = Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(list(row))
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


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
    assert r.status_code == 200, r.text
    eid = r.json()["engagement_id"]
    assert r.json()["intake_status"] == "intake"

    # -- ingest TB (upload) --------------------------------------------------
    r = client.post(
        f"/api/engagements/{eid}/ingest/tb",
        files={"file": ("tb.xlsx", _tb_xlsx_bytes(), "application/vnd.openxmlformats")},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["lines"] == len(BASE)
    assert body["balanced"]

    # -- map (dictionary only) ----------------------------------------------
    r = client.post(f"/api/engagements/{eid}/map", json={"encoder": "none"})
    assert r.status_code == 200, r.text
    summary = r.json()
    assert summary["lines"] == len(BASE)
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

    # invalid target -> 400
    r = client.post("/api/mappings/resolve", json={"line_id": pending[1]["line_id"], "fsli_code": "NOPE"})
    assert r.status_code == 400
    assert "unknown FSLI" in r.json()["detail"]

    # -- draft FS ------------------------------------------------------------
    draft = _draft_fs_pdf(tmp_path)
    r = client.post(f"/api/engagements/{eid}/ingest/fs", params={"path": str(draft)})
    assert r.status_code == 200, r.text
    ingest_body = r.json()
    assert ingest_body["mapped_weighted"] == len(PRESENTED)

    # fs-review queue is empty (all labels considered)
    assert client.get(f"/api/engagements/{eid}/fs-review").json() == []

    # -- materiality: recon fails loudly before it is set ----------------------
    r = client.post(f"/api/engagements/{eid}/recon/run", json={})
    assert r.status_code == 400
    assert "materiality" in r.json()["detail"]

    r = client.get(f"/api/engagements/{eid}/materiality")
    suggestion = r.json()
    assert suggestion["suggestion"]["suggested"] > 0

    r = client.post(f"/api/engagements/{eid}/materiality", json={"value": 100.0, "basis": "test"})
    assert r.status_code == 200 and r.json()["materiality_value"] == 100.0

    # -- baseline recon: everything the client presented ties ----------------
    r = client.post(f"/api/engagements/{eid}/recon/run", json={})
    assert r.status_code == 200, r.text
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
    r = client.post(f"/api/mappings/{pending[0]['line_id']}/reset")
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
    assert client.get("/api/engagements/9999").status_code == 404
    eid = client.post("/api/engagements", json={"client_code": "T08", "period": "FY25-26"}).json()["engagement_id"]
    bad = client.get(f"/api/engagements/{eid}/mappings", params={"status": "bogus"})
    assert bad.status_code == 400


def test_api_mapped_exposure_lines(tmp_path, monkeypatch):
    """Side A: accepted books contain the mystery head only after approval."""
    pass
