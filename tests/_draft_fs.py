"""Synthetic draft-financial-statement PDFs.

There is no real draft-FS sample in the repository, so this module generates a
Schedule III face (balance sheet + statement of profit and loss) as a PDF using
PyMuPDF — already a dependency of the PDF reader, so no extra dependency is
required for tests. The generated layout mirrors the text-line form the reader's
text path expects: ``label  note  current  prior``.

The helpers are deliberately tiny and deterministic; tests build their own rows.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional, Sequence

# A face row: (label, note_ref, current, prior). ``note_ref``/``prior`` may be None.
Row = tuple


def _format_number(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    if isinstance(value, int):
        return f"{value:,}"
    return f"{value:,.2f}"


def render_rows(rows: Iterable[Row]) -> list[str]:
    """Render face rows as ``label  note  current  prior`` text lines."""
    lines: list[str] = []
    for label, note, current, prior in rows:
        parts = [str(label)]
        if note not in (None, "", 0):
            parts.append(str(note))
        if current is not None:
            parts.append(_format_number(current))
        if prior is not None:
            parts.append(_format_number(prior))
        lines.append("  ".join(parts))
    return lines


def write_fs_pdf(
    path: str | Path,
    *,
    company: str = "Test Co Limited",
    period: str = "FY25-26",
    unit: str = "absolute",
    basis: str = "Standalone",
    bs_rows: Sequence[Row] = (),
    pl_rows: Sequence[Row] = (),
) -> Path:
    """Write a draft balance sheet + P&L to a PDF and return its path."""
    import pymupdf  # lazy: [report] extra

    path = Path(path)
    unit_line = "(Amount in Rs.)" if unit == "absolute" else f"(Amount in Rs. {unit})"

    pages: list[tuple[str, Sequence[Row]]] = []
    if bs_rows:
        pages.append(("Balance Sheet as at 31 March 2026", bs_rows))
    if pl_rows:
        pages.append(
            ("Statement of Profit and Loss for the year ended 31 March 2026", pl_rows)
        )

    document = pymupdf.open()
    try:
        for index, (heading, rows) in enumerate(pages):
            page = document.new_page()
            y = 72.0
            if index == 0:
                page.insert_text((72, y), company, fontsize=12)
                y += 18
                page.insert_text((72, y), f"{basis} financial statements", fontsize=9)
                y += 20
            page.insert_text((72, y), heading, fontsize=11)
            y += 16
            page.insert_text((72, y), unit_line, fontsize=8)
            y += 16
            page.insert_text((72, y), "Particulars  Note  Current  Prior", fontsize=9)
            y += 16
            for line in render_rows(rows):
                page.insert_text((72, y), line, fontsize=9)
                y += 14
        document.save(str(path))
    finally:
        document.close()
    return path


def schedule_iii_rows(
    totals_by_fsli: dict[str, float],
    taxonomy,
    *,
    note: Optional[str] = None,
) -> tuple[list[Row], list[Row]]:
    """Turn ``{fsli_code: amount}`` into ``(bs_rows, pl_rows)`` face rows.

    The current-year column carries the amount and the prior year is left blank,
    so a tie-out only needs the current column.
    """
    bs_rows: list[Row] = []
    pl_rows: list[Row] = []
    for code, amount in totals_by_fsli.items():
        item = taxonomy.get(code)
        if item is None:
            continue
        row = (item.name, note, round(float(amount), 2), None)
        statement = item.statement.lower()
        if statement.startswith("balance"):
            bs_rows.append(row)
        elif "profit and loss" in statement:
            pl_rows.append(row)
    return bs_rows, pl_rows


def describe(rows: Sequence[Row]) -> str:
    """Human-readable dump of rows, handy when debugging a failing test."""
    return "\n".join(render_rows(rows))


__all__ = ["Row", "describe", "render_rows", "schedule_iii_rows", "write_fs_pdf"]
