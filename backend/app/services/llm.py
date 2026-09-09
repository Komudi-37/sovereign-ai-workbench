"""
LLM integration layer for Sovereign AI Workbench.

Architecture:
    LLMService  (facade — used by API routes)
        └── LLMProvider  (abstract base)
                └── OllamaProvider  (concrete — talks to local Ollama)

This abstraction keeps Ollama-specific HTTP details isolated.
To add a new local provider later, create a new LLMProvider subclass
and swap it into LLMService — no route changes needed.
"""

import logging
from abc import ABC, abstractmethod

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Abstract base — defines what any LLM provider must implement
# ---------------------------------------------------------------------------

class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    async def generate(self, prompt: str, model: str) -> str:
        """
        Send a prompt to the LLM and return the generated text.

        Args:
            prompt: The user's message / prompt text.
            model: The model identifier to use.

        Returns:
            The generated response text.

        Raises:
            LLMConnectionError: If the provider is unreachable.
            LLMGenerationError: If generation fails for any reason.
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check if the provider is reachable and healthy.

        Returns:
            True if the provider is reachable, False otherwise.
        """
        pass


# ---------------------------------------------------------------------------
# Custom exceptions — clean error handling without leaking internals
# ---------------------------------------------------------------------------

class LLMConnectionError(Exception):
    """Raised when the LLM provider is unreachable."""
    pass


class LLMGenerationError(Exception):
    """Raised when the LLM provider fails to generate a response."""
    pass


# ---------------------------------------------------------------------------
# Ollama provider — concrete implementation for local Ollama server
# ---------------------------------------------------------------------------

class OllamaProvider(LLMProvider):
    """
    Communicates with a local Ollama server via its HTTP API.

    Ollama API docs: https://github.com/ollama/ollama/blob/main/docs/api.md
    """

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        # Timeout: 30s connect, 300s read (local CPU inference can be slow)
        self.timeout = httpx.Timeout(connect=30.0, read=300.0, write=30.0, pool=30.0)

    async def generate(self, prompt: str, model: str) -> str:
        """Send a prompt to Ollama and return the generated text."""
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,  # Wait for full response (simpler for Milestone 1)
        }

        logger.info("Sending request to Ollama (model: %s)", model)

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()

        except httpx.ConnectError:
            logger.error("Cannot connect to Ollama at %s", self.base_url)
            raise LLMConnectionError(
                f"Cannot connect to Ollama at {self.base_url}. "
                "Is Ollama running? Start it with: ollama serve"
            )

        except httpx.TimeoutException:
            logger.error("Ollama request timed out")
            raise LLMGenerationError(
                "Ollama request timed out. The model may be too slow or not loaded. "
                "Try running: ollama run qwen3:4b"
            )

        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            logger.error("Ollama returned HTTP %d", status)

            # 404 usually means the model isn't installed
            if status == 404:
                raise LLMGenerationError(
                    f"Model '{model}' not found in Ollama. "
                    f"Pull it with: ollama pull {model}"
                )

            raise LLMGenerationError(
                f"Ollama returned an error (HTTP {status}). "
                "Check Ollama logs for details."
            )

        # Parse the response
        try:
            data = response.json()
            generated_text = data.get("response", "")

            if not generated_text:
                logger.warning("Ollama returned an empty response")
                raise LLMGenerationError(
                    "Ollama returned an empty response. The model may not have loaded correctly."
                )

            logger.info("Ollama response received (%d chars)", len(generated_text))
            return generated_text

        except (ValueError, KeyError) as exc:
            logger.error("Unexpected Ollama response format: %s", exc)
            raise LLMGenerationError(
                "Unexpected response format from Ollama. Check Ollama version and logs."
            )

    async def health_check(self) -> bool:
        """Check if Ollama is reachable by hitting its root endpoint."""
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
                response = await client.get(self.base_url)
                return response.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException):
            return False


# ---------------------------------------------------------------------------
# LLM Service — facade used by the API layer
# ---------------------------------------------------------------------------

class LLMService:
    """
    High-level service that API routes interact with.

    Wraps an LLMProvider and adds configuration (model selection, etc.).
    This is the ONLY class that API routes should import from this module.
    """

    def __init__(self, provider: LLMProvider, model: str):
        self.provider = provider
        self.model = model

    async def chat(self, message: str) -> tuple[str, str]:
        """
        Send a user message to the LLM and return the response.

        Args:
            message: The user's chat message.

        Returns:
            A tuple of (response_text, model_name).
        """
        logger.info("Chat request — model: %s", self.model)
        response = await self.provider.generate(prompt=message, model=self.model)
        return response, self.model

    async def health_check(self) -> bool:
        """Check if the underlying LLM provider is healthy."""
        return await self.provider.health_check()


# ---------------------------------------------------------------------------
# Factory — creates the default LLMService from app settings
# ---------------------------------------------------------------------------

def create_llm_service() -> LLMService:
    """
    Create an LLMService configured from environment variables.

    This is the single place where the provider choice is wired up.
    To add a new provider later, add a conditional here.
    """
    provider = OllamaProvider(base_url=settings.ollama_base_url)
    service = LLMService(provider=provider, model=settings.ollama_model)

    logger.info(
        "LLM service initialized — provider: Ollama, model: %s, url: %s",
        settings.ollama_model,
        settings.ollama_base_url,
    )
    return service
