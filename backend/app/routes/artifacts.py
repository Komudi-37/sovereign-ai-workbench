"""
Artifact management API routes.

GET /api/artifacts              — List all artifacts
GET /api/artifacts/{id}         — Get artifact details
GET /api/artifacts/{id}/download — Download artifact file
"""

import logging
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.db.database import SessionLocal
from app.db import repositories as repo

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/artifacts", tags=["artifacts"])


@router.get("")
async def list_artifacts():
    """List all generated artifacts."""
    db = SessionLocal()
    try:
        artifacts = repo.list_artifacts(db)
        return [
            {
                "id": a.id,
                "filename": a.filename,
                "path": a.path,
                "artifact_type": a.artifact_type,
                "mime_type": a.mime_type,
                "agent_name": a.agent_name,
                "workflow_id": a.workflow_id,
                "size": a.size,
                "created_at": a.created_at.isoformat() if a.created_at else None,
            }
            for a in artifacts
        ]
    finally:
        db.close()


@router.get("/{artifact_id}")
async def get_artifact(artifact_id: str):
    """Get details of a specific artifact."""
    db = SessionLocal()
    try:
        artifact = repo.get_artifact(db, artifact_id)
        if not artifact:
            raise HTTPException(404, "Artifact not found")

        return {
            "id": artifact.id,
            "filename": artifact.filename,
            "path": artifact.path,
            "artifact_type": artifact.artifact_type,
            "mime_type": artifact.mime_type,
            "agent_name": artifact.agent_name,
            "workflow_id": artifact.workflow_id,
            "size": artifact.size,
            "created_at": artifact.created_at.isoformat() if artifact.created_at else None,
        }
    finally:
        db.close()


@router.get("/{artifact_id}/download")
async def download_artifact(artifact_id: str):
    """Download an artifact file."""
    db = SessionLocal()
    try:
        artifact = repo.get_artifact(db, artifact_id)
        if not artifact:
            raise HTTPException(404, "Artifact not found")

        file_path = Path(artifact.path)
        if not file_path.exists():
            raise HTTPException(
                404,
                f"Artifact file not found on disk: {artifact.filename}"
            )

        return FileResponse(
            path=str(file_path),
            filename=artifact.filename,
            media_type=artifact.mime_type or "application/octet-stream",
        )
    finally:
        db.close()
