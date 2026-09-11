"""
Core data structures for the orchestrator.

These are the shared types that every agent adapter imports:
    from agents.orchestrator.state import AgentResult

Design decisions:
    - AgentResult is a Pydantic BaseModel because the report adapter
      calls .model_dump(mode="json") on it.
    - AgentContext groups everything an adapter needs: task details,
      user request, file paths, and upstream results.
    - AgentTask describes a single step in a workflow.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# AgentTask — describes one step in a workflow
# ---------------------------------------------------------------------------

class AgentTask(BaseModel):
    """
    A single agent invocation within a workflow.

    Attributes:
        agent_name:  Registry key (e.g. "data_analysis", "vision", "report").
        instruction: What this agent should do (passed to the adapter as
                     context.task.instruction).
        depends_on:  List of agent_name values that must complete before
                     this task runs. Their AgentResults are passed into
                     context.dependencies keyed by agent_name.
    """
    agent_name: str
    instruction: str = ""
    depends_on: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# AgentResult — returned by every adapter
# ---------------------------------------------------------------------------

class AgentResult(BaseModel):
    """
    Structured output from an agent adapter.

    Every adapter returns one of these. Downstream agents receive them
    via context.dependencies.

    Attributes:
        agent_name: Which agent produced this result.
        status:     "completed", "failed", or "skipped".
        summary:    Human-readable summary of what happened.
        data:       Arbitrary structured data (analysis results, report
                    manifests, vision findings, etc.).
        artifacts:  List of file paths created by the agent.
        warnings:   Non-fatal issues encountered during execution.
        errors:     Error messages if the agent failed.
    """
    agent_name: str = ""
    status: str = "completed"
    summary: str = ""
    data: dict = Field(default_factory=dict)
    artifacts: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# AgentContext — passed to every adapter function
# ---------------------------------------------------------------------------

class AgentContext(BaseModel):
    """
    Everything an agent adapter needs to do its work.

    Attributes:
        task:          The AgentTask describing this invocation.
        user_request:  The original user instruction (the "what").
        files:         Attached file paths (images, CSVs, etc.).
        dependencies:  Results from upstream agents, keyed by agent_name.
        metadata:      Arbitrary extra data for future extensibility.
    """
    task: AgentTask
    user_request: str = ""
    files: list[str] = Field(default_factory=list)
    dependencies: dict[str, AgentResult] = Field(default_factory=dict)
    metadata: dict = Field(default_factory=dict)
