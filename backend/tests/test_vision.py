import pytest
from agents.vision.local_vision_model import LocalVisionModel
from agents.vision.image_analyzer import vision_adapter
from agents.orchestrator.state import AgentContext, AgentTask

def test_local_vision_model_no_cloud_dependency():
    # Verify local vision model does not have cloud openai dependency
    assert not hasattr(LocalVisionModel, "openai")
    assert hasattr(LocalVisionModel, "analyze")

def test_vision_adapter_non_image_handling(tmp_path):
    # Non-image file or missing model should return failed AgentResult gracefully without crashing
    doc_file = tmp_path / "text.txt"
    doc_file.write_text("not an image", encoding="utf-8")
    
    task = AgentTask(agent_name="vision", instruction="Inspect")
    context = AgentContext(task=task, files=[str(doc_file)])
    
    result = vision_adapter(context)
    assert result.status == "failed"
    assert len(result.errors) >= 1 or "unavailable" in result.summary.lower()
