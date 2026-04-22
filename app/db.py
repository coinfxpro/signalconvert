"""DB engine + session yardımcıları."""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlmodel import Session, SQLModel, create_engine

from .config import settings

# SQLite için check_same_thread=False gerekli (FastAPI thread'lerinden erişim)
connect_args = {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(settings.DATABASE_URL, echo=False, connect_args=connect_args)


def init_db() -> None:
    """Uygulama açılışında tabloları oluştur."""
    # Modellerin import edildiğinden emin ol
    from . import models  # noqa: F401

    SQLModel.metadata.create_all(engine)


@contextmanager
def session_scope() -> Iterator[Session]:
    """Context manager tabanlı session."""
    with Session(engine) as session:
        yield session


def get_session() -> Iterator[Session]:
    """FastAPI Depends için generator."""
    with Session(engine) as session:
        yield session
