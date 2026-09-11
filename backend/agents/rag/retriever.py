from __future__ import annotations
import logging
from agents.rag.embeddings import generate_embedding
from agents.rag.vector_store import FAISSVectorStore

logger = logging.getLogger(__name__)

def retrieve(query: str, top_k: int = 5) -> list[dict]:
    """
    Retrieves relevant documents for a given query.
    Returns a list of dicts containing {text, document, page, score, citation}.
    """
    try:
        query_embedding = generate_embedding(query)
    except RuntimeError as e:
        logger.error(f"Failed to generate query embedding: {e}")
        return []
        
    store = FAISSVectorStore()
    results = store.search(query_embedding, top_k=top_k)
    
    formatted_results = []
    for res in results:
        doc = res.get('document', 'Unknown')
        page = res.get('page', 1)
        citation = f"[Source: {doc}, page {page}]"
        
        formatted_results.append({
            'text': res.get('text', ''),
            'document': doc,
            'page': page,
            'score': res.get('score', 0.0),
            'chunk_index': res.get('chunk_index', 0),
            'citation': citation
        })
        
    return formatted_results
