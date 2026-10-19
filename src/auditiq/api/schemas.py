"""Typed request/response models for the AuditIQ HTTP API.

Every route declares an explicit ``response_model`` from this module, so the
generated OpenAPI document is a usable client contract: field names, types and
nullability are all stated here rather than inferred at runtime.

The services keep returning plain dataclasses. Models use
``from_attributes=True`` so FastAPI validates those objects directly, and
derived ``@property`` values (``abs_amount``, ``mapped_weighted``, ``status``,
...) are declared as real fields — a generated client sees them.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class _Out(BaseModel):
    """Base for response models built from service dataclasses."""

    model_config = ConfigDict(from_attributes=True)


# -- envelope --------------------------------------------------------------


ErrorCode = Literal[
    "bad_request",
    "validation_failed",
    "not_found",
    "materiality_unset",
    "ingest_failed",
    "schema_drift",
    "internal_error",
]


class ErrorBody(BaseModel):
    code: ErrorCode = Field(description="Stable machine-readable error code.")
    message: str = Field(description="Human-readable explanation.")
    details: dict[str, Any] = Field(
        default_factory=dict, description="Optional structured context."
    )


class ErrorOut(BaseModel):
    """Every non-2xx response uses this envelope."""

    error: ErrorBody


# -- meta ------------------------------------------------------------------


class MetaOut(BaseModel):
    """Vocabulary and capabilities, so clients never hardcode enums."""

    version: str
    statements: list[str]
    bases: list[str]
    units: list[str]
    encoder_kinds: list[str]
    mapping_statuses: list[str]
    mapping_methods: list[str]
    fs_measures: list[str]
    classifications: list[str]
    severities: list[str]
    exception_kinds: list[str]
    exception_statuses: list[str]
    document_kinds: list[str]
    erp_sources: list[str]
    cors_origins: list[str] = Field(
        default_factory=list, description="Browser origins the API accepts."
    )
    features: dict[str, bool] = Field(
        default_factory=dict,
        description="Server capabilities, e.g. path_ingest / llm.",
    )


# -- engagement ------------------------------------------------------------


class EngagementSummaryOut(_Out):
    engagement_id: int
    client_code: str
    client_name: str
    period: str
    basis: str
    materiality_value: Optional[float] = None
    materiality_basis: Optional[str] = None
    tb_lines: int = 0
    tb_documents: int = 0
    fs_documents: int = 0
    fs_lines: int = 0
    fs_subtotals: int = 0
    fs_unmapped_rows: int = 0
    mappings: dict[str, int] = Field(
        default_factory=dict, description="Mapping status -> line count."
    )
    resolved_lines: int = 0
    pending_lines: int = 0
    intake_status: str = Field(description="intake | in progress | reconcilable")
    recon_run_id: Optional[int] = None
    recon_status: Optional[str] = None
    recon_exposure_a: float = 0.0
    recon_exposure_b: float = 0.0
    open_exceptions: int = 0


class EngagementInfoOut(_Out):
    engagement_id: int
    client_code: str
    period: str
    basis: str
    materiality_value: Optional[float] = None
    materiality_basis: Optional[str] = None


class CreateEngagementIn(BaseModel):
    client_code: str = Field(description="Short client code, e.g. T00.")
    period: str = Field(description="Financial year, e.g. FY25-26.")
    basis: str = Field(default="Standalone", description="Standalone | Consolidated.")
    client_name: str = ""


class DocumentOut(_Out):
    document_id: int
    engagement_id: Optional[int]
    kind: str = Field(description="tb_erp | fs_structured | fs_document | published_report")
    system: str
    filename: str
    file_hash: str
    uploaded_at: Optional[datetime]
    parse_stats: dict[str, Any] = Field(default_factory=dict)


class TbLineOut(_Out):
    line_id: int
    document_id: int
    raw_code: str
    raw_name: str
    group_name: str
    erp_acc_type: str
    amount: float
    side: str
    unit: str
    normalized_amount: float
    source_row: Optional[int]
    fsli_code: Optional[str] = None
    mapping_status: Optional[str] = None
    mapping_method: Optional[str] = None
    mapping_confidence: Optional[float] = None


class PageOut(BaseModel):
    """A page of trial-balance lines."""

    items: list[TbLineOut]
    total: int
    limit: int
    offset: int


# -- ingestion -------------------------------------------------------------


class TbIngestOut(_Out):
    engagement_id: int
    document_id: int
    source: str = Field(description="Detected ERP layout.")
    client_code: str
    period: str
    basis: str
    unit: str
    lines: int
    duplicates_skipped: int
    total_debit: float
    total_credit: float
    balanced: bool
    balance_difference: float


class ValidationIssueOut(_Out):
    code: str
    severity: str = Field(description="info | warning | error")
    message: str


class FsIngestOut(_Out):
    engagement_id: int
    document_id: int
    reader: str
    company: str
    period: str
    prior_period: str
    unit: str
    basis: str
    pages: int
    rows: int = Field(description="Labelled face rows found.")
    lines: int = Field(description="Persisted values (current + prior).")
    mapped: int
    unmapped: int
    subtotals: int
    by_statement: dict[str, int] = Field(default_factory=dict)
    by_layer: dict[str, int] = Field(default_factory=dict)
    tables: int = 0
    encoder: str = "none"
    tuned: bool = False
    issues: list[ValidationIssueOut] = Field(default_factory=list)
    mapped_weighted: int = Field(
        description="Mapped values excluding subtotals — what feeds reconciliation."
    )


class FsUnmappedLabelOut(BaseModel):
    """One statement label that resolved to nothing."""

    statement: str
    label: str

    @model_validator(mode="before")
    @classmethod
    def _from_pair(cls, value):
        """The service reports ``(statement, label)`` pairs."""
        if isinstance(value, (tuple, list)) and len(value) == 2:
            return {"statement": value[0], "label": value[1]}
        return value


class FsCoverageOut(_Out):
    path: str
    reader: str
    company: str
    period: str
    unit: str
    rows: int
    mapped: int
    by_layer: dict[str, int] = Field(default_factory=dict)
    encoder: str = "none"
    tuned: bool = False
    unmapped: list[FsUnmappedLabelOut] = Field(
        default_factory=list, description="Statement labels left unresolved."
    )
    unmapped_rows: int
    coverage: float = Field(description="mapped / rows, 0..1.")


# -- mapping ---------------------------------------------------------------


class MapIn(BaseModel):
    encoder: Optional[str] = Field(
        default=None, description="auto | none | tfidf | sbert. Omit to auto-detect."
    )
    use_llm: bool = Field(default=False, description="Opt in to the constrained LLM layer.")


class MappingSummaryOut(_Out):
    engagement_id: int
    lines: int
    resolved: int
    review: int
    by_layer: dict[str, int] = Field(default_factory=dict)
    llm_calls: int = 0
    tuned: bool = False
    encoder: str = "none"
    resolution_rate: float = Field(description="resolved / lines, 0..1.")


class PendingHeadOut(_Out):
    """A review-queue head.

    ``status`` is ``pending_review`` or ``unmapped`` while the head awaits a
    decision, and ``resolved`` once a reviewer has approved it — in which case
    ``candidates`` holds the single chosen FSLI code.
    """

    line_id: int = Field(description="Representative line; resolving it resolves the head.")
    raw_name: str
    raw_code: str
    group_name: str
    status: str = Field(description="pending_review | unmapped | resolved")
    method: str
    confidence: Optional[float]
    amount: float = Field(description="Signed, Dr-positive, absolute rupees.")
    lines: int = Field(description="Ledger lines collapsed into this head.")
    candidates: list[str] = Field(default_factory=list)
    embed_score: Optional[float] = None
    embed_margin: Optional[float] = None
    abs_amount: float


class ResolveIn(BaseModel):
    line_id: int
    fsli_code: str
    reviewer: str = ""


class BulkResolveIn(BaseModel):
    pairs: list[tuple[int, str]] = Field(default_factory=list)
    reviewer: str = ""


class ResolutionOut(_Out):
    line_id: int
    head: str
    fsli_code: Optional[str]
    resolved_lines: int
    reviewer: str = ""


class BulkResolveOut(BaseModel):
    resolved: list[ResolutionOut]
    failures: dict[str, str] = Field(
        default_factory=dict,
        description="line_id -> reason. Keys are strings in JSON.",
    )


class MappingCountsOut(BaseModel):
    counts: dict[str, int]
    total: int


# -- financial statements --------------------------------------------------


class FsUnmappedOut(_Out):
    line_id: int
    label: str
    statement: str
    document_id: int
    rows: int
    periods: list[str] = Field(default_factory=list)
    total: float
    abs_total: float


class FsResolveIn(BaseModel):
    fsli_code: Optional[str] = None
    group_code: Optional[str] = None


class FsResolveOut(_Out):
    line_id: int
    label: str
    fsli_code: Optional[str]
    group_code: Optional[str]
    resolved_rows: int


# -- materiality -----------------------------------------------------------


class MaterialityIn(BaseModel):
    value: float
    basis: str = ""


class MaterialitySuggestionOut(_Out):
    revenue: float
    total_assets: float
    ratio: float
    basis: str = Field(description="revenue | total assets")
    suggested: float
    unit: str


class MaterialityOut(BaseModel):
    value: Optional[float]
    basis: Optional[str]
    suggestion: Optional[MaterialitySuggestionOut] = None


# -- reconciliation --------------------------------------------------------


class FindingOut(_Out):
    code: str
    statement: str
    severity: str
    message: str
    amount: float = 0.0


class ReconLineBriefOut(_Out):
    unit_code: str
    name: str
    statement: str
    is_group: bool
    side_a: float
    side_b: float
    variance: float
    variance_pct: Optional[float]
    a_lines: int
    b_rows: int
    classification: str = Field(description="tied | rounding | minor | watch | material")
    severity: str


class ReconOut(_Out):
    engagement_id: int
    run_id: Optional[int]
    period: str
    basis: str
    unit: str
    materiality: float
    performance_materiality: float
    rounding_decimals: int
    tolerance: float
    statements: list[str]
    materiality_basis: str = ""
    units: int = 0
    tied: int = 0
    rounding: int = 0
    minor: int = 0
    watch: int = 0
    material: int = 0
    exposure_a: float = 0.0
    exposure_a_lines: int = 0
    exposure_b: float = 0.0
    exposure_b_rows: int = 0
    attributed: int = 0
    findings: list[FindingOut] = Field(default_factory=list)
    worst: list[ReconLineBriefOut] = Field(default_factory=list)
    reconciled: bool
    status: str


class ReconRunIn(BaseModel):
    materiality: Optional[float] = Field(
        default=None, description="Override the engagement materiality for this run."
    )
    pm: float = Field(default=0.75, description="Performance materiality as a ratio.")
    rounding_decimals: int = 2
    statements: Optional[str] = Field(
        default=None, description='"BS", "P&L", "BS,P&L" or "all".'
    )
    side_b_period: Optional[str] = None
    no_persist: bool = False


class RunOut(_Out):
    run_id: int
    engagement_id: int
    period: str
    basis: str
    unit: str
    statements: str
    materiality: float
    performance_materiality: float
    rounding_decimals: int
    units_total: int
    tied: int
    rounding: int
    minor: int
    watch: int
    material: int
    exposure_a: float
    exposure_b: float


class StoredLineOut(_Out):
    unit_code: str
    name: str
    statement: str
    is_group: bool
    side_a: float
    side_b: float
    variance: float
    variance_pct: Optional[float]
    a_lines: int
    b_rows: int
    classification: str
    severity: str
    attribution: dict[str, Any] = Field(default_factory=dict)
    refs: dict[str, Any] = Field(default_factory=dict)


class ReconLatestOut(BaseModel):
    run: RunOut
    lines: list[StoredLineOut]


class ReconExplainOut(BaseModel):
    run: RunOut
    line: StoredLineOut


# -- exceptions ------------------------------------------------------------


class ExceptionOut(_Out):
    exception_id: int
    engagement_id: Optional[int]
    kind: str
    severity: str
    status: str = Field(description="open | explained | accepted")
    amount: Optional[float]
    fsli: Optional[str]
    note: str = ""
    detail: str = ""


class DisposeIn(BaseModel):
    status: str = Field(description="explained | accepted")
    note: str = ""


# -- reference data --------------------------------------------------------


class TaxonomyItemOut(_Out):
    code: str
    statement: str
    category: str
    sub_category_1: str
    sub_category_2: str
    name: str
    normal_balance: str
    description: str
    is_debit: bool


class GroupOut(_Out):
    code: str
    name: str
    statement: str
    members: list[str]
    category: str = ""
    statement_code: str


class ErpSourcesOut(BaseModel):
    sources: list[str]


class HealthOut(BaseModel):
    status: str
    version: str


class RootOut(BaseModel):
    service: str
    version: str
    openapi: str
    docs: str
    api: str


__all__ = [
    "BulkResolveIn",
    "BulkResolveOut",
    "CreateEngagementIn",
    "DisposeIn",
    "DocumentOut",
    "EngagementInfoOut",
    "EngagementSummaryOut",
    "ErpSourcesOut",
    "ErrorBody",
    "ErrorCode",
    "ErrorOut",
    "ExceptionOut",
    "FindingOut",
    "FsCoverageOut",
    "FsIngestOut",
    "FsResolveIn",
    "FsResolveOut",
    "FsUnmappedLabelOut",
    "FsUnmappedOut",
    "GroupOut",
    "HealthOut",
    "MapIn",
    "MappingCountsOut",
    "MappingSummaryOut",
    "MaterialityIn",
    "MaterialityOut",
    "MaterialitySuggestionOut",
    "MetaOut",
    "PageOut",
    "PendingHeadOut",
    "ReconExplainOut",
    "ReconLatestOut",
    "ReconLineBriefOut",
    "ReconOut",
    "ReconRunIn",
    "ResolveIn",
    "ResolutionOut",
    "RootOut",
    "RunOut",
    "StoredLineOut",
    "TbIngestOut",
    "TbLineOut",
    "TaxonomyItemOut",
    "ValidationIssueOut",
]
