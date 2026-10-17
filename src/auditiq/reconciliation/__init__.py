"""Reconciliation: tie the mapped trial balance (Side A) to the client's draft
financial statements (Side B).

Public surface:

* :func:`run_recon` — aggregate, tie out, articulate, attribute and persist.
* :func:`latest_run` / :func:`explain_unit` — read a persisted run back.
* :func:`set_materiality` / :func:`suggest_for_engagement` — materiality helpers.
* :class:`MaterialityError` — raised when no usable materiality is set.
"""
from __future__ import annotations

from .aggregate import ExposureLine, FsExposureRow, SideA, SideB, SubtotalRow, side_a, side_b
from .articulation import Finding, articulate
from .attribution import Attribution, Candidate, attribute
from .materiality import (
    DEFAULT_PM_RATIO,
    DEFAULT_ROUNDING_DECIMALS,
    ReconConfig,
    MaterialityError,
    build_config,
    classify,
    rounding_tolerance,
    suggest_materiality,
    variance_percent,
)
from .service import (
    ReconSummary,
    StoredLine,
    explain_unit,
    latest_run,
    run_recon,
    set_materiality,
    suggest_for_engagement,
)
from .tieout import ReconLineResult, ReconUnit, build_units, tieout

__all__ = [
    "Attribution",
    "Candidate",
    "DEFAULT_PM_RATIO",
    "DEFAULT_ROUNDING_DECIMALS",
    "ExposureLine",
    "Finding",
    "FsExposureRow",
    "MaterialityError",
    "ReconConfig",
    "ReconLineResult",
    "ReconSummary",
    "ReconUnit",
    "SideA",
    "SideB",
    "StoredLine",
    "SubtotalRow",
    "articulate",
    "attribute",
    "build_config",
    "build_units",
    "classify",
    "explain_unit",
    "latest_run",
    "rounding_tolerance",
    "run_recon",
    "set_materiality",
    "side_a",
    "side_b",
    "suggest_for_engagement",
    "suggest_materiality",
    "tieout",
    "variance_percent",
]
