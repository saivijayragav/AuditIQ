"""GST Reconciliation Engine (GSTR-2B / GSTR-2 vs Books Purchase Register).

Implements multi-pass deterministic & fuzzy matching conforming to:
- Section 16(2)(aa) CGST Act, 2017 (GSTR-2B ITC entitlement)
- Section 17(5) CGST Act, 2017 (Blocked & Ineligible ITC)
- Form 3CD Clause 44 & GSTR-9C Table 12
"""

from __future__ import annotations

import difflib
import uuid
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional, Set, Tuple

from auditiq.gst.models import (
    GstInvoice,
    GstMatchRecord,
    GstReconReport,
    GstReconSummary,
    MatchStatus,
    RiskLevel,
)


def _string_similarity(a: str, b: str) -> float:
    """Calculate character-level similarity ratio between two strings (0.0 to 1.0)."""
    if not a or not b:
        return 0.0
    return difflib.SequenceMatcher(None, a, b).ratio()


def reconcile_itc(
    books_invoices: List[GstInvoice],
    portal_invoices: List[GstInvoice],
    tolerance: Decimal = Decimal("5.0"),
    engagement_id: Optional[str] = None,
) -> GstReconReport:
    """Reconcile Books Purchase Register against GST Portal GSTR-2B / GSTR-2 invoices.

    Parameters:
        books_invoices: Invoices recorded in the client's accounting books (Tally/ERP).
        portal_invoices: Invoices reported by suppliers to GSTN portal (GSTR-2B).
        tolerance: Allowable round-off difference in INR (default: Rs 5.0).
        engagement_id: Optional audit engagement identifier.

    Returns:
        GstReconReport with summary metrics and line-by-line match records.
    """
    records: List[GstMatchRecord] = []
    matched_books_idx: Set[int] = set()
    matched_portal_idx: Set[int] = set()

    # Index portal invoices by (normalized_gstin, normalized_invoice_no)
    portal_exact_map: Dict[Tuple[str, str], List[int]] = {}
    for p_idx, p_inv in enumerate(portal_invoices):
        key = (p_inv.gstin, p_inv.invoice_number_norm)
        portal_exact_map.setdefault(key, []).append(p_idx)

    # -------------------------------------------------------------
    # PASS 1: Exact Key Matching (GSTIN + Normalized Invoice Number)
    # -------------------------------------------------------------
    for b_idx, b_inv in enumerate(books_invoices):
        key = (b_inv.gstin, b_inv.invoice_number_norm)
        candidates = portal_exact_map.get(key, [])
        avail_candidates = [idx for idx in candidates if idx not in matched_portal_idx]

        if not avail_candidates:
            continue

        # Pick the candidate closest in taxable value
        best_p_idx = min(
            avail_candidates,
            key=lambda idx: abs(b_inv.taxable_value - portal_invoices[idx].taxable_value),
        )
        p_inv = portal_invoices[best_p_idx]

        taxable_diff = b_inv.taxable_value - p_inv.taxable_value
        tax_diff = b_inv.total_tax - p_inv.total_tax

        matched_books_idx.add(b_idx)
        matched_portal_idx.add(best_p_idx)

        # Check tolerance
        if abs(taxable_diff) <= tolerance and abs(tax_diff) <= tolerance:
            records.append(
                GstMatchRecord(
                    match_status=MatchStatus.EXACT_MATCH,
                    books_invoice=b_inv,
                    portal_invoice=p_inv,
                    taxable_difference=taxable_diff,
                    tax_difference=tax_diff,
                    confidence_score=1.0,
                    risk_level=RiskLevel.LOW,
                    audit_remark="Invoice matched completely with GSTR-2B. Full ITC eligible under Section 16(2)(aa).",
                    statutory_reference="Section 16(2)(aa) CGST Act, 2017",
                )
            )
        else:
            # Value or tax mismatch
            is_excess_claim = tax_diff > tolerance
            risk = RiskLevel.HIGH if is_excess_claim else RiskLevel.MEDIUM
            remark = (
                f"Value/tax mismatch detected. Books Taxable: INR {b_inv.taxable_value:,.2f}, "
                f"Portal Taxable: INR {p_inv.taxable_value:,.2f}. "
                f"Tax Variance: INR {tax_diff:+,.2f}. "
                + ("Excess ITC claimed in books must be reversed with interest per S.50(3)." if is_excess_claim else "Unclaimed ITC available in GSTR-2B.")
            )
            records.append(
                GstMatchRecord(
                    match_status=MatchStatus.VALUE_MISMATCH,
                    books_invoice=b_inv,
                    portal_invoice=p_inv,
                    taxable_difference=taxable_diff,
                    tax_difference=tax_diff,
                    confidence_score=0.95,
                    risk_level=risk,
                    audit_remark=remark,
                    statutory_reference="Section 16(2)(aa) & Section 50(3) CGST Act, 2017",
                )
            )

    # -------------------------------------------------------------
    # PASS 2: Probable Match (Same GSTIN + Value Match + Fuzzy Inv No)
    # -------------------------------------------------------------
    unmatched_books = [idx for idx in range(len(books_invoices)) if idx not in matched_books_idx]
    unmatched_portal = [idx for idx in range(len(portal_invoices)) if idx not in matched_portal_idx]

    # Index remaining portal invoices by GSTIN
    portal_gstin_map: Dict[str, List[int]] = {}
    for p_idx in unmatched_portal:
        portal_gstin_map.setdefault(portal_invoices[p_idx].gstin, []).append(p_idx)

    for b_idx in unmatched_books:
        b_inv = books_invoices[b_idx]
        candidates = [
            idx for idx in portal_gstin_map.get(b_inv.gstin, [])
            if idx not in matched_portal_idx
        ]
        if not candidates:
            continue

        best_candidate: Optional[int] = None
        best_score = 0.0

        for p_idx in candidates:
            p_inv = portal_invoices[p_idx]
            taxable_diff = abs(b_inv.taxable_value - p_inv.taxable_value)
            tax_diff = abs(b_inv.total_tax - p_inv.total_tax)

            # Value must be within tolerance or 1%
            if taxable_diff > max(tolerance, b_inv.taxable_value * Decimal("0.01")):
                continue

            # Date proximity check (if available, within 60 days)
            days_diff = 0
            if b_inv.invoice_date and p_inv.invoice_date:
                days_diff = abs((b_inv.invoice_date - p_inv.invoice_date).days)
                if days_diff > 60:
                    continue

            # Invoice number similarity
            sim = _string_similarity(b_inv.invoice_number_norm, p_inv.invoice_number_norm)
            # Also check if one contains the other (e.g. '1001' in 'INV1001')
            if (
                b_inv.invoice_number_norm in p_inv.invoice_number_norm
                or p_inv.invoice_number_norm in b_inv.invoice_number_norm
            ):
                sim = max(sim, 0.85)

            if sim >= 0.70 and sim > best_score:
                best_score = sim
                best_candidate = p_idx

        if best_candidate is not None:
            p_inv = portal_invoices[best_candidate]
            matched_books_idx.add(b_idx)
            matched_portal_idx.add(best_candidate)

            taxable_diff = b_inv.taxable_value - p_inv.taxable_value
            tax_diff = b_inv.total_tax - p_inv.total_tax

            records.append(
                GstMatchRecord(
                    match_status=MatchStatus.PROBABLE_MATCH,
                    books_invoice=b_inv,
                    portal_invoice=p_inv,
                    taxable_difference=taxable_diff,
                    tax_difference=tax_diff,
                    confidence_score=round(best_score, 2),
                    risk_level=RiskLevel.LOW,
                    audit_remark=(
                        f"Probable match identified with invoice number typo/formatting difference "
                        f"(Books: '{b_inv.invoice_number}', Portal: '{p_inv.invoice_number}'). "
                        f"Supplier GSTIN and values align. Verify ERP voucher numbering."
                    ),
                    statutory_reference="Section 16(2) CGST Act, 2017",
                )
            )

    # -------------------------------------------------------------
    # PASS 3: Unmatched Books Invoices (Section 17(5) Blocked vs Missing in 2B)
    # -------------------------------------------------------------
    for b_idx in range(len(books_invoices)):
        if b_idx in matched_books_idx:
            continue
        b_inv = books_invoices[b_idx]

        if b_inv.blocked_reason:
            records.append(
                GstMatchRecord(
                    match_status=MatchStatus.BLOCKED_CREDIT,
                    books_invoice=b_inv,
                    portal_invoice=None,
                    taxable_difference=b_inv.taxable_value,
                    tax_difference=b_inv.total_tax,
                    confidence_score=1.0,
                    risk_level=RiskLevel.HIGH,
                    audit_remark=(
                        f"Blocked / Ineligible ITC identified under {b_inv.blocked_reason}. "
                        f"ITC of INR {b_inv.total_tax:,.2f} claimed in books must be reversed in GSTR-3B Table 4(B)."
                    ),
                    statutory_reference="Section 17(5) CGST Act, 2017",
                )
            )
        else:
            records.append(
                GstMatchRecord(
                    match_status=MatchStatus.BOOKS_ONLY,
                    books_invoice=b_inv,
                    portal_invoice=None,
                    taxable_difference=b_inv.taxable_value,
                    tax_difference=b_inv.total_tax,
                    confidence_score=1.0,
                    risk_level=RiskLevel.CRITICAL,
                    audit_remark=(
                        f"Invoice missing from GSTR-2B. Vendor '{b_inv.party_name or b_inv.gstin}' has not uploaded invoice "
                        f"or filed GSTR-1. Ineligible ITC of INR {b_inv.total_tax:,.2f} claimed in books violates Section 16(2)(aa). "
                        f"Subject to demand notice and 18% p.a. interest under Section 50."
                    ),
                    statutory_reference="Section 16(2)(aa) CGST Act, 2017",
                )
            )

    # -------------------------------------------------------------
    # PASS 4: Unmatched Portal Invoices (Missing in Books)
    # -------------------------------------------------------------
    for p_idx in range(len(portal_invoices)):
        if p_idx in matched_portal_idx:
            continue
        p_inv = portal_invoices[p_idx]

        records.append(
            GstMatchRecord(
                match_status=MatchStatus.PORTAL_ONLY,
                books_invoice=None,
                portal_invoice=p_inv,
                taxable_difference=-p_inv.taxable_value,
                tax_difference=-p_inv.total_tax,
                confidence_score=1.0,
                risk_level=RiskLevel.MEDIUM,
                audit_remark=(
                    f"Invoice reported by supplier '{p_inv.gstin}' in GSTR-1 (present in GSTR-2B) but missing from Books Purchase Register. "
                    f"Taxable: INR {p_inv.taxable_value:,.2f}, Tax: INR {p_inv.total_tax:,.2f}. "
                    f"Auditor must verify potential unrecorded expense/liability or unauthorized use of client GSTIN."
                ),
                statutory_reference="Section 16 & Section 37 CGST Act, 2017",
            )
        )

    # -------------------------------------------------------------
    # Summary Metrics Calculation
    # -------------------------------------------------------------
    summary = GstReconSummary()

    # Books aggregates
    summary.books_invoice_count = len(books_invoices)
    summary.books_taxable_value = sum((b.taxable_value for b in books_invoices), Decimal("0.0"))
    summary.books_total_itc = sum((b.total_tax for b in books_invoices), Decimal("0.0"))

    # Portal aggregates
    summary.portal_invoice_count = len(portal_invoices)
    summary.portal_taxable_value = sum((p.taxable_value for p in portal_invoices), Decimal("0.0"))
    summary.portal_total_itc = sum((p.total_tax for p in portal_invoices), Decimal("0.0"))

    # Breakdown by status
    for rec in records:
        if rec.match_status == MatchStatus.EXACT_MATCH:
            summary.exact_match_count += 1
            if rec.books_invoice:
                summary.exact_match_itc += rec.books_invoice.total_tax

        elif rec.match_status == MatchStatus.PROBABLE_MATCH:
            summary.probable_match_count += 1
            if rec.books_invoice:
                summary.probable_match_itc += rec.books_invoice.total_tax

        elif rec.match_status == MatchStatus.VALUE_MISMATCH:
            summary.value_mismatch_count += 1
            summary.value_mismatch_tax_diff += rec.tax_difference

        elif rec.match_status == MatchStatus.BOOKS_ONLY:
            summary.books_only_count += 1
            if rec.books_invoice:
                summary.books_only_itc += rec.books_invoice.total_tax

        elif rec.match_status == MatchStatus.PORTAL_ONLY:
            summary.portal_only_count += 1
            if rec.portal_invoice:
                summary.portal_only_taxable += rec.portal_invoice.taxable_value
                summary.portal_only_itc += rec.portal_invoice.total_tax

        elif rec.match_status == MatchStatus.BLOCKED_CREDIT:
            summary.blocked_credit_count += 1
            if rec.books_invoice:
                summary.blocked_credit_itc += rec.books_invoice.total_tax

    # Compliance ratio
    matched_itc = summary.exact_match_itc + summary.probable_match_itc
    if summary.books_total_itc > Decimal("0.0"):
        summary.itc_compliance_ratio = round(
            float((matched_itc / summary.books_total_itc) * Decimal("100.0")), 2
        )
    else:
        summary.itc_compliance_ratio = 100.0

    report = GstReconReport(
        report_id=f"GSTR-{uuid.uuid4().hex[:8]}",
        generated_at=datetime.now(),
        tolerance=tolerance,
        summary=summary,
        records=records,
    )
    return report
