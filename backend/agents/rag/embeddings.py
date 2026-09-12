from __future__ import annotations
import hashlib
import logging
import httpx
import numpy as np
from app.config import settings

logger = logging.getLogger(__name__)

def _local_deterministic_embedding(text: str, dim: int = 768) -> list[float]:
    """
    Deterministic local embedding fallback when nomic-embed-text is not installed in Ollama.
    Uses hashed character n-grams and tokens projected onto a unit sphere.
    Zero external network calls, zero cloud dependencies.
    """
    vec = np.zeros(dim, dtype=np.float32)
    tokens = text.lower().split()
    if not tokens:
        return vec.tolist()
        
    for token in tokens:
        # Token hash
        h1 = int(hashlib.sha256(token.encode("utf-8")).hexdigest()[:8], 16)
        idx1 = h1 % dim
        sign1 = 1.0 if (h1 >> 8) % 2 == 0 else -1.0
        vec[idx1] += sign1
        
        # Sub-token / character 3-gram hashes for subword matching
        for i in range(len(token) - 2):
            gram = token[i:i+3]
            h2 = int(hashlib.md5(gram.encode("utf-8")).hexdigest()[:8], 16)
            idx2 = h2 % dim
            sign2 = 0.5 if (h2 >> 8) % 2 == 0 else -0.5
            vec[idx2] += sign2

    norm = np.linalg.norm(vec)
    if norm > 0:
        vec = vec / norm
    return vec.tolist()

def generate_embedding(text: str) -> list[float]:
    """
    Generates embedding for a single text string using local Ollama instance,
    with graceful local deterministic fallback if embedding model is not yet pulled.
    """
    model = getattr(settings, "embedding_model", None) or getattr(settings, "EMBEDDING_MODEL", "nomic-embed-text")
    base_url = getattr(settings, "ollama_base_url", None) or getattr(settings, "OLLAMA_API_URL", "http://localhost:11434")
    url = f"{base_url.rstrip('/')}/api/embed"
    
    try:
        from app.services.network_monitor import network_monitor
        network_monitor.record_connection(
            source="EmbeddingService",
            destination=base_url,
            reason=f"Local embedding generation (model: {model})",
        )
    except Exception:
        pass

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.post(
                url,
                json={"model": model, "input": text}
            )
            if response.status_code == 200:
                data = response.json()
                if "embeddings" in data and len(data["embeddings"]) > 0:
                    return data["embeddings"][0]
                elif "embedding" in data:
                    return data["embedding"]
            else:
                logger.warning("Ollama embedding model '%s' returned status %d. Using local deterministic fallback.", model, response.status_code)
    except Exception as e:
        logger.warning("Could not reach Ollama embedding endpoint: %s. Using local deterministic fallback.", e)
        
    return _local_deterministic_embedding(text)

def generate_embeddings_batch(texts: list[str]) -> list[list[float]]:
    """
    Generates embeddings for a batch of texts.
    """
    if not texts:
        return []
        
    model = getattr(settings, "embedding_model", None) or getattr(settings, "EMBEDDING_MODEL", "nomic-embed-text")
    base_url = getattr(settings, "ollama_base_url", None) or getattr(settings, "OLLAMA_API_URL", "http://localhost:11434")
    url = f"{base_url.rstrip('/')}/api/embed"
    
    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                url,
                json={"model": model, "input": texts}
            )
            if response.status_code == 200:
                data = response.json()
                if "embeddings" in data and len(data["embeddings"]) == len(texts):
                    return data["embeddings"]
            else:
                logger.warning("Ollama embedding batch returned status %d. Using local deterministic fallback.", response.status_code)
    except Exception as e:
        logger.warning("Could not reach Ollama for batch embeddings: %s. Using local deterministic fallback.", e)

    return [_local_deterministic_embedding(t) for t in texts]
