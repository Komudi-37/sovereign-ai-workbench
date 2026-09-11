import io
import uuid
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_upload_file_and_list():
    # 1. Upload a CSV with unique content
    unique_id = str(uuid.uuid4())
    content = f"col1,col2\n{unique_id},4\n".encode("utf-8")
    response = client.post(
        "/api/files/upload",
        files={"file": (f"test_{unique_id[:8]}.csv", io.BytesIO(content), "text/csv")}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["filename"] == f"test_{unique_id[:8]}.csv"
    assert "document_id" in data
    doc_id = data["document_id"]
    
    # 2. Get file details
    res_get = client.get(f"/api/files/{doc_id}")
    assert res_get.status_code == 200
    assert res_get.json()["id"] == doc_id
    
    # 3. List files
    res_list = client.get("/api/files")
    assert res_list.status_code == 200
    assert any(f["id"] == doc_id for f in res_list.json())

def test_upload_invalid_extension():
    content = b"malicious executable"
    response = client.post(
        "/api/files/upload",
        files={"file": ("bad.exe", io.BytesIO(content), "application/x-msdownload")}
    )
    assert response.status_code == 400
    assert "not supported" in response.json()["detail"]
