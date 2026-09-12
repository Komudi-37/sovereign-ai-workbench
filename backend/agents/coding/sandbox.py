"""
Secure local sandbox execution environment for Sovereign AI Workbench.

Executes Python code in an isolated subprocess with:
- Sanitized environment variables (all cloud API keys and secrets stripped)
- Working directory isolation in dedicated output folders
- Execution timeout enforcement
- Pre-execution static security policy checks (no os.system, raw sockets, etc.)
- Stdout/stderr capture and truncation limits
- Artifact tracking for generated files
"""

import ast
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Keys or substrings to purge from the subprocess environment
SENSITIVE_ENV_PATTERNS = [
    "KEY",
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "DATABASE",
    "URL",
    "CREDENTIAL",
    "AUTH",
    "OPENAI",
    "ANTHROPIC",
    "GOOGLE",
    "GEMINI",
    "AZURE",
    "AWS",
]

# Prohibited AST node or call patterns for security enforcement
FORBIDDEN_CALLS = {
    "os.system",
    "os.popen",
    "os.spawn",
    "subprocess.Popen",
    "subprocess.run",
    "subprocess.call",
    "subprocess.check_output",
    "shutil.rmtree",
    "eval",
    "exec",
    "__import__",
}

FORBIDDEN_MODULES = {
    "socket",
    "urllib.request",
    "requests",
    "httpx",
    "aiohttp",
    "telnetlib",
    "ftplib",
}


def sanitize_environment() -> dict[str, str]:
    """
    Produce a sanitized copy of os.environ.
    Strips any keys matching sensitive patterns to ensure zero secret leakage.
    """
    safe_env = {}
    for k, v in os.environ.items():
        k_upper = k.upper()
        if any(pattern in k_upper for pattern in SENSITIVE_ENV_PATTERNS):
            continue
        safe_env[k] = v

    # Ensure Python operates cleanly and unbuffered
    safe_env["PYTHONUNBUFFERED"] = "1"
    safe_env["PYTHONDONTWRITEBYTECODE"] = "1"
    return safe_env


class SecurityViolationError(Exception):
    """Raised when Python code violates static security analysis."""
    pass


class CodeSecurityValidator(ast.NodeVisitor):
    """
    Static AST visitor to check for disallowed calls, imports, or dangerous operations.
    """

    def __init__(self):
        self.violations: list[str] = []

    def visit_Import(self, node: ast.Import):
        for alias in node.names:
            name = alias.name
            if name in FORBIDDEN_MODULES:
                self.violations.append(f"Import of forbidden network/system module: '{name}'")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom):
        mod = node.module or ""
        if mod in FORBIDDEN_MODULES or any(mod.startswith(m + ".") for m in FORBIDDEN_MODULES):
            self.violations.append(f"Import from forbidden network/system module: '{mod}'")
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call):
        call_repr = ""
        if isinstance(node.func, ast.Attribute):
            val = node.func.value
            attr = node.func.attr
            if isinstance(val, ast.Name):
                call_repr = f"{val.id}.{attr}"
        elif isinstance(node.func, ast.Name):
            call_repr = node.func.id

        if call_repr in FORBIDDEN_CALLS:
            self.violations.append(f"Forbidden function call: '{call_repr}()'")

        self.generic_visit(node)


def validate_code_safety(code: str) -> list[str]:
    """
    Performs static AST inspection on code before execution.
    Returns a list of violation messages, if any.
    """
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return []

    validator = CodeSecurityValidator()
    validator.visit(tree)
    return validator.violations


class LocalSandbox:
    """
    Isolated execution environment for Python scripts.
    """

    def __init__(
        self,
        base_dir: str | Path | None = None,
        default_timeout: int = 15,
        max_output_bytes: int = 65536,
    ):
        self.base_dir = Path(base_dir) if base_dir else Path("outputs/coding")
        self.default_timeout = default_timeout
        self.max_output_bytes = max_output_bytes

    def execute_code(
        self,
        code: str,
        timeout: int | None = None,
        workspace_dir: str | Path | None = None,
        filename: str = "solution.py",
    ) -> dict[str, Any]:
        """
        Execute Python code string inside a dedicated workspace directory.

        Returns dict:
        {
            "exit_code": int,
            "stdout": str,
            "stderr": str,
            "execution_time": float,
            "timed_out": bool,
            "artifacts": list[str],
            "error": str | None,
            "script_path": str,
        }
        """
        timeout = timeout or self.default_timeout

        # 1. Static security check
        violations = validate_code_safety(code)
        if violations:
            violation_msg = "; ".join(violations)
            logger.warning("Code rejected by security validator: %s", violation_msg)
            return {
                "exit_code": -1,
                "stdout": "",
                "stderr": f"SecurityViolationError: {violation_msg}",
                "execution_time": 0.0,
                "timed_out": False,
                "artifacts": [],
                "error": f"SecurityViolationError: {violation_msg}",
                "script_path": "",
            }

        # 2. Setup workspace directory
        if workspace_dir:
            work_path = Path(workspace_dir).resolve()
        else:
            work_path = self.base_dir.resolve()
        work_path.mkdir(parents=True, exist_ok=True)

        # Snapshot files in directory before execution to detect newly created artifacts
        pre_files = {p.resolve() for p in work_path.glob("**/*") if p.is_file()}

        # 3. Write script to workspace using safe_path
        from app.services.workspace import safe_path, sanitize_filename
        clean_filename = sanitize_filename(filename)
        script_file = safe_path(work_path, clean_filename)
        script_file.write_text(code, encoding="utf-8")

        # 4. Prepare sanitized environment and subprocess command
        env = sanitize_environment()
        cmd = [sys.executable, "-I", str(script_file.name)]

        start_time = time.monotonic()
        timed_out = False
        exit_code = 0
        stdout_str = ""
        stderr_str = ""
        err_msg = None

        try:
            proc = subprocess.run(
                cmd,
                cwd=str(work_path),
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            exit_code = proc.returncode
            stdout_str = proc.stdout or ""
            stderr_str = proc.stderr or ""
        except subprocess.TimeoutExpired as exc:
            timed_out = True
            exit_code = -1
            stdout_str = (exc.stdout or "") if isinstance(exc.stdout, str) else ""
            stderr_str = (exc.stderr or "") if isinstance(exc.stderr, str) else ""
            err_msg = f"Execution timed out after {timeout} seconds."
        except Exception as exc:
            exit_code = -1
            err_msg = f"Execution failed: {str(exc)}"
            stderr_str = str(exc)

        elapsed = time.monotonic() - start_time

        # 5. Enforce output truncation
        if len(stdout_str) > self.max_output_bytes:
            stdout_str = stdout_str[: self.max_output_bytes] + "\n... [stdout truncated]"
        if len(stderr_str) > self.max_output_bytes:
            stderr_str = stderr_str[: self.max_output_bytes] + "\n... [stderr truncated]"

        # 6. Detect generated artifacts
        post_files = {p.resolve() for p in work_path.glob("**/*") if p.is_file()}
        new_files = sorted(list(post_files - pre_files))
        artifacts = [str(p) for p in new_files if p.name != filename]

        return {
            "exit_code": exit_code,
            "stdout": stdout_str,
            "stderr": stderr_str,
            "execution_time": round(elapsed, 3),
            "timed_out": timed_out,
            "artifacts": artifacts,
            "error": err_msg or (stderr_str if exit_code != 0 else None),
            "script_path": str(script_file),
        }
