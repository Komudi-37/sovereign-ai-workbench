"""
Sovereign AI Workbench — FastAPI Backend

Main application entry point.
Configures CORS, logging, and API routes.

Architecture:
    React frontend (port 5173)
        → FastAPI (port 8000)
            → LLMService → OllamaProvider → Ollama (port 11434)
                → qwen3:4b
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.models import ChatRequest, ChatResponse, HealthResponse
from app.services.llm import (
    LLMConnectionError,
    LLMGenerationError,
    LLMService,
    create_llm_service,
)

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s — %(name)s — %(levelname)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Application lifespan — initialize and clean up resources
# ---------------------------------------------------------------------------

# Global LLM service instance (initialized on startup)
llm_service: LLMService | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the LLM service when the server starts."""
    global llm_service
    llm_service = create_llm_service()
    logger.info("Sovereign AI Workbench backend started")
    yield
    logger.info("Sovereign AI Workbench backend stopped")


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Sovereign AI Workbench",
    description="Local AI workbench — Milestone 1: Chat with qwen3:4b via Ollama",
    version="0.1.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS — allow the React frontend to call the API
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

logger.info("CORS configured — allowed origin: %s", settings.frontend_origin)

# ---------------------------------------------------------------------------
# API Routes
# ---------------------------------------------------------------------------


@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """
    Health check endpoint.

    Verifies:
    1. FastAPI backend is running (always true if this responds).
    2. Ollama server is reachable.
    """
    ollama_healthy = await llm_service.health_check()

    return HealthResponse(
        status="ok" if ollama_healthy else "degraded",
        backend="ok",
        ollama="ok" if ollama_healthy else "unavailable",
    )


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Chat endpoint — sends a user message to the local LLM and returns the response.

    The message is forwarded through:
        FastAPI → LLMService → OllamaProvider → Ollama → qwen3:4b
    """
    logger.info("Chat request received")

    try:
        response_text, model_used = await llm_service.chat(request.message)
        logger.info("Chat request completed (model: %s)", model_used)

        return ChatResponse(response=response_text, model=model_used)

    except LLMConnectionError as exc:
        logger.error("LLM connection error: %s", exc)
        raise HTTPException(
            status_code=503,
            detail=str(exc),
        )

    except LLMGenerationError as exc:
        logger.error("LLM generation error: %s", exc)
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        )

    except Exception as exc:
        # Catch-all — log the real error, return a generic message
        logger.exception("Unexpected error during chat: %s", exc)
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred. Check the backend logs for details.",
        )
