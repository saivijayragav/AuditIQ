"""Shared pytest fixtures."""
from __future__ import annotations

import pytest

from auditiq.core import load_default_taxonomy


@pytest.fixture(scope="session")
def taxonomy():
    return load_default_taxonomy()
