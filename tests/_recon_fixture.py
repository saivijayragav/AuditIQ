"""Direct-to-store fixtures for reconciliation tests.

Reconciliation tests need exact control over Side A (mapped trial balance) and
Side B (draft financial statements) figures. Rather than reverse-engineer them
through file ingestion, these helpers write ``tb_line`` / ``tb_mapping`` /
``fs_line`` rows directly — the reconciliation layer reads only those tables.
"""
from __future__ import annotations

from typing import Optional

from auditiq.core.taxonomy import Taxonomy, load_default_taxonomy
from auditiq.store.models import (
    Engagement,
    FsLine,
    SourceDocument,
    TbLine,
    TbMapping,
)
from auditiq.store.sync import sync_taxonomy


def sign(taxonomy: Taxonomy, code: str) -> int:
    """+1 for debit-normal FSLIs, -1 for credit-normal ones."""
    item = taxonomy.get(code)
    return 1 if (item is not None and item.is_debit) else -1


def to_tb_amount(taxonomy: Taxonomy, presented: dict[str, float]) -> dict[str, float]:
    """Convert desired presented (natural-side, positive) values to Dr-positive TB amounts."""
    return {code: sign(taxonomy, code) * value for code, value in presented.items()}


def seed_engagement(
    session,
    client_code: str = "T00",
    period: str = "FY25-26",
    basis: str = "Standalone",
    taxonomy: Optional[Taxonomy] = None,
) -> Engagement:
    sync_taxonomy(session, taxonomy or load_default_taxonomy())
    engagement = Engagement(
        client_code=client_code, client_name=client_code, period=period, basis=basis
    )
    session.add(engagement)
    session.flush()
    return engagement


def add_tb(
    session,
    engagement: Engagement,
    specs: list[dict],
    *,
    unit: str = "absolute",
    system: str = "tally",
    filename: str = "tb.xlsx",
) -> None:
    """Insert trial-balance lines (and mappings).

    Each spec: ``{"name", "amount", "fsli"?, "status"?, "method"?, "group"?}``.
    ``amount`` is Dr-positive (debit +, credit -). ``status`` defaults to
    ``"auto"`` when an ``fsli`` is given, else ``"unmapped"`` (no mapping row).
    """
    document = SourceDocument(
        engagement_id=engagement.id,
        kind="tb_erp",
        system=system,
        filename=filename,
        file_hash="tb-" + filename,
    )
    session.add(document)
    session.flush()

    for spec in specs:
        line = TbLine(
            document_id=document.id,
            engagement_id=engagement.id,
            client_code=engagement.client_code,
            period=engagement.period,
            raw_code=spec.get("code", ""),
            raw_name=spec["name"],
            group_name=spec.get("group", ""),
            amount=spec["amount"],
            side="Dr" if spec["amount"] >= 0 else "Cr",
            unit=unit,
            normalized_amount=spec["amount"],
        )
        session.add(line)
        session.flush()

        status = spec.get("status")
        fsli = spec.get("fsli")
        if status is None:
            status = "auto" if fsli else "unmapped"
        if status == "unmapped" and not fsli:
            continue
        session.add(
            TbMapping(
                line_id=line.id,
                fsli_code=fsli,
                method=spec.get("method", "dict" if fsli else "review"),
                status=status,
                confidence=1.0 if fsli else None,
            )
        )


def add_fs_lines(
    session,
    engagement: Engagement,
    specs: list[dict],
    *,
    unit: str = "absolute",
    period: str = "FY25-26",
    filename: str = "draft.pdf",
) -> None:
    """Insert financial-statement face rows (Side B).

    Each spec: ``{"label", "value", "fsli"? | "group"?, "statement"?,
    "measure"?, "is_current"?, "is_subtotal"?, "period"?}``.
    """
    document = SourceDocument(
        engagement_id=engagement.id,
        kind="fs_document",
        system="pdf",
        filename=filename,
        file_hash="fs-" + filename,
    )
    session.add(document)
    session.flush()

    for spec in specs:
        fsli = spec.get("fsli")
        group = spec.get("group")
        statement = spec.get("statement")
        if statement is None:
            statement = "BS" if (fsli or "").startswith(("AST", "LIA", "EQ")) else "P&L"
        session.add(
            FsLine(
                document_id=document.id,
                engagement_id=engagement.id,
                fsli_code=fsli,
                group_code=group,
                statement=statement,
                measure=spec.get("measure", "face"),
                report_value=spec["value"],
                unit=unit,
                normalized_value=spec["value"],
                period=spec.get("period", period),
                is_current=spec.get("is_current", True),
                is_subtotal=spec.get("is_subtotal", False),
                value_text=str(spec["value"]),
                source_ref=spec["label"],
            )
        )


__all__ = ["add_fs_lines", "add_tb", "seed_engagement", "sign", "to_tb_amount"]
