"""
Unit and integration tests for Network Monitor and Zero-External-Call Proof.
"""

import os
from fastapi.testclient import TestClient
import pytest

from app.main import app
from app.services.network_monitor import NetworkMonitorService, network_monitor

client = TestClient(app)


def test_localhost_classified_as_local():
    """Test that localhost, 127.0.0.1, and loopback are classified as LOCAL and ALLOWED."""
    mon = NetworkMonitorService()
    
    # 127.0.0.1
    ev1 = mon.record_connection(source="LLMService", destination="http://127.0.0.1:11434")
    assert ev1["classification"] == "LOCAL"
    assert ev1["action"] == "ALLOWED"

    # localhost
    ev2 = mon.record_connection(source="EmbeddingService", destination="localhost:11434")
    assert ev2["classification"] == "LOCAL"
    assert ev2["action"] == "ALLOWED"

    # IPv6 loopback
    ev3 = mon.record_connection(source="System", destination="http://[::1]:8000")
    assert ev3["classification"] == "LOCAL"
    assert ev3["action"] == "ALLOWED"

    assert mon.local_calls == 3
    assert mon.external_calls_attempted == 0
    assert mon.external_calls_blocked == 0


def test_external_destination_classified_and_blocked():
    """Test that external domains are classified as EXTERNAL and BLOCKED under sovereign policy."""
    mon = NetworkMonitorService()

    # Cloud AI attempt (OpenAI)
    ev_openai = mon.record_connection(
        source="LLMService",
        destination="https://api.openai.com/v1/chat/completions",
        reason="Test external connection",
    )
    assert ev_openai["classification"] == "EXTERNAL"
    assert ev_openai["action"] == "BLOCKED"
    assert "Sovereign" in ev_openai["reason"]

    # Cloud AI attempt (Anthropic)
    ev_anthropic = mon.record_connection(
        source="LLMService",
        destination="api.anthropic.com:443",
        reason="Test anthropic connection",
    )
    assert ev_anthropic["classification"] == "EXTERNAL"
    assert ev_anthropic["action"] == "BLOCKED"

    # Cloud AI attempt (Google Gemini)
    ev_gemini = mon.record_connection(
        source="LLMService",
        destination="https://generativelanguage.googleapis.com/v1beta/models",
    )
    assert ev_gemini["classification"] == "EXTERNAL"
    assert ev_gemini["action"] == "BLOCKED"

    assert mon.external_calls_attempted == 3
    assert mon.external_calls_blocked == 3
    assert mon.local_calls == 0


def test_cloud_api_key_detection_behavior(monkeypatch):
    """Test cloud API key detection reports presence without revealing secret values."""
    mon = NetworkMonitorService()

    # When no keys are present
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("AZURE_OPENAI_API_KEY", raising=False)
    
    clean_res = mon.detect_cloud_api_keys()
    # If environment is clean of these specific keys
    if not any(k in os.environ for k in ["OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY"]):
        assert clean_res["detected"] is False
        assert len(clean_res["keys_detected"]) == 0

    # Inject mock key
    secret_value = "sk-super-secret-production-token-12345"
    monkeypatch.setenv("OPENAI_API_KEY", secret_value)

    detected_res = mon.detect_cloud_api_keys()
    assert detected_res["detected"] is True
    assert "OPENAI_API_KEY" in detected_res["keys_detected"]

    # CRITICAL: Verify the secret value itself is NEVER returned
    summary = mon.get_summary()
    assert secret_value not in str(detected_res)
    assert secret_value not in str(summary)


def test_sovereign_mode_and_policy_flags():
    """Verify sovereign policy configuration constants."""
    summary = network_monitor.get_summary()
    assert summary["sovereign_mode"] is True
    assert summary["external_network_allowed"] is False
    assert summary["local_llm_only"] is True


def test_security_status_api_with_network_stats():
    """Test GET /api/security/status contains sovereign mode and network statistics."""
    r = client.get("/api/security/status")
    assert r.status_code == 200
    data = r.json()

    # Existing expected fields
    assert data["sovereign_mode"] is True
    assert data["llm_provider"] == "Ollama"
    assert data["database"] == "SQLite"
    assert data["vector_store"] == "FAISS"
    assert "ocr" in data
    assert "vision" in data
    assert "embeddings" in data
    assert "coding_agent" in data
    assert "sandbox" in data

    # New network monitor fields
    assert "external_calls_attempted" in data
    assert "external_calls_blocked" in data
    assert "local_calls" in data
    assert "cloud_api_keys_detected" in data
    assert isinstance(data["external_calls_attempted"], int)
    assert isinstance(data["external_calls_blocked"], int)
    assert isinstance(data["local_calls"], int)


def test_network_events_endpoint():
    """Test GET /api/security/network-events returns recorded events."""
    # Record a test local event
    network_monitor.record_connection("TestSource", "127.0.0.1:11434", reason="Unit test query")

    r = client.get("/api/security/network-events?limit=10")
    assert r.status_code == 200
    events = r.json()
    assert isinstance(events, list)
    assert len(events) >= 1

    first_event = events[0]
    assert "timestamp" in first_event
    assert "source" in first_event
    assert "destination" in first_event
    assert "classification" in first_event
    assert "action" in first_event
    assert first_event["classification"] in ["LOCAL", "EXTERNAL"]
    assert first_event["action"] in ["ALLOWED", "BLOCKED"]
