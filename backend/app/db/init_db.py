"""
Database initialization for Sovereign AI Workbench.

Creates all tables and seeds the default user on first run.
Called automatically during FastAPI startup.
"""

import logging

from app.db.database import Base, engine, SessionLocal
from app.db.models import (  # noqa: F401 — import to register models
    UserModel,
    SessionModel,
    MessageModel,
    DocumentModel,
    DocumentChunkModel,
    WorkflowRunModel,
    AgentRunModel,
    ArtifactModel,
    AuditLogModel,
)

logger = logging.getLogger(__name__)


def init_database() -> None:
    """
    Create all database tables and seed initial data.

    Safe to call multiple times — SQLAlchemy's create_all
    is a no-op for tables that already exist.
    """
    logger.info("Initializing database...")

    # Create all tables
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created/verified")

    # Seed default user if not exists
    db = SessionLocal()
    try:
        existing = db.query(UserModel).filter_by(username="admin").first()
        if not existing:
            default_user = UserModel(
                username="admin",
                role="admin",
            )
            db.add(default_user)
            db.commit()
            logger.info("Default admin user created")
        else:
            logger.debug("Default admin user already exists")
    except Exception as exc:
        logger.error("Error seeding default user: %s", exc)
        db.rollback()
    finally:
        db.close()

    logger.info("Database initialization complete")
