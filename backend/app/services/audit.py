"""
Audit logging service for Sovereign AI Workbench.

Records all important actions to the database audit_logs table.
This is a subsystem, not an agent.
"""

import json
import logging

from app.db.database import SessionLocal
from app.db.models import AuditLogModel

logger = logging.getLogger(__name__)


# Action constants
DOCUMENT_UPLOADED = "DOCUMENT_UPLOADED"
DOCUMENT_OCR_STARTED = "DOCUMENT_OCR_STARTED"
DOCUMENT_OCR_COMPLETED = "DOCUMENT_OCR_COMPLETED"
RAG_INDEX_STARTED = "RAG_INDEX_STARTED"
RAG_INDEX_COMPLETED = "RAG_INDEX_COMPLETED"
RAG_SEARCH = "RAG_SEARCH"
VISION_ANALYSIS = "VISION_ANALYSIS"
DATA_ANALYSIS = "DATA_ANALYSIS"
REPORT_GENERATED = "REPORT_GENERATED"
MODEL_SELECTED = "MODEL_SELECTED"
WORKFLOW_STARTED = "WORKFLOW_STARTED"
WORKFLOW_COMPLETED = "WORKFLOW_COMPLETED"
WORKFLOW_FAILED = "WORKFLOW_FAILED"
ARTIFACT_CREATED = "ARTIFACT_CREATED"
CHAT_MESSAGE = "CHAT_MESSAGE"


def audit_log(
    action: str,
    agent_name: str = None,
    resource: str = None,
    session_id: str = None,
    user_id: str = None,
    metadata: dict = None,
) -> None:
    """
    Record an audit event.

    This creates its own database session to avoid coupling
    with the caller's transaction.
    """
    try:
        db = SessionLocal()
        try:
            log_entry = AuditLogModel(
                action=action,
                agent_name=agent_name,
                resource=resource,
                session_id=session_id,
                user_id=user_id,
                metadata_json=json.dumps(metadata) if metadata else None,
            )
            db.add(log_entry)
            db.commit()
            logger.debug("Audit: %s — agent=%s resource=%s", action, agent_name, resource)
        finally:
            db.close()
    except Exception as exc:
        # Audit logging should never crash the main operation
        logger.error("Failed to write audit log: %s", exc)
