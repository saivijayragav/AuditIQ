"""Enumerations shared across AuditIQ Core."""
from __future__ import annotations

from enum import Enum


class Statement(str, Enum):
    """Primary financial statement a line item belongs to."""

    PROFIT_LOSS = "P&L"
    BALANCE_SHEET = "BS"
    CASH_FLOW = "CF"
    EQUITY = "Equity"
    NOTES = "Notes"


class SourceSystem(str, Enum):
    """ERP / accounting system a trial balance was exported from."""

    TALLY = "tally"
    SAP = "sap"
    ZOHO = "zoho"
    GENERIC = "generic"


class DocumentKind(str, Enum):
    """Classification of an ingested source document."""

    TB_ERP = "tb_erp"
    FS_STRUCTURED = "fs_structured"
    FS_DOCUMENT = "fs_document"
    PUBLISHED_REPORT = "published_report"


class MappingMethod(str, Enum):
    """Which layer produced a trial-balance -> FSLI mapping."""

    CACHE = "cache"
    DICT = "dict"
    EMB = "emb"
    LLM = "llm"
    REVIEW = "review"
    MANUAL = "manual"
    UNMAPPED = "unmapped"


class MappingStatus(str, Enum):
    """Lifecycle status of a trial-balance -> FSLI mapping."""

    AUTO = "auto"
    PENDING_REVIEW = "pending_review"
    RESOLVED = "resolved"


class NoteCategory(str, Enum):
    """Footnote / disclosure categories."""

    PPE = "PP&E"
    CWIP = "CWIP"
    DEBT = "Debt"
    RPT = "RPT"
    CONTINGENT = "Contingent"
    COMMITMENT = "Commitment"


class Side(str, Enum):
    """Accounting side of a balance."""

    DEBIT = "Dr"
    CREDIT = "Cr"
