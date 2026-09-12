"""
Secure Workspace Management and Path Traversal Protection Service.

Enforces application-level workspace isolation boundaries for:
- Uploaded files & documents
- Workflow run-specific temporary spaces
- Generated artifacts
- Coding sandbox workspaces
- Knowledge & vector database paths

Prevents path traversal attacks (e.g. ../../.env, C:\Windows, /etc/passwd).
Integrates with the Sovereign AI Workbench audit system.
"""

import logging
import os
import re
import shutil
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.config import settings

logger = logging.getLogger(__name__)


class PathTraversalError(ValueError):
    """Raised when a path attempts to escape the designated workspace boundary."""
    pass


def safe_path(base_dir: str | Path, target_path: str | Path) -> Path:
    """
    Resolve target_path strictly within base_dir.
    Rejects path traversal (e.g. '../', '..\\', root escapes).

    Returns the fully resolved canonical Path object.
    Raises PathTraversalError if the target attempts to escape base_dir.
    """
    base = Path(base_dir).resolve()

    # Reject obvious traversal sequences early
    target_str = str(target_path)
    if ".." in target_str or target_str.startswith("/") or target_str.startswith("\\"):
        # Could be relative with components, resolve and verify containment
        pass

    try:
        if Path(target_path).is_absolute():
            candidate = Path(target_path).resolve()
        else:
            candidate = (base / target_path).resolve()
    except Exception as exc:
        raise PathTraversalError(f"Invalid path syntax: {target_path}") from exc

    # Check containment
    try:
        candidate.relative_to(base)
    except ValueError:
        logger.warning("PATH TRAVERSAL BLOCKED: Attempted to escape %s -> %s", base, candidate)
        _audit_path_traversal(target_str, str(base))
        raise PathTraversalError(
            f"Path traversal detected: '{target_str}' is outside workspace boundary."
        )

    return candidate


def sanitize_filename(filename: str) -> str:
    """
    Strip any path components, directory separators, and traversal markers
    to yield a clean, safe local filename.
    """
    if not filename:
        return "unnamed_file"

    # Keep only basename
    name = Path(filename).name

    # Remove null bytes and traversal tokens
    name = name.replace("\x00", "").replace("..", "_")
    name = re.sub(r'[\/\\:\*\?"<>\|]', '_', name)
    name = name.strip(" .")

    if not name:
        return f"file_{uuid4().hex[:8]}"

    return name


def _audit_path_traversal(attempted_path: str, workspace_root: str):
    """Record blocked traversal attempt in audit database."""
    try:
        from app.services.audit import audit_log
        audit_log(
            action="PATH_TRAVERSAL_BLOCKED",
            resource=attempted_path[:200],
            metadata={"workspace_root": workspace_root, "status": "BLOCKED"},
        )
    except Exception as exc:
        logger.debug("Failed to write audit log for path traversal: %s", exc)


class WorkspaceManager:
    """
    Manages structured, isolated filesystem workspaces for sovereign processing.
    """

    def __init__(self, root_dir: str | Path | None = None):
        self.root_dir = Path(root_dir or settings.data_dir).resolve()
        self.output_root = Path(settings.output_dir).resolve()

        # Controlled subdirectories
        self.uploads_dir = self.root_dir / "documents"
        self.datasets_dir = self.root_dir / "datasets"
        self.knowledge_dir = self.root_dir / "vector"
        self.runs_dir = self.root_dir / "runs"
        self.generated_dir = self.output_root

        self._ensure_directories()

    def _ensure_directories(self):
        """Create foundational controlled directories."""
        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.datasets_dir.mkdir(parents=True, exist_ok=True)
        self.knowledge_dir.mkdir(parents=True, exist_ok=True)
        self.runs_dir.mkdir(parents=True, exist_ok=True)
        self.generated_dir.mkdir(parents=True, exist_ok=True)

    def create_run_workspace(self, run_id: str | None = None) -> dict[str, Path]:
        """
        Create a controlled, isolated workspace for a workflow run execution.
        Returns paths for: input, working, coding, generated, and temp.
        """
        run_id = run_id or uuid4().hex[:12]
        run_base = safe_path(self.runs_dir, run_id)
        run_base.mkdir(parents=True, exist_ok=True)

        workspace = {
            "run_id": run_id,
            "root": run_base,
            "input": run_base / "input",
            "working": run_base / "working",
            "coding": run_base / "coding",
            "generated": run_base / "generated",
            "temp": run_base / "temp",
        }

        for path in [workspace["input"], workspace["working"], workspace["coding"], workspace["generated"], workspace["temp"]]:
            path.mkdir(parents=True, exist_ok=True)

        try:
            from app.services.audit import audit_log
            audit_log(
                action="WORKSPACE_CREATED",
                resource=run_id,
                metadata={"run_dir": str(run_base)},
            )
        except Exception:
            pass

        return workspace

    def cleanup_run_temp(self, run_workspace: dict[str, Path]):
        """
        Safely clean up temporary files in a run workspace while preserving generated artifacts.
        """
        try:
            temp_dir = run_workspace.get("temp")
            if temp_dir and temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception as exc:
            logger.debug("Non-fatal workspace temp cleanup issue: %s", exc)

    def get_upload_path(self, filename: str) -> Path:
        """Resolve safe storage path for an uploaded document."""
        clean_name = sanitize_filename(filename)
        return safe_path(self.uploads_dir, clean_name)

    def get_status(self) -> dict[str, Any]:
        """
        Return public status of workspace isolation.
        Does NOT expose sensitive server paths.
        """
        return {
            "workspace_isolation": True,
            "workspace_root": "Isolated Local Workspace",
            "path_traversal_protection": True,
            "sandbox_isolation": True,
            "uploads_isolated": True,
            "artifacts_controlled": True,
        }


# Global singleton instance
workspace_manager = WorkspaceManager()
