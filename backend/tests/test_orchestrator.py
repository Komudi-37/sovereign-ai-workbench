from agents.orchestrator.orchestrator import Orchestrator, auto_route
from agents.orchestrator.registry import list_agents

def test_list_agents():
    agents = list_agents()
    assert "ocr" in agents
    assert "rag" in agents
    assert "vision" in agents
    assert "data_analysis" in agents
    assert "report" in agents

def test_auto_route_heuristics():
    assert auto_route("Analyze this equipment data", ["data.csv"]) == "data_analysis"
    assert auto_route("Inspect this photograph", ["pump.jpg"]) in ["vision", "vision_report"]
    assert auto_route("Read this inspection report and compare with SOP", ["report.pdf"]) in ["full_inspection", "ocr_rag_report"]

def test_orchestrator_execution(tmp_path):
    # Test OCR-only workflow
    test_doc = tmp_path / "doc.txt"
    test_doc.write_text("Sovereign AI Workbench Test Document", encoding="utf-8")
    
    orc = Orchestrator()
    res = orc.run(user_request="Read document", files=[str(test_doc)], workflow_name="ocr")
    assert res.status == "completed"
    assert "ocr" in res.results
