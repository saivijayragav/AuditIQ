"""Monetary amount and reporting-unit helpers.

``absolute`` is the base unit (whole rupees). Reporting units are converted to
absolute rupees via :data:`UNIT_FACTORS`, then to crores for comparison.
"""
from __future__ import annotations

import math
import re
from typing import Optional

# Multiplier that converts a value expressed in the given unit into absolute rupees.
UNIT_FACTORS: dict[str, float] = {
    "absolute": 1.0,
    "rupee": 1.0,
    "rupees": 1.0,
    "thousand": 1e3,
    "thousands": 1e3,
    "lakh": 1e5,
    "lakhs": 1e5,
    "lac": 1e5,
    "lacs": 1e5,
    "million": 1e6,
    "millions": 1e6,
    "crore": 1e7,
    "crores": 1e7,
    "cr": 1e7,
    "billion": 1e9,
    "billions": 1e9,
}

CRORE: float = 1e7

_BLANK_TOKENS = {"", "-", "--", "---", "–", "—", "nil", "na", "n/a", "none"}


def normalize_unit(unit: Optional[str]) -> str:
    """Return a canonical unit keyword, defaulting to ``absolute``."""
    if not unit:
        return "absolute"
    key = str(unit).strip().lower().rstrip(".")
    key = key.replace("in ", "").strip()
    if key in UNIT_FACTORS:
        return "absolute" if key in ("rupee", "rupees") else key
    return "absolute"


def detect_unit(text: Optional[str]) -> str:
    """Detect a reporting unit from free text (e.g. ``in Rs. Crores``)."""
    if not text:
        return "absolute"
    low = str(text).lower()
    if re.search(r"\bcrores?\b|\bcr\b", low):
        return "crores"
    if re.search(r"\blakhs?\b|\blacs?\b", low):
        return "lakhs"
    if re.search(r"\bmillions?\b", low):
        return "millions"
    if re.search(r"\bbillions?\b", low):
        return "billions"
    if re.search(r"\bthousands?\b", low):
        return "thousands"
    return "absolute"


def to_absolute(value: float, unit: Optional[str] = None) -> float:
    """Convert ``value`` (expressed in ``unit``) to absolute rupees."""
    factor = UNIT_FACTORS.get(normalize_unit(unit), 1.0)
    return float(value) * factor


def to_crores(value: float, unit: Optional[str] = None) -> float:
    """Convert ``value`` (expressed in ``unit``) to crores."""
    return to_absolute(value, unit) / CRORE


def parse_amount(text: object) -> Optional[float]:
    """Parse a financial-statement cell into a float.

    Handles thousands separators, currency symbols, parenthesised negatives and
    common blank/dash tokens. Returns ``None`` for blanks.
    """
    if text is None:
        return None
    if isinstance(text, bool):
        return None
    if isinstance(text, (int, float)):
        if isinstance(text, float) and math.isnan(text):
            return None
        return float(text)

    raw = str(text).strip()
    if raw.lower() in _BLANK_TOKENS:
        return None

    negative = False
    if raw.startswith("(") and raw.endswith(")"):
        negative = True
        raw = raw[1:-1].strip()
    if raw.startswith("-"):
        negative = True
        raw = raw[1:].strip()

    # Keep digits, separators and a decimal point.
    cleaned = re.sub(r"[^0-9.,]", "", raw)
    if not cleaned:
        return None
    cleaned = cleaned.replace(",", "")
    try:
        value = float(cleaned)
    except ValueError:
        return None
    return -value if negative else value
