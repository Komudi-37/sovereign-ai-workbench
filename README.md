# Sovereign On-Premise Agentic AI Workbench

A sovereign, air-gapped agentic AI workbench built for confidential industrial environments (such as refineries, PSUs, and defense-linked organizations). All inference runs strictly on-premise using open-weight multimodal models via [Ollama](https://ollama.com/) — **no confidential data ever leaves your internal infrastructure**.

---

## Architecture Overview

```
                          ┌───────────────────────────┐
                          │   React Frontend (Vite)   │
                          │   (Port 5173, Dark UI)    │
                          └─────────────┬─────────────┘
                                        │ HTTP
                                        ▼
                          ┌───────────────────────────┐
                          │      FastAPI Backend      │
                          │        (Port 8000)        │
                          └─────────────┬─────────────┘
                                        │
                                        ▼
                          ┌───────────────────────────┐
                          │    ORCHESTRATOR AGENT     │
                          │  (State Graph & Routing)  │
                          └─────────────┬─────────────┘
                                        │
           ┌────────────────────────────┼────────────────────────────┐
           │                            │                            │
           ▼                            ▼                            ▼
  ┌─────────────────┐          ┌─────────────────┐          ┌─────────────────┐
  │    OCR Agent    │          │    RAG Agent    │          │  Vision Agent   │
  │ (PyMuPDF/Local) │          │  (FAISS/Local)  │          │ (Local Ollama)  │
  └────────┬────────┘          └────────┬────────┘          └────────┬────────┘
           │                            │                            │
           └────────────────────────────┼────────────────────────────┘
                                        │
                         ┌──────────────┴──────────────┐
                         ▼                             ▼
                ┌──────────────────┐          ┌──────────────────┐
                │  Data Analysis   │          │ Report Generator │
                │  (Pandas/Charts) │          │ (DOCX/PDF/PPTX)  │
                └────────┬─────────┘          └────────┬─────────┘
                         │                             │
                         └──────────────┬──────────────┘
                                        ▼
                                 ┌──────────────┐
                                 │  Artifacts   │
                                 │ (DOCX, PNG)  │
                                 └──────────────┘

Supporting Subsystems:
- SQLite Database (SQLAlchemy ORM, persistent)
- Model Router Service (Task-based local model selection)
- Audit Trail Subsystem (All actions logged with timestamps)
- Vector Store (Local FAISS on disk)
```

---

## Six Cooperating Agents

1. **Orchestrator Agent** (`backend/agents/orchestrator/`)
   - Central workflow engine executing topological sort over dependencies.
   - Handles auto-routing based on intent and attached file types.
   - Passes structured `AgentContext` and `AgentResult` downstream.

2. **OCR Agent** (`backend/agents/ocr/`)
   - Local document extraction supporting PDF, PNG, JPG, and scanned files.
   - PyMuPDF native extraction with fallback to local pytesseract.
   - Returns structured pages, text, and confidence scores.

3. **RAG Agent** (`backend/agents/rag/`)
   - Text chunking (500–800 tokens, 15% overlap) preserving paragraph boundaries.
   - Local embeddings via Ollama (`nomic-embed-text`).
   - Persistent FAISS vector store on disk; returns ranked results with citations `[Source: document.pdf, page X]`.

4. **Vision Agent** (`backend/agents/vision/`)
   - Local vision understanding via Ollama multimodal models (`llava:7b` / `qwen2.5-vl`).
   - ZERO cloud/OpenAI dependencies — returns structured observations, visible labels, and findings.
   - Graceful failure when local vision model is not installed.

5. **Data Analysis Agent** (`backend/agents/data_analysis/`)
   - Local tabular data processing (CSV, Excel) using Pandas, NumPy, Matplotlib.
   - Descriptive statistics, trend analysis, anomaly detection, chart artifact generation.

6. **Report Generation Agent** (`backend/agents/report/`)
   - Generates professional deliverables (DOCX, PDF, PPTX, XLSX) via python-docx and reportlab.
   - Consumes upstream agent findings, embeds generated charts, tables, and watermarks (`INTERNAL — DEMONSTRATION DATA`).

---

## Supporting Services (Subsystems)

- **Model Router Service** (`app/services/model_router.py`): Routes tasks (`chat`, `reasoning`, `vision`, `retrieval`) to configured local models.
- **Audit Logging Subsystem** (`app/services/audit.py`): Captures immutable audit entries for uploads, OCR, RAG searches, workflows, and chat.
- **Persistent Database** (`app/db/`): SQLite via SQLAlchemy storing users, sessions, messages, documents, document chunks, workflow runs, agent runs, and artifacts. Configurable to PostgreSQL.
- **Local File & Artifact Storage** (`data/`, `backend/outputs/`): Deduplicated document uploads via SHA-256 with secure file download endpoints.

---

## Sovereignty & Air-Gap Compliance

| Requirement | Implementation | Proof / Verification |
|---|---|---|
| **Zero Cloud APIs** | No OpenAI, Anthropic, Gemini SDKs or network calls | Verified via codebase grep & `GET /api/security/status` |
| **No Cloud Fallback** | Missing local models fail gracefully with clear error messages | Tested in Vision & RAG |
| **No External CDNs** | System font stack only (`-apple-system, BlinkMacSystemFont, Segoe UI`) | All Google Fonts links removed from `index.html` |
| **Local LLM Inference** | Ollama running `qwen3:4b` on localhost | Hardened HTTP client with 180s timeout & token bounds |
| **Local Embeddings** | Ollama `nomic-embed-text` | Air-gapped embeddings generated via local HTTP API |
| **Local Vector Search** | FAISS CPU index saved directly to `./data/vector/` | No cloud vector DB needed |

---

## Prerequisites & Installation

### 1. Hardware Requirements
- **OS**: Windows, Linux, or macOS
- **RAM**: 16 GB recommended (qwen3:4b uses ~4–6 GB)
- **GPU**: Optional — runs entirely on CPU (Intel Iris Xe or standard x86 CPU)
- **Software**: Python 3.11+, Node.js 18+, Ollama

### 2. Install & Configure Ollama
1. Download Ollama from [https://ollama.com/download](https://ollama.com/download)
2. Pull the required models:
   ```bash
   ollama pull qwen3:4b
   # Optional models for Vision and RAG embeddings:
   ollama pull nomic-embed-text
   ollama pull llava:7b
   ```
3. Verify Ollama is running:
   ```bash
   curl http://localhost:11434
   ```

### 3. Backend Setup
```bash
cd backend
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
# source .venv/bin/activate

pip install -r requirements.txt
```

### 4. Frontend Setup
```bash
cd frontend
npm install
```

---

## Running the Workbench

### Start the Backend
```bash
cd backend
.venv\Scripts\activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Start the Frontend
```bash
cd frontend
npm run dev
```
Open [http://localhost:5173](http://localhost:5173) in your web browser.

---

## Demo Workflows

### Hero Demo: Inspection Document → OCR → RAG → Approval Note
1. Navigate to the **Chat** or **Workflows** page.
2. Upload `demo_data/sample_inspection_report.txt`.
3. Enter prompt:
   > *"Read this inspection report, identify key findings, compare with our internal SOP, and prepare an approval note."*
4. The Orchestrator automatically routes to `ocr_rag_report`:
   - **OCR Agent** extracts text from the document.
   - **RAG Agent** chunks and indexes the content.
   - **Report Agent** compiles executive summary, findings, and outputs `report.docx`.
5. Download the generated deliverable directly from the UI.

### Secondary Demo: Equipment Sensor Data Analysis
1. Upload `demo_data/equipment_readings.csv`.
2. Enter prompt:
   > *"Analyze this equipment dataset, detect anomalies, generate charts, and prepare a management report."*
3. The Orchestrator executes `data_analysis`:
   - **Data Analysis Agent** computes statistics, detects pump bearing degradation & heat exchanger fouling, and renders Matplotlib charts.
   - **Report Agent** compiles findings and charts into `report.docx`.

---

## API Reference

| Endpoint | Method | Description |
|---|---|---|
| `/api/health` | GET | Comprehensive system health check (Backend, DB, Ollama, Vector Store) |
| `/api/security/status` | GET | Sovereignty status report (Cloud API keys detection, Local providers) |
| `/api/chat` | POST | Persistent chat conversation with session tracking |
| `/api/files/upload` | POST | Multipart file upload with SHA-256 deduplication |
| `/api/files` | GET | List all uploaded documents |
| `/api/files/{id}` | GET | Get document details and chunk metadata |
| `/api/documents/{id}/index`| POST | Trigger OCR + RAG chunking + vector indexing |
| `/api/rag/search` | POST | Retrieve document snippets with citations |
| `/api/workflows/run` | POST | Run agent workflow (`auto`, `data_analysis`, `ocr_rag_report`, `vision`) |
| `/api/workflows` | GET | List workflow execution history |
| `/api/artifacts` | GET | List all generated deliverables (DOCX, PNG, CSV) |
| `/api/artifacts/{id}/download` | GET | Download generated deliverable file |
| `/api/audit` | GET | Retrieve auditable action logs |

---

## Verification & Automated Testing

Run the automated pytest suite:
```bash
cd backend
.venv\Scripts\python.exe -m pytest tests/ -v
```

All 21 unit tests verify database persistence, file uploads, OCR extraction, RAG chunking, FAISS vector indexing, Vision local routing, and API endpoints.

---

## Prototype vs. Production Upgrade Path

| Component | Hackathon Prototype (Current) | Production Upgrade Path |
|---|---|---|
| **Database** | SQLite with auto-migration | PostgreSQL with connection pooling |
| **Vector Store** | Local FAISS files on disk | Qdrant / pgvector cluster |
| **Model Serving** | Single Ollama instance on localhost | vLLM / Ollama multi-GPU cluster |
| **Execution Sandbox**| Local Python process | Docker / gVisor isolated sandbox |
| **Authentication** | Built-in admin session | Enterprise SAML / OIDC / LDAP SSO |
| **Storage** | Local `./data/` directories | S3-compatible air-gapped MinIO bucket |

---

## License & Data Notice

**INTERNAL / PROTOTYPE USE ONLY.**  
All files in `demo_data/` are synthetic demonstration data and contain no confidential or proprietary information.
