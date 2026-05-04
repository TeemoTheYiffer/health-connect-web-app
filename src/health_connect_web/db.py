"""SQLAlchemy engine and session factory."""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from health_connect_web.config import get_settings


def _make_engine() -> Engine:
    url = get_settings().database_url
    # SQLite needs check_same_thread=False when used across FastAPI threadpool.
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args, pool_pre_ping=True, future=True)


_engine: Engine | None = None
_SessionLocal: sessionmaker[Session] | None = None


def engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = _make_engine()
    return _engine


def session_factory() -> sessionmaker[Session]:
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=engine(), autoflush=False, expire_on_commit=False)
    return _SessionLocal


@contextmanager
def session_scope() -> Iterator[Session]:
    """Context-managed Session that commits on success and rolls back on error."""
    s = session_factory()()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


# FastAPI dependency
def get_db() -> Iterator[Session]:
    s = session_factory()()
    try:
        yield s
    finally:
        s.close()
