from agents.report.report_agent import report_adapter
from agents.orchestrator.state import AgentContext, AgentTask, AgentResult

def test_report_adapter_with_upstream_dependency():
    task = AgentTask(agent_name="report", instruction="Create inspection summary report", depends_on=["ocr"])
    upstream_ocr = AgentResult(
        agent_name="ocr",
        status="completed",
        summary="Extracted text from inspection report",
        data={"text": "Inspection Report: All pumps operational. No leakages detected."}
    )
    context = AgentContext(
        task=task,
        dependencies={"ocr": upstream_ocr}
    )
    
    result = report_adapter(context)
    assert result.status == "completed"
    assert len(result.artifacts) >= 1
    # Check generated files include .docx
    assert any(a.endswith(".docx") for a in result.artifacts)
