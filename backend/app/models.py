"""
Pydantic models for API request and response validation.

These schemas define the contract between the React frontend and the FastAPI backend.
"""

from typing import Any

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """Incoming chat message from the frontend."""
    message: str = Field(
        ...,
        min_length=1,
        max_length=10000,
        description="The user's message to send to the AI model."
    )


class ChatResponse(BaseModel):
    """AI response returned to the frontend."""
    response: str = Field(
        ...,
        description="The AI model's generated response."
    )
    model: str = Field(
        ...,
        description="The model that generated the response."
    )


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = Field(..., description="Overall system status.")
    backend: str = Field(..., description="Backend server status.")
    ollama: str = Field(..., description="Ollama server connectivity status.")


# ---------------------------------------------------------------------------
# Workflow API schemas
# ---------------------------------------------------------------------------

class WorkflowRequest(BaseModel):
    """Request to execute a workflow via the orchestrator."""
    instruction: str = Field(
        ...,
        min_length=1,
        max_length=10000,
        description="User instruction describing the desired task.",
    )
    files: list[str] = Field(
        default_factory=list,
        description="Optional list of file paths to process.",
    )
    workflow: str = Field(
        default="data_analysis",
        description="Workflow name: 'data_analysis' or 'vision'.",
    )


class WorkflowStepResponse(BaseModel):
    """Summary of a single agent execution step."""
    agent: str
    status: str
    instruction: str = ""
    summary: str = ""
    duration_ms: float | None = None
    error: str | None = None
    warning: str | None = None
    artifact_count: int | None = None


class WorkflowResponse(BaseModel):
    """Response from a workflow execution."""
    workflow_name: str = Field(..., description="Which workflow was executed.")
    status: str = Field(..., description="Overall: completed, partial, or failed.")
    steps: list[dict[str, Any]] = Field(
        default_factory=list,
        description="Ordered execution steps with per-agent details.",
    )
    agent_results: dict[str, Any] = Field(
        default_factory=dict,
        description="Full agent results keyed by agent name.",
    )
    artifacts: list[str] = Field(
        default_factory=list,
        description="All file paths created during the workflow.",
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-fatal issues from any agent.",
    )
    errors: list[str] = Field(
        default_factory=list,
        description="Errors from any agent.",
    )
    duration_ms: float = Field(
        default=0,
        description="Total workflow execution time in milliseconds.",
    )
