"""
Pydantic models for API request and response validation.

These schemas define the contract between the React frontend and the FastAPI backend.
"""

from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    """Incoming chat message from the frontend."""
    message: str = Field(..., min_length=1, max_length=10000)
    session_id: Optional[str] = Field(None, description="Existing session ID to continue")
    conversation_id: Optional[str] = Field(None, description="Alias for session_id")
    document_ids: list[str] = Field(default_factory=list, description="Associated document IDs")


class ChatResponse(BaseModel):
    """AI response returned to the frontend."""
    response: str
    model: str
    session_id: str = Field("", description="Session ID for conversation continuity")
    conversation_id: str = Field("", description="Alias for session ID")
    citations: list[dict[str, Any]] = Field(default_factory=list)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    timeline: list[dict[str, Any]] = Field(default_factory=list)
    coding: Optional[dict[str, Any]] = Field(None, description="Coding Agent execution details if applicable")
    vision: Optional[dict[str, Any]] = Field(None, description="Vision Agent structured visual analysis details")
    data_analysis: Optional[dict[str, Any]] = Field(None, description="Data Analysis Agent structured results")
    execution_plan: Optional[dict[str, Any]] = Field(None, description="Task Planner structured execution plan")


class CreateConversationRequest(BaseModel):
    title: Optional[str] = Field(None, max_length=500)


class UpdateConversationRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)


class ConversationResponse(BaseModel):
    id: str
    title: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    message_count: int = 0


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    backend: str
    database: str = "ok"
    ollama: str
    vector_store: str = "not_initialized"


# ---------------------------------------------------------------------------
# Workflows
# ---------------------------------------------------------------------------

class WorkflowRunRequest(BaseModel):
    """Request to execute a workflow via the orchestrator."""
    instruction: str = Field(
        default="",
        max_length=10000,
        description="User instruction (legacy field).",
    )
    message: Optional[str] = Field(
        None,
        max_length=10000,
        description="User message (preferred field).",
    )
    files: list[str] = Field(
        default_factory=list,
        description="Direct file paths (legacy).",
    )
    document_ids: list[str] = Field(
        default_factory=list,
        description="Document IDs from the file upload API.",
    )
    workflow: str = Field(
        default="auto",
        description="Workflow name or 'auto' for automatic routing.",
    )
    session_id: Optional[str] = Field(None)


class WorkflowRunResponse(BaseModel):
    """Response from a workflow execution."""
    workflow_id: str = ""
    workflow_name: str = ""
    status: str = ""
    steps: list[dict[str, Any]] = Field(default_factory=list)
    agent_results: dict[str, Any] = Field(default_factory=dict)
    artifacts: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    duration_ms: float = 0
