"""SQLAlchemy ORM schema for AuditIQ Core.

Design principle: **raw before derived.** ``tb_line`` and ``fs_line`` hold raw,
provenance-tagged facts. Every mapping/sum is derived and never overwrites raw
rows. ``source_document`` records where each row came from.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Engagement(Base):
    """A client audit engagement for a specific period and reporting basis."""

    __tablename__ = "engagement"
    __table_args__ = (
        UniqueConstraint("client_code", "period", "basis", name="uq_engagement"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    client_code: Mapped[str] = mapped_column(String(64), index=True)
    client_name: Mapped[str] = mapped_column(String(200), default="")
    period: Mapped[str] = mapped_column(String(20), index=True)  # e.g. FY25-26
    basis: Mapped[str] = mapped_column(String(20), default="Standalone")
    materiality_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    materiality_basis: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class SourceDocument(Base):
    """A single ingested artefact (ERP export, draft FS file, report PDF)."""

    __tablename__ = "source_document"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    engagement_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("engagement.id"), nullable=True, index=True
    )
    kind: Mapped[str] = mapped_column(String(30), index=True)  # DocumentKind
    system: Mapped[str] = mapped_column(String(30), default="")  # SourceSystem
    filename: Mapped[str] = mapped_column(String(400), default="")
    file_hash: Mapped[str] = mapped_column(String(64), index=True, default="")
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    parse_stats: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON


class FsliRef(Base):
    """Mirror of the committed FSLI taxonomy, for joins inside the database."""

    __tablename__ = "fsli"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    statement: Mapped[str] = mapped_column(String(16), default="")
    category: Mapped[str] = mapped_column(String(64), default="")
    sub_category_1: Mapped[str] = mapped_column(String(64), default="")
    sub_category_2: Mapped[str] = mapped_column(String(64), default="")
    name: Mapped[str] = mapped_column(String(200), default="")
    normal_balance: Mapped[str] = mapped_column(String(16), default="")
    description: Mapped[str] = mapped_column(Text, default="")


class TbLine(Base):
    """A single raw trial-balance ledger line (immutable evidence)."""

    __tablename__ = "tb_line"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("source_document.id"), index=True)
    engagement_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("engagement.id"), nullable=True, index=True
    )
    client_code: Mapped[str] = mapped_column(String(64), index=True, default="")
    period: Mapped[str] = mapped_column(String(20), index=True, default="")
    raw_code: Mapped[str] = mapped_column(String(64), default="")
    raw_name: Mapped[str] = mapped_column(String(400), default="")
    group_name: Mapped[str] = mapped_column(String(200), default="")
    erp_acc_type: Mapped[str] = mapped_column(String(120), default="")
    amount: Mapped[float] = mapped_column(Float, default=0.0)  # debit positive
    side: Mapped[str] = mapped_column(String(2), default="Dr")
    unit: Mapped[str] = mapped_column(String(20), default="absolute")
    normalized_amount: Mapped[float] = mapped_column(Float, default=0.0)  # rupees
    source_row: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)


class TbMapping(Base):
    """Mapping of a trial-balance line to an FSLI (one current row per line)."""

    __tablename__ = "tb_mapping"
    __table_args__ = (UniqueConstraint("line_id", name="uq_tb_mapping_line"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    line_id: Mapped[int] = mapped_column(ForeignKey("tb_line.id"), index=True)
    fsli_code: Mapped[Optional[str]] = mapped_column(
        ForeignKey("fsli.code"), nullable=True, index=True
    )
    method: Mapped[str] = mapped_column(String(20), default="unmapped")  # MappingMethod
    confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending_review")
    reviewer: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    resolved_fsli: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    # Cascade shortlist persisted for the review queue (JSON: codes + embed
    # scores). Written by ``map_engagement`` when the embedding layer ran so the
    # reviewer can pick a suggestion without re-encoding.
    candidates_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)


class FsLine(Base):
    """A reported figure extracted from a financial-statement document."""

    __tablename__ = "fs_line"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("source_document.id"), index=True)
    engagement_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("engagement.id"), nullable=True, index=True
    )
    fsli_code: Mapped[Optional[str]] = mapped_column(
        ForeignKey("fsli.code"), nullable=True, index=True
    )
    group_code: Mapped[Optional[str]] = mapped_column(
        String(32), nullable=True, index=True
    )  # presentation group (config, not an FK); set when the face line aggregates
    # How the label was resolved: the cascade layer (group|cache|dict|emb|llm),
    # ``manual`` after reviewer resolution, or ``reset`` after the reviewer undid
    # a decision (a cache tombstone). Empty on legacy rows.
    method: Mapped[str] = mapped_column(String(20), default="")
    statement: Mapped[str] = mapped_column(String(16), default="")
    category: Mapped[str] = mapped_column(String(64), default="")
    measure: Mapped[str] = mapped_column(
        String(50), default="reported_amount"
    )  # face|subtotal|note_total (non-face statement rows)
    report_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    unit: Mapped[str] = mapped_column(String(20), default="absolute")
    normalized_value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    period: Mapped[str] = mapped_column(String(20), default="", index=True)  # FY this figure belongs to
    column_label: Mapped[str] = mapped_column(String(50), default="")  # raw column header
    is_current: Mapped[bool] = mapped_column(Boolean, default=True)
    is_subtotal: Mapped[bool] = mapped_column(Boolean, default=False)
    value_text: Mapped[str] = mapped_column(Text, default="")
    cell_ref: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    evidence_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("evidence.id"), nullable=True, index=True
    )
    source_page: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source_ref: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)


class NoteItem(Base):
    """A footnote / disclosure item extracted from a financial-statement document."""

    __tablename__ = "note_item"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("source_document.id"), index=True)
    engagement_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("engagement.id"), nullable=True, index=True
    )
    fsli_code: Mapped[Optional[str]] = mapped_column(
        ForeignKey("fsli.code"), nullable=True, index=True
    )
    note_number: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    category: Mapped[str] = mapped_column(String(50), default="")  # NoteCategory
    item: Mapped[str] = mapped_column(String(300), default="")
    measure: Mapped[str] = mapped_column(String(50), default="reported_amount")
    value: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    unit: Mapped[str] = mapped_column(String(20), default="absolute")
    period: Mapped[str] = mapped_column(String(20), default="")
    is_subtotal: Mapped[bool] = mapped_column(Boolean, default=False)
    value_text: Mapped[str] = mapped_column(Text, default="")
    counterparty: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    relationship: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    transaction_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    source_page: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source_text: Mapped[str] = mapped_column(Text, default="")


class DocumentTable(Base):
    """Registry of a table extracted from a document (statement or note)."""

    __tablename__ = "document_table"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    table_id: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("source_document.id"), index=True)
    sql_table_name: Mapped[str] = mapped_column(String(120), default="")
    title: Mapped[str] = mapped_column(String(300), default="")
    note_number: Mapped[str] = mapped_column(String(20), default="")
    section: Mapped[str] = mapped_column(String(100), default="")
    page_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    headers_json: Mapped[str] = mapped_column(Text, default="[]")
    column_types_json: Mapped[str] = mapped_column(Text, default="[]")
    row_count: Mapped[int] = mapped_column(Integer, default=0)
    col_count: Mapped[int] = mapped_column(Integer, default=0)


class DocumentTableRow(Base):
    """A generic JSON row belonging to a :class:`DocumentTable`.

    Replaces the FRA runtime ``CREATE TABLE`` per extracted table: one portable
    table, no DDL at runtime.
    """

    __tablename__ = "document_table_row"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    table_id: Mapped[str] = mapped_column(String(64), index=True)
    row_index: Mapped[int] = mapped_column(Integer, default=0)
    cells_json: Mapped[str] = mapped_column(Text, default="[]")


class Evidence(Base):
    """A page / cell / table locator backing an extracted fact."""

    __tablename__ = "evidence"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("source_document.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20), default="page")  # page | cell | table
    page: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    bbox_json: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    quote: Mapped[str] = mapped_column(Text, default="")


class ExceptionRecord(Base):
    """A reconciliation / review exception awaiting disposition."""

    __tablename__ = "exception"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    engagement_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("engagement.id"), nullable=True, index=True
    )
    kind: Mapped[str] = mapped_column(String(40), default="")  # tieout | review | ...
    fsli_code: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    severity: Mapped[str] = mapped_column(String(20), default="watch")
    status: Mapped[str] = mapped_column(String(20), default="open")  # open|explained|accepted
    amount: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    detail: Mapped[str] = mapped_column(Text, default="")
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ReconRun(Base):
    """One reconciliation of an engagement's trial balance against its draft FS.

    Side A is the mapped trial balance; Side B is the client's draft financial
    statements. The run records the materiality config that produced it so a
    result is reproducible and explainable.
    """

    __tablename__ = "recon_run"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    engagement_id: Mapped[int] = mapped_column(
        ForeignKey("engagement.id"), index=True
    )
    period: Mapped[str] = mapped_column(String(20), default="")
    basis: Mapped[str] = mapped_column(String(20), default="")
    unit: Mapped[str] = mapped_column(String(20), default="absolute")
    statements: Mapped[str] = mapped_column(String(40), default="BS,P&L")
    rounding_decimals: Mapped[int] = mapped_column(Integer, default=2)
    materiality: Mapped[float] = mapped_column(Float, default=0.0)
    performance_materiality: Mapped[float] = mapped_column(Float, default=0.0)
    materiality_basis: Mapped[str] = mapped_column(String(100), default="")
    units_total: Mapped[int] = mapped_column(Integer, default=0)
    tied: Mapped[int] = mapped_column(Integer, default=0)
    rounding: Mapped[int] = mapped_column(Integer, default=0)
    minor: Mapped[int] = mapped_column(Integer, default=0)
    watch: Mapped[int] = mapped_column(Integer, default=0)
    material: Mapped[int] = mapped_column(Integer, default=0)
    exposure_a: Mapped[float] = mapped_column(Float, default=0.0)
    exposure_b: Mapped[float] = mapped_column(Float, default=0.0)
    config_json: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class ReconLine(Base):
    """One reconciliation unit (an FSLI or a presentation group) in a run."""

    __tablename__ = "recon_line"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("recon_run.id"), index=True)
    unit_code: Mapped[str] = mapped_column(String(32), index=True)
    is_group: Mapped[bool] = mapped_column(Boolean, default=False)
    statement: Mapped[str] = mapped_column(String(16), default="")
    name: Mapped[str] = mapped_column(String(200), default="")
    side_a: Mapped[float] = mapped_column(Float, default=0.0)
    side_b: Mapped[float] = mapped_column(Float, default=0.0)
    variance: Mapped[float] = mapped_column(Float, default=0.0)
    variance_pct: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    a_lines: Mapped[int] = mapped_column(Integer, default=0)
    b_rows: Mapped[int] = mapped_column(Integer, default=0)
    classification: Mapped[str] = mapped_column(String(20), default="tied")
    severity: Mapped[str] = mapped_column(String(20), default="none")
    refs_json: Mapped[str] = mapped_column(Text, default="[]")
    attribution_json: Mapped[str] = mapped_column(Text, default="{}")


__all__ = [
    "Base",
    "DocumentTable",
    "DocumentTableRow",
    "Engagement",
    "Evidence",
    "ExceptionRecord",
    "FsLine",
    "FsliRef",
    "NoteItem",
    "ReconLine",
    "ReconRun",
    "SourceDocument",
    "TbLine",
    "TbMapping",
]
