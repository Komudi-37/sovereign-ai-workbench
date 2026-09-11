"""
SQLAlchemy ORM models for Sovereign AI Workbench.

Schema covers: users, sessions, messages, documents, chunks,
workflow/agent runs, artifacts, and audit logs.
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Column, DateTime, Float, ForeignKey, Integer, String, Text, Index
)
from sqlalchemy.orm import relationship

from app.db.database import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

class UserModel(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=_uuid)
    username = Column(String(100), unique=True, nullable=False)
    role = Column(String(50), default="user")
    created_at = Column(DateTime, default=_now)

    sessions = relationship("SessionModel", back_populates="user")


# ---------------------------------------------------------------------------
# Sessions (chat sessions)
# ---------------------------------------------------------------------------

class SessionModel(Base):
    __tablename__ = "sessions"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, ForeignKey("users.id"), nullable=True)
    title = Column(String(500), default="New Chat")
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)

    user = relationship("UserModel", back_populates="sessions")
    messages = relationship("MessageModel", back_populates="session", order_by="MessageModel.created_at")
    workflow_runs = relationship("WorkflowRunModel", back_populates="session")


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------

class MessageModel(Base):
    __tablename__ = "messages"

    id = Column(String, primary_key=True, default=_uuid)
    session_id = Column(String, ForeignKey("sessions.id"), nullable=False)
    role = Column(String(20), nullable=False)  # user, assistant, system
    content = Column(Text, nullable=False)
    model = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=_now)

    session = relationship("SessionModel", back_populates="messages")


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------

class DocumentModel(Base):
    __tablename__ = "documents"

    id = Column(String, primary_key=True, default=_uuid)
    filename = Column(String(500), nullable=False)
    path = Column(String(1000), nullable=False)
    mime_type = Column(String(200), nullable=True)
    classification = Column(String(100), default="INTERNAL — DEMONSTRATION DATA")
    size = Column(Integer, nullable=True)
    checksum = Column(String(64), nullable=True)  # SHA-256
    status = Column(String(50), default="uploaded")  # uploaded, processing, indexed, error
    created_at = Column(DateTime, default=_now)

    chunks = relationship("DocumentChunkModel", back_populates="document")

    __table_args__ = (
        Index("ix_documents_checksum", "checksum"),
    )


# ---------------------------------------------------------------------------
# Document Chunks (for RAG)
# ---------------------------------------------------------------------------

class DocumentChunkModel(Base):
    __tablename__ = "document_chunks"

    id = Column(String, primary_key=True, default=_uuid)
    document_id = Column(String, ForeignKey("documents.id"), nullable=False)
    chunk_index = Column(Integer, nullable=False)
    text = Column(Text, nullable=False)
    page_number = Column(Integer, nullable=True)
    metadata_json = Column(Text, nullable=True)
    embedding_reference = Column(String(200), nullable=True)
    created_at = Column(DateTime, default=_now)

    document = relationship("DocumentModel", back_populates="chunks")


# ---------------------------------------------------------------------------
# Workflow Runs
# ---------------------------------------------------------------------------

class WorkflowRunModel(Base):
    __tablename__ = "workflow_runs"

    id = Column(String, primary_key=True, default=_uuid)
    session_id = Column(String, ForeignKey("sessions.id"), nullable=True)
    request = Column(Text, nullable=True)
    workflow_type = Column(String(100), nullable=True)
    status = Column(String(50), default="pending")
    result_json = Column(Text, nullable=True)
    started_at = Column(DateTime, default=_now)
    completed_at = Column(DateTime, nullable=True)

    session = relationship("SessionModel", back_populates="workflow_runs")
    agent_runs = relationship("AgentRunModel", back_populates="workflow")
    artifacts = relationship("ArtifactModel", back_populates="workflow")


# ---------------------------------------------------------------------------
# Agent Runs
# ---------------------------------------------------------------------------

class AgentRunModel(Base):
    __tablename__ = "agent_runs"

    id = Column(String, primary_key=True, default=_uuid)
    workflow_id = Column(String, ForeignKey("workflow_runs.id"), nullable=False)
    agent_name = Column(String(100), nullable=False)
    status = Column(String(50), default="pending")
    input_json = Column(Text, nullable=True)
    output_json = Column(Text, nullable=True)
    started_at = Column(DateTime, default=_now)
    completed_at = Column(DateTime, nullable=True)
    duration_ms = Column(Float, nullable=True)
    error = Column(Text, nullable=True)

    workflow = relationship("WorkflowRunModel", back_populates="agent_runs")


# ---------------------------------------------------------------------------
# Artifacts
# ---------------------------------------------------------------------------

class ArtifactModel(Base):
    __tablename__ = "artifacts"

    id = Column(String, primary_key=True, default=_uuid)
    workflow_id = Column(String, ForeignKey("workflow_runs.id"), nullable=True)
    agent_name = Column(String(100), nullable=True)
    filename = Column(String(500), nullable=False)
    path = Column(String(1000), nullable=False)
    artifact_type = Column(String(50), nullable=True)  # chart, report, data, etc.
    mime_type = Column(String(200), nullable=True)
    size = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=_now)

    workflow = relationship("WorkflowRunModel", back_populates="artifacts")


# ---------------------------------------------------------------------------
# Audit Logs
# ---------------------------------------------------------------------------

class AuditLogModel(Base):
    __tablename__ = "audit_logs"

    id = Column(String, primary_key=True, default=_uuid)
    user_id = Column(String, nullable=True)
    session_id = Column(String, nullable=True)
    action = Column(String(100), nullable=False)
    agent_name = Column(String(100), nullable=True)
    resource = Column(String(500), nullable=True)
    metadata_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=_now)

    __table_args__ = (
        Index("ix_audit_logs_action", "action"),
        Index("ix_audit_logs_created_at", "created_at"),
    )
