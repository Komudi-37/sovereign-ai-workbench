from pathlib import Path
from agents.ocr.ocr_agent import OCRAgent, ocr_adapter
from agents.orchestrator.state import AgentContext, AgentTask

def test_ocr_agent_text_file(tmp_path):
    test_file = tmp_path / "sample_doc.txt"
    test_file.write_text("Equipment: Boiler B-101\nStatus: Operational\nInspection Passed.", encoding="utf-8")
    
    agent = OCRAgent()
    result = agent.process_file(str(test_file))
    
    assert "text" in result
    assert "Boiler B-101" in result["text"]
    assert len(result["pages"]) >= 1

def test_ocr_adapter_execution(tmp_path):
    test_file = tmp_path / "inspection.txt"
    test_file.write_text("Inspection Report: Normal operation observed.", encoding="utf-8")
    
    task = AgentTask(agent_name="ocr", instruction="Extract text")
    context = AgentContext(task=task, files=[str(test_file)])
    
    agent_result = ocr_adapter(context)
    assert agent_result.status == "completed"
    assert "Normal operation observed" in agent_result.data["text"]
