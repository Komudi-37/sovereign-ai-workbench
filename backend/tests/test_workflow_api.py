from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_workflow_api_data_analysis():
    payload = {
        "workflow": "data_analysis",
        "instruction": "Analyze test dataset",
        "files": ["demo_data/equipment_readings.csv"],
    }
    r = client.post("/api/workflows/run", json=payload)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "completed"
    assert len(data["steps"]) == 2
    assert len(data["artifacts"]) >= 1

def test_list_workflows_endpoint():
    r = client.get("/api/workflows")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
