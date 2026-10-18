"""Engine / session helpers for the AuditIQ store."""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from ..settings import DATABASE_URL, ensure_dirs
from .models import Base

_engine: Optional[Engine] = None
_session_factory: Optional[sessionmaker] = None
_schema_checked: set[str] = set()


class SchemaDriftError(RuntimeError):
    """Raised when an existing database predates the current ORM models.

    ``create_all`` can add missing *tables* but never *columns*, so a database
    created before a model change stays stale. Callers surface this and point
    the user at ``auditiq store reset``.
    """


def _missing_columns(engine: Engine) -> list[str]:
    """Model columns that are absent from an existing table."""
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    missing: list[str] = []
    for name, table in Base.metadata.tables.items():
        if name not in existing:  # not present yet: create_all will build it
            continue
        have = {column["name"] for column in inspector.get_columns(name)}
        missing.extend(
            f"{name}.{column.name}" for column in table.columns if column.name not in have
        )
    return sorted(missing)


def check_schema(engine: Engine) -> None:
    """Raise :class:`SchemaDriftError` when *engine*'s schema is out of date.

    Checked once per engine URL per process; a healthy schema caches the result
    so repeated service calls stay cheap.
    """
    key = str(engine.url)
    if key in _schema_checked:
        return
    missing = _missing_columns(engine)
    if missing:
        listed = "\n".join(f"  - {name}" for name in missing)
        raise SchemaDriftError(
            "Database schema is out of date — these columns are missing:\n"
            f"{listed}\n"
            "init_db() creates new tables but cannot add columns to an existing "
            "one. Rebuild the local database with 'auditiq store reset' (this "
            "deletes local data)."
        )
    _schema_checked.add(key)


def get_engine(url: Optional[str] = None, echo: bool = False) -> Engine:
    """Return a (cached) SQLAlchemy engine."""
    global _engine, _session_factory
    if url is not None:
        engine = create_engine(url, echo=echo, future=True)
        _engine = engine
        _session_factory = sessionmaker(bind=engine, future=True)
        return engine
    if _engine is None:
        ensure_dirs()
        _engine = create_engine(DATABASE_URL, echo=echo, future=True)
        _session_factory = sessionmaker(bind=_engine, future=True)
    return _engine


def init_db(url: Optional[str] = None, echo: bool = False) -> Engine:
    """Create all tables if they do not exist and return the engine.

    Raises :class:`SchemaDriftError` when an existing database is missing
    columns the models expect (see :func:`check_schema`).
    """
    engine = get_engine(url, echo=echo)
    Base.metadata.create_all(engine)
    check_schema(engine)
    return engine


def reset_db(url: Optional[str] = None) -> Engine:
    """Delete the SQLite database file and rebuild an empty schema.

    Disposes any cached engine, removes the database file (and its ``-wal`` /
    ``-shm`` companions), then re-creates the schema via :func:`init_db`.
    Source files under ``data/uploads`` are left untouched. SQLite only.
    """
    global _engine, _session_factory
    engine = get_engine(url)
    if engine.dialect.name != "sqlite":
        raise RuntimeError(
            f"'store reset' only supports SQLite databases, not "
            f"'{engine.dialect.name}'. Drop the schema manually instead."
        )
    database = engine.url.database
    key = str(engine.url)
    _engine = None
    _session_factory = None
    engine.dispose()
    if database and database != ":memory:":
        for suffix in ("", "-wal", "-shm"):
            Path(f"{database}{suffix}").unlink(missing_ok=True)
    _schema_checked.discard(key)
    return init_db(url)


@contextmanager
def session_scope(url: Optional[str] = None) -> Iterator[Session]:
    """Transactional session context. Commits on success, rolls back on error."""
    factory = _session_factory
    if url is not None or factory is None:
        get_engine(url)
        factory = _session_factory
    assert factory is not None
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
