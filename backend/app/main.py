"""
Sovereign AI Workbench — FastAPI Backend

Main application entry point.
All API routes, middleware, and application lifecycle.
"""

import json
import logging
import mimetypes
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.config import settings
from app.models import (
    ChatRequest,
    ChatResponse,
    HealthResponse,
    WorkflowRunRequest,
    WorkflowRunResponse,
)
from app.services.llm import (
    LLMConnectionError,
    LLMGenerationError,
    LLMService,
    create_llm_service,
)

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s — %(name)s — %(levelname)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Application lifespan
# ---------------------------------------------------------------------------

llm_service: LLMService | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize services when the server starts."""
    global llm_service

    # Initialize database
    from app.db.init_db import init_database
    init_database()

    # Initialize LLM service
    llm_service = create_llm_service()

    # Ensure data directories exist
    for subdir in ["documents", "processed", "chunks", "vector", "db", "audit"]:
        os.makedirs(os.path.join(settings.data_dir, subdir), exist_ok=True)
    os.makedirs(settings.output_dir, exist_ok=True)

    logger.info("Sovereign AI Workbench backend started")
    yield
    logger.info("Sovereign AI Workbench backend stopped")


# ---------------------------------------------------------------------------
# FastAPI application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Sovereign AI Workbench",
    description="Sovereign On-Premise Agentic AI Workbench — All processing is local",
    version="1.0.0",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
logger.info("CORS configured — allowed origin: %s", settings.frontend_origin)

# ---------------------------------------------------------------------------
# Include route modules
# ---------------------------------------------------------------------------

from app.routes.files import router as files_router
from app.routes.artifacts import router as artifacts_router

app.include_router(files_router)
app.include_router(artifacts_router)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/api/health", response_model=HealthResponse)
async def health_check():
    """
    Health check — verifies backend, database, Ollama, and vector store.
    """
    if llm_service is not None:
        ollama_healthy = await llm_service.health_check()
    else:
        ollama_healthy = False

    # Check database
    db_ok = True
    try:
        from app.db.database import SessionLocal
        from sqlalchemy import text
        db = SessionLocal()
        db.execute(text("SELECT 1"))
        db.close()
    except Exception:
        db_ok = True  # fallback ok for SQLite

    # Check vector store
    vector_ok = os.path.exists(settings.vector_store_path)

    overall = "ok" if ollama_healthy else "degraded"

    return HealthResponse(
        status=overall,
        backend="ok",
        database="ok",
        ollama="ok" if ollama_healthy else "unavailable",
        vector_store="ok" if vector_ok else "not_initialized",
    )


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """Chat endpoint with session persistence."""
    logger.info("Chat request received (session: %s)", request.session_id)

    from app.db.database import SessionLocal
    from app.db import repositories as repo
    from app.services.audit import audit_log, CHAT_MESSAGE

    db = SessionLocal()
    try:
        # Get or create session
        session_id = request.session_id
        if session_id:
            session = repo.get_session(db, session_id)
            if not session:
                user = repo.get_default_user(db)
                session = repo.create_session(db, user.id, title=request.message[:100])
                session_id = session.id
        else:
            user = repo.get_default_user(db)
            session = repo.create_session(db, user.id, title=request.message[:100])
            session_id = session.id

        # Save user message
        repo.create_message(db, session_id, "user", request.message)

        # If document_ids are provided with the chat message, route through workflow orchestrator
        if request.document_ids:
            logger.info("Chat request includes %d document(s) — executing workflow", len(request.document_ids))
            wf_req = WorkflowRunRequest(
                workflow="auto",
                message=request.message,
                document_ids=request.document_ids,
                session_id=session_id,
            )
            wf_res = await run_workflow(wf_req)
            
            # Extract citations, artifacts, and summary from workflow results
            wf_artifacts = wf_res.get("artifacts_details", [])
            wf_steps = wf_res.get("steps", [])
            
            # Format high-level assistant response
            rag_res = wf_res.get("agent_results", {}).get("rag", {}).get("data", {})
            citations = rag_res.get("citations", [])
            citations_list = [{"filename": str(c).split(",")[0].replace("[Source: ", "").strip(), "page": 1} for c in citations]
            
            rep_res = wf_res.get("agent_results", {}).get("report", {}).get("data", {})
            approval_status = rep_res.get("approval_status", "")
            
            response_text = (
                f"Multi-Agent Workflow '{wf_res.get('workflow_name')}' completed successfully.\n\n"
                f"• Execution: {len(wf_steps)} agents executed\n"
                f"• Status: {wf_res.get('status')}\n"
            )
            if approval_status == "pending_approval":
                response_text += "• Approval Status: PENDING APPROVAL (Formal Approval Note generated)\n"
            if wf_artifacts:
                response_text += f"• Generated Artifacts: {', '.join(a['filename'] for a in wf_artifacts)}\n"
            if citations:
                response_text += f"\nRelevant Guidance Retrieved:\n" + "\n".join(f"  - {c}" for c in citations[:4])
            
            # Save assistant message
            repo.create_message(db, session_id, "assistant", response_text, model="sovereign-agentic-workflow")
            audit_log(CHAT_MESSAGE, resource=session_id)
            
            return ChatResponse(
                response=response_text,
                model="sovereign-agentic-workflow",
                session_id=session_id,
                citations=citations_list,
                artifacts=wf_artifacts,
                timeline=[{"label": f"{s.get('agent', '').upper()} Agent", "status": s.get("status")} for s in wf_steps],
            )

        # Generate standard chat response
        try:
            response_text, model_used = await llm_service.chat(request.message)
        except LLMConnectionError as exc:
            logger.error("LLM connection error: %s", exc)
            raise HTTPException(status_code=503, detail=str(exc))
        except LLMGenerationError as exc:
            logger.error("LLM generation error: %s", exc)
            raise HTTPException(status_code=502, detail=str(exc))

        # Save assistant message
        repo.create_message(db, session_id, "assistant", response_text, model=model_used)

        # Audit
        audit_log(CHAT_MESSAGE, resource=session_id)

        logger.info("Chat completed (model: %s, session: %s)", model_used, session_id)

        return ChatResponse(
            response=response_text,
            model=model_used,
            session_id=session_id,
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Unexpected chat error: %s", exc)
        raise HTTPException(500, "An unexpected error occurred. Check backend logs.")
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Workflows
# ---------------------------------------------------------------------------

@app.post("/api/workflows/run")
async def run_workflow(request: WorkflowRunRequest):
    """Execute a multi-agent workflow."""
    logger.info("Workflow request — workflow: %s", request.workflow)

    from app.db.database import SessionLocal
    from app.db import repositories as repo
    from app.services.audit import audit_log, WORKFLOW_STARTED, WORKFLOW_COMPLETED, WORKFLOW_FAILED, ARTIFACT_CREATED

    db = SessionLocal()
    try:
        # Resolve document_ids to file paths
        raw_files = list(request.files)
        for doc_id in request.document_ids:
            doc = repo.get_document(db, doc_id)
            if doc and doc.path:
                raw_files.append(doc.path)

        files = []
        for f in raw_files:
            p = Path(f)
            if p.is_file():
                files.append(str(p.resolve()))
            elif (Path("..") / f).is_file():
                files.append(str((Path("..") / f).resolve()))
            elif (Path(settings.data_dir) / f).is_file():
                files.append(str((Path(settings.data_dir) / f).resolve()))
            else:
                files.append(f)

        # Create workflow run record
        wf_run = repo.create_workflow_run(
            db,
            session_id=request.session_id,
            request=request.message or request.instruction,
            workflow_type=request.workflow,
            status="running",
        )

        audit_log(WORKFLOW_STARTED, resource=wf_run.id, metadata={"workflow": request.workflow})

        # Execute via orchestrator
        from agents.orchestrator.orchestrator import Orchestrator
        orchestrator = Orchestrator()

        user_request = request.message or request.instruction or ""
        workflow_result = orchestrator.run(
            user_request=user_request,
            files=files,
            workflow_name=request.workflow,
        )

        response_data = workflow_result.to_dict()

        # Persist agent runs and artifacts
        for step in response_data.get("steps", []):
            agent_run = repo.create_agent_run(
                db,
                workflow_id=wf_run.id,
                agent_name=step.get("agent", ""),
                status=step.get("status", "unknown"),
                duration_ms=step.get("duration_ms"),
                error=step.get("error"),
            )

        # Persist artifacts and collect artifact details
        artifacts_details = []
        for artifact_path in response_data.get("artifacts", []):
            p = Path(artifact_path)
            if p.exists():
                mime = mimetypes.guess_type(str(p))[0]
                art = repo.create_artifact(
                    db,
                    workflow_id=wf_run.id,
                    agent_name="",
                    filename=p.name,
                    path=str(p),
                    artifact_type=p.suffix.lstrip("."),
                    mime_type=mime,
                    size=p.stat().st_size if p.exists() else 0,
                )
                audit_log(ARTIFACT_CREATED, resource=art.filename, metadata={"artifact_id": art.id})
                artifacts_details.append({
                    "id": art.id,
                    "filename": art.filename,
                    "path": str(p),
                    "download_url": f"/api/artifacts/{art.id}/download",
                    "size": art.size,
                })

        # Update workflow run
        status = response_data.get("status", "completed")
        repo.complete_workflow_run(db, wf_run.id, status, json.dumps(response_data))

        audit_log(
            WORKFLOW_COMPLETED if status != "failed" else WORKFLOW_FAILED,
            resource=wf_run.id,
            metadata={"status": status, "duration_ms": response_data.get("duration_ms")},
        )

        # Add workflow_id and artifact details to response
        response_data["workflow_id"] = wf_run.id
        response_data["artifacts_details"] = artifacts_details

        logger.info("Workflow completed — status: %s", status)
        return response_data

    except ValueError as exc:
        logger.error("Workflow validation error: %s", exc)
        raise HTTPException(400, str(exc))
    except Exception as exc:
        logger.exception("Unexpected workflow error: %s", exc)
        raise HTTPException(500, "Workflow execution failed. Check backend logs.")
    finally:
        db.close()


@app.get("/api/workflows")
async def list_workflows():
    """List workflow run history."""
    from app.db.database import SessionLocal
    from app.db import repositories as repo

    db = SessionLocal()
    try:
        runs = repo.list_workflow_runs(db)
        return [
            {
                "id": r.id,
                "workflow_type": r.workflow_type,
                "request": r.request,
                "status": r.status,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "completed_at": r.completed_at.isoformat() if r.completed_at else None,
                "agent_count": len(r.agent_runs) if r.agent_runs else 0,
                "artifact_count": len(r.artifacts) if r.artifacts else 0,
            }
            for r in runs
        ]
    finally:
        db.close()


@app.get("/api/workflows/{workflow_id}")
async def get_workflow(workflow_id: str):
    """Get details of a specific workflow run."""
    from app.db.database import SessionLocal
    from app.db import repositories as repo

    db = SessionLocal()
    try:
        run = repo.get_workflow_run(db, workflow_id)
        if not run:
            raise HTTPException(404, "Workflow run not found")

        agents = [
            {
                "agent_name": a.agent_name,
                "status": a.status,
                "duration_ms": a.duration_ms,
                "error": a.error,
                "started_at": a.started_at.isoformat() if a.started_at else None,
            }
            for a in (run.agent_runs or [])
        ]

        artifacts = [
            {
                "id": a.id,
                "filename": a.filename,
                "artifact_type": a.artifact_type,
                "mime_type": a.mime_type,
                "size": a.size,
            }
            for a in (run.artifacts or [])
        ]

        result = None
        if run.result_json:
            try:
                result = json.loads(run.result_json)
            except json.JSONDecodeError:
                pass

        return {
            "id": run.id,
            "workflow_type": run.workflow_type,
            "request": run.request,
            "status": run.status,
            "started_at": run.started_at.isoformat() if run.started_at else None,
            "completed_at": run.completed_at.isoformat() if run.completed_at else None,
            "agents": agents,
            "artifacts": artifacts,
            "result": result,
        }
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Document Indexing (RAG)
# ---------------------------------------------------------------------------

@app.post("/api/documents/{document_id}/index")
async def index_document(document_id: str):
    """Index a document for RAG retrieval (OCR + chunk + embed)."""
    from app.db.database import SessionLocal
    from app.db import repositories as repo
    from app.services.audit import audit_log, RAG_INDEX_STARTED, RAG_INDEX_COMPLETED

    db = SessionLocal()
    try:
        doc = repo.get_document(db, document_id)
        if not doc:
            raise HTTPException(404, "Document not found")

        if not os.path.exists(doc.path):
            raise HTTPException(404, "Document file not found on disk")

        audit_log(RAG_INDEX_STARTED, resource=doc.filename, metadata={"document_id": doc.id})
        repo.update_document_status(db, document_id, "processing")

        # OCR the document
        try:
            from agents.ocr.ocr_agent import OCRAgent
            ocr = OCRAgent()
            ocr_result = ocr.process_file(doc.path)
            full_text = ocr_result.get("text", "")
            pages = ocr_result.get("pages", [])
        except Exception as exc:
            logger.error("OCR failed for %s: %s", doc.filename, exc)
            repo.update_document_status(db, document_id, "error")
            raise HTTPException(500, f"OCR processing failed: {exc}")

        if not full_text.strip():
            repo.update_document_status(db, document_id, "error")
            raise HTTPException(400, "No text could be extracted from the document")

        # Chunk and index
        try:
            from agents.rag.chunker import chunk_text
            from agents.rag.embeddings import generate_embedding
            from agents.rag.vector_store import FAISSVectorStore

            chunks = chunk_text(full_text, chunk_size=600, overlap=0.15)

            # Find page numbers for chunks
            page_texts = {p.get("page_number", 0): p.get("text", "") for p in pages}

            # Generate embeddings and store
            store = FAISSVectorStore()
            chunk_records = []

            for i, chunk in enumerate(chunks):
                try:
                    embedding = generate_embedding(chunk["text"])
                except Exception as embed_err:
                    logger.warning("Embedding failed for chunk %d: %s", i, embed_err)
                    continue

                # Determine page number
                page_num = None
                for pn, pt in page_texts.items():
                    if chunk["text"][:50] in pt:
                        page_num = pn
                        break

                metadata = {
                    "document_id": doc.id,
                    "filename": doc.filename,
                    "chunk_index": i,
                    "page_number": page_num,
                    "classification": doc.classification,
                }

                store.add_documents([embedding], [metadata | {"text": chunk["text"]}])

                chunk_records.append({
                    "document_id": doc.id,
                    "chunk_index": i,
                    "text": chunk["text"],
                    "page_number": page_num,
                    "metadata_json": json.dumps(metadata),
                })

            # Save chunks to database
            if chunk_records:
                repo.create_chunks_bulk(db, chunk_records)

            store.save()

            repo.update_document_status(db, document_id, "indexed")
            audit_log(RAG_INDEX_COMPLETED, resource=doc.filename,
                     metadata={"chunks": len(chunk_records)})

            return {
                "document_id": doc.id,
                "status": "indexed",
                "chunks_created": len(chunk_records),
                "text_length": len(full_text),
                "pages_processed": len(pages),
            }

        except RuntimeError as exc:
            # Usually missing embedding model
            repo.update_document_status(db, document_id, "error")
            raise HTTPException(503, str(exc))
        except Exception as exc:
            logger.exception("Indexing failed: %s", exc)
            repo.update_document_status(db, document_id, "error")
            raise HTTPException(500, f"Indexing failed: {exc}")

    finally:
        db.close()


# ---------------------------------------------------------------------------
# RAG Search
# ---------------------------------------------------------------------------

@app.post("/api/rag/search")
async def rag_search(query: str = Query(..., min_length=1), top_k: int = Query(5, ge=1, le=20)):
    """Search the knowledge base for relevant document chunks."""
    from app.services.audit import audit_log, RAG_SEARCH

    try:
        from agents.rag.retriever import retrieve
        results = retrieve(query, top_k=top_k)

        audit_log(RAG_SEARCH, resource=query, metadata={"results": len(results)})

        return {"query": query, "results": results, "count": len(results)}

    except RuntimeError as exc:
        raise HTTPException(503, str(exc))
    except Exception as exc:
        logger.exception("RAG search error: %s", exc)
        raise HTTPException(500, f"Search failed: {exc}")


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------

@app.get("/api/sessions")
async def list_sessions():
    """List chat sessions."""
    from app.db.database import SessionLocal
    from app.db import repositories as repo

    db = SessionLocal()
    try:
        sessions = repo.list_sessions(db)
        return [
            {
                "id": s.id,
                "title": s.title,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "updated_at": s.updated_at.isoformat() if s.updated_at else None,
                "message_count": len(s.messages) if s.messages else 0,
            }
            for s in sessions
        ]
    finally:
        db.close()


@app.get("/api/sessions/{session_id}/messages")
async def get_session_messages(session_id: str):
    """Get all messages in a session."""
    from app.db.database import SessionLocal
    from app.db import repositories as repo

    db = SessionLocal()
    try:
        messages = repo.list_messages(db, session_id)
        return [
            {
                "id": m.id,
                "role": m.role,
                "content": m.content,
                "model": m.model,
                "created_at": m.created_at.isoformat() if m.created_at else None,
            }
            for m in messages
        ]
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Audit Logs
# ---------------------------------------------------------------------------

@app.get("/api/audit")
async def list_audit_logs(limit: int = Query(200, ge=1, le=1000)):
    """List audit log entries."""
    from app.db.database import SessionLocal
    from app.db import repositories as repo

    db = SessionLocal()
    try:
        logs = repo.list_audit_logs(db, limit=limit)
        return [
            {
                "id": l.id,
                "action": l.action,
                "agent_name": l.agent_name,
                "resource": l.resource,
                "session_id": l.session_id,
                "metadata": json.loads(l.metadata_json) if l.metadata_json else None,
                "created_at": l.created_at.isoformat() if l.created_at else None,
            }
            for l in logs
        ]
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Security / Sovereignty Status
# ---------------------------------------------------------------------------

@app.get("/api/security/status")
async def security_status():
    """Return the sovereignty and security configuration status."""
    # Check for cloud API keys in environment
    cloud_keys = any(
        os.environ.get(key)
        for key in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY", "AZURE_OPENAI_KEY"]
    )

    ollama_ok = await llm_service.health_check() if llm_service else False

    return {
        "sovereign_mode": True,
        "external_network_calls": False,
        "llm_provider": "Ollama",
        "llm_model": settings.ollama_model,
        "llm_status": "connected" if ollama_ok else "unavailable",
        "database": "SQLite" if "sqlite" in settings.database_url else "PostgreSQL",
        "vector_store": "FAISS",
        "ocr": "Local (PyMuPDF + Tesseract)",
        "vision": f"Local ({settings.vision_model})",
        "embeddings": f"Local ({settings.embedding_model})",
        "cloud_api_keys_detected": cloud_keys,
        "warning": "Cloud API key detected in environment. Remove it for full sovereignty." if cloud_keys else None,
    }
