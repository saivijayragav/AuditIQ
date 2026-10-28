"""Service layer for GST Reconciliation."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import List, Optional, Union

from auditiq.gst.ingest import auto_load_books_file, auto_load_portal_file
from auditiq.gst.models import GstInvoice, GstReconReport
from auditiq.gst.reconcile import reconcile_itc


def run_gst_recon_files(
    books_file: Union[str, Path],
    portal_file: Union[str, Path],
    tolerance: float = 5.0,
    engagement_id: Optional[str] = None,
) -> GstReconReport:
    """Run end-to-end GST Reconciliation between Books Purchase Register and Portal GSTR-2B.

    Parameters:
        books_file: Path to Books Purchase Register (.xlsx or .csv).
        portal_file: Path to GSTN GSTR-2B / GSTR-2 (.xlsx, .csv, or .json).
        tolerance: Round-off tolerance in INR (default: Rs 5.0).
        engagement_id: Optional engagement reference.

    Returns:
        GstReconReport with complete summary statistics and itemized findings.
    """
    books_path = Path(books_file)
    portal_path = Path(portal_file)

    if not books_path.is_file():
        raise FileNotFoundError(f"Books file does not exist: {books_path}")
    if not portal_path.is_file():
        raise FileNotFoundError(f"GST Portal file does not exist: {portal_path}")

    books_invoices = auto_load_books_file(books_path)
    portal_invoices = auto_load_portal_file(portal_path)

    return reconcile_itc(
        books_invoices=books_invoices,
        portal_invoices=portal_invoices,
        tolerance=Decimal(str(tolerance)),
        engagement_id=engagement_id,
    )


def run_gst_recon_invoices(
    books_invoices: List[GstInvoice],
    portal_invoices: List[GstInvoice],
    tolerance: float = 5.0,
    engagement_id: Optional[str] = None,
) -> GstReconReport:
    """Run GST reconciliation directly on pre-parsed invoice objects."""
    return reconcile_itc(
        books_invoices=books_invoices,
        portal_invoices=portal_invoices,
        tolerance=Decimal(str(tolerance)),
        engagement_id=engagement_id,
    )
