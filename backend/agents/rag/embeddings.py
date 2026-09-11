from __future__ import annotations
import logging
import httpx
from app.config import settings

logger = logging.getLogger(__name__)

def generate_embedding(text: str) -> list[float]:
    """
    Generates embedding for a single text string using local Ollama instance.
    """
    model = getattr(settings, "EMBEDDING_MODEL", "nomic-embed-text")
    url = getattr(settings, "OLLAMA_API_URL", "http://localhost:11434") + "/api/embed"
    
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                url,
                json={"model": model, "input": text}
            )
            response.raise_for_status()
            data = response.json()
            if "embeddings" in data and len(data["embeddings"]) > 0:
                return data["embeddings"][0]
            elif "embedding" in data:
                return data["embedding"]
            raise RuntimeError(f"Unexpected response format from Ollama: {data}")
    except httpx.HTTPError as e:
        logger.error(f"Error generating embedding: {e}")
        raise RuntimeError(f"Failed to connect to Ollama embedding API. Is Ollama running? Error: {e}")
    except Exception as e:
        logger.error(f"Error in generate_embedding: {e}")
        raise RuntimeError(f"Failed to generate embedding: {e}")

def generate_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """
    Generates embeddings for a batch of texts.
    """
    if not texts:
        return []
        
    model = getattr(settings, "EMBEDDING_MODEL", "nomic-embed-text")
    url = getattr(settings, "OLLAMA_API_URL", "http://localhost:11434") + "/api/embed"
    
    try:
        with httpx.Client(timeout=120.0) as client:
            response = client.post(
                url,
                json={"model": model, "input": texts}
            )
            response.raise_for_status()
            data = response.json()
            if "embeddings" in data:
                return data["embeddings"]
            raise RuntimeError(f"Unexpected response format from Ollama: {data}")
    except httpx.HTTPError as e:
        logger.error(f"Error generating embeddings batch: {e}")
        raise RuntimeError(f"Failed to connect to Ollama embedding API. Is Ollama running? Error: {e}")
    except Exception as e:
        logger.error(f"Error in generate_embeddings_batch: {e}")
        raise RuntimeError(f"Failed to generate embeddings batch: {e}")
