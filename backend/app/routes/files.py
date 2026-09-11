"""
File upload and document management API routes.

POST /api/files/upload — Upload a document
GET  /api/files        — List all documents
GET  /api/files/{id}   — Get document details
"""

import hashlib
import logging
import mimetypes
import os
import shutil
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.config import settings
from app.db.database import SessionLocal
from app.db import repositories as repo
from app.services.audit import audit_log, DOCUMENT_UPLOADED

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/files", tags=["files"])

ALLOWED_EXTENSIONS = {
    ".pdf", ".csv", ".xlsx", ".xls", ".json",
    ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp",
    ".txt", ".docx", ".pptx",
}

MAX_SIZE = settings.max_upload_size_mb * 1024 * 1024  # Convert MB to bytes


def _get_upload_dir() -> Path:
    """Get or create the document upload directory."""
    upload_dir = Path(settings.data_dir) / "documents"
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir


def _safe_filename(filename: str) -> str:
    """Sanitize a filename to prevent path traversal."""
    # Remove any path components, keep only the base name
    name = Path(filename).name
    # Replace potentially dangerous characters
    return name.replace("..", "_").replace("/", "_").replace("\\", "_")


@router.post("/upload")
async def upload_file(file: UploadFile = File(...)):
    """
    Upload a document file.

    Validates file type, size, and content. Computes SHA-256 checksum
    for deduplication. Stores file in data/documents/.
    """
    if not file.filename:
        raise HTTPException(400, "No filename provided")

    safe_name = _safe_filename(file.filename)
    ext = Path(safe_name).suffix.lower()

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            400,
            f"File type '{ext}' not supported. "
            f"Allowed: {', '.join(sorted(ALLOWED_EXTENSIONS))}"
        )

    # Read file content
    content = await file.read()

    if len(content) > MAX_SIZE:
        raise HTTPException(
            400,
            f"File too large ({len(content) / 1024 / 1024:.1f} MB). "
            f"Maximum: {settings.max_upload_size_mb} MB"
        )

    if len(content) == 0:
        raise HTTPException(400, "Empty file")

    # Compute SHA-256 checksum
    checksum = hashlib.sha256(content).hexdigest()

    # Check for duplicate
    db = SessionLocal()
    try:
        existing = repo.get_document_by_checksum(db, checksum)
        if existing:
            return {
                "document_id": existing.id,
                "filename": existing.filename,
                "status": "duplicate",
                "message": "This file has already been uploaded.",
            }

        # Save file to disk
        upload_dir = _get_upload_dir()
        # Use checksum prefix to avoid collisions
        dest_name = f"{checksum[:12]}_{safe_name}"
        dest_path = upload_dir / dest_name
        dest_path.write_bytes(content)

        # Detect MIME type
        mime_type = mimetypes.guess_type(safe_name)[0] or "application/octet-stream"

        # Create database record
        doc = repo.create_document(
            db,
            filename=safe_name,
            path=str(dest_path),
            mime_type=mime_type,
            size=len(content),
            checksum=checksum,
            status="uploaded",
        )

        # Audit log
        audit_log(
            DOCUMENT_UPLOADED,
            resource=safe_name,
            metadata={"document_id": doc.id, "size": len(content), "mime_type": mime_type},
        )

        logger.info("File uploaded: %s (%d bytes, %s)", safe_name, len(content), mime_type)

        return {
            "document_id": doc.id,
            "filename": doc.filename,
            "status": "uploaded",
            "size": len(content),
            "mime_type": mime_type,
            "checksum": checksum,
        }

    finally:
        db.close()


@router.get("")
async def list_files():
    """List all uploaded documents."""
    db = SessionLocal()
    try:
        docs = repo.list_documents(db)
        return [
            {
                "id": d.id,
                "filename": d.filename,
                "mime_type": d.mime_type,
                "size": d.size,
                "status": d.status,
                "classification": d.classification,
                "checksum": d.checksum,
                "created_at": d.created_at.isoformat() if d.created_at else None,
            }
            for d in docs
        ]
    finally:
        db.close()


@router.get("/{document_id}")
async def get_file(document_id: str):
    """Get details of a specific document."""
    db = SessionLocal()
    try:
        doc = repo.get_document(db, document_id)
        if not doc:
            raise HTTPException(404, "Document not found")

        chunks = repo.get_chunks_for_document(db, document_id)

        return {
            "id": doc.id,
            "filename": doc.filename,
            "path": doc.path,
            "mime_type": doc.mime_type,
            "size": doc.size,
            "status": doc.status,
            "classification": doc.classification,
            "checksum": doc.checksum,
            "chunk_count": len(chunks),
            "created_at": doc.created_at.isoformat() if doc.created_at else None,
        }
    finally:
        db.close()
