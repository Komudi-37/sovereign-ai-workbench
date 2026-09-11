"""
SQLAlchemy database engine and session management.

Configurable via DATABASE_URL environment variable.
Default: SQLite for prototype portability.
Supports PostgreSQL for production deployment.
"""

import logging
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""
    pass


def _ensure_db_directory(url: str) -> None:
    """Create the parent directory for SQLite database files."""
    if url.startswith("sqlite"):
        # Extract path from sqlite:///./data/sovereign.db
        db_path = url.replace("sqlite:///", "")
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)


_ensure_db_directory(settings.database_url)

engine = create_engine(
    settings.database_url,
    connect_args={"check_same_thread": False} if "sqlite" in settings.database_url else {},
    echo=False,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db():
    """FastAPI dependency — yields a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
