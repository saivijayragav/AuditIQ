"""Ingest a financial-statement document into the store (reconciliation Side B).

Reads a document with the reader registry, segments it into statements, resolves
each face label to an FSLI through the shared mapping cascade, converts every
figure to absolute rupees bound to a financial year, and persists ``fs_line``
rows with evidence pointers. Re-running the same file for the same engagement is
idempotent (keyed on the file content hash).
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Sequence

from sqlalchemy import delete, select

from ...core.periods import normalize_fy, prior_fy
from ...core.taxonomy import load_default_taxonomy
from ...store import init_db, session_scope
from ...store.models import (
    DocumentTable,
    DocumentTableRow,
    Engagement,
    Evidence,
    FsLine,
    NoteItem,
    SourceDocument,
)
from ...store.sync import sync_taxonomy
from ..prepare.mapper import ALL_LAYERS
from .base import STATEMENT_LABELS, FsDocument
from .labels import build_fs_mapper, label_rows, summarise
from .normalize import bind_row, resolve_unit
from .registry import read_fs
from .statements import extract_statements
from .validation import ValidationIssue, validate_document


@dataclass
class FsIngestResult:
    engagement_id: int
    document_id: int
    reader: str
    company: str
    period: str
    prior_period: str
    unit: str
    basis: str
    pages: int
    rows: int                 # labelled face rows
    lines: int                # persisted fs_line values (current + prior)
    mapped: int               # persisted values resolved to an FSLI
    unmapped: int             # persisted values left for review
    subtotals: int            # persisted values that are subtotals
    by_statement: dict[str, int] = field(default_factory=dict)
    by_layer: dict[str, int] = field(default_factory=dict)
    tables: int = 0
    encoder: str = "none"
    tuned: bool = False
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def mapped_weighted(self) -> int:
        """Mapped values excluding subtotals (the values that feed reconciliation)."""
        return self.mapped - self.subtotals


def file_hash(path: str | Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _get_or_create_engagement(session, client_code, client_name, period, basis) -> Engagement:
    engagement = session.scalars(
        select(Engagement).where(
            Engagement.client_code == client_code,
            Engagement.period == period,
            Engagement.basis == basis,
        )
    ).one_or_none()
    if engagement is None:
        engagement = Engagement(
            client_code=client_code,
            client_name=client_name or client_code,
            period=period,
            basis=basis,
        )
        session.add(engagement)
        session.flush()
    elif client_name:
        engagement.client_name = client_name
    return engagement


def _purge_prior(session, document_ids: list[int]) -> None:
    """Delete an earlier ingest of the same file (lines, evidence, tables)."""
    if not document_ids:
        return
    session.execute(delete(FsLine).where(FsLine.document_id.in_(document_ids)))
    session.execute(delete(NoteItem).where(NoteItem.document_id.in_(document_ids)))
    session.execute(delete(Evidence).where(Evidence.document_id.in_(document_ids)))
    table_ids = session.scalars(
        select(DocumentTable.table_id).where(DocumentTable.document_id.in_(document_ids))
    ).all()
    if table_ids:
        session.execute(delete(DocumentTableRow).where(DocumentTableRow.table_id.in_(table_ids)))
    session.execute(delete(DocumentTable).where(DocumentTable.document_id.in_(document_ids)))
    session.execute(delete(SourceDocument).where(SourceDocument.id.in_(document_ids)))


def _persist_tables(session, document_id: int, digest: str, document: FsDocument) -> int:
    count = 0
    for position, table in enumerate(document.tables):
        page = table.location.page if table.location else None
        ref = (table.location.table_ref if table.location else "") or f"t{position}"
        table_id = f"{digest[:12]}-{position}-{ref}"
        session.add(
            DocumentTable(
                table_id=table_id,
                document_id=document_id,
                title=table.title,
                note_number=table.note_number,
                section=table.section,
                page_number=page,
                headers_json=json.dumps(table.headers),
                row_count=len(table.rows),
                col_count=max((len(r) for r in table.rows), default=0),
            )
        )
        for index, raw in enumerate(table.rows):
            session.add(
                DocumentTableRow(
                    table_id=table_id,
                    row_index=index,
                    cells_json=json.dumps([str(cell) for cell in raw]),
                )
            )
        count += 1
    return count


def _bbox_json(location) -> Optional[str]:
    if location is not None and location.bbox:
        return json.dumps(list(location.bbox))
    return None


def ingest_fs(
    path: str | Path,
    client_code: str,
    period: str,
    basis: str = "Standalone",
    kind: Optional[str] = None,
    client_name: str = "",
    unit: Optional[str] = None,
    url: Optional[str] = None,
    encoder_kind: Optional[str] = None,
    layers: Sequence[str] = ALL_LAYERS,
) -> FsIngestResult:
    """Read and persist a financial-statement document."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"financial statement not found: {path}")

    document = read_fs(path, kind)
    normalized_period = normalize_fy(period) or document.period or period
    resolved_unit = resolve_unit(unit, document.unit)

    statements = extract_statements(document)
    issues = validate_document(document, normalized_period, resolved_unit, statements)

    taxonomy = load_default_taxonomy()
    mapper, _thresholds, resolved_encoder, tuned = build_fs_mapper(
        taxonomy=taxonomy, client=client_code, encoder_kind=encoder_kind
    )
    labelled = label_rows(statements, mapper, client=client_code, layers=layers)
    summary = summarise(labelled, resolved_encoder, tuned)

    digest = file_hash(path)
    init_db(url)
    with session_scope(url) as session:
        engagement = _get_or_create_engagement(
            session, client_code, client_name, normalized_period, basis
        )

        prior_ids = list(
            session.scalars(
                select(SourceDocument.id).where(
                    SourceDocument.engagement_id == engagement.id,
                    SourceDocument.file_hash == digest,
                )
            ).all()
        )
        _purge_prior(session, prior_ids)

        by_statement: Counter[str] = Counter()
        line_count = 0
        subtotals = 0
        mapped = 0
        labelled_rows = len(labelled)

        document_row = SourceDocument(
            engagement_id=engagement.id,
            kind="fs_document",
            system=document.reader_kind,
            filename=path.name,
            file_hash=digest,
            parse_stats=json.dumps(
                {
                    "reader": document.reader_kind,
                    "pages": document.page_count,
                    "company": document.company,
                    "period": document.period,
                    "unit": document.unit,
                    "basis": document.basis,
                    "statements": {k: len(v) for k, v in statements.items()},
                    "rows": labelled_rows,
                    "mapped": summary.mapped,
                    "unmapped": summary.unmapped,
                }
            ),
        )
        session.add(document_row)
        session.flush()
        sync_taxonomy(session, taxonomy)

        for item in labelled:
            statement_label = STATEMENT_LABELS.get(item.statement, item.statement)
            category = ""
            fsli = taxonomy.get(item.fsli_code)
            if fsli is not None:
                category = fsli.category

            bound_values = bind_row(
                item.row,
                period=normalized_period,
                unit=resolved_unit,
                fsli_code=item.fsli_code,
                statement=statement_label,
                layer=item.layer,
            )
            for bound in bound_values:
                location = bound.location
                evidence = Evidence(
                    document_id=document_row.id,
                    kind="cell" if (location and location.cell) else "page",
                    page=location.page if location else None,
                    bbox_json=_bbox_json(location),
                    quote=item.row.raw_text,
                )
                session.add(evidence)
                session.flush()

                session.add(
                    FsLine(
                        document_id=document_row.id,
                        engagement_id=engagement.id,
                        fsli_code=bound.fsli_code,
                        statement=bound.statement,
                        category=category,
                        measure=bound.measure,
                        report_value=bound.report_value,
                        unit=bound.unit,
                        normalized_value=bound.normalized_value,
                        period=bound.period,
                        column_label=bound.period,
                        is_current=bound.is_current,
                        is_subtotal=bound.is_subtotal,
                        value_text=bound.value_text,
                        cell_ref=location.ref() if location else None,
                        evidence_id=evidence.id,
                        source_page=location.page if location else None,
                        source_ref=item.row.label,
                    )
                )
                by_statement[statement_label] += 1
                line_count += 1
                if bound.fsli_code:
                    mapped += 1
                if bound.is_subtotal:
                    subtotals += 1

        table_count = _persist_tables(session, document_row.id, digest, document)

        return FsIngestResult(
            engagement_id=engagement.id,
            document_id=document_row.id,
            reader=document.reader_kind,
            company=document.company,
            period=normalized_period,
            prior_period=prior_fy(normalized_period) or "",
            unit=resolved_unit,
            basis=basis,
            pages=document.page_count,
            rows=labelled_rows,
            lines=line_count,
            mapped=mapped,
            unmapped=line_count - mapped,
            subtotals=subtotals,
            by_statement=dict(by_statement),
            by_layer=dict(summary.by_layer),
            tables=table_count,
            encoder=resolved_encoder,
            tuned=tuned,
            issues=issues,
        )


__all__ = ["FsIngestResult", "file_hash", "ingest_fs"]
