"""Data models for GST Reconciliation under Indian Statutory Audit (GSTR-2B vs Books, GSTR-1).

Complies with:
- Section 16(2)(aa) of CGST Act, 2017: Mandatory matching of ITC with GSTR-2B.
- Section 17(5) of CGST Act, 2017: Ineligible / blocked Input Tax Credit.
- Section 9(3)/9(4) of CGST Act, 2017: Reverse Charge Mechanism (RCM).
- Form 3CD Clause 44 & GSTR-9C Table 12 / Table 5.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class MatchStatus(str, Enum):
    """Reconciliation classification for GST invoice matching."""
    EXACT_MATCH = "EXACT_MATCH"
    PROBABLE_MATCH = "PROBABLE_MATCH"
    VALUE_MISMATCH = "VALUE_MISMATCH"
    BOOKS_ONLY = "BOOKS_ONLY"
    PORTAL_ONLY = "PORTAL_ONLY"
    BLOCKED_CREDIT = "BLOCKED_CREDIT"


class RiskLevel(str, Enum):
    """Audit risk level of reconciliation finding."""
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class GstInvoice(BaseModel):
    """Unified representation of a GST invoice from either Books or GSTN Portal."""
    source: str = Field(description="'books' or 'portal'")
    gstin: str = Field(description="15-character GSTIN of supplier (inward) or recipient (outward)")
    party_name: str = Field(default="", description="Trade name or legal name of counterparty")
    invoice_number: str = Field(description="Raw invoice/document number as recorded")
    invoice_number_norm: str = Field(description="Normalized alphanumeric invoice number for fuzzy matching")
    invoice_date: Optional[date] = Field(default=None, description="Invoice date")
    invoice_type: str = Field(default="Regular", description="Regular, SEZ, Deemed Exp, Credit Note, etc.")
    place_of_supply: str = Field(default="", description="State code and state name e.g. '27-Maharashtra'")
    reverse_charge: bool = Field(default=False, description="Whether reverse charge applies")
    rate: Decimal = Field(default=Decimal("0.0"), description="GST rate % (0, 0.25, 3, 5, 12, 18, 28)")
    taxable_value: Decimal = Field(default=Decimal("0.0"), description="Taxable assessable value in INR")
    igst: Decimal = Field(default=Decimal("0.0"), description="Integrated Goods and Services Tax in INR")
    cgst: Decimal = Field(default=Decimal("0.0"), description="Central Goods and Services Tax in INR")
    sgst: Decimal = Field(default=Decimal("0.0"), description="State / UT Goods and Services Tax in INR")
    cess: Decimal = Field(default=Decimal("0.0"), description="GST Compensation Cess in INR")
    total_tax: Decimal = Field(default=Decimal("0.0"), description="Sum of IGST + CGST + SGST + Cess")
    invoice_value: Decimal = Field(default=Decimal("0.0"), description="Total invoice amount (Taxable + Tax)")
    itc_eligibility: str = Field(default="Eligible", description="Eligible, Ineligible, Inputs, Capital goods")
    blocked_reason: Optional[str] = Field(default=None, description="Section 17(5) blocked category if any")
    notes: Optional[str] = Field(default=None, description="Additional item description, voucher remarks")

    @property
    def total_calculated_tax(self) -> Decimal:
        return self.igst + self.cgst + self.sgst + self.cess


class GstMatchRecord(BaseModel):
    """Individual paired reconciliation line item."""
    match_status: MatchStatus
    books_invoice: Optional[GstInvoice] = None
    portal_invoice: Optional[GstInvoice] = None
    taxable_difference: Decimal = Field(
        default=Decimal("0.0"),
        description="Books Taxable - Portal Taxable. Positive = Books higher; Negative = Portal higher."
    )
    tax_difference: Decimal = Field(
        default=Decimal("0.0"),
        description="Books Tax - Portal Tax. Positive = Excess Books Claim; Negative = Unclaimed Portal Tax."
    )
    confidence_score: float = Field(
        default=1.0,
        description="Match confidence between 0.0 and 1.0"
    )
    risk_level: RiskLevel = Field(default=RiskLevel.LOW)
    audit_remark: str = Field(default="", description="Human-readable statutory audit finding")
    statutory_reference: str = Field(default="", description="CGST Act section reference (e.g. S.16(2)(aa))")


class GstReconSummary(BaseModel):
    """Aggregate statistics for GST reconciliation."""
    books_invoice_count: int = 0
    books_taxable_value: Decimal = Decimal("0.0")
    books_total_itc: Decimal = Decimal("0.0")

    portal_invoice_count: int = 0
    portal_taxable_value: Decimal = Decimal("0.0")
    portal_total_itc: Decimal = Decimal("0.0")

    exact_match_count: int = 0
    exact_match_itc: Decimal = Decimal("0.0")

    probable_match_count: int = 0
    probable_match_itc: Decimal = Decimal("0.0")

    value_mismatch_count: int = 0
    value_mismatch_tax_diff: Decimal = Decimal("0.0")

    books_only_count: int = 0
    books_only_itc: Decimal = Decimal("0.0")  # Section 16(2)(aa) risk

    portal_only_count: int = 0
    portal_only_taxable: Decimal = Decimal("0.0")
    portal_only_itc: Decimal = Decimal("0.0")  # Unrecorded liability

    blocked_credit_count: int = 0
    blocked_credit_itc: Decimal = Decimal("0.0")  # Section 17(5) reversal needed

    itc_compliance_ratio: float = Field(
        default=0.0,
        description="Matched ITC as a % of Total Books ITC (0.0 to 100.0)"
    )


class GstReconReport(BaseModel):
    """Complete GST Reconciliation report."""
    report_id: str
    generated_at: datetime
    tolerance: Decimal = Decimal("5.0")
    summary: GstReconSummary
    records: List[GstMatchRecord] = Field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return self.model_dump(mode="json")
