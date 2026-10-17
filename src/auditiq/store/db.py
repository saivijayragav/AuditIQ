"""Engine / session helpers for the AuditIQ store."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator, Optional

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from ..settings import DATABASE_URL, ensure_dirs
from .models import Base

_engine: Optional[Engine] = None
_session_factory: Optional[sessionmaker] = None


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
    """Create all tables if they do not exist and return the engine."""
    engine = get_engine(url, echo=echo)
    Base.metadata.create_all(engine)
    return engine


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
