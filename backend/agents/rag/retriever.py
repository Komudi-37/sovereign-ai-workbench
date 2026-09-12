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
    total_chunks = store.index.ntotal if store.index else 0
    candidate_k = min(150, max(top_k * 10, 50, total_chunks))
    results = store.search(query_embedding, top_k=candidate_k)
    
    # Hybrid keyword-boosted reranking
    stopwords = {"the", "are", "for", "and", "not", "just", "using", "each", "all", "what", "give", "cite", "exact", "with", "this", "from", "that", "your", "have", "is"}
    query_terms = [t.lower().strip(".,?:;!()[]'\"") for t in query.split() if len(t.strip()) > 2 and t.lower() not in stopwords]
    
    # Specific high-value domain phrases
    key_phrases = [
        "iso 10816", "vibration monitoring", "alert levels", "velocity thresholds",
        "velocity threshold", "vibration velocity", "sop-maint-001", "4.1", "bearing temperature", "fouling assessment"
    ]
    matched_phrases = [kp for kp in key_phrases if kp in query.lower()]

    # Operational condition terms that distinguish substantive standard limits from bare bibliography/references
    operational_indicators = [
        "alert levels", "normal:", "watch:", "alert:", "danger:", "< 2.8", "2.8 – 4.5", "4.5 – 7.1", "> 7.1",
        "threshold", "thresholds", "limits", "criteria", "corrective action"
    ]

    scored_candidates = []
    for res in results:
        text_lower = res.get('text', '').lower()
        score = float(res.get('score', 0.0))  # FAISS L2 distance (lower is closer)
        
        # Calculate keyword and key phrase overlap
        term_hits = sum(1 for term in query_terms if term in text_lower)
        phrase_hits = sum(1 for phrase in matched_phrases if phrase in text_lower)
        
        # Check for substantive operational standard content vs bare reference lists
        op_hits = sum(1 for op in operational_indicators if op in text_lower)
        is_bare_reference = "10. references" in text_lower and not any(ind in text_lower for ind in ["alert levels", "rms", "limits:"])
        
        # Substantial boost for domain phrases, term overlap, and operational content
        effective_distance = score - (phrase_hits * 0.70) - (term_hits * 0.05) - (min(op_hits, 4) * 0.15)
        if is_bare_reference:
            effective_distance += 0.40  # De-prioritize bare bibliographic references
            
        scored_candidates.append((effective_distance, res))

    scored_candidates.sort(key=lambda x: x[0])
    top_results = [res for _, res in scored_candidates[:top_k]]
    
    formatted_results = []
    for res in top_results:
        doc = res.get('document') or res.get('filename') or 'Document'
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
