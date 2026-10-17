"""Reconstruct visual text rows from PDF word coordinates.

Many financial statements are laid out as borderless tables: PyMuPDF's plain text
extraction then emits the label and the figures as *separate* lines (or reorders
columns), which defeats line-based parsing. Grouping words by their vertical band
recovers the original visual row (``label ... current prior``) regardless of how
the text is ordered in the content stream.
"""
from __future__ import annotations

from typing import Iterable


def visual_lines(page, y_tolerance: float = 3.0) -> list[str]:
    """Return the page's text rows, reconstructed from word coordinates.

    ``page`` is a PyMuPDF page. Words whose baseline is within ``y_tolerance``
    points are treated as the same visual row and joined left-to-right.
    """
    words = sorted(page.get_text("words"), key=lambda w: (round(float(w[1]), 1), w[0]))
    if not words:
        return []

    lines: list[str] = []
    band: list[tuple[float, str]] = []
    band_y: float | None = None

    for word in words:
        x0, y0, text = float(word[0]), float(word[1]), word[4]
        if band_y is None or abs(y0 - band_y) <= y_tolerance:
            band.append((x0, text))
            if band_y is None:
                band_y = y0
        else:
            lines.append(_join(band))
            band, band_y = [(x0, text)], y0

    if band:
        lines.append(_join(band))
    return [line for line in lines if line]


def _join(band: Iterable[tuple[float, str]]) -> str:
    return " ".join(text for _, text in sorted(band, key=lambda item: item[0])).strip()


__all__ = ["visual_lines"]
