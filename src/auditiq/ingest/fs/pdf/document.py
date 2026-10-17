"""PDF document parsing: metadata detection and page/text assembly.

Ports the generic parts of the FRA ``DocumentParser`` without its ITC-specific
page heuristics: company, financial year, reporting unit and reporting basis are
all detected from the document text rather than hard-coded.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Optional

from ....core.periods import normalize_fy
from ....core.units import detect_unit

# A company name: a capitalised noun phrase ending in a corporate suffix.
_COMPANY = re.compile(
    r"([A-Z][A-Za-z0-9&.,'()\- ]{2,80}"
    r"(?:Limited|Ltd\.?|LLP|Corporation|Industries|Company|Enterprise|Enterprises|Bank))",
)

_FY = re.compile(r"(?:FY\s*)?(?:19|20)\d{2}\s*[-/]\s*(?:19|20)?\d{2}", re.IGNORECASE)
_DATE = re.compile(
    r"\d{1,2}(?:st|nd|rd|th)?\s+[A-Za-z]+\s*,?\s*(?:19|20)\d{2}", re.IGNORECASE
)
_BASIS = re.compile(r"\b(consolidated|standalone)\b", re.IGNORECASE)

# A reporting-unit statement such as "(Amount in Rs. lakhs)" or "(₹ in crores)".
_UNIT_LINE = re.compile(
    r"(?:₹|rs\.?|rupees?|\bin\b|\bamounts?\s+in\b)[^\n]{0,25}?"
    r"\b(crores?|lakhs?|lacs?|millions?|billions?|thousands?)\b",
    re.IGNORECASE,
)


def detect_company(text: object) -> str:
    """Return the first plausible company name found in ``text``."""
    if not text:
        return ""
    match = _COMPANY.search(str(text))
    return match.group(1).strip() if match else ""


def detect_period(text: object) -> Optional[str]:
    """Return the most likely financial year (``FY25-26``) mentioned in ``text``.

    Dates (``31 March 2026``) are preferred over bare FY/year tokens, and the most
    frequently mentioned year wins (ties broken by the latest year).
    """
    if not text:
        return None
    source = str(text)
    dated = [normalize_fy(m.group(0)) for m in _DATE.finditer(source)]
    ranged = [normalize_fy(m.group(0)) for m in _FY.finditer(source)]
    for candidates in (dated, ranged):
        years = [y for y in candidates if y]
        if years:
            counts = Counter(years)
            best = max(counts, key=lambda y: (counts[y], y))
            return best
    return None


def detect_basis(text: object) -> str:
    """Return ``Consolidated`` or ``Standalone`` (title-cased), else ``\"\"``."""
    if not text:
        return ""
    match = _BASIS.search(str(text))
    return match.group(1).capitalize() if match else ""


def detect_unit_from(text: object) -> str:
    """Detect the reporting unit from a unit statement line (default absolute)."""
    if not text:
        return "absolute"
    match = _UNIT_LINE.search(str(text))
    if not match:
        return "absolute"
    return detect_unit(match.group(0))


__all__ = [
    "detect_basis",
    "detect_company",
    "detect_period",
    "detect_unit_from",
]
