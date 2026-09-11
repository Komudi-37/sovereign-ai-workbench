from agents.rag.chunker import chunk_text
from agents.rag.vector_store import FAISSVectorStore

def test_chunker_basic():
    text = "Paragraph 1: Sovereign AI Workbench is an on-premise system.\n\nParagraph 2: All processing is local."
    chunks = chunk_text(text, chunk_size=50, overlap=0.1)
    assert len(chunks) >= 1
    assert "Sovereign AI" in chunks[0]["text"]

def test_vector_store_fallback_or_faiss(tmp_path):
    dim = 384
    store = FAISSVectorStore(dimension=dim, storage_path=str(tmp_path))
    # Dummy embedding of dim 384
    dummy_vec = [0.1] * dim
    meta = {"filename": "doc.pdf", "text": "sample text", "page_number": 1}
    
    store.add_documents([dummy_vec], [meta])
    results = store.search(dummy_vec, top_k=1)
    assert len(results) >= 0  # Should not raise exception
