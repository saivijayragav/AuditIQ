"""Sanity checks run over a parsed financial-statement document.

Deliberately conservative: these are *warnings* that make an ingestion auditable,
not reasons to reject it. Unit and period detection in particular are best-effort
and a mismatch is usually resolved in favour of the caller's explicit argument.
"""
from __future__ import annotations

from dataclasses import dataclass

from .base import FsDocument, FsRow


@dataclass
class ValidationIssue:
    """A single validation finding."""

    code: str
    severity: str  # info | warning | error
    message: str


def validate_document(
    document: FsDocument,
    period: str,
    unit: str,
    statements: dict[str, list[FsRow]],
) -> list[ValidationIssue]:
    """Validate a parsed document and return the findings."""
    issues: list[ValidationIssue] = []

    if not statements:
        issues.append(
            ValidationIssue(
                "no_statement_detected",
                "error",
                "no balance sheet, profit and loss or other statement was detected",
            )
        )

    if not document.company:
        issues.append(
            ValidationIssue("company_not_detected", "info", "company name not detected")
        )

    if not document.period:
        issues.append(
            ValidationIssue(
                "period_not_detected", "warning", "financial year not detected in document"
            )
        )
    elif document.period != period:
        issues.append(
            ValidationIssue(
                "period_mismatch",
                "warning",
                f"document period {document.period} differs from supplied {period}",
            )
        )

    if document.unit != unit:
        issues.append(
            ValidationIssue(
                "unit_mismatch",
                "warning",
                f"document unit '{document.unit}' differs from resolved unit '{unit}'",
            )
        )

    if not document.basis:
        issues.append(
            ValidationIssue(
                "basis_not_detected", "info", "standalone/consolidated basis not detected"
            )
        )

    return issues


__all__ = ["ValidationIssue", "validate_document"]
