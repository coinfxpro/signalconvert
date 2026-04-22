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
    """Uygulama açılışında tabloları oluştur ve basit migrasyon uygula."""
    # Modellerin import edildiğinden emin ol
    from . import models  # noqa: F401

    SQLModel.metadata.create_all(engine)
    _apply_migrations()


def _apply_migrations() -> None:
    """Eski DB'lere yeni kolonları ekleyen minimal migrasyon (SQLite)."""
    from sqlalchemy import text, inspect

    inspector = inspect(engine)
    tables = inspector.get_table_names()
    if "bot" not in tables:
        return
    cols = {c["name"] for c in inspector.get_columns("bot")}
    migrations: list[str] = []
    if "brand_name" not in cols:
        migrations.append("ALTER TABLE bot ADD COLUMN brand_name VARCHAR")
    if not migrations:
        return
    with engine.begin() as conn:
        for sql in migrations:
            conn.execute(text(sql))


@contextmanager
def session_scope() -> Iterator[Session]:
    """Context manager tabanlı session."""
    with Session(engine) as session:
        yield session


def get_session() -> Iterator[Session]:
    """FastAPI Depends için generator."""
    with Session(engine) as session:
        yield session
