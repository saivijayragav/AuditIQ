"""Statement segmentation and face-line extraction (reader-neutral).

Takes a reader-produced :class:`FsDocument` and produces, per statement, a list
of :class:`FsRow` objects — ``(label, note_ref, current, prior, is_subtotal)`` —
with **no** knowledge of the FSLI taxonomy. Mapping the label to an FSLI is a
separate stage (see :mod:`auditiq.ingest.fs.labels`), so this layer is fully
generic across document types.
"""
from __future__ import annotations

import re
from typing import Optional

from ...core.periods import normalize_fy, prior_fy
from ...core.units import parse_amount
from .base import (
    STATEMENT_BS,
    STATEMENT_CF,
    STATEMENT_EQUITY,
    STATEMENT_KEYS,
    STATEMENT_NOTES,
    STATEMENT_PL,
    FsDocument,
    FsPage,
    FsRow,
    FsTable,
)

# Keyword signatures per statement (lower-cased substrings).
_SECTION_KEYWORDS: dict[str, tuple[str, ...]] = {
    STATEMENT_BS: (
        "balance sheet",
        "statement of assets and liabilities",
        "equity and liabilities",
        "assets and liabilities",
    ),
    STATEMENT_PL: (
        "statement of profit and loss",
        "statement of profit & loss",
        "profit and loss",
        "income statement",
        "statement of income",
    ),
    STATEMENT_CF: ("cash flow",),
    STATEMENT_EQUITY: (
        "statement of changes in equity",
        "changes in equity",
        "statement of changes in",
    ),
    STATEMENT_NOTES: (
        "notes to the financial statements",
        "notes to accounts",
        "notes forming part",
        "significant accounting policies",
        "notes to the standalone",
        "notes to the consolidated",
    ),
}

# A trailing run of numeric tokens, e.g. " 1,234  1,000" or " 4  1,234  1,000".
_TRAILING_NUMBERS = re.compile(r"((?:\s+\(?-?[\d,]+(?:\.\d+)?\)?\s*)+)$")
_NUMBER = re.compile(r"\(?-?[\d,]+(?:\.\d+)?\)?")
_LETTER = re.compile(r"[A-Za-z]{2,}")
_SUBTOTAL = re.compile(r"^\s*(?:sub[\s-]?total|total)\b", re.IGNORECASE)
_LEADING_JUNK = re.compile(r"^[\s\u2022\-\*\.\)]+")
_ROMAN = re.compile(r"^\(?(?:[ivxlc]{1,4})\)?[\.\)]?\s+", re.IGNORECASE)
_ENUM = re.compile(r"^\(?(?:[a-z]|\d{1,2})\)?[\.\)]\s+", re.IGNORECASE)
# A trailing note reference such as "3A" or "23A,23B" left inside the label.
_TRAILING_NOTE = re.compile(
    r"\s+\(?\d{1,3}[A-Za-z]?(?:\s*,\s*\d{1,3}[A-Za-z]?)*\)?$"
)

# Head-line fragments that look numeric but are headers/date lines, not line items.
_SKIP_HEAD = re.compile(
    r"\b(as at|as of|year ended|years ended|period ended|particulars|note\s*no|"
    r"s\.?\s*no|figures? in|amounts? in|for the year|balance as at|audited|unaudited|"
    r"report and accounts|membership\s*no|registered office|chartered accountants|"
    r"company secretary|corporate information|for and on behalf|place\s*:|date\s*:|"
    r"signed|signature|din\b|"
    r"balance sheet|statement of profit|statement of changes|statement of cash flows|"
    r"independent auditor|financial statements)\b",
    re.IGNORECASE,
)
_MONTH = re.compile(
    r"\b(january|february|march|april|may|june|july|august|september|october|"
    r"november|december)\b",
    re.IGNORECASE,
)


# --------------------------------------------------------------------------- #
# segmentation
# --------------------------------------------------------------------------- #
def classify_page(page: FsPage) -> Optional[str]:
    """Return the statement key a page belongs to, or ``None`` when unclear.

    A title-line hit (weight 3) is required: a page that merely *mentions* a
    statement in body text (an auditor's report, a note) is not classified, which
    keeps report boilerplate out of the extracted face rows.
    """
    lines = page.text.splitlines()
    head = "\n".join(lines[:6]).lower()
    body = page.text.lower()
    best: Optional[str] = None
    best_score = 0.0
    for key, keywords in _SECTION_KEYWORDS.items():
        score = 0.0
        for keyword in keywords:
            if keyword in head:
                score += 3.0
            elif keyword in body:
                score += 1.0
        if score > best_score:
            best, best_score = key, score
    return best if best_score >= 3.0 else None


def segment_pages(document: FsDocument) -> dict[str, list[FsPage]]:
    """Group document pages by statement key."""
    grouped: dict[str, list[FsPage]] = {}
    for page in document.pages:
        key = classify_page(page)
        if key is not None:
            grouped.setdefault(key, []).append(page)
    return grouped


# --------------------------------------------------------------------------- #
# extraction
# --------------------------------------------------------------------------- #
def _is_subtotal_label(label: str) -> bool:
    return bool(_SUBTOTAL.match(label))


def _clean_label(text: str) -> str:
    label = _LEADING_JUNK.sub("", text or "")
    label = _ROMAN.sub("", label)
    label = _ENUM.sub("", label)
    label = _LEADING_JUNK.sub("", label)
    return re.sub(r"\s{2,}", " ", label).strip(" .:-")


def _split_trailing(numbers: list[str]) -> tuple[Optional[str], str, str]:
    """Split trailing numeric tokens into ``(note_ref, current_text, prior_text)``.

    The Schedule III face layout is ``Particulars | Note | Current | Prior``; a
    third trailing number is treated as the note reference.
    """
    if len(numbers) >= 3:
        return numbers[-3], numbers[-2], numbers[-1]
    if len(numbers) == 2:
        return None, numbers[0], numbers[1]
    return None, numbers[0], ""


def row_from_line(line: str, page: int) -> Optional[FsRow]:
    """Parse a single face-statement text line into an :class:`FsRow`."""
    text = (line or "").strip()
    if not text or not _LETTER.search(text):
        return None

    match = _TRAILING_NUMBERS.search(text)
    if not match:
        return None
    numbers = _NUMBER.findall(match.group(1))
    if not 1 <= len(numbers) <= 3:
        return None

    head = text[: match.start()].strip()
    if not head or not _LETTER.search(head):
        return None
    if _SKIP_HEAD.search(head) or _MONTH.search(head):
        return None

    head = _TRAILING_NOTE.sub("", head).strip()
    label = _clean_label(head)
    if not label:
        return None

    note_ref, current_text, prior_text = _split_trailing(numbers)
    current = parse_amount(current_text) if current_text else None
    prior = parse_amount(prior_text) if prior_text else None
    if current is None and prior is None:
        return None

    return FsRow(
        label=label,
        note_ref=note_ref,
        current=current,
        prior=prior,
        current_text=current_text,
        prior_text=prior_text,
        is_subtotal=_is_subtotal_label(label),
        raw_text=text,
        location=_page_location(page),
    )


def _page_location(page: int):
    from .base import FsLocation

    return FsLocation(kind="pdf", page=page)


def value_columns(headers: list[str], period: Optional[str]) -> tuple[Optional[int], Optional[int]]:
    """Locate the current-year and prior-year columns in a table header."""
    current = prior = None
    dated: list[tuple[int, str]] = []
    want_current = normalize_fy(period) if period else None
    want_prior = prior_fy(period) if period else None

    for index, header in enumerate(headers):
        year = normalize_fy(header)
        if not year:
            continue
        dated.append((index, year))
        if want_current and year == want_current:
            current = index
        elif want_prior and year == want_prior:
            prior = index

    if current is None and dated:
        dated.sort(key=lambda item: item[1], reverse=True)
        current = dated[0][0]
        if prior is None and len(dated) > 1:
            prior = dated[1][0]

    if current is None and len(headers) >= 2:
        current, prior = len(headers) - 2, len(headers) - 1

    return current, prior


def rows_from_table(table: FsTable, period: Optional[str]) -> list[FsRow]:
    """Extract face rows from a table, binding current/prior columns."""
    if not table.rows:
        return []
    current_col, prior_col = value_columns(table.headers, period)
    start = 1 if table.headers else 0
    rows: list[FsRow] = []

    for raw in table.rows[start:]:
        if not raw:
            continue
        label = _clean_label(str(raw[0]))
        if not label or not _LETTER.search(label):
            continue

        current = (
            parse_amount(raw[current_col])
            if current_col is not None and current_col < len(raw)
            else None
        )
        prior = (
            parse_amount(raw[prior_col])
            if prior_col is not None and prior_col < len(raw)
            else None
        )
        if current is None and prior is None:
            continue

        rows.append(
            FsRow(
                label=label,
                current=current,
                prior=prior,
                is_subtotal=_is_subtotal_label(label),
                raw_text=" | ".join(str(cell) for cell in raw),
                location=table.location,
            )
        )
    return rows


def rows_from_page(page: FsPage, period: Optional[str]) -> list[FsRow]:
    """Extract face rows from one page.

    Preference order: a usable extracted table, then coordinate-reconstructed
    visual rows, then the raw text lines.
    """
    for table in page.tables:
        rows = rows_from_table(table, period)
        if len(rows) >= 2:
            return rows

    source_lines = page.word_rows or page.text.splitlines()
    return [
        row
        for line in source_lines
        if (row := row_from_line(line, page.page)) is not None
    ]


def extract_statements(document: FsDocument) -> dict[str, list[FsRow]]:
    """Segment the document and extract face rows per statement.

    Populates ``document.statements`` and returns only non-empty statements.
    """
    period = document.period
    out: dict[str, list[FsRow]] = {}
    for key, pages in segment_pages(document).items():
        rows: list[FsRow] = []
        for page in pages:
            rows.extend(rows_from_page(page, period))
        if rows:
            out[key] = rows
    for key in STATEMENT_KEYS:
        if key in out:
            document.statements[key] = out[key]
    return out


__all__ = [
    "classify_page",
    "extract_statements",
    "row_from_line",
    "rows_from_page",
    "rows_from_table",
    "segment_pages",
    "value_columns",
]
