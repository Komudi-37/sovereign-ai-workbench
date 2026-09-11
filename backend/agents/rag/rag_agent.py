from __future__ import annotations
import logging
from agents.orchestrator.state import AgentResult
from agents.rag.chunker import chunk_text
from agents.rag.embeddings import generate_embeddings_batch
from agents.rag.vector_store import FAISSVectorStore
from agents.rag.retriever import retrieve

logger = logging.getLogger(__name__)

def rag_adapter(context) -> AgentResult:
    """
    Adapter for the RAG Agent.
    """
    instruction = context.task.instruction if context.task and context.task.instruction else ""
    user_request = context.user_request or ""
    mode = "SEARCH"
    
    # Determine mode based on dependencies
    if context.dependencies and 'ocr' in context.dependencies:
        mode = "INDEX"
        
    if mode == "INDEX":
        logger.info("RAG Agent running in INDEX mode")
        ocr_result = context.dependencies.get('ocr')
        if not ocr_result or not ocr_result.data:
            return AgentResult(
                agent_name="rag",
                status="failed",
                data={},
                message="No OCR data available in dependencies."
            )
            
        document = ocr_result.data.get('document', 'Unknown')
        pages = ocr_result.data.get('pages', [])
        text = ocr_result.data.get('text', '')
        
        all_chunks = []
        if pages:
            for page in pages:
                page_text = page.get('text', '')
                page_num = page.get('page_num', 1)
                
                chunks = chunk_text(page_text)
                for chunk in chunks:
                    chunk['document'] = document
                    chunk['page'] = page_num
                    all_chunks.append(chunk)
        elif text:
             chunks = chunk_text(text)
             for chunk in chunks:
                chunk['document'] = document
                chunk['page'] = 1
                all_chunks.append(chunk)
                
        if not all_chunks:
            return AgentResult(
                agent_name="rag",
                status="completed",
                data={"indexed_chunks": 0},
                message="No text chunks generated for indexing."
            )
            
        texts_to_embed = [c['text'] for c in all_chunks]
        try:
            embeddings = generate_embeddings_batch(texts_to_embed)
        except RuntimeError as e:
            return AgentResult(
                agent_name="rag",
                status="failed",
                data={},
                message=str(e)
            )
            
        store = FAISSVectorStore()
        try:
            store.add_documents(embeddings, all_chunks)
        except RuntimeError as e:
             return AgentResult(
                agent_name="rag",
                status="failed",
                data={},
                message=f"Failed to add documents to vector store: {e}"
            )
            
        # Store chunks in DB
        try:
            from app.db.database import SessionLocal
            from app.db.repositories import create_chunks_bulk
            db = SessionLocal()
            try:
                db_chunks = [{"text": c["text"], "document": c["document"], "page": c["page"]} for c in all_chunks]
                create_chunks_bulk(db, db_chunks)
            finally:
                db.close()
        except ImportError:
            logger.warning("Could not import DB models. Skipping DB storage.")
            
        return AgentResult(
            agent_name="rag",
            status="completed",
            data={"indexed_chunks": len(all_chunks)},
            message=f"Successfully indexed {len(all_chunks)} chunks."
        )
        
    else: # SEARCH mode
        logger.info("RAG Agent running in SEARCH mode")
        query = user_request if user_request else instruction
        if not query:
            return AgentResult(
                agent_name="rag",
                status="failed",
                data={},
                message="No query provided for search."
            )
            
        results = retrieve(query)
        
        return AgentResult(
            agent_name="rag",
            status="completed",
            data={"results": results},
            message=f"Retrieved {len(results)} relevant chunks."
        )
