"""Web harness (JSON API + server-rendered UI) for AuditIQ Core."""
from .app import create_app

__all__ = ["create_app"]
