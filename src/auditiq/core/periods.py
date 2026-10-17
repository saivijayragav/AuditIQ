"""Financial-year parsing and normalisation.

Canonical form is ``FY25-26`` (Indian April–March financial year).
"""
from __future__ import annotations

import re
from typing import Optional

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12,
}

_FY_RANGE = re.compile(r"(?:FY)?\s*(\d{2,4})\s*[-/]\s*(\d{2,4})", re.IGNORECASE)
_FY_SINGLE = re.compile(r"FY\s*(\d{2,4})\b", re.IGNORECASE)
_DATE = re.compile(
    r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]+)[,\s]+(\d{4})", re.IGNORECASE
)


def _fmt(start_year: int, end_year: int) -> str:
    return f"FY{start_year % 100:02d}-{end_year % 100:02d}"


def _expand(year: int) -> int:
    """Turn a 2-digit year into a 4-digit year (assume 2000s)."""
    if year < 100:
        return 2000 + year
    return year


def normalize_fy(raw: object) -> Optional[str]:
    """Normalise a variety of year formats to ``FY25-26``.

    Accepts ``FY25-26``, ``2025-26``, ``FY2025-2026``, ``FY26`` and dates such
    as ``31 March 2026``. Returns ``None`` when nothing can be parsed.
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None

    # A date implies the year ending on that date.
    date_match = _DATE.search(text)
    if date_match:
        day = int(date_match.group(1))
        month = _MONTHS.get(date_match.group(2).lower())
        year = int(date_match.group(3))
        if month is not None and day <= 31:
            # The Indian financial year ends 31 March. Dates Apr-Dec fall in the
            # FY ending the following March; Jan-Mar fall in the FY ending that March.
            end = year + 1 if month >= 4 else year
            return _fmt(end - 1, end)

    range_match = _FY_RANGE.search(text)
    if range_match:
        start = _expand(int(range_match.group(1)))
        end = _expand(int(range_match.group(2)))
        # ``2025-26`` -> end must be reconstructed from the short form.
        if int(range_match.group(2)) < 100 and start >= 2000:
            end = (start // 100) * 100 + int(range_match.group(2))
            if end <= start:
                end += 100
        if end == start + 1 or end == start:
            return _fmt(start, end)
        # Fall back to treating the larger number as the ending year.
        lo, hi = sorted((start, end))
        return _fmt(hi - 1, hi)

    single = _FY_SINGLE.search(text)
    if single:
        end = _expand(int(single.group(1)))
        return _fmt(end - 1, end)

    # Bare 4-digit year.
    bare = re.fullmatch(r"(\d{4})", text)
    if bare:
        end = int(bare.group(1))
        return _fmt(end - 1, end)

    return None


def prior_fy(fy: object) -> Optional[str]:
    """Return the previous financial year for a ``FY25-26``-style input."""
    normalized = normalize_fy(fy)
    if not normalized:
        return None
    match = re.fullmatch(r"FY(\d{2})-(\d{2})", normalized)
    if not match:
        return None
    start = int(match.group(1))
    end = int(match.group(2))
    prev_start = start - 1
    prev_end = end - 1
    return f"FY{prev_start % 100:02d}-{prev_end % 100:02d}"


def fy_start_year(fy: object) -> Optional[int]:
    """Return the four-digit starting year of a financial year."""
    normalized = normalize_fy(fy)
    if not normalized:
        return None
    match = re.fullmatch(r"FY(\d{2})-(\d{2})", normalized)
    if not match:
        return None
    start = int(match.group(1))
    return 2000 + start
