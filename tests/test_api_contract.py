"""Contract guard: the OpenAPI document is the frontend's source of truth.

A generated client silently degrades when a route loses its typed response, its
summary, or its documented error envelope. These tests drive the same
``app.openapi()`` a codegen tool would and fail loudly instead.
"""
from __future__ import annotations

import json

import pytest

from auditiq.api import create_app

METHODS = {"get", "post", "put", "patch", "delete"}


@pytest.fixture(scope="module")
def spec() -> dict:
    return create_app().openapi()


def _operations(spec: dict):
    for path, item in spec["paths"].items():
        for method, op in item.items():
            if method in METHODS:
                yield method.upper(), path, op


def _refs(node):
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "$ref" and isinstance(value, str):
                yield value
            else:
                yield from _refs(value)
    elif isinstance(node, list):
        for item in node:
            yield from _refs(item)


def _json_schema(response: dict) -> dict:
    return response.get("content", {}).get("application/json", {}).get("schema", {})


def test_every_route_is_typed_and_documented(spec):
    """No bare ``{}`` responses: every route states a summary, tag and schema."""
    for method, path, op in _operations(spec):
        assert op.get("summary"), f"{method} {path} has no summary"
        assert op.get("tags"), f"{method} {path} has no tags"
        success = {c: r for c, r in op["responses"].items() if c.startswith("2")}
        assert success, f"{method} {path} declares no success response"
        for code, response in success.items():
            assert _json_schema(response), f"{method} {path} {code} is untyped"


def test_success_models_all_resolve(spec):
    """Every ``$ref`` in a 2xx response points at a declared component."""
    declared = set(spec["components"]["schemas"])
    for method, path, op in _operations(spec):
        for code, response in op["responses"].items():
            if code.startswith("2"):
                for ref in _refs(_json_schema(response)):
                    name = ref.rsplit("/", 1)[-1]
                    assert name in declared, f"{method} {path} {code}: {ref}"


def test_errors_use_one_uniform_envelope(spec):
    """Every declared error is ``ErrorOut``, so a client parses exactly one shape."""
    seen: set[str] = set()
    for method, path, op in _operations(spec):
        for code, response in op["responses"].items():
            if code.startswith("2"):
                continue
            schema = _json_schema(response)
            name = schema.get("$ref", "").rsplit("/", 1)[-1]
            assert name == "ErrorOut", f"{method} {path} {code} -> {schema}"
            seen.add(code)
    assert {"400", "404", "409", "422", "500", "503"} <= seen


def test_error_envelope_shape(spec):
    envelope = spec["components"]["schemas"]["ErrorOut"]["properties"]
    assert set(envelope) == {"error"}
    body = spec["components"]["schemas"]["ErrorBody"]["properties"]
    assert set(body) == {"code", "message", "details"}
    assert "enum" in body["code"], "error codes must be a closed enumeration"


def test_creation_routes_return_201(spec):
    for path, method in [
        ("/api/engagements", "post"),
        ("/api/engagements/{engagement_id}/ingest/tb", "post"),
        ("/api/engagements/{engagement_id}/ingest/fs", "post"),
        ("/api/engagements/{engagement_id}/recon/run", "post"),
    ]:
        op = spec["paths"][path][method]
        assert "201" in op["responses"], f"{method} {path} should answer 201"
        assert "200" not in op["responses"], f"{method} {path} should not double-declare 200"


def test_lists_are_bare_arrays(spec):
    """No ``{items, count}`` envelope — list endpoints return an array."""
    for path in [
        "/api/engagements",
        "/api/engagements/{engagement_id}/documents",
        "/api/engagements/{engagement_id}/fs-review",
        "/api/engagements/{engagement_id}/exceptions",
        "/api/taxonomy",
        "/api/groups",
    ]:
        schema = _json_schema(spec["paths"][path]["get"]["responses"]["200"])
        assert schema.get("type") == "array", f"GET {path} is not a bare array"


def test_paged_endpoint_declares_its_window(spec):
    schema = _json_schema(
        spec["paths"]["/api/engagements/{engagement_id}/tb-lines"]["get"]["responses"]["200"]
    )
    assert schema.get("$ref", "").endswith("/PageOut")
    assert set(spec["components"]["schemas"]["PageOut"]["properties"]) == {
        "items",
        "total",
        "limit",
        "offset",
    }


def test_derived_service_properties_are_declared_fields(spec):
    """Values the services expose as ``@property`` still appear in the contract."""
    def props(name: str) -> set[str]:
        return set(spec["components"]["schemas"][name]["properties"])

    assert {"abs_amount", "lines"} <= props("PendingHeadOut")
    assert "resolution_rate" in props("MappingSummaryOut")
    assert "intake_status" in props("EngagementSummaryOut")
    assert {"worst", "status", "reconciled", "tolerance"} <= props("ReconOut")
    assert {"unit_code", "name", "statement", "is_group"} <= props("ReconLineBriefOut")
    assert "mapped_weighted" in props("FsIngestOut")
    assert "coverage" in props("FsCoverageOut")


def test_meta_surfaces_the_vocabulary(spec):
    meta = set(spec["components"]["schemas"]["MetaOut"]["properties"])
    assert {
        "statements",
        "bases",
        "units",
        "encoder_kinds",
        "mapping_statuses",
        "mapping_methods",
        "fs_measures",
        "classifications",
        "severities",
        "exception_kinds",
        "exception_statuses",
        "document_kinds",
        "erp_sources",
        "cors_origins",
        "features",
    } <= meta


def test_every_api_route_is_tagged_and_grouped(spec):
    tags = {t["name"] for t in spec["tags"]}
    for method, path, op in _operations(spec):
        if not path.startswith("/api/"):
            continue
        assert set(op["tags"]) <= tags, f"{method} {path} uses an undeclared tag"


def test_openapi_is_deterministic():
    """Two builds must serialise identically, or codegen output churns."""
    first = json.dumps(create_app().openapi(), sort_keys=True)
    second = json.dumps(create_app().openapi(), sort_keys=True)
    assert first == second
