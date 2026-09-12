"""
Tests for Coding Agent and Secure Sandbox in Sovereign AI Workbench.
"""

import sys
from pathlib import Path
import pytest

from agents.coding.sandbox import LocalSandbox, validate_code_safety
from agents.coding.coding_agent import CodingAgent, extract_python_code, coding_adapter
from agents.orchestrator.state import AgentContext, AgentTask
from agents.orchestrator.orchestrator import Orchestrator, auto_route
from agents.orchestrator.registry import list_agents, get_agent


def test_coding_agent_registered():
    """Verify coding agent is registered and available in the orchestrator registry."""
    agents = list_agents()
    assert "coding" in agents
    assert agents["coding"] == "available"
    adapter = get_agent("coding")
    assert callable(adapter)


def test_code_extraction():
    """Test extracting clean python code from various markdown patterns."""
    text_fenced = "Here is the code:\n```python\nprint('hello')\n```\nDone."
    assert extract_python_code(text_fenced) == "print('hello')"

    text_no_fence = "x = 10\ny = 20\nprint(x + y)"
    assert extract_python_code(text_no_fence) == text_no_fence


def test_sandbox_clean_execution(tmp_path):
    """Test standard valid Python code execution in local sandbox."""
    sandbox = LocalSandbox(base_dir=tmp_path, default_timeout=5)
    code = """
import math
vals = [1.0, 2.0, 3.0, 4.0]
mean = sum(vals) / len(vals)
print(f"MEAN:{mean:.2f}")
"""
    result = sandbox.execute_code(code, workspace_dir=tmp_path)
    assert result["exit_code"] == 0
    assert not result["timed_out"]
    assert "MEAN:2.50" in result["stdout"]
    assert result["error"] is None


def test_sandbox_security_rejection(tmp_path):
    """Test static security AST checks rejecting prohibited calls."""
    sandbox = LocalSandbox(base_dir=tmp_path, default_timeout=5)

    # os.system forbidden
    code_unsafe = "import os\nos.system('dir')"
    result = sandbox.execute_code(code_unsafe, workspace_dir=tmp_path)
    assert result["exit_code"] == -1
    assert "SecurityViolationError" in result["stderr"]

    # raw socket forbidden
    code_socket = "import socket\ns = socket.socket()"
    result2 = sandbox.execute_code(code_socket, workspace_dir=tmp_path)
    assert result2["exit_code"] == -1
    assert "SecurityViolationError" in result2["stderr"]


def test_sandbox_timeout_enforcement(tmp_path):
    """Test timeout enforcement terminates runaway loops."""
    sandbox = LocalSandbox(base_dir=tmp_path, default_timeout=2)
    code_infinite = "import time\ntime.sleep(10)"
    result = sandbox.execute_code(code_infinite, timeout=1, workspace_dir=tmp_path)
    assert result["timed_out"] is True
    assert result["exit_code"] != 0


def test_sandbox_artifact_creation(tmp_path):
    """Test that files created during script run are captured as artifacts."""
    sandbox = LocalSandbox(base_dir=tmp_path, default_timeout=5)
    code = """
with open('output_data.txt', 'w') as f:
    f.write('computed payload')
print('Artifact created')
"""
    result = sandbox.execute_code(code, workspace_dir=tmp_path)
    assert result["exit_code"] == 0
    assert len(result["artifacts"]) == 1
    assert Path(result["artifacts"][0]).name == "output_data.txt"


def test_coding_agent_auto_repair_loop(tmp_path, monkeypatch):
    """
    Test the automatic repair loop (max 2 attempts).
    Attempt 1 fails with a syntax/runtime error; repair prompt fixes it in attempt 2.
    """
    call_count = 0

    def mock_call_llm(prompt, system, timeout=120):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First attempt produces bugged code (NameError)
            return "```python\nprint(undefined_variable)\n```"
        else:
            # Second repair attempt produces fixed code
            return "```python\nfixed_variable = 42\nprint(f'Repaired: {fixed_variable}')\n```"

    from agents.coding import coding_agent
    monkeypatch.setattr(coding_agent, "call_local_llm", mock_call_llm)

    agent = CodingAgent(output_dir=tmp_path, max_attempts=2, sandbox_timeout=5)
    outcome = agent.run("Calculate the vibration value")

    assert outcome["status"] == "completed"
    assert outcome["attempts"] == 2
    assert "Repaired: 42" in outcome["stdout"]
    assert outcome["exit_code"] == 0


def test_coding_adapter_via_orchestrator(tmp_path):
    """Test full integration with orchestrator via 'coding' workflow."""
    orc = Orchestrator()
    result = orc.run(
        user_request="Calculate the average vibration from these values: 4.2, 4.5, 4.1, 5.0, 4.7 using Python and show the result.",
        workflow_name="coding",
    )
    assert result.status == "completed"
    assert "coding" in result.results
    coding_res = result.results["coding"]
    assert coding_res.status == "completed"
    stdout_text = coding_res.data.get("stdout", "")
    # Verify calculated mean ~ 4.5 within floating point tolerance
    import re
    numbers_in_stdout = [float(n) for n in re.findall(r"[-+]?(?:\d*\.\d+|\d+)", stdout_text)]
    assert any(abs(n - 4.5) < 0.01 for n in numbers_in_stdout)
    assert len(result.artifacts) > 0


def test_auto_route_coding():
    """Verify auto_route sends coding requests to coding workflow."""
    route = auto_route("Please write a python script to calculate pump efficiency", [])
    assert route == "coding"

    route2 = auto_route("Compute the formula average using sandbox code", [])
    assert route2 == "coding"
