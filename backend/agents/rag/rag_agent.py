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
    Handles both document indexing from upstream OCR and local knowledge retrieval with citations.
    """
    instruction = context.task.instruction if context.task and context.task.instruction else ""
    user_request = context.user_request or ""
    
    ocr_result = context.dependencies.get('ocr') if context.dependencies else None
    all_chunks = []
    
    # 1. Indexing phase (if OCR text is available)
    if ocr_result and ocr_result.data:
        logger.info("RAG Agent indexing text from OCR upstream")
        pages = ocr_result.data.get('pages', [])
        text = ocr_result.data.get('text', '')
        
        if pages:
            for page in pages:
                page_text = page.get('text', '')
                page_num = page.get('page_number', page.get('page_num', 1))
                doc_name = page.get('document', ocr_result.data.get('document', 'Document'))
                
                chunks = chunk_text(page_text)
                for chunk in chunks:
                    chunk['document'] = doc_name
                    chunk['page'] = page_num
                    all_chunks.append(chunk)
        elif text:
            doc_name = ocr_result.data.get('document', 'Document')
            chunks = chunk_text(text)
            for chunk in chunks:
                chunk['document'] = doc_name
                chunk['page'] = 1
                all_chunks.append(chunk)
                
        if all_chunks:
            texts_to_embed = [c['text'] for c in all_chunks]
            try:
                embeddings = generate_embeddings_batch(texts_to_embed)
                store = FAISSVectorStore()
                store.add_documents(embeddings, all_chunks)
                logger.info("Indexed %d chunks into FAISS vector store", len(all_chunks))
            except Exception as e:
                logger.warning("Vector store addition warning: %s", e)
                
            # Store in DB if available
            try:
                from app.db.database import SessionLocal
                from app.db.repositories import create_chunks_bulk
                from app.db.models import DocumentModel
                db = SessionLocal()
                try:
                    db_chunks = []
                    # Cache document lookup by filename
                    doc_cache = {}
                    for idx, c in enumerate(all_chunks):
                        doc_name = c.get("document", "Document")
                        if doc_name not in doc_cache:
                            doc_rec = db.query(DocumentModel).filter_by(filename=doc_name).first()
                            doc_cache[doc_name] = doc_rec.id if doc_rec else None
                        doc_id = doc_cache[doc_name]
                        if doc_id:
                            db_chunks.append({
                                "document_id": doc_id,
                                "chunk_index": idx,
                                "text": c["text"],
                                "page_number": c.get("page", 1),
                            })
                    if db_chunks:
                        create_chunks_bulk(db, db_chunks)
                finally:
                    db.close()
            except Exception as e:
                logger.warning("Database chunk storage skipped: %s", e)

    # 2. Retrieval phase
    query = user_request or instruction or "SOP maintenance standards vibration limits corrective action"
    logger.info("RAG Agent performing retrieval for query: '%s'", query[:60])
    results = retrieve(query, top_k=6)
    
    # If initial retrieve yielded few results and request relates to SOP/maintenance, run a domain query
    if len(results) < 3 and any(k in query.lower() for k in ["sop", "inspection", "corrective", "approval", "pump", "bearing"]):
        extra_results = retrieve("SOP-MAINT-001 rotating equipment vibration temperature limits corrective action", top_k=4)
        seen_texts = {r["text"][:100] for r in results}
        for er in extra_results:
            if er["text"][:100] not in seen_texts:
                results.append(er)
                seen_texts.add(er["text"][:100])

    citations = [r.get("citation") for r in results if r.get("citation")]
    context_str = "\n\n".join([f"{r.get('citation', '')}\n{r.get('text', '')}" for r in results])
    
    summary_msg = f"Indexed {len(all_chunks)} chunk(s); retrieved {len(results)} relevant section(s) from local knowledge base."
    
    return AgentResult(
        agent_name="rag",
        status="completed",
        summary=summary_msg,
        data={
            "indexed_chunks": len(all_chunks),
            "results": results,
            "context": context_str,
            "citations": citations,
        },
        artifacts=[],
        warnings=[],
        errors=[]
    )
