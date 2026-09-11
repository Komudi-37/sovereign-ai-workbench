"""
Model Router service for Sovereign AI Workbench.

Routes tasks to appropriate local models based on task type.
This is a SERVICE, not an agent — used by the orchestrator and API routes.

All models are local via Ollama. No cloud APIs.
"""

import logging
from dataclasses import dataclass
from typing import Literal

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

TaskType = Literal[
    "chat", "reasoning", "summarization", "ocr",
    "vision", "retrieval", "data_analysis", "report",
]


@dataclass
class ModelSelection:
    """Result of model routing."""
    model: str
    task_type: str
    reason: str
    provider: str = "ollama"
    available: bool = True


# Task type → settings attribute mapping
_TASK_MODEL_MAP: dict[str, str] = {
    "chat": "fast_model",
    "reasoning": "reasoning_model",
    "summarization": "fast_model",
    "ocr": "fast_model",
    "vision": "vision_model",
    "retrieval": "embedding_model",
    "data_analysis": "fast_model",
    "report": "reasoning_model",
}


class ModelRouter:
    """
    Routes tasks to the appropriate local model.

    Usage:
        router = ModelRouter()
        selection = router.route("vision")
        print(selection.model)  # "llava:7b"
    """

    def __init__(self):
        self._available_models: set[str] | None = None

    def route(self, task_type: TaskType) -> ModelSelection:
        """Select the best model for a given task type."""
        attr = _TASK_MODEL_MAP.get(task_type, "fast_model")
        model = getattr(settings, attr, settings.ollama_model)

        reason = f"Configured {attr} for {task_type} tasks"

        return ModelSelection(
            model=model,
            task_type=task_type,
            reason=reason,
            provider="ollama",
        )

    async def check_model_available(self, model: str) -> bool:
        """Check if a specific model is available in Ollama."""
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
                response = await client.get(f"{settings.ollama_base_url}/api/tags")
                if response.status_code == 200:
                    data = response.json()
                    models = [m.get("name", "") for m in data.get("models", [])]
                    # Check both exact match and base name match
                    return any(
                        model == m or model == m.split(":")[0]
                        for m in models
                    )
        except Exception as exc:
            logger.warning("Failed to check model availability: %s", exc)
        return False

    async def list_available_models(self) -> list[str]:
        """List all models available in Ollama."""
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
                response = await client.get(f"{settings.ollama_base_url}/api/tags")
                if response.status_code == 200:
                    data = response.json()
                    return [m.get("name", "") for m in data.get("models", [])]
        except Exception as exc:
            logger.warning("Failed to list models: %s", exc)
        return []


# Shared instance
model_router = ModelRouter()
