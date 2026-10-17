"""Ingest an ERP trial-balance export into the store.

Creates/reuses an engagement, records a ``source_document`` with a content hash
(for idempotent re-runs) and writes one ``tb_line`` per ledger with an
absolute-rupee ``normalized_amount``.
"""
from __future__ import annotations

import hashlib
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from sqlalchemy import delete, select

from ...core.periods import normalize_fy
from ...core.units import to_absolute
from ...store import init_db, session_scope
from ...store.models import Engagement, SourceDocument, TbLine
from .registry import read_with_source


@dataclass
class TbIngestResult:
    engagement_id: int
    document_id: int
    source: str
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


def ingest_tb(
    path: str | Path,
    client_code: str,
    period: str,
    basis: str = "Standalone",
    source: Optional[str] = None,
    client_name: str = "",
    unit: str = "absolute",
    url: Optional[str] = None,
) -> TbIngestResult:
    """Ingest a trial-balance file and persist its lines."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"trial balance not found: {path}")

    normalized_period = normalize_fy(period) or period
    records, resolved_source = read_with_source(path, source)
    digest = file_hash(path)

    init_db(url)
    with session_scope(url) as session:
        engagement = _get_or_create_engagement(
            session, client_code, client_name, normalized_period, basis
        )

        # Idempotency: drop any earlier ingest of the same file for this engagement.
        prior_docs = session.scalars(
            select(SourceDocument).where(
                SourceDocument.engagement_id == engagement.id,
                SourceDocument.file_hash == digest,
            )
        ).all()
        if prior_docs:
            prior_ids = [d.id for d in prior_docs]
            session.execute(delete(TbLine).where(TbLine.document_id.in_(prior_ids)))
            session.execute(
                delete(SourceDocument).where(SourceDocument.id.in_(prior_ids))
            )

        document = SourceDocument(
            engagement_id=engagement.id,
            kind="tb_erp",
            system=resolved_source,
            filename=path.name,
            file_hash=digest,
        )
        session.add(document)
        session.flush()

        seen: set[tuple] = set()
        duplicates = 0
        total_debit = 0.0
        total_credit = 0.0
        line_count = 0

        for record in records:
            key = (record.raw_code, record.raw_name.strip().lower(), round(record.amount, 2))
            if key in seen:
                duplicates += 1
                continue
            seen.add(key)

            normalized = to_absolute(record.amount, unit)
            if record.amount >= 0:
                total_debit += normalized
            else:
                total_credit += -normalized

            session.add(
                TbLine(
                    document_id=document.id,
                    engagement_id=engagement.id,
                    client_code=client_code,
                    period=normalized_period,
                    raw_code=record.raw_code,
                    raw_name=record.raw_name,
                    group_name=record.group,
                    erp_acc_type=record.erp_acc_type,
                    amount=record.amount,
                    side=record.side,
                    unit=unit,
                    normalized_amount=normalized,
                    source_row=record.source_row,
                )
            )
            line_count += 1

        difference = total_debit - total_credit
        balanced = math.isclose(total_debit, total_credit, abs_tol=1.0)

        return TbIngestResult(
            engagement_id=engagement.id,
            document_id=document.id,
            source=resolved_source,
            client_code=client_code,
            period=normalized_period,
            basis=basis,
            unit=unit,
            lines=line_count,
            duplicates_skipped=duplicates,
            total_debit=total_debit,
            total_credit=total_credit,
            balanced=balanced,
            balance_difference=difference,
        )
