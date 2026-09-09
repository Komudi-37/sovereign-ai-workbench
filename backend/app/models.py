"""
Pydantic models for API request and response validation.

These schemas define the contract between the React frontend and the FastAPI backend.
"""

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
