"""AuditIQ HTTP API.

A thin adapter: the domain services under ``ingest.*``, ``reconciliation.*`` and
``store.queries`` hold all business rules; routes only translate HTTP in/out and
never touch the store directly. The same vices as the CLI — engagement-scoped,
deterministic by default, LLM strictly opt-in.

Every route declares a typed ``response_model`` and a documented error envelope,
so ``/openapi.json`` is a contract a separate frontend can codegen against.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, FastAPI, Query, Request, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .. import __version__
from ..core.enums import (
    DocumentKind,
    MappingMethod,
    MappingStatus,
    SourceSystem,
    Statement,
)
from ..core.units import UNIT_FACTORS
from ..ingest.erp import ADAPTERS, ingest_tb
from ..ingest.fs import (
    MEASURE_FACE,
    MEASURE_NOTE_TOTAL,
    MEASURE_SUBTOTAL,
    fs_coverage,
    ingest_fs,
    list_unmapped_fs,
    reset_fs_line,
    resolve_fs_line,
)
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
from ..reconciliation.materiality import (
    MATERIAL,
    MINOR,
    ROUNDING,
    SEVERITY_NONE,
    TIED,
    WATCH,
)
from ..settings import (
    ALLOW_PATH_INGEST,
    CORS_ORIGINS,
    UPLOAD_DIR,
    ensure_dirs,
)
from ..store import SchemaDriftError
from ..store.queries import (
    create_engagement,
    dispose_exception,
    engagement_summary,
    list_documents,
    list_engagements,
    list_exceptions,
    list_tb_lines,
    mapping_counts,
)
from .schemas import (
    BulkResolveIn,
    BulkResolveOut,
    CreateEngagementIn,
    DisposeIn,
    DocumentOut,
    EngagementInfoOut,
    EngagementSummaryOut,
    ErpSourcesOut,
    ErrorOut,
    ExceptionOut,
    FindingOut,
    FsCoverageOut,
    FsIngestOut,
    FsResolveIn,
    FsResolveOut,
    FsUnmappedOut,
    GroupOut,
    HealthOut,
    MapIn,
    MappingCountsOut,
    MappingSummaryOut,
    MaterialityIn,
    MaterialityOut,
    MaterialitySuggestionOut,
    MetaOut,
    PageOut,
    PendingHeadOut,
    ReconExplainOut,
    ReconLatestOut,
    ReconLineBriefOut,
    ReconOut,
    ReconRunIn,
    ResolveIn,
    ResolutionOut,
    RootOut,
    RunOut,
    StoredLineOut,
    TbIngestOut,
    TbLineOut,
    TaxonomyItemOut,
    ValidationIssueOut,
)


# -- errors ----------------------------------------------------------------

ERROR_RESPONSES: dict[int | str, dict] = {
    400: {"model": ErrorOut, "description": "Malformed or unsupported request."},
    404: {"model": ErrorOut, "description": "No such engagement, unit or run."},
    409: {"model": ErrorOut, "description": "Precondition not met (e.g. materiality unset)."},
    422: {"model": ErrorOut, "description": "Request failed validation."},
    500: {"model": ErrorOut, "description": "Unexpected server error."},
    503: {"model": ErrorOut, "description": "The database schema is out of date."},
}

# Read-only routes cannot 404/409, but they can still fail validation, drift or
# blow up. Declaring those explicitly stops FastAPI from emitting its own
# ``HTTPValidationError`` shape for query parameters.
READ_RESPONSES: dict[int | str, dict] = {
    key: ERROR_RESPONSES[key] for key in (422, 500, 503)
}

_STATUS_FOR_CODE = {
    "bad_request": 400,
    "validation_failed": 422,
    "not_found": 404,
    "materiality_unset": 409,
    "ingest_failed": 422,
    "schema_drift": 503,
    "internal_error": 500,
}


class ApiError(Exception):
    """A domain failure translated into the uniform error envelope."""

    def __init__(
        self,
        code: str,
        message: str,
        status: Optional[int] = None,
        details: Optional[dict] = None,
    ) -> None:
        if code not in _STATUS_FOR_CODE:
            # A typo would otherwise ship an out-of-enum code to clients.
            raise ValueError(f"unknown API error code {code!r}")
        self.code = code
        self.message = message
        self.status = status or _STATUS_FOR_CODE[code]
        self.details = details or {}
        super().__init__(message)


def error_body(code: str, message: str, details: Optional[dict] = None) -> dict:
    return {"error": {"code": code, "message": message, "details": details or {}}}


def _fail(message: str, code: str = "validation_failed"):
    raise ApiError(code, message)


def _engagement(engagement_id: int):
    try:
        return engagement_summary(engagement_id)
    except ValueError as exc:
        raise ApiError("not_found", str(exc)) from exc


# -- upload helpers --------------------------------------------------------


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
    """Uploaded file, or a server-side path when that is explicitly enabled."""
    if file is not None:
        return _save_upload(file)
    if path:
        if not ALLOW_PATH_INGEST:
            _fail(
                "server-side 'path' ingestion is disabled; upload the file instead "
                "or set AUDITIQ_ALLOW_PATH_INGEST=1",
                code="bad_request",
            )
        candidate = Path(path)
        if not candidate.exists():
            raise ApiError("not_found", f"file not found: {path}")
        return candidate
    _fail("provide an uploaded file (multipart 'file') or a 'path' parameter")


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


# -- routers ---------------------------------------------------------------


def engagements_router() -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get(
        "/health",
        response_model=HealthOut,
        summary="Liveness and version",
        tags=["meta"],
        responses=READ_RESPONSES,
    )
    def health():
        return HealthOut(status="ok", version=__version__)

    @router.get(
        "/meta",
        response_model=MetaOut,
        summary="Enum vocabulary and server capabilities",
        tags=["meta"],
        responses=READ_RESPONSES,
    )
    def meta():
        return MetaOut(
            version=__version__,
            statements=[s.value for s in Statement],
            bases=["Standalone", "Consolidated"],
            units=sorted(UNIT_FACTORS),
            encoder_kinds=["auto", "none", "tfidf", "sbert"],
            mapping_statuses=[s.value for s in MappingStatus],
            mapping_methods=[m.value for m in MappingMethod],
            fs_measures=[MEASURE_FACE, MEASURE_SUBTOTAL, MEASURE_NOTE_TOTAL],
            classifications=[TIED, ROUNDING, MINOR, WATCH, MATERIAL],
            severities=[SEVERITY_NONE, MINOR, WATCH, MATERIAL],
            exception_kinds=["tieout"],
            exception_statuses=["open", "explained", "accepted"],
            document_kinds=[k.value for k in DocumentKind],
            erp_sources=sorted(ADAPTERS),
            cors_origins=CORS_ORIGINS,
            features={
                "path_ingest": ALLOW_PATH_INGEST,
                "llm": True,
            },
        )

    @router.get(
        "/engagements",
        response_model=list[EngagementSummaryOut],
        summary="List engagements with pipeline status",
        tags=["engagements"],
        responses=ERROR_RESPONSES,
    )
    def engagements():
        return list_engagements()

    @router.post(
        "/engagements",
        response_model=EngagementSummaryOut,
        status_code=201,
        summary="Create (or reopen) an engagement",
        tags=["engagements"],
        responses=ERROR_RESPONSES,
    )
    def engagements_create(body: CreateEngagementIn):
        try:
            return create_engagement(**body.model_dump())
        except ValueError as exc:
            raise ApiError("validation_failed", str(exc)) from exc

    @router.get(
        "/engagements/{engagement_id}",
        response_model=EngagementSummaryOut,
        summary="One engagement's status",
        tags=["engagements"],
        responses=ERROR_RESPONSES,
    )
    def engagement_get(engagement_id: int):
        return _engagement(engagement_id)

    @router.get(
        "/engagements/{engagement_id}/documents",
        response_model=list[DocumentOut],
        summary="Documents ingested for an engagement",
        tags=["ingest"],
        responses=ERROR_RESPONSES,
    )
    def documents_route(engagement_id: int, kind: Optional[str] = None):
        _engagement(engagement_id)
        return list_documents(engagement_id, kind=kind)

    @router.get(
        "/engagements/{engagement_id}/tb-lines",
        response_model=PageOut,
        summary="Paged trial-balance lines with mapping state",
        tags=["ingest"],
        responses=ERROR_RESPONSES,
    )
    def tb_lines_route(
        engagement_id: int,
        limit: int = Query(100, ge=1, le=1000),
        offset: int = Query(0, ge=0),
        status: Optional[str] = Query(
            None, description="Filter by mapping status, or 'unmapped'."
        ),
    ):
        _engagement(engagement_id)
        page = list_tb_lines(engagement_id, limit=limit, offset=offset, status=status)
        return PageOut(
            items=[TbLineOut.model_validate(item) for item in page.items],
            total=page.total,
            limit=page.limit,
            offset=page.offset,
        )

    @router.post(
        "/engagements/{engagement_id}/ingest/tb",
        response_model=TbIngestOut,
        status_code=201,
        summary="Ingest an ERP trial balance",
        tags=["ingest"],
        responses=ERROR_RESPONSES,
    )
    def ingest_tb_route(
        engagement_id: int,
        file: Optional[UploadFile] = None,
        path: Optional[str] = None,
    ):
        engagement = _engagement(engagement_id)
        try:
            return ingest_tb(
                _source(file, path),
                client_code=engagement.client_code,
                period=engagement.period,
                basis=engagement.basis,
                client_name=engagement.client_name,
            )
        except (FileNotFoundError, ValueError) as exc:
            raise ApiError("ingest_failed", str(exc)) from exc

    @router.post(
        "/engagements/{engagement_id}/ingest/fs",
        response_model=FsIngestOut,
        status_code=201,
        summary="Ingest draft financial statements (Side B)",
        tags=["ingest"],
        responses=ERROR_RESPONSES,
    )
    def ingest_fs_route(
        engagement_id: int,
        file: Optional[UploadFile] = None,
        path: Optional[str] = None,
        kind: Optional[str] = None,
        unit: Optional[str] = None,
        use_llm: bool = False,
    ):
        engagement = _engagement(engagement_id)
        try:
            return ingest_fs(
                _source(file, path),
                client_code=engagement.client_code,
                period=engagement.period,
                basis=engagement.basis,
                kind=kind,
                client_name=engagement.client_name,
                unit=unit,
                use_llm=use_llm,
            )
        except (FileNotFoundError, ValueError, RuntimeError) as exc:
            raise ApiError("ingest_failed", str(exc)) from exc

    @router.post(
        "/engagements/{engagement_id}/fs/coverage",
        response_model=FsCoverageOut,
        summary="Label coverage of a financial-statement file (no persistence)",
        tags=["ingest"],
        responses=ERROR_RESPONSES,
    )
    def coverage_route(
        engagement_id: int,
        file: Optional[UploadFile] = None,
        path: Optional[str] = None,
        kind: Optional[str] = None,
        encoder: Optional[str] = None,
        use_llm: bool = False,
    ):
        engagement = _engagement(engagement_id)
        try:
            return fs_coverage(
                _source(file, path),
                kind=kind,
                client=engagement.client_code,
                encoder_kind=encoder,
                use_llm=use_llm,
            )
        except (FileNotFoundError, ValueError, RuntimeError) as exc:
            raise ApiError("ingest_failed", str(exc)) from exc

    @router.post(
        "/engagements/{engagement_id}/map",
        response_model=MappingSummaryOut,
        summary="Run the FSLI mapping cascade",
        tags=["mapping"],
        responses=ERROR_RESPONSES,
    )
    def map_route(engagement_id: int, body: MapIn):
        _engagement(engagement_id)
        try:
            return map_engagement(
                engagement_id,
                encoder_kind=body.encoder,
                use_llm=body.use_llm,
            )
        except (RuntimeError, ValueError) as exc:
            raise ApiError("validation_failed", str(exc)) from exc

    @router.post(
        "/engagements/{engagement_id}/materiality",
        response_model=EngagementInfoOut,
        summary="Set engagement materiality",
        tags=["materiality"],
        responses=ERROR_RESPONSES,
    )
    def materiality_set(engagement_id: int, body: MaterialityIn):
        try:
            return set_materiality(engagement_id, body.value, body.basis)
        except ValueError as exc:
            raise ApiError("validation_failed", str(exc)) from exc

    @router.get(
        "/engagements/{engagement_id}/materiality",
        response_model=MaterialityOut,
        summary="Current materiality and the revenue-based suggestion",
        tags=["materiality"],
        responses=ERROR_RESPONSES,
    )
    def materiality_get(engagement_id: int):
        summary = _engagement(engagement_id)
        suggestion = None
        try:
            raw = suggest_for_engagement(engagement_id)
        except ValueError:
            raw = None
        if raw and raw.get("suggested"):
            suggestion = MaterialitySuggestionOut.model_validate(raw)
        return MaterialityOut(
            value=summary.materiality_value,
            basis=summary.materiality_basis,
            suggestion=suggestion,
        )

    @router.post(
        "/engagements/{engagement_id}/recon/run",
        response_model=ReconOut,
        status_code=201,
        summary="Reconcile books (Side A) against the draft statements (Side B)",
        tags=["reconciliation"],
        responses=ERROR_RESPONSES,
    )
    def recon_run_route(engagement_id: int, body: ReconRunIn):
        _engagement(engagement_id)
        try:
            return run_recon(
                engagement_id,
                materiality=body.materiality,
                pm_ratio=body.pm,
                rounding_decimals=body.rounding_decimals,
                statements=_parse_statements(body.statements),
                persist=not body.no_persist,
                side_b_period=body.side_b_period,
            )
        except MaterialityError as exc:
            raise ApiError("materiality_unset", str(exc)) from exc
        except ValueError as exc:
            raise ApiError("validation_failed", str(exc)) from exc

    @router.get(
        "/engagements/{engagement_id}/recon",
        response_model=ReconLatestOut,
        summary="The latest persisted reconciliation run",
        tags=["reconciliation"],
        responses=ERROR_RESPONSES,
    )
    def recon_latest_route(engagement_id: int):
        _engagement(engagement_id)
        run, lines = latest_run(engagement_id)
        if run is None:
            raise ApiError("not_found", "no reconciliation run yet; POST .../recon/run first")
        return ReconLatestOut(
            run=RunOut.model_validate(run),
            lines=[StoredLineOut.model_validate(line) for line in lines],
        )

    @router.get(
        "/engagements/{engagement_id}/recon/explain/{unit_code}",
        response_model=ReconExplainOut,
        summary="Explain one reconciled unit (attribution + refs)",
        tags=["reconciliation"],
        responses=ERROR_RESPONSES,
    )
    def recon_explain_route(engagement_id: int, unit_code: str):
        _engagement(engagement_id)
        run, line = explain_unit(engagement_id, unit_code)
        if run is None:
            raise ApiError("not_found", "no reconciliation run yet")
        if line is None:
            raise ApiError("not_found", f"unit '{unit_code}' is not in the latest run")
        return ReconExplainOut(
            run=RunOut.model_validate(run),
            line=StoredLineOut.model_validate(line),
        )

    @router.get(
        "/engagements/{engagement_id}/exceptions",
        response_model=list[ExceptionOut],
        summary="Exception records, newest first",
        tags=["exceptions"],
        responses=ERROR_RESPONSES,
    )
    def exceptions_route(engagement_id: int, status: Optional[str] = None):
        _engagement(engagement_id)
        return list_exceptions(engagement_id, status=status)

    return router


def review_router() -> APIRouter:
    router = APIRouter(prefix="/api")

    @router.get(
        "/engagements/{engagement_id}/mappings",
        response_model=list[PendingHeadOut] | MappingCountsOut,
        summary="Review queue: pending heads, resolved heads, or status counts",
        description=(
            "`status=pending_review` (default) and `status=resolved` return a bare "
            "array of heads; `status=all` returns per-status counts."
        ),
        tags=["mapping"],
        responses=ERROR_RESPONSES,
    )
    def mappings_route(
        engagement_id: int,
        status: str = Query(
            "pending_review",
            description="pending_review | resolved | all (counts)",
        ),
    ):
        _engagement(engagement_id)
        wanted = (status or "").strip().lower()
        if wanted in ("pending", "pending_review"):
            return list_pending(engagement_id)
        if wanted in ("resolved", "reviewed"):
            return list_resolved(engagement_id)
        if wanted in ("all", "counts"):
            counts = mapping_counts(engagement_id)
            return MappingCountsOut(counts=counts, total=sum(counts.values()))
        raise ApiError(
            "bad_request", "status must be pending_review, resolved or all"
        )

    @router.post(
        "/mappings/resolve",
        response_model=ResolutionOut,
        summary="Resolve one ledger head to an FSLI",
        tags=["mapping"],
        responses=ERROR_RESPONSES,
    )
    def resolve_route(body: ResolveIn):
        try:
            return resolve_mapping(body.line_id, body.fsli_code, reviewer=body.reviewer)
        except ValueError as exc:
            raise ApiError("validation_failed", str(exc)) from exc

    @router.post(
        "/mappings/resolve-bulk",
        response_model=BulkResolveOut,
        summary="Resolve several heads; failures are reported per line",
        tags=["mapping"],
        responses=ERROR_RESPONSES,
    )
    def bulk_route(body: BulkResolveIn):
        results, failures = bulk_resolve(body.pairs, reviewer=body.reviewer)
        return BulkResolveOut(
            resolved=[ResolutionOut.model_validate(r) for r in results],
            failures={str(k): v for k, v in failures.items()},
        )

    @router.post(
        "/mappings/{line_id}/reset",
        response_model=ResolutionOut,
        summary="Undo a resolution and return the head to the queue",
        tags=["mapping"],
        responses=ERROR_RESPONSES,
    )
    def reset_route(line_id: int):
        try:
            return reset_mapping(line_id)
        except ValueError as exc:
            raise ApiError("validation_failed", str(exc)) from exc

    @router.get(
        "/engagements/{engagement_id}/fs-review",
        response_model=list[FsUnmappedOut],
        summary="Financial-statement labels that resolved to nothing",
        tags=["financial-statements"],
        responses=ERROR_RESPONSES,
    )
    def fs_review_route(engagement_id: int):
        _engagement(engagement_id)
        return list_unmapped_fs(engagement_id)

    @router.post(
        "/fs-lines/{line_id}/resolve",
        response_model=FsResolveOut,
        summary="Resolve an FS label to an FSLI or a presentation group",
        tags=["financial-statements"],
        responses=ERROR_RESPONSES,
    )
    def fs_resolve_route(line_id: int, body: FsResolveIn):
        try:
            return resolve_fs_line(
                line_id, fsli_code=body.fsli_code, group_code=body.group_code
            )
        except ValueError as exc:
            raise ApiError("validation_failed", str(exc)) from exc

    @router.post(
        "/fs-lines/{line_id}/reset",
        response_model=FsResolveOut,
        summary="Undo an FS-label resolution",
        tags=["financial-statements"],
        responses=ERROR_RESPONSES,
    )
    def fs_reset_route(line_id: int):
        try:
            return reset_fs_line(line_id)
        except ValueError as exc:
            raise ApiError("validation_failed", str(exc)) from exc

    @router.post(
        "/exceptions/{exception_id}/dispose",
        response_model=ExceptionOut,
        summary="Explain or accept an exception",
        tags=["exceptions"],
        responses=ERROR_RESPONSES,
    )
    def dispose_route(exception_id: int, body: DisposeIn):
        try:
            return dispose_exception(exception_id, body.status, note=body.note)
        except ValueError as exc:
            raise ApiError("validation_failed", str(exc)) from exc

    return router


def reference_router() -> APIRouter:
    from ..core.groups import load_default_groups
    from ..core.taxonomy import load_default_taxonomy

    router = APIRouter(prefix="/api")

    @router.get(
        "/taxonomy",
        response_model=list[TaxonomyItemOut],
        summary="The Schedule III FSLI taxonomy",
        tags=["reference"],
        responses=READ_RESPONSES,
    )
    def taxonomy_route(statement: Optional[str] = None, search: Optional[str] = None):
        taxonomy = load_default_taxonomy()
        items = list(taxonomy)
        if statement:
            needle = statement.strip().lower()
            items = [i for i in items if needle in i.statement.lower()]
        if search:
            items = taxonomy.search(search)
        return items

    @router.get(
        "/groups",
        response_model=list[GroupOut],
        summary="Presentation aggregates (e.g. REV_OPERATIONS)",
        tags=["reference"],
        responses=READ_RESPONSES,
    )
    def groups_route():
        return load_default_groups()

    @router.get(
        "/erp-sources",
        response_model=ErpSourcesOut,
        summary="Supported ERP trial-balance layouts",
        tags=["reference"],
        responses=READ_RESPONSES,
    )
    def sources_route():
        return ErpSourcesOut(sources=sorted(ADAPTERS))

    return router


def create_app() -> FastAPI:
    app = FastAPI(
        title="AuditIQ Core",
        version=__version__,
        description=(
            "Trial-balance ingestion, FSLI mapping, financial-statement ingestion "
            "and reconciliation. Deterministic by default; the LLM layer is opt-in. "
            "All errors use a uniform `{error: {code, message, details}}` envelope."
        ),
        openapi_tags=[
            {"name": "meta", "description": "Health, version and enum vocabulary."},
            {"name": "engagements", "description": "Engagement lifecycle and status."},
            {"name": "ingest", "description": "Trial balance and draft-FS ingestion."},
            {"name": "mapping", "description": "FSLI cascade and the review queue."},
            {"name": "financial-statements", "description": "Side B label resolution."},
            {"name": "materiality", "description": "Engagement materiality."},
            {"name": "reconciliation", "description": "Side A vs Side B tie-out."},
            {"name": "exceptions", "description": "Escalations and dispositions."},
            {"name": "reference", "description": "Taxonomy, groups and ERP sources."},
        ],
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=CORS_ORIGINS,
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # -- error handlers: one envelope for every failure --------------------

    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError):
        return JSONResponse(
            status_code=exc.status,
            content=error_body(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(SchemaDriftError)
    async def _schema_drift(request: Request, exc: SchemaDriftError):
        return JSONResponse(
            status_code=503,
            content=error_body(
                "schema_drift",
                str(exc),
                {"fix": "Run 'auditiq store reset' to rebuild the local database."},
            ),
        )

    @app.exception_handler(MaterialityError)
    async def _materiality_unset(request: Request, exc: MaterialityError):
        return JSONResponse(
            status_code=409, content=error_body("materiality_unset", str(exc))
        )

    @app.exception_handler(ValueError)
    async def _value_error(request: Request, exc: ValueError):
        return JSONResponse(
            status_code=422, content=error_body("validation_failed", str(exc))
        )

    @app.exception_handler(RequestValidationError)
    async def _request_validation(request: Request, exc: RequestValidationError):
        """FastAPI's own body/query validation, in the house envelope."""
        return JSONResponse(
            status_code=422,
            content=error_body(
                "validation_failed",
                "request failed validation",
                {"errors": jsonable_encoder(exc.errors())},
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException):
        """Routing-level errors (unknown path, wrong method) keep the envelope."""
        if exc.status_code == 404:
            code = "not_found"
        elif exc.status_code < 500:
            code = "bad_request"
        else:
            code = "internal_error"
        return JSONResponse(
            status_code=exc.status_code,
            content=error_body(code, str(exc.detail)),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(Exception)
    async def _unexpected(request: Request, exc: Exception):
        return JSONResponse(
            status_code=500,
            content=error_body("internal_error", "unexpected server error"),
        )

    @app.get("/", response_model=RootOut, include_in_schema=False)
    def root():
        return RootOut(
            service="auditiq",
            version=__version__,
            openapi="/openapi.json",
            docs="/docs",
            api="/api/health",
        )

    app.include_router(engagements_router())
    app.include_router(review_router())
    app.include_router(reference_router())

    return app


__all__ = ["ApiError", "create_app", "error_body"]
