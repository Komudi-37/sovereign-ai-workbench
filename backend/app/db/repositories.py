"""
Database repository functions for Sovereign AI Workbench.

Provides CRUD operations for all database models.
Used by API routes and agent integrations.
"""

import json
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.db.models import (
    ArtifactModel,
    AuditLogModel,
    AgentRunModel,
    DocumentChunkModel,
    DocumentModel,
    MessageModel,
    SessionModel,
    UserModel,
    WorkflowRunModel,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

def get_default_user(db: Session) -> UserModel:
    """Get or create the default admin user."""
    user = db.query(UserModel).filter_by(username="admin").first()
    if not user:
        user = UserModel(username="admin", role="admin")
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

def create_session(db: Session, user_id: str, title: str = "New Chat") -> SessionModel:
    session = SessionModel(user_id=user_id, title=title)
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def get_session(db: Session, session_id: str) -> SessionModel | None:
    return db.query(SessionModel).filter_by(id=session_id).first()


def list_sessions(db: Session, limit: int = 50) -> list[SessionModel]:
    return db.query(SessionModel).order_by(SessionModel.updated_at.desc()).limit(limit).all()


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

def create_message(db: Session, session_id: str, role: str, content: str, model: str = None) -> MessageModel:
    msg = MessageModel(session_id=session_id, role=role, content=content, model=model)
    db.add(msg)
    db.commit()
    db.refresh(msg)
    # Update session's updated_at
    session = db.query(SessionModel).filter_by(id=session_id).first()
    if session:
        session.updated_at = datetime.now(timezone.utc)
        db.commit()
    return msg


def list_messages(db: Session, session_id: str) -> list[MessageModel]:
    return db.query(MessageModel).filter_by(session_id=session_id).order_by(MessageModel.created_at).all()


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------

def create_document(db: Session, **kwargs) -> DocumentModel:
    doc = DocumentModel(**kwargs)
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


def get_document(db: Session, doc_id: str) -> DocumentModel | None:
    return db.query(DocumentModel).filter_by(id=doc_id).first()


def get_document_by_checksum(db: Session, checksum: str) -> DocumentModel | None:
    return db.query(DocumentModel).filter_by(checksum=checksum).first()


def list_documents(db: Session, limit: int = 100) -> list[DocumentModel]:
    return db.query(DocumentModel).order_by(DocumentModel.created_at.desc()).limit(limit).all()


def update_document_status(db: Session, doc_id: str, status: str) -> None:
    doc = db.query(DocumentModel).filter_by(id=doc_id).first()
    if doc:
        doc.status = status
        db.commit()


# ---------------------------------------------------------------------------
# Document Chunks
# ---------------------------------------------------------------------------

def create_chunk(db: Session, **kwargs) -> DocumentChunkModel:
    chunk = DocumentChunkModel(**kwargs)
    db.add(chunk)
    db.commit()
    db.refresh(chunk)
    return chunk


def create_chunks_bulk(db: Session, chunks: list[dict]) -> int:
    """Insert multiple chunks at once. Returns count inserted."""
    objs = [DocumentChunkModel(**c) for c in chunks]
    db.add_all(objs)
    db.commit()
    return len(objs)


def get_chunks_for_document(db: Session, doc_id: str) -> list[DocumentChunkModel]:
    return db.query(DocumentChunkModel).filter_by(document_id=doc_id).order_by(DocumentChunkModel.chunk_index).all()


def count_chunks(db: Session) -> int:
    return db.query(DocumentChunkModel).count()


# ---------------------------------------------------------------------------
# Workflow Runs
# ---------------------------------------------------------------------------

def create_workflow_run(db: Session, **kwargs) -> WorkflowRunModel:
    run = WorkflowRunModel(**kwargs)
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def get_workflow_run(db: Session, run_id: str) -> WorkflowRunModel | None:
    return db.query(WorkflowRunModel).filter_by(id=run_id).first()


def list_workflow_runs(db: Session, limit: int = 50) -> list[WorkflowRunModel]:
    return db.query(WorkflowRunModel).order_by(WorkflowRunModel.started_at.desc()).limit(limit).all()


def complete_workflow_run(db: Session, run_id: str, status: str, result_json: str = None) -> None:
    run = db.query(WorkflowRunModel).filter_by(id=run_id).first()
    if run:
        run.status = status
        run.completed_at = datetime.now(timezone.utc)
        if result_json:
            run.result_json = result_json
        db.commit()


# ---------------------------------------------------------------------------
# Agent Runs
# ---------------------------------------------------------------------------

def create_agent_run(db: Session, **kwargs) -> AgentRunModel:
    run = AgentRunModel(**kwargs)
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def complete_agent_run(db: Session, run_id: str, status: str, output_json: str = None,
                       duration_ms: float = None, error: str = None) -> None:
    run = db.query(AgentRunModel).filter_by(id=run_id).first()
    if run:
        run.status = status
        run.completed_at = datetime.now(timezone.utc)
        run.output_json = output_json
        run.duration_ms = duration_ms
        run.error = error
        db.commit()


# ---------------------------------------------------------------------------
# Artifacts
# ---------------------------------------------------------------------------

def create_artifact(db: Session, **kwargs) -> ArtifactModel:
    artifact = ArtifactModel(**kwargs)
    db.add(artifact)
    db.commit()
    db.refresh(artifact)
    return artifact


def get_artifact(db: Session, artifact_id: str) -> ArtifactModel | None:
    return db.query(ArtifactModel).filter_by(id=artifact_id).first()


def list_artifacts(db: Session, limit: int = 100) -> list[ArtifactModel]:
    return db.query(ArtifactModel).order_by(ArtifactModel.created_at.desc()).limit(limit).all()


# ---------------------------------------------------------------------------
# Audit Logs
# ---------------------------------------------------------------------------

def create_audit_log(db: Session, action: str, agent_name: str = None,
                     resource: str = None, session_id: str = None,
                     user_id: str = None, metadata: dict = None) -> AuditLogModel:
    log = AuditLogModel(
        action=action,
        agent_name=agent_name,
        resource=resource,
        session_id=session_id,
        user_id=user_id,
        metadata_json=json.dumps(metadata) if metadata else None,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def list_audit_logs(db: Session, limit: int = 200) -> list[AuditLogModel]:
    return db.query(AuditLogModel).order_by(AuditLogModel.created_at.desc()).limit(limit).all()
