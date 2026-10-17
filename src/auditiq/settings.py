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

# Database (SQLite by default; swap the URL for Postgres later).
DATABASE_URL: str = os.getenv("DATABASE_URL", f"sqlite:///{DATA_DIR / 'auditiq.db'}")

# Optional LLM layer.
GOOGLE_API_KEY: str | None = os.getenv("GOOGLE_API_KEY")
LLM_MODEL: str = os.getenv("AUDITIQ_LLM_MODEL", "gemini-3.1-flash-lite")


def ensure_dirs() -> None:
    """Create the writable data directories if they do not exist."""
    for path in (DATA_DIR, UPLOAD_DIR, THRESHOLDS_DIR):
        path.mkdir(parents=True, exist_ok=True)
