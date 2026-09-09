# Sovereign AI Workbench

**Milestone 1** — Local AI Chat Interface

A self-hosted AI workbench for confidential/industrial environments. All inference runs locally through [Ollama](https://ollama.com/) — no data ever leaves your machine.

> ⚠️ This is **Milestone 1** — a foundational chat interface. The complete air-gapped production system (RAG, OCR, agents, document generation, etc.) is planned for future milestones.

---

## Architecture

```
Browser
  ↓
React frontend (Vite, port 5173)
  ↓ HTTP
FastAPI backend (port 8000)
  ↓
LLMService → OllamaProvider
  ↓ HTTP
Ollama (port 11434)
  ↓
qwen3:4b
```

- The **frontend** never communicates directly with Ollama.
- The **LLM integration layer** abstracts the provider, making it easy to add new local models later.
- **No cloud AI services** are used — all inference is local.

---

## Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| **Python** | 3.11+ | For the FastAPI backend |
| **Node.js** | 18+ | For the React frontend |
| **Ollama** | Latest | Local LLM inference server |

### Hardware

- **RAM**: 16 GB recommended (qwen3:4b uses ~4-6 GB)
- **GPU**: Optional — works on CPU (Intel Iris Xe or similar is fine)
- **Disk**: ~3 GB for the qwen3:4b model

---

## Setup

### 1. Install Ollama

Download from [https://ollama.com/download](https://ollama.com/download) and install.

### 2. Pull the Qwen3 4B model

```bash
ollama pull qwen3:4b
```

### 3. Start Ollama

Ollama usually runs automatically after installation. To start manually:

```bash
ollama serve
```

Verify it's running:

```bash
curl http://localhost:11434
```

You should see: `Ollama is running`

### 4. Set up the backend

```bash
cd backend

# Create virtual environment
python -m venv .venv

# Activate it
# Windows:
.venv\Scripts\activate
# macOS/Linux:
# source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Create .env from template (adjust if needed)
copy ..\.env.example .env
```

### 5. Start the backend

```bash
cd backend
.venv\Scripts\activate
uvicorn app.main:app --reload --port 8000
```

### 6. Set up and start the frontend

```bash
cd frontend
npm install
npm run dev
```

### 7. Open the app

Navigate to [http://localhost:5173](http://localhost:5173) in your browser.

---

## Environment Configuration

Copy `.env.example` to `backend/.env`:

```env
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen3:4b
FRONTEND_ORIGIN=http://localhost:5173
```

| Variable | Description | Default |
|----------|-------------|---------|
| `OLLAMA_BASE_URL` | Ollama server URL | `http://localhost:11434` |
| `OLLAMA_MODEL` | Model to use for chat | `qwen3:4b` |
| `FRONTEND_ORIGIN` | Allowed CORS origin | `http://localhost:5173` |

---

## API Endpoints

### `GET /api/health`

Health check — verifies the backend and Ollama connectivity.

```bash
curl http://localhost:8000/api/health
```

Response:

```json
{
  "status": "ok",
  "backend": "ok",
  "ollama": "ok"
}
```

### `POST /api/chat`

Send a message to the AI model.

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d "{\"message\": \"What is a refinery?\"}"
```

Response:

```json
{
  "response": "A refinery is...",
  "model": "qwen3:4b"
}
```

---

## Project Structure

```
sovereign-ai-workbench/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py          ← FastAPI routes, CORS, lifespan
│   │   ├── config.py        ← Environment configuration
│   │   ├── models.py        ← Pydantic request/response schemas
│   │   └── services/
│   │       ├── __init__.py
│   │       └── llm.py       ← LLMService, LLMProvider, OllamaProvider
│   ├── requirements.txt
│   └── .env                  ← Local config (gitignored)
├── frontend/
│   ├── src/
│   │   ├── App.jsx           ← Chat UI component
│   │   ├── App.css           ← Chat styles
│   │   ├── api.js            ← Backend API helper
│   │   ├── index.css         ← Global styles
│   │   └── main.jsx          ← React entry point
│   ├── index.html
│   ├── package.json
│   └── vite.config.js
├── .env.example              ← Config template (safe to commit)
├── .gitignore
└── README.md
```

---

## Troubleshooting

### "Cannot connect to the backend server"

- Is FastAPI running? Start it with: `uvicorn app.main:app --reload --port 8000`
- Check the terminal for Python errors.

### "Cannot connect to Ollama"

- Is Ollama running? Start it with: `ollama serve`
- Check: `curl http://localhost:11434` should return "Ollama is running"

### "Model not found"

- Pull the model: `ollama pull qwen3:4b`
- Verify: `ollama list` should show qwen3:4b

### "Request timed out"

- qwen3:4b on CPU can take 20-60 seconds per response. This is normal.
- Ensure you have enough free RAM (~6 GB for the model).

### CORS errors in browser console

- Verify `FRONTEND_ORIGIN` in `backend/.env` matches your frontend URL.
- Default: `http://localhost:5173`

---

## Current Limitations (Milestone 1)

- Single-turn chat only (no conversation memory / context window)
- No streaming responses (waits for full response)
- No file uploads or document processing
- No authentication or user management
- No model selection UI
- No conversation persistence (refreshing clears history)

---

## Future Architecture (Planned)

```
Frontend
  ↓
FastAPI
  ↓
LangGraph Orchestrator
  ↓
Model Router
  ↓
Multiple Local LLM Providers
  ↓
RAG (Qdrant) · OCR · Vision · Coding Agent
  ↓
Docker Sandbox · Verification · Document Generation
  ↓
Security / Audit Layer
```

These features will be implemented in future milestones.

---

## License

Private / Internal Use
