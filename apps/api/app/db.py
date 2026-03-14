"""Database bootstrap and session management utilities.

The repository supports both local-development SQLite usage and production-style
database URLs, so this module centralizes engine creation, session lifecycle,
and test-time reset behavior. Tests rely on the reset hooks here to rebuild the
database cleanly between runs.
"""

from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings


class Base(DeclarativeBase):
    pass


SessionLocal = sessionmaker(
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    future=True,
)

_engine: Engine | None = None


def _build_engine() -> Engine:
    settings = get_settings()
    connect_args = {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
    return create_engine(
        settings.database_url,
        future=True,
        connect_args=connect_args,
    )


def get_engine() -> Engine:
    global _engine

    if _engine is None:
        _engine = _build_engine()
        SessionLocal.configure(bind=_engine)
    return _engine


def reset_db_connection() -> None:
    global _engine

    if _engine is not None:
        _engine.dispose()
    _engine = None
    SessionLocal.configure(bind=get_engine())


def get_db() -> Generator[Session, None, None]:
    get_engine()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    import app.models  # noqa: F401

    Base.metadata.create_all(bind=get_engine())
