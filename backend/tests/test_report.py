import json
from pathlib import Path
import pytest
from openpyxl import load_workbook
from pptx import Presentation
from PIL import Image

from agents.orchestrator.planner import TaskPlanner
from agents.orchestrator.state import AgentContext, AgentResult, AgentTask
from agents.report.excel_generator import generate_excel, _safe_cell
from agents.report.ppt_generator import generate_ppt
from agents.report.report_agent import ReportAgent, ReportSpec, ReportSection, ReportTable, Figure, report_adapter


def _create_sample_report_payload(tmp_path) -> tuple[dict, str]:
    """Helper to create a rich report payload with statistics, trends, anomalies, and a figure."""
    img_path = tmp_path / "chart.png"
    img = Image.new("RGB", (300, 200), color=(50, 100, 150))
    img.save(img_path)

    payload = {
        "title": "Facility Vibration & Thermal Assessment",
        "subtitle": "Quarterly Operational Review",
        "prepared_by": "Reliability Engineering",
        "generated_at": "2025-06-01T10:00:00Z",
        "summary": "Comprehensive analysis of Pump-101 telemetry and oil analysis records. Deviation noted in vibration peak.",
        "approval_note": True,
        "decision_requested": "Approve updated lubrication schedule and replace bearing assembly.",
        "sections": [
            {
                "heading": "Quantitative Analysis",
                "paragraphs": ["Data recorded from 10 sensors over 90 operational days."],
                "tables": [
                    {
                        "title": "Descriptive Statistics",
                        "columns": ["dataset", "column", "count", "missing", "mean", "std", "min", "q25", "median", "q75", "max"],
                        "rows": [
                            ["Telemetry", "vibration_rms", 1440, 0, 3.42, 0.81, 1.20, 2.80, 3.35, 4.10, 6.85],
                            ["Telemetry", "bearing_temp", 1440, 0, 68.5, 5.2, 52.0, 64.0, 68.0, 72.5, 88.0],
                        ],
                        "note": "Descriptive statistics computed via IQR and z-score verification.",
                    },
                    {
                        "title": "Trend Analysis",
                        "columns": ["metric", "direction", "slope", "r2", "first_value", "last_value", "notes"],
                        "rows": [
                            ["vibration_rms", "INCREASING", 0.0412, 0.8845, 1.85, 6.20, "Steep rise observed past day 60"],
                            ["bearing_temp", "STABLE", 0.0015, 0.1200, 67.0, 69.2, "Normal fluctuations"],
                        ],
                        "note": "Calculated via ordinary least squares regression.",
                    },
                    {
                        "title": "Detected Statistical Anomalies (IQR Outliers)",
                        "columns": ["column", "row", "value", "bound", "threshold", "equipment_context", "note"],
                        "rows": [
                            ["vibration_rms", 1120, 6.85, "upper", 5.45, "Pump-101", "Vibration surge during peak load"],
                            ["bearing_temp", 1342, 88.0, "upper", 82.0, "Pump-101", "Thermal excursion"],
                        ],
                        "note": "Flagged with 1.5*IQR threshold.",
                    },
                    {
                        "title": "Data Preview",
                        "columns": ["timestamp", "vibration_rms", "bearing_temp"],
                        "rows": [
                            ["2025-06-01 00:00", 2.1, 65.0],
                            ["2025-06-01 01:00", 2.3, 65.4],
                        ],
                        "note": "First 2 records preview.",
                    },
                ],
                "figures": [
                    {
                        "path": str(img_path),
                        "caption": "Vibration Trend (RMS mm/s) over Time",
                    }
                ],
            }
        ],
        "sources": ["SOP-MAINT-001 (Rev 3)", "Telemetry_Log_Q2.csv", "Inspection_Report_Pump101.pdf"],
        "warnings": ["Sensor #4 had brief calibration drift on 2025-05-14."],
    }
    return payload, str(img_path)


def test_generate_excel_multi_sheet_structure(tmp_path):
    """Verify Excel generator produces canonical sheets, frozen panes, and auto-filters."""
    payload, _ = _create_sample_report_payload(tmp_path)
    out_xlsx = tmp_path / "facility_report.xlsx"

    res = generate_excel(payload, out_xlsx)
    assert Path(res["path"]).is_file()

    wb = load_workbook(out_xlsx)
    sheet_names = wb.sheetnames

    # Verify canonical sheet names
    assert "Summary" in sheet_names
    assert "Statistics" in sheet_names
    assert "Trends" in sheet_names
    assert "Anomalies" in sheet_names
    assert "Data Preview" in sheet_names
    assert "Figures" in sheet_names
    assert "References" in sheet_names

    # Sheet 1: Summary validation
    summary_ws = wb["Summary"]
    assert summary_ws["A1"].value == "REPORT SUMMARY & OVERVIEW"
    assert summary_ws.freeze_panes == "B2"

    # Sheet 2: Statistics validation
    stats_ws = wb["Statistics"]
    assert stats_ws.freeze_panes == "A2"
    assert stats_ws.auto_filter.ref is not None
    assert stats_ws["A1"].value == "dataset"
    assert stats_ws["B1"].value == "column"

    # Sheet 3: Trends validation
    trends_ws = wb["Trends"]
    assert trends_ws.freeze_panes == "A2"
    assert trends_ws["A1"].value == "metric"
    assert trends_ws["B1"].value == "direction"

    # Sheet 4: Anomalies validation
    anom_ws = wb["Anomalies"]
    assert anom_ws.freeze_panes == "A2"
    assert anom_ws["A1"].value == "column"
    assert anom_ws["D1"].value == "bound"


def test_generate_excel_numeric_cell_formatting(tmp_path):
    """Verify numbers in XLSX are written as true numeric types with number formats."""
    payload, _ = _create_sample_report_payload(tmp_path)
    out_xlsx = tmp_path / "numbers_report.xlsx"

    generate_excel(payload, out_xlsx)
    wb = load_workbook(out_xlsx)
    stats_ws = wb["Statistics"]

    # Row 2 is the first data row
    # Column 3 is count (1440) -> integer
    cell_count = stats_ws.cell(row=2, column=3)
    assert isinstance(cell_count.value, (int, float))
    assert cell_count.value == 1440

    # Column 5 is mean (3.42) -> float
    cell_mean = stats_ws.cell(row=2, column=5)
    assert isinstance(cell_mean.value, float)
    assert abs(cell_mean.value - 3.42) < 1e-4
    assert cell_mean.number_format == "0.00"

    # Trends sheet slope / r2
    trends_ws = wb["Trends"]
    cell_slope = trends_ws.cell(row=2, column=3)
    assert isinstance(cell_slope.value, float)
    assert cell_slope.number_format == "0.0000"


def test_generate_excel_formula_injection_protection():
    """Verify formula injection characters are escaped while numbers are preserved."""
    # Pure numbers should parse as numbers
    assert _safe_cell("42") == 42
    assert _safe_cell("-1.5") == -1.5
    assert _safe_cell(3.14) == 3.14
    assert _safe_cell(100) == 100

    # Leading-zero ID codes should remain intact as strings
    assert _safe_cell("007") == "007"
    assert _safe_cell("0123") == "0123"

    # Formula injection strings must be escaped with a quote
    assert _safe_cell("=1+1") == "'=1+1"
    assert _safe_cell("+cmd|' /C calc'!A0") == "'+cmd|' /C calc'!A0"
    assert _safe_cell("-SUM(A1:A10)") == "'-SUM(A1:A10)"
    assert _safe_cell("@IMPORTDATA('http://malicious')") == "'@IMPORTDATA('http://malicious')"

    # Regular text remains regular text
    assert _safe_cell("Pump-101") == "Pump-101"
    assert _safe_cell("Normal vibration") == "Normal vibration"


def test_generate_pptx_widescreen_and_slides(tmp_path):
    """Verify PPTX generator produces 16:9 widescreen presentation with the 8 structured slides."""
    payload, _ = _create_sample_report_payload(tmp_path)
    out_pptx = tmp_path / "executive_presentation.pptx"

    res = generate_ppt(payload, out_pptx)
    assert Path(res["path"]).is_file()

    prs = Presentation(out_pptx)
    # Check 16:9 widescreen dimensions (13.333" x 7.5")
    assert abs(prs.slide_width.inches - 13.333) < 0.01
    assert abs(prs.slide_height.inches - 7.5) < 0.01

    # Should have at least 8 slides (Title, Summary, Scope, Statistics, Trends, Anomalies, Figures, Recommendations)
    assert len(prs.slides) >= 8

    # Verify native tables exist on Statistics, Trends, and Anomalies slides
    found_tables = 0
    for slide in prs.slides:
        for shape in slide.shapes:
            if shape.has_table:
                found_tables += 1
    assert found_tables >= 2  # Statistics and Trends/Anomalies tables


def test_report_agent_full_deliverables_integration(tmp_path):
    """Verify ReportAgent can generate all formats (docx, pdf, xlsx, pptx) with a valid manifest."""
    payload, img_path = _create_sample_report_payload(tmp_path)
    
    agent = ReportAgent(
        output_directory=str(tmp_path / "reports"),
        allowed_image_roots=[tmp_path, "outputs", "data", "demo_data", "workspaces"]
    )
    
    spec = ReportSpec.model_validate(payload)
    formats = ["docx", "pdf", "xlsx", "pptx", "approval_note"]
    
    manifest = agent.generate(spec, formats)
    assert manifest["status"] == "completed"
    assert len(manifest["generated_files"]) >= 4
    
    # Verify all target extensions were produced
    generated_exts = {Path(f).suffix.lower() for f in manifest["generated_files"]}
    assert ".docx" in generated_exts
    assert ".pdf" in generated_exts
    assert ".xlsx" in generated_exts
    assert ".pptx" in generated_exts
    
    assert Path(manifest["manifest_path"]).is_file()
    assert len(manifest["failures"]) == 0


def test_report_agent_security_image_confinement(tmp_path):
    """Verify ReportAgent rejects images outside of allowed roots."""
    outside_dir = tmp_path / "untrusted_zone"
    outside_dir.mkdir()
    bad_img = outside_dir / "unauthorized.png"
    Image.new("RGB", (100, 100)).save(bad_img)

    agent = ReportAgent(
        output_directory=str(tmp_path / "out"),
        allowed_image_roots=[tmp_path / "safe_zone"]
    )

    spec = ReportSpec(
        title="Restricted Test",
        sections=[
            ReportSection(
                heading="Sec",
                figures=[Figure(path=str(bad_img), caption="Bad")]
            )
        ]
    )

    with pytest.raises(ValueError, match="outside allowed image directories"):
        agent.generate(spec, ["docx"])


def test_report_adapter_format_detection(tmp_path):
    """Verify report_adapter detects xlsx, pptx, presentation, excel, all formats correctly."""
    upstream_ocr = AgentResult(
        agent_name="ocr",
        status="completed",
        summary="Extracted findings",
        data={"text": "All mechanical checks passed."}
    )

    # Test 1: Excel request
    task_excel = AgentTask(agent_name="report", instruction="Create an Excel spreadsheet deliverable")
    ctx_excel = AgentContext(task=task_excel, dependencies={"ocr": upstream_ocr}, user_request="Export to xlsx")
    res_excel = report_adapter(ctx_excel)
    assert res_excel.status == "completed"
    assert any(a.endswith(".xlsx") for a in res_excel.artifacts)

    # Test 2: PowerPoint / Presentation request
    task_ppt = AgentTask(agent_name="report", instruction="Prepare an executive PowerPoint presentation")
    ctx_ppt = AgentContext(task=task_ppt, dependencies={"ocr": upstream_ocr}, user_request="Generate slides deck")
    res_ppt = report_adapter(ctx_ppt)
    assert res_ppt.status == "completed"
    assert any(a.endswith(".pptx") for a in res_ppt.artifacts)

    # Test 3: Complete report / all formats
    task_all = AgentTask(agent_name="report", instruction="Provide complete report in all formats")
    ctx_all = AgentContext(task=task_all, dependencies={"ocr": upstream_ocr}, user_request="Generate complete deliverables")
    res_all = report_adapter(ctx_all)
    assert res_all.status == "completed"
    assert any(a.endswith(".xlsx") for a in res_all.artifacts)
    assert any(a.endswith(".pptx") for a in res_all.artifacts)
    assert any(a.endswith(".docx") for a in res_all.artifacts)


def test_planner_routing_to_data_analysis_and_presentation():
    """Verify TaskPlanner plans data_analysis and report when user requests presentation or excel."""
    planner = TaskPlanner()

    # Excel deliverable request with CSV
    plan1 = planner.plan(
        user_request="Analyze telemetry and generate an Excel workbook",
        files=["telemetry.csv"]
    )
    assert plan1.planned_agents == ["data_analysis", "report"]
    assert any(t.agent_name == "report" for t in plan1.tasks)

    # PowerPoint request with data
    plan2 = planner.plan(
        user_request="Create a PowerPoint presentation summarizing sensor trends",
        files=["sensor_log.xlsx"]
    )
    assert plan2.planned_agents == ["data_analysis", "report"]
    assert any(t.agent_name == "report" for t in plan2.tasks)
