"""AuditIQ JSON API (web harness).

A thin adapter: the domain services under ``ingest.*`` and ``reconciliation.*``
hold all business rules; routes only translate HTTP in/out and never touch the
store directly. The same vices as the CLI — engagement-scoped, deterministic by
default, LLM strictly opt-in.
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, FastAPI, HTTPException, UploadFile
from pydantic import BaseModel, Field

from .. import __version__
from ..ingest.erp import ADAPTERS, ingest_tb
from ..ingest.fs import fs_coverage, ingest_fs, list_unmapped_fs, resolve_fs_line, reset_fs_line
from ..ingest.prepare import (
    bulk_resolve,
    list_pending,
    list_resolved,
    map_engagement,
    reset_mapping,
    resolve_mapping,
)
from ..reconciliation import (
    MaterialityError,
    explain_unit,
    latest_run,
    run_recon,
    set_materiality,
    suggest_for_engagement,
)
from ..settings import UPLOAD_DIR, ensure_dirs
from ..store.queries import (
    create_engagement,
    dispose_exception,
    engagement_summary,
    list_engagements,
    list_exceptions,
)


# -- helpers ---------------------------------------------------------------


def _data(obj):
    """Plain-JSON conversion for service results (dataclasses, lists, tuples).

    Public ``@property`` accessors are included, so derived values such as
    ``FsIngestResult.mapped_weighted`` or ``EngagementSummary.intake_status``
    stay available to clients; the person consuming the API should not have to
    compute them.
    """
    if is_dataclass(obj):
        out = asdict(obj)
        for name, attr in vars(type(obj)).items():
            if isinstance(attr, property) and not name.startswith("_"):
                try:
                    out[name] = attr.fget(obj)
                except Exception:  # a property may legitimately fail on partial rows
                    out[name] = None
        return out
    if isinstance(obj, (list, tuple)):
        return [_data(item) for item in obj]
    return obj


def api_error(exc: Exception, status: int = 400) -> HTTPException:
    return HTTPException(status_code=status, detail=str(exc))


def _fail(message: str):
    raise ValueError(message)


def _engagement(engagement_id: int):
    try:
        return engagement_summary(engagement_id)
    except ValueError as exc:
        raise api_error(exc, status=404) from exc


def _save_upload(file: UploadFile) -> Path:
    """Store an uploaded artefact under data/uploads and return its path."""
    ensure_dirs()
    digest = hashlib.sha256()
    handle = file.file
    handle.seek(0)
    while True:
        chunk = handle.read(65536)
        if not chunk:
            break
        digest.update(chunk)
    name = Path(file.filename or "uploaded.bin").name
    path = UPLOAD_DIR / f"{digest.hexdigest()[:16]}-{name}"
    handle.seek(0)
    with open(path, "wb") as sink:
        while True:
            chunk = handle.read(65536)
            if not chunk:
                break
            sink.write(chunk)
    return path


def _source(file: Optional[UploadFile], path: Optional[str]) -> Path:
    """Upload (prefer) or server-side path."""
    if file is not None:
        return _save_upload(file)
    if path:
        return _resolve_path(path)
    _fail("provide an uploaded file or a 'path' parameter")


def _resolve_path(path: str) -> Path:
    candidate = Path(path)
    if not candidate.exists():
        raise ValueError(f"file not found: {path}")
    return candidate


def _parse_statements(value: Optional[str]) -> Optional[tuple[str, ...]]:
    if not value or value.strip().lower() == "all":
        return None
    out = []
    for part in value.split(","):
        token = part.strip().upper()
        if token in ("PL", "P&L", "PNL", "PLL"):
            out.append("P&L")
        elif token:
            out.append(token)
    return tuple(dict.fromkeys(out)) if out else None


# -- request bodies ---------------------------------------------------------


class CreateEngagementIn(BaseModel):
    client_code: str
    period: str
    basis: str = "Standalone"
    client_name: str = ""


class MapIn(BaseModel):
    encoder: Optional[str] = None
    use_llm: bool = False


class ResolveIn(BaseModel):
    line_id: int
    fsli_code: str
    reviewer: str = ""


class BulkResolveIn(BaseModel):
    pairs: list[tuple[int, str]] = Field(default_factory=list)
    reviewer: str = ""


class MaterialityIn(BaseModel):
    value: float
    basis: str = ""


class ReconRunIn(BaseModel):
    materiality: Optional[float] = None
    pm: float = 0.75
    rounding_decimals: int = 2
    statements: Optional[str] = None  # "BS", "P&L", "BS,P&L" or "all"
    side_b_period: Optional[str] = None
    no_persist: bool = False


class FsResolveIn(BaseModel):
    fsli_code: Optional[str] = None
    group_code: Optional[str] = None


class DisposeIn(BaseModel):
    status: str
    note: str = ""


# -- routers ----------------------------------------------------------------


def engagements_router() -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/health")
    def health():
        return {"status": "ok", "version": __version__}

    @router.get("/engagements")
    def engagements():
        return _data(list_engagements())

    @router.post("/engagements")
    def engagements_create(body: CreateEngagementIn):
        try:
            return _data(create_engagement(**body.model_dump()))
        except ValueError as exc:
            raise api_error(exc) from exc

    @router.get("/engagements/{engagement_id}")
    def engagement_get(engagement_id: int):
        return _data(_engagement(engagement_id))

    @router.post("/engagements/{engagement_id}/ingest/tb")
    def ingest_tb_route(engagement_id: int, file: Optional[UploadFile] = None, path: Optional[str] = None):
        engagement = _engagement(engagement_id)
        try:
            result = ingest_tb(
                _source(file, path),
                client_code=engagement.client_code,
                period=engagement.period,
                basis=engagement.basis,
                client_name=engagement.client_name,
            )
        except (FileNotFoundError, ValueError) as exc:
            raise api_error(exc) from exc
        return _data(result)

    @router.post("/engagements/{engagement_id}/ingest/fs")
    def ingest_fs_route(
        engagement_id: int,
        file: Optional[UploadFile] = None,
        path: Optional[str] = None,
        kind: Optional[str] = None,
        unit: Optional[str] = None,
    ):
        engagement = _engagement(engagement_id)
        try:
            result = ingest_fs(
                _source(file, path),
                client_code=engagement.client_code,
                period=engagement.period,
                basis=engagement.basis,
                kind=kind,
                client_name=engagement.client_name,
                unit=unit,
            )
        except (FileNotFoundError, ValueError, RuntimeError) as exc:
            raise api_error(exc) from exc
        return _data(result)

    @router.post("/engagements/{engagement_id}/fs/coverage")
    def coverage_route(
        engagement_id: int,
        file: Optional[UploadFile] = None,
        path: Optional[str] = None,
        kind: Optional[str] = None,
        encoder: Optional[str] = None,
    ):
        engagement = _engagement(engagement_id)
        try:
            report = fs_coverage(
                _source(file, path),
                kind=kind,
                client=engagement.client_code,
                encoder_kind=encoder,
            )
        except (FileNotFoundError, ValueError, RuntimeError) as exc:
            raise api_error(exc) from exc
        return _data(report)

    @router.post("/engagements/{engagement_id}/map")
    def map_route(engagement_id: int, body: MapIn):
        try:
            summary = map_engagement(
                engagement_id,
                encoder_kind=body.encoder,
                use_llm=body.use_llm,
            )
        except (RuntimeError, ValueError) as exc:
            raise api_error(exc) from exc
        return _data(summary)

    @router.post("/engagements/{engagement_id}/materiality")
    def materiality_set(engagement_id: int, body: MaterialityIn):
        try:
            row = set_materiality(engagement_id, body.value, body.basis)
        except ValueError as exc:
            raise api_error(exc) from exc
        return _data(row)

    @router.get("/engagements/{engagement_id}/materiality")
    def materiality_get(engagement_id: int):
        summary = _engagement(engagement_id)
        try:
            suggestion = suggest_for_engagement(engagement_id)
        except ValueError as exc:
            raise api_error(exc) from exc
        return {
            "value": summary.materiality_value,
            "basis": summary.materiality_basis,
            "suggestion": suggestion,
        }

    @router.post("/engagements/{engagement_id}/recon/run")
    def recon_run_route(engagement_id: int, body: ReconRunIn):
        try:
            summary = run_recon(
                engagement_id,
                materiality=body.materiality,
                pm_ratio=body.pm,
                rounding_decimals=body.rounding_decimals,
                statements=_parse_statements(body.statements),
                persist=not body.no_persist,
                side_b_period=body.side_b_period,
            )
        except (MaterialityError, ValueError) as exc:
            raise api_error(exc) from exc
        return _data(summary)

    @router.get("/engagements/{engagement_id}/recon")
    def recon_latest_route(engagement_id: int):
        _engagement(engagement_id)
        run, lines = latest_run(engagement_id)
        if run is None:
            raise api_error(ValueError("no reconciliation run yet; POST .../recon/run first"), status=404)
        return {"run": _data(run), "lines": _data(lines)}

    @router.get("/engagements/{engagement_id}/recon/explain/{unit_code}")
    def recon_explain_route(engagement_id: int, unit_code: str):
        run, line = explain_unit(engagement_id, unit_code)
        if run is None:
            raise api_error(ValueError("no reconciliation run yet"), status=404)
        if line is None:
            raise api_error(ValueError(f"unit '{unit_code}' is not in the latest run"), status=404)
        return {"run": _data(run), "line": _data(line)}

    @router.get("/engagements/{engagement_id}/exceptions")
    def exceptions_route(engagement_id: int, status: Optional[str] = None):
        _engagement(engagement_id)
        return _data(list_exceptions(engagement_id, status=status))

    return router


def review_router() -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get("/engagements/{engagement_id}/mappings")
    def mappings_route(engagement_id: int, status: str = "pending_review"):
        _engagement(engagement_id)
        if status in ("pending", "pending_review"):
            return _data(list_pending(engagement_id))
        if status in ("resolved", "reviewed"):
            return _data(list_resolved(engagement_id))
        raise api_error(ValueError("status must be pending_review or resolved"))

    @router.post("/mappings/resolve")
    def resolve_route(body: ResolveIn):
        try:
            return _data(resolve_mapping(body.line_id, body.fsli_code, reviewer=body.reviewer))
        except ValueError as exc:
            raise api_error(exc) from exc

    @router.post("/mappings/resolve-bulk")
    def bulk_route(body: BulkResolveIn):
        results, failures = bulk_resolve(body.pairs, reviewer=body.reviewer)
        return {"resolved": _data(results), "failures": failures}

    @router.post("/mappings/{line_id}/reset")
    def reset_route(line_id: int):
        try:
            return _data(reset_mapping(line_id))
        except ValueError as exc:
            raise api_error(exc) from exc

    @router.get("/engagements/{engagement_id}/fs-review")
    def fs_review_route(engagement_id: int):
        _engagement(engagement_id)
        return _data(list_unmapped_fs(engagement_id))

    @router.post("/fs-lines/{line_id}/resolve")
    def fs_resolve_route(line_id: int, body: FsResolveIn):
        try:
            return _data(resolve_fs_line(line_id, fsli_code=body.fsli_code, group_code=body.group_code))
        except ValueError as exc:
            raise api_error(exc) from exc

    @router.post("/fs-lines/{line_id}/reset")
    def fs_reset_route(line_id: int):
        try:
            return _data(reset_fs_line(line_id))
        except ValueError as exc:
            raise api_error(exc) from exc

    @router.post("/exceptions/{exception_id}/dispose")
    def dispose_route(exception_id: int, body: DisposeIn):
        try:
            return _data(dispose_exception(exception_id, body.status, note=body.note))
        except ValueError as exc:
            raise api_error(exc) from exc

    return router


def reference_router() -> APIRouter:
    from ..core.groups import load_default_groups
    from ..core.taxonomy import load_default_taxonomy

    router = APIRouter(prefix="/api")

    @router.get("/taxonomy")
    def taxonomy_route(statement: Optional[str] = None, search: Optional[str] = None):
        taxonomy = load_default_taxonomy()
        items = list(taxonomy)
        if statement:
            needle = statement.strip().lower()
            items = [i for i in items if needle in i.statement.lower()]
        if search:
            items = taxonomy.search(search)
        return _data(list(items))

    @router.get("/groups")
    def groups_route():
        return _data(load_default_groups())

    @router.get("/erp-sources")
    def sources_route():
        return {"sources": sorted(ADAPTERS)}

    return router


def create_app() -> FastAPI:
    app = FastAPI(
        title="AuditIQ Core",
        version=__version__,
        description="Trial-balance ingestion, FS reconciliation and review — deterministic by default.",
    )
    app.include_router(engagements_router())
    app.include_router(review_router())
    app.include_router(reference_router())

    @app.get("/")
    def root():
        return {"service": "auditiq", "version": __version__, "docs": "/docs", "api": "/api/health"}

    return app


__all__ = ["create_app"]
