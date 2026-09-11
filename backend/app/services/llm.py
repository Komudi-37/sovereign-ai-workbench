"""
LLM integration layer for Sovereign AI Workbench.

Architecture:
    LLMService  (facade — used by API routes)
        └── LLMProvider  (abstract base)
                └── OllamaProvider  (concrete — talks to local Ollama)

This abstraction keeps Ollama-specific HTTP details isolated.
"""

import logging
from abc import ABC, abstractmethod

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------

class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
    async def generate(self, prompt: str, model: str, system: str = None) -> str:
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        pass


# ---------------------------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------------------------

class LLMConnectionError(Exception):
    """Raised when the LLM provider is unreachable."""
    pass


class LLMGenerationError(Exception):
    """Raised when the LLM provider fails to generate a response."""
    pass


SOVEREIGN_SYSTEM_PROMPT = """You are Sovereign AI Workbench, an on-premise, air-gapped, sovereign agentic AI system for confidential industrial operations.
You operate entirely locally with open-weight models (such as Qwen and local tools) with zero cloud external services.
The system features 6 core cooperating agents:
1. Orchestrator Agent: Routes tasks, coordinates agent dependencies, and manages state.
2. OCR Agent: Extracts text and tables from local documents (PDF, scans, images) using local PyMuPDF and pytesseract.
3. RAG Agent: Indexes documents into FAISS vector database with local embeddings, retrieving SOPs and engineering standards with citations.
4. Vision Agent: Analyzes equipment photos, P&ID diagrams, and visual anomalies using local vision models.
5. Data Analysis Agent: Analyzes industrial time-series sensor data, CSVs, and telemetry for anomalies, trends, and statistics.
6. Report Agent: Synthesizes evidence from upstream agents into formal documents (DOCX, PDF) and Approval Notes.

Always answer accurately, professionally, and concisely as the Sovereign AI Workbench assistant."""


# ---------------------------------------------------------------------------
# Ollama provider
# ---------------------------------------------------------------------------

class OllamaProvider(LLMProvider):
    """Communicates with a local Ollama server via its HTTP API."""

    def __init__(self, base_url: str, timeout: int = 180):
        self.base_url = base_url.rstrip("/")
        self.timeout = httpx.Timeout(
            connect=30.0,
            read=float(timeout),
            write=30.0,
            pool=30.0,
        )

    async def generate(self, prompt: str, model: str, system: str = None) -> str:
        """Send a prompt to Ollama and return the generated text."""
        url = f"{self.base_url}/api/generate"
        payload = {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "num_predict": 256,
                "temperature": 0.7,
            },
        }
        if system:
            payload["system"] = system

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
                "Local model is still processing or not loaded. "
                "This can take 30-120 seconds on CPU. "
                "If this persists, try: ollama run " + model
            )

        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            logger.error("Ollama returned HTTP %d", status)

            if status == 404:
                raise LLMGenerationError(
                    f"Model '{model}' not found in Ollama. "
                    f"Pull it with: ollama pull {model}"
                )

            raise LLMGenerationError(
                f"Ollama returned an error (HTTP {status}). "
                "Check Ollama logs for details."
            )

        try:
            data = response.json()
            generated_text = data.get("response", "").strip()

            # Handle thinking models (such as Qwen3/DeepSeek) where output may be in thinking field
            if not generated_text:
                thinking_text = data.get("thinking", "").strip()
                if thinking_text:
                    generated_text = thinking_text

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
                "Unexpected response format from Ollama."
            )

    async def health_check(self) -> bool:
        """Check if Ollama is reachable."""
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
                response = await client.get(self.base_url)
                return response.status_code == 200
        except (httpx.ConnectError, httpx.TimeoutException):
            return False

    async def generate_embeddings(self, text: str, model: str) -> list[float]:
        """Generate embeddings using Ollama's /api/embed endpoint."""
        url = f"{self.base_url}/api/embed"
        payload = {"model": model, "input": text}

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                data = response.json()
                embeddings = data.get("embeddings", [[]])[0]
                if not embeddings:
                    raise LLMGenerationError("Empty embeddings returned")
                return embeddings
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 404:
                raise LLMGenerationError(
                    f"Embedding model '{model}' not found. "
                    f"Pull it with: ollama pull {model}"
                )
            raise
        except httpx.ConnectError:
            raise LLMConnectionError("Cannot connect to Ollama for embeddings")


# ---------------------------------------------------------------------------
# LLM Service — facade
# ---------------------------------------------------------------------------

class LLMService:
    """High-level service that API routes interact with."""

    def __init__(self, provider: LLMProvider, model: str):
        self.provider = provider
        self.model = model

    async def chat(self, message: str) -> tuple[str, str]:
        """Send a user message and return (response_text, model_name)."""
        logger.info("Chat request — model: %s", self.model)
        response = await self.provider.generate(
            prompt=message,
            model=self.model,
            system=SOVEREIGN_SYSTEM_PROMPT,
        )
        return response, self.model

    async def generate(self, prompt: str, model: str = None) -> str:
        """Generate text with an optionally specified model."""
        model = model or self.model
        return await self.provider.generate(prompt=prompt, model=model)

    async def health_check(self) -> bool:
        return await self.provider.health_check()


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------

def create_llm_service() -> LLMService:
    """Create an LLMService configured from environment variables."""
    provider = OllamaProvider(
        base_url=settings.ollama_base_url,
        timeout=settings.ollama_timeout,
    )
    service = LLMService(provider=provider, model=settings.ollama_model)

    logger.info(
        "LLM service initialized — provider: Ollama, model: %s, url: %s, timeout: %ds",
        settings.ollama_model,
        settings.ollama_base_url,
        settings.ollama_timeout,
    )
    return service
