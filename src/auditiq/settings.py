"""Filesystem locations and configuration for AuditIQ Core.

All paths default to repo-relative locations and can be overridden with
environment variables (see ``.env.example``).
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _default_root() -> Path:
    # src/auditiq/settings.py -> repo root is three levels up.
    return Path(__file__).resolve().parents[2]


BASE_DIR: Path = Path(os.getenv("AUDITIQ_HOME", str(_default_root()))).resolve()

CONFIG_DIR: Path = BASE_DIR / "config"
TAXONOMY_DIR: Path = CONFIG_DIR / "taxonomy"

DATA_DIR: Path = Path(os.getenv("AUDITIQ_DATA_DIR", str(BASE_DIR / "data"))).resolve()
UPLOAD_DIR: Path = DATA_DIR / "uploads"
THRESHOLDS_DIR: Path = DATA_DIR / "thresholds"

# Committed reference taxonomy / alias / seed assets.
FSLI_SCHEMA_PATH: Path = Path(
    os.getenv("AUDITIQ_FSLI_SCHEMA", str(TAXONOMY_DIR / "fsli_schema.csv"))
)
ALIASES_PATH: Path = Path(os.getenv("AUDITIQ_ALIASES", str(TAXONOMY_DIR / "aliases.csv")))
SEEDS_PATH: Path = Path(os.getenv("AUDITIQ_SEEDS", str(TAXONOMY_DIR / "seeds.csv")))

# Reconciliation group layer: presentation aggregates that span several FSLIs
# (e.g. "Revenue from Operations" = the three revenue FSLIs presented as one face
# line). Membership lives in ``fsli_groups.csv``; presentation labels in
# ``group_aliases.csv``.
FSLI_GROUPS_PATH: Path = Path(
    os.getenv("AUDITIQ_FSLI_GROUPS", str(TAXONOMY_DIR / "fsli_groups.csv"))
)
GROUP_ALIASES_PATH: Path = Path(
    os.getenv("AUDITIQ_GROUP_ALIASES", str(TAXONOMY_DIR / "group_aliases.csv"))
)

# Database (SQLite by default; swap the URL for Postgres later).
DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'auditiq.db'}")

# --- HTTP API -------------------------------------------------------------
# Origins allowed to call the API from a browser. The frontend is a separate
# app, so local dev servers are permitted by default; override for anything else.
CORS_ORIGINS: list[str] = [
    origin.strip()
    for origin in os.getenv(
        "AUDITIQ_CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,"
        "http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if origin.strip()
]

# Reading a file straight off the server's disk is a CLI affordance. A browser
# client has no business doing it, so it is off unless explicitly enabled.
ALLOW_PATH_INGEST: bool = os.getenv("AUDITIQ_ALLOW_PATH_INGEST", "").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)

# Optional LLM layer.
GOOGLE_API_KEY: str | None = os.getenv("GOOGLE_API_KEY")
LLM_MODEL: str = os.getenv("AUDITIQ_LLM_MODEL", "gemini-3.1-flash-lite")


def ensure_dirs() -> None:
    """Create the writable data directories if they do not exist."""
    for path in (DATA_DIR, UPLOAD_DIR, THRESHOLDS_DIR):
        path.mkdir(parents=True, exist_ok=True)
