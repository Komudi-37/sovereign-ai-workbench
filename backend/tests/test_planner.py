"""
Tests for Intelligent Task Planner and Dynamic Agent Routing in Sovereign AI Workbench.
"""

from pathlib import Path
import pytest

from agents.orchestrator.planner import TaskPlanner, task_planner
from agents.orchestrator.orchestrator import Orchestrator


def test_inspection_intent_detection():
    """Verify inspection request with approval note generates OCR -> RAG -> REPORT plan."""
    planner = TaskPlanner()
    plan = planner.plan(
        user_request="Analyze the uploaded inspection report and generate an approval note.",
        files=["inspection_report.pdf"],
    )
    assert plan.intent == "INSPECTION"
    assert plan.confidence >= 0.85
    assert plan.planned_agents == ["ocr", "rag", "report"]
    assert len(plan.tasks) == 3
    assert plan.tasks[0].agent_name == "ocr"
    assert plan.tasks[1].agent_name == "rag"
    assert plan.tasks[2].agent_name == "report"
    assert plan.workflow_name == "full_inspection"


def test_coding_intent_detection():
    """Verify calculation/python requests generate CODING -> SANDBOX plan."""
    planner = TaskPlanner()
    plan = planner.plan(
        user_request="Calculate the average of these values using Python: 4.2, 4.5, 4.1, 5.0.",
        files=[],
    )
    assert plan.intent == "CODING"
    assert plan.confidence >= 0.90
    assert plan.planned_agents == ["coding"]
    assert len(plan.tasks) == 1
    assert plan.tasks[0].agent_name == "coding"
    assert plan.workflow_name == "coding"


def test_data_analysis_intent_detection():
    """Verify CSV dataset analysis request generates DATA_ANALYSIS -> REPORT plan."""
    planner = TaskPlanner()
    plan = planner.plan(
        user_request="Analyze this CSV and identify unusual trends.",
        files=["telemetry_data.csv"],
    )
    assert plan.intent == "DATA_ANALYSIS"
    assert plan.confidence >= 0.85
    assert "data_analysis" in plan.planned_agents
    assert plan.tasks[0].agent_name == "data_analysis"


def test_vision_intent_detection():
    """Verify image / diagram inspection generates VISION plan."""
    planner = TaskPlanner()
    plan = planner.plan(
        user_request="Inspect this engineering drawing for anomalies.",
        files=["pump_p_and_id.png"],
    )
    assert plan.intent == "VISION"
    assert plan.confidence >= 0.85
    assert "vision" in plan.planned_agents
    assert plan.tasks[0].agent_name == "vision"


def test_knowledge_search_intent_detection():
    """Verify SOP question without attachments routes to RAG search."""
    planner = TaskPlanner()
    plan = planner.plan(
        user_request="What does the local SOP say about centrifugal pump bearing failure?",
        files=[],
    )
    assert plan.intent == "KNOWLEDGE_SEARCH"
    assert plan.confidence >= 0.90
    assert plan.planned_agents == ["rag"]
    assert plan.tasks[0].agent_name == "rag"


def test_document_ocr_intent_detection():
    """Verify pure text extraction request routes to OCR."""
    planner = TaskPlanner()
    plan = planner.plan(
        user_request="Extract text from this document.",
        files=["scanned_log.pdf"],
    )
    assert plan.intent == "DOCUMENT"
    assert plan.planned_agents == ["ocr"]


def test_file_aware_routing():
    """Verify file extensions influence plan construction."""
    planner = TaskPlanner()

    # CSV file
    p_csv = planner.plan("Review these numbers", files=["sensor_metrics.csv"])
    assert p_csv.intent == "DATA_ANALYSIS"

    # Image file
    p_img = planner.plan("Check this", files=["pump_photo.jpg"])
    assert p_img.intent == "VISION"

    # Python script
    p_code = planner.plan("Run this script", files=["calc_pressure.py"])
    assert p_code.intent == "CODING"


def test_confidence_and_explainable_reasoning():
    """Verify every plan has a valid confidence score and plain-English explanation."""
    planner = TaskPlanner()
    plan = planner.plan("Calculate pressure drop using Python formula")
    assert 0.0 <= plan.confidence <= 1.0
    assert len(plan.explanation) > 10
    assert "signals" in plan.model_dump() or "detected_signals" in plan.model_dump()


def test_named_workflow_backward_compatibility():
    """Verify explicit workflow names (e.g. full_inspection, coding) are respected."""
    planner = TaskPlanner()
    plan = planner.plan(
        user_request="Run the full inspection",
        files=["inspection.pdf"],
        requested_workflow="full_inspection",
    )
    assert plan.confidence == 1.0
    assert plan.workflow_name == "full_inspection"
    assert plan.planned_agents == ["ocr", "rag", "report"]


def test_orchestrator_execution_with_planner(tmp_path):
    """Verify Orchestrator.run integrates TaskPlanner seamlessly."""
    test_doc = tmp_path / "inspection.txt"
    test_doc.write_text("Compressor C-101 bearing temperature exceeds threshold.", encoding="utf-8")

    orc = Orchestrator()
    res = orc.run(
        user_request="Analyze the uploaded inspection report and generate an approval note.",
        files=[str(test_doc)],
        workflow_name="auto",
    )
    assert res.status == "completed"
    assert res.execution_plan is not None
    assert res.execution_plan["intent"] == "INSPECTION"
    assert "ocr" in res.results


def test_knowledge_search_negative_report_constraints():
    """Verify that requests containing negative clauses like 'do not generate a report' route to RAG search only."""
    planner = TaskPlanner()
    query = (
        "What are the vibration velocity thresholds specified in the available SOP for ISO 10816?\n\n"
        "Give me the applicable limits for each condition and cite the exact source document and section.\n"
        "Do not generate a report or approval note. Just answer the question using the local knowledge base."
    )
    plan = planner.plan(user_request=query, files=[])
    assert plan.intent == "KNOWLEDGE_SEARCH"
    assert plan.planned_agents == ["rag"]
    assert plan.workflow_name == "rag_search"
    assert "report" not in plan.planned_agents
    assert "ocr" not in plan.planned_agents


def test_regression_case_a_telemetry_data_analysis_routing():
    """Test A: The exact user prompt + equipment_readings.csv -> DATA_ANALYSIS -> ['data_analysis', 'report']."""
    planner = TaskPlanner()
    prompt = (
        "Analyze the uploaded equipment telemetry dataset. Calculate the key statistics, "
        "identify abnormal readings, detect important trends, and highlight any equipment risks. "
        "Create a management-ready analysis report with charts and recommendations."
    )
    plan = planner.plan(user_request=prompt, files=["equipment_readings.csv"])
    assert plan.intent == "DATA_ANALYSIS"
    assert plan.planned_agents == ["data_analysis", "report"]
    assert plan.workflow_name == "data_analysis"
    assert plan.tasks[0].agent_name == "data_analysis"
    assert plan.tasks[1].agent_name == "report"


def test_regression_case_b_explicit_python_code_on_csv():
    """Test B: 'Write Python code to analyze this CSV and execute it.' -> CODING."""
    planner = TaskPlanner()
    prompt = "Write Python code to analyze this CSV and execute it."
    plan = planner.plan(user_request=prompt, files=["telemetry.csv"])
    assert plan.intent == "CODING"
    assert plan.workflow_name == "coding"
    assert "coding" in plan.planned_agents
    assert plan.tasks[0].agent_name == "coding"


def test_regression_case_c_analyze_csv_excel_report():
    """Test C: 'Analyze this CSV and create an Excel report.' -> DATA_ANALYSIS -> ['data_analysis', 'report']."""
    planner = TaskPlanner()
    prompt = "Analyze this CSV and create an Excel report."
    plan = planner.plan(user_request=prompt, files=["telemetry.csv"])
    assert plan.intent == "DATA_ANALYSIS"
    assert plan.planned_agents == ["data_analysis", "report"]
    assert plan.workflow_name == "data_analysis"


def test_regression_case_d_debug_python_script():
    """Test D: 'Debug this Python script.' + files=['script.py'] -> CODING."""
    planner = TaskPlanner()
    prompt = "Debug this Python script."
    plan = planner.plan(user_request=prompt, files=["script.py"])
    assert plan.intent == "CODING"
    assert plan.workflow_name == "coding"
    assert plan.planned_agents == ["coding"]
    assert plan.tasks[0].agent_name == "coding"


