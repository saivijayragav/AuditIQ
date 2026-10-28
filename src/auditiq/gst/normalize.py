"""Data normalization, parsing, and statutory compliance checks for GST Reconciliation."""

from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Optional


# Official 15-digit GSTIN regex pattern
GSTIN_REGEX = re.compile(r"^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$")

# Section 17(5) Blocked Credit keyword heuristics
BLOCKED_PATTERNS = [
    (
        re.compile(r"\b(motor\s*vehicle|car\s*insurance|car\s*repair|cab|taxi|uber|ola|petrol|diesel|fuel)\b", re.IGNORECASE),
        "Section 17(5)(a) - Motor vehicles and conveyances",
    ),
    (
        re.compile(r"\b(food|beverage|catering|restaurant|party|lunch|dinner|refreshment|snacks|canteen)\b", re.IGNORECASE),
        "Section 17(5)(b)(i) - Food, beverages, outdoor catering",
    ),
    (
        re.compile(r"\b(club|gym|fitness|membership|spa|health\s*centre)\b", re.IGNORECASE),
        "Section 17(5)(b)(ii) - Club, health and fitness centre membership",
    ),
    (
        re.compile(r"\b(gift|free\s*sample|personal|diwali\s*gift|staff\s*gift)\b", re.IGNORECASE),
        "Section 17(5)(h) - Goods disposed of by way of gift or free samples",
    ),
    (
        re.compile(r"\b(works\s*contract|construction|civil\s*contract|building\s*renovation)\b", re.IGNORECASE),
        "Section 17(5)(c) - Works contract services for construction of immovable property",
    ),
]


def normalize_gstin(val: Any) -> str:
    """Normalize GSTIN string to uppercase stripped alphanumeric."""
    if val is None:
        return ""
    s = str(val).strip().upper()
    # Strip any internal whitespace
    s = re.sub(r"\s+", "", s)
    return s


def validate_gstin(gstin: str) -> bool:
    """Return True if gstin matches standard 15-digit GSTIN pattern."""
    return bool(GSTIN_REGEX.match(gstin))


def normalize_invoice_number(val: Any) -> str:
    """Normalize invoice number for robust fuzzy matching.

    Strips whitespace, dashes, slashes, periods, underscores, and removes
    leading zeros from segments so that e.g.:
      'INV/2023-24/0042' -> 'INV20232442'
      '0001001'           -> '1001'
      'INV-0089'         -> 'INV89'
      'Bill # 452'       -> 'BILL452'
    """
    if val is None:
        return ""
    s = str(val).strip().upper()
    tokens = re.split(r"[^A-Z0-9]+", s)
    norm_tokens = []
    for t in tokens:
        if not t:
            continue
        if t.isdigit():
            norm_tokens.append(str(int(t)))
        else:
            m = re.match(r"^([A-Z]+)0+([0-9]+.*)$", t)
            if m:
                norm_tokens.append(f"{m.group(1)}{m.group(2)}")
            else:
                norm_tokens.append(t)
    return "".join(norm_tokens)


def parse_date_safe(val: Any) -> Optional[date]:
    """Parse a date from string, datetime, or date object across common Indian formats."""
    if val is None:
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    if isinstance(val, datetime):
        return val.date()

    s = str(val).strip()
    if not s or s.lower() in ("nan", "none", "null", "-"):
        return None

    # Handle formats like '12-Jul-17', '12-Jul-2017', '15/04/2023', '2023-04-15'
    date_formats = [
        "%d-%b-%y",
        "%d-%b-%Y",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y-%m-%d",
        "%d.%m.%Y",
        "%Y/%m/%d",
        "%b %d, %Y",
        "%d %b %Y",
    ]
    for fmt in date_formats:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue

    # Fallback ISO parser
    try:
        return datetime.fromisoformat(s).date()
    except Exception:
        return None


def parse_decimal_safe(val: Any) -> Decimal:
    """Convert input into Decimal safely. Returns Decimal('0.0') on failure."""
    if val is None:
        return Decimal("0.0")
    if isinstance(val, (int, float, Decimal)):
        try:
            return Decimal(str(val))
        except InvalidOperation:
            return Decimal("0.0")

    s = str(val).strip().replace(",", "").replace(" ", "").replace("₹", "")
    if not s or s.lower() in ("nan", "none", "null", "-"):
        return Decimal("0.0")
    try:
        return Decimal(s)
    except InvalidOperation:
        return Decimal("0.0")


def detect_blocked_credit_17_5(text: Optional[str] = None, eligibility: Optional[str] = None) -> Optional[str]:
    """Detect if an expense or ITC claim is blocked under Section 17(5) of the CGST Act.

    Returns the statutory clause reference and rationale, or None if eligible.
    """
    if eligibility and eligibility.strip().lower() in ("ineligible", "blocked", "no"):
        return "Section 17(5) - Ineligible ITC flagged by counterparty/portal"

    if not text:
        return None

    for pattern, rationale in BLOCKED_PATTERNS:
        if pattern.search(text):
            return rationale

    return None
