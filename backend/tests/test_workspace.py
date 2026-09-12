"""
Tests for Secure Workspace Isolation and Path Traversal Protection.
"""

import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services.workspace import (
    WorkspaceManager,
    safe_path,
    sanitize_filename,
    PathTraversalError,
    workspace_manager,
)
from agents.coding.sandbox import LocalSandbox

client = TestClient(app)


def test_safe_path_valid_subpath(tmp_path):
    """Test that valid paths inside base directory resolve properly."""
    sub_dir = tmp_path / "sub"
    sub_dir.mkdir()
    target_file = sub_dir / "test.txt"
    target_file.write_text("hello")

    resolved = safe_path(tmp_path, "sub/test.txt")
    assert resolved == target_file.resolve()


def test_safe_path_rejects_parent_traversal(tmp_path):
    """Test that ../ traversal attempts raise PathTraversalError."""
    with pytest.raises(PathTraversalError):
        safe_path(tmp_path, "../outside.txt")

    with pytest.raises(PathTraversalError):
        safe_path(tmp_path, "../../etc/passwd")

    with pytest.raises(PathTraversalError):
        safe_path(tmp_path, "sub/../../secret.env")


def test_safe_path_rejects_absolute_path_escape(tmp_path):
    """Test that an absolute path outside base is rejected."""
    outside = Path(r"C:\Windows\System32" if os.name == "nt" else "/etc").resolve()
    with pytest.raises(PathTraversalError):
        safe_path(tmp_path, outside)


def test_sanitize_filename():
    """Test filename sanitization strips directories and harmful characters."""
    assert sanitize_filename("../../secret.txt") == "secret.txt"
    assert sanitize_filename("..\\..\\passwords.csv") == "passwords.csv"
    assert sanitize_filename("normal_file.pdf") == "normal_file.pdf"
    assert sanitize_filename("file/with/slash.txt") == "slash.txt"
    assert sanitize_filename("") == "unnamed_file"


def test_workspace_manager_directories(tmp_path):
    """Test WorkspaceManager initializes controlled subdirectories."""
    wm = WorkspaceManager(root_dir=tmp_path)
    assert wm.uploads_dir.exists()
    assert wm.datasets_dir.exists()
    assert wm.knowledge_dir.exists()
    assert wm.runs_dir.exists()
    assert wm.generated_dir.exists()


def test_workspace_manager_create_and_cleanup_run(tmp_path):
    """Test run workspace creation and temp cleanup."""
    wm = WorkspaceManager(root_dir=tmp_path)
    run_ws = wm.create_run_workspace(run_id="test_run_123")
    
    assert run_ws["root"].exists()
    assert run_ws["input"].exists()
    assert run_ws["working"].exists()
    assert run_ws["coding"].exists()
    assert run_ws["generated"].exists()
    assert run_ws["temp"].exists()

    # Create dummy temp and generated files
    temp_file = run_ws["temp"] / "temp.log"
    temp_file.write_text("debug temp")
    gen_file = run_ws["generated"] / "report.pdf"
    gen_file.write_text("final report")

    # Clean up temp
    wm.cleanup_run_temp(run_ws)
    assert not run_ws["temp"].exists()
    assert gen_file.exists()


def test_coding_sandbox_workspace_isolation(tmp_path):
    """Test coding sandbox operates in safe workspace."""
    sandbox = LocalSandbox(base_dir=tmp_path)
    code = "with open('sandbox_test.txt', 'w') as f: f.write('sandbox isolated')\nprint('SUCCESS')"
    result = sandbox.execute_code(code)

    assert result["exit_code"] == 0
    assert "SUCCESS" in result["stdout"]
    # File is written inside run directory created in base_dir
    created_files = list(tmp_path.rglob("sandbox_test.txt"))
    assert len(created_files) == 1


def test_security_status_workspace_fields():
    """Test /api/security/status contains workspace isolation telemetry."""
    r = client.get("/api/security/status")
    assert r.status_code == 200
    data = r.json()

    assert data["workspace_isolation"] is True
    assert data["workspace_root"] == "Isolated Local Workspace"
    assert data["path_traversal_protection"] is True
    assert data["sandbox_isolation"] is True
    assert data["uploads_isolated"] is True
    assert data["artifacts_controlled"] is True


def test_upload_path_traversal_blocked():
    """Test file upload endpoint resists path traversal filenames."""
    # Attempt upload with malicious path traversal filename
    files = {"file": ("../../malicious.txt", b"evil content", "text/plain")}
    r = client.post("/api/files/upload", files=files)
    assert r.status_code == 200
    data = r.json()
    # The saved filename must be sanitized to 'malicious.txt' without parent dirs
    assert data["filename"] == "malicious.txt"
    assert ".." not in data["filename"]
