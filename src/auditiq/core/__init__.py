"""Core primitives: taxonomy, units, periods and shared enums."""
from __future__ import annotations

from .enums import (
    DocumentKind,
    MappingMethod,
    MappingStatus,
    NoteCategory,
    Side,
    SourceSystem,
    Statement,
)
from .periods import fy_start_year, normalize_fy, prior_fy
from .groups import FsliGroup, GroupIndex, load_default_groups
from .taxonomy import Fsli, Taxonomy, load_default_taxonomy, statement_code
from .text import clean, nu
from .units import (
    CRORE,
    detect_unit,
    normalize_unit,
    parse_amount,
    to_absolute,
    to_crores,
)

__all__ = [
    "CRORE",
    "DocumentKind",
    "Fsli",
    "FsliGroup",
    "GroupIndex",
    "MappingMethod",
    "MappingStatus",
    "NoteCategory",
    "Side",
    "SourceSystem",
    "Statement",
    "Taxonomy",
    "clean",
    "detect_unit",
    "fy_start_year",
    "load_default_groups",
    "load_default_taxonomy",
    "normalize_fy",
    "normalize_unit",
    "nu",
    "parse_amount",
    "prior_fy",
    "statement_code",
    "to_absolute",
    "to_crores",
]
