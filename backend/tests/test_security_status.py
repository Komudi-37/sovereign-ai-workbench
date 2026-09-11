from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_security_status_endpoint():
    r = client.get("/api/security/status")
    assert r.status_code == 200
    data = r.json()
    assert data["sovereign_mode"] is True
    assert data["external_network_calls"] is False
    assert data["llm_provider"] == "Ollama"
    assert data["database"] == "SQLite"
    assert data["vector_store"] == "FAISS"
    assert data["cloud_api_keys_detected"] is False

def test_health_check_endpoint():
    r = client.get("/api/health")
    assert r.status_code == 200
    data = r.json()
    assert data["backend"] == "ok"
    assert data["database"] == "ok"
