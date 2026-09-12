"""
Comprehensive tests for Feature 5: Advanced Local Vision Preprocessing & Vision Agent.
"""

import io
from pathlib import Path
import pytest
from PIL import Image
import fitz

from agents.vision.image_preprocessor import (
    ImagePreprocessor,
    PreprocessorConfig,
    PreprocessingError,
    preprocessor,
)
from agents.vision.local_vision_model import LocalVisionModel
from agents.vision.vision_model import SourceReference
from agents.vision.image_analyzer import vision_adapter
from agents.orchestrator.state import AgentContext, AgentTask
from agents.orchestrator.planner import TaskPlanner
from app.services.network_monitor import network_monitor
from app.services.workspace import workspace_manager


@pytest.fixture
def sample_png(tmp_path):
    img_path = tmp_path / "equipment.png"
    img = Image.new("RGBA", (800, 600), color=(100, 150, 200, 255))
    img.save(img_path, format="PNG")
    return img_path


@pytest.fixture
def sample_jpg(tmp_path):
    img_path = tmp_path / "valve.jpg"
    img = Image.new("RGB", (640, 480), color=(200, 100, 50))
    img.save(img_path, format="JPEG")
    return img_path


@pytest.fixture
def sample_multipage_pdf(tmp_path):
    pdf_path = tmp_path / "pid_drawings.pdf"
    doc = fitz.open()
    for page_idx in range(3):
        page = doc.new_page(width=612, height=792)
        page.draw_rect(fitz.Rect(50, 50, 500, 700), color=(0, 0, 0), width=2)
        page.insert_text((100, 100), f"P&ID Drawing Page {page_idx + 1} Tag: P-10{page_idx + 1}")
    doc.save(str(pdf_path))
    doc.close()
    return pdf_path


def test_png_preprocessing(sample_png):
    """1. Test PNG preprocessing with transparency normalization."""
    visuals = preprocessor.process_raster_file(sample_png)
    assert len(visuals) == 1
    v = visuals[0]
    assert v.source_filename == "equipment.png"
    assert v.width == 800
    assert v.height == 600
    assert v.format == "JPEG"
    assert len(v.image_bytes) > 0


def test_jpg_preprocessing(sample_jpg):
    """2. Test standard JPG preprocessing."""
    visuals = preprocessor.process_raster_file(sample_jpg)
    assert len(visuals) == 1
    v = visuals[0]
    assert v.source_filename == "valve.jpg"
    assert v.width == 640
    assert v.height == 480
    assert not v.was_resized


def test_oversized_image_resizing(tmp_path):
    """3. Test safe resizing for oversized images preserving aspect ratio."""
    huge_path = tmp_path / "huge_drawing.png"
    # Create an image larger than default max_image_side (2048)
    huge_img = Image.new("RGB", (3000, 1500), color=(255, 255, 255))
    huge_img.save(huge_path, format="PNG")

    cfg = PreprocessorConfig(max_image_side=1600)
    p = ImagePreprocessor(config=cfg)
    visuals = p.process_raster_file(huge_path)

    assert len(visuals) == 1
    v = visuals[0]
    assert v.was_resized is True
    assert v.width == 1600
    assert v.height == 800  # Preserved 2:1 aspect ratio
    assert any("downscaled" in w.lower() for w in v.warnings)


def test_invalid_image_rejection(tmp_path):
    """4. Test rejection of non-image and corrupt files."""
    bad_file = tmp_path / "corrupt.png"
    bad_file.write_bytes(b"not an actual image file content")

    with pytest.raises(PreprocessingError):
        preprocessor.process_raster_file(bad_file)


def test_pdf_page_rendering(sample_multipage_pdf):
    """5. Test local PDF page rendering via PyMuPDF."""
    visuals = preprocessor.process_pdf_file(sample_multipage_pdf, dpi=100)
    assert len(visuals) == 3
    assert visuals[0].page_number == 1
    assert visuals[1].page_number == 2
    assert visuals[2].page_number == 3
    assert visuals[0].metadata["rendered_dpi"] == 100


def test_pdf_page_selection(sample_multipage_pdf):
    """6. Test selecting specific PDF pages."""
    visuals = preprocessor.process_pdf_file(sample_multipage_pdf, pages=[2])
    assert len(visuals) == 1
    assert visuals[0].page_number == 2


def test_multi_page_limit_enforcement(sample_multipage_pdf):
    """7. Test multi-page limit cap."""
    cfg = PreprocessorConfig(max_pdf_pages=2)
    p = ImagePreprocessor(config=cfg)
    visuals = p.process_pdf_file(sample_multipage_pdf)
    assert len(visuals) == 2


def test_temporary_workspace_isolation_and_cleanup(tmp_path, sample_multipage_pdf):
    """8 & 9. Test temporary workspace creation and cleanup."""
    run_ws = workspace_manager.create_run_workspace()
    temp_dir = run_ws["temp"]
    assert temp_dir.exists()

    visuals = preprocessor.process_file_in_workspace(sample_multipage_pdf, run_workspace=run_ws)
    assert len(visuals) == 3

    # Cleanup temp
    workspace_manager.cleanup_run_temp(run_ws)
    assert not temp_dir.exists()


def test_structured_vision_output(monkeypatch, sample_jpg):
    """10. Test structured findings parsing from vision model."""
    mock_response = {
        "description": "Visible centrifugal pump assembly with suction and discharge flanges.",
        "detected_text": "TAG: P-101A",
        "objects": ["centrifugal pump", "gate valve", "pressure gauge"],
        "findings": [
            {"type": "equipment", "label": "Centrifugal Pump P-101A", "confidence": 0.92},
            {"type": "valve", "label": "Suction Gate Valve", "confidence": 0.88}
        ],
        "warnings": ["Slight motion blur near impeller casing"],
        "confidence": "high"
    }

    # Mock analyze call
    def mock_analyze(self, *, image_bytes, source, request, reference_context=""):
        return {
            "description": mock_response["description"],
            "detected_text": mock_response["detected_text"],
            "objects": mock_response["objects"],
            "findings": mock_response["findings"],
            "warnings": mock_response["warnings"],
            "confidence": mock_response["confidence"],
            "source_id": source.source_id,
            "file_name": source.file_name,
            "page_number": getattr(source, "page_number", None),
        }

    monkeypatch.setattr(LocalVisionModel, "analyze", mock_analyze)
    monkeypatch.setattr(LocalVisionModel, "_check_model_availability", lambda self: None)

    task = AgentTask(agent_name="vision", instruction="Inspect pump image")
    ctx = AgentContext(task=task, files=[str(sample_jpg)], user_request="Identify components in pump")

    result = vision_adapter(ctx)
    assert result.status == "completed"
    assert "results" in result.data
    first_res = result.data["results"][0]
    assert first_res["confidence"] == "high"
    assert len(first_res["findings"]) == 2
    assert first_res["findings"][0]["label"] == "Centrifugal Pump P-101A"


def test_unavailable_local_vision_model(monkeypatch, sample_jpg):
    """11 & 12. Test graceful failure and zero cloud fallback when model unavailable."""
    def mock_init_fail(self):
        raise RuntimeError("Vision model 'llava:7b' is not available in Ollama.")

    monkeypatch.setattr(LocalVisionModel, "__init__", mock_init_fail)

    task = AgentTask(agent_name="vision", instruction="Inspect")
    ctx = AgentContext(task=task, files=[str(sample_jpg)])

    result = vision_adapter(ctx)
    assert result.status == "failed"
    assert "unavailable" in result.summary.lower()
    # Confirm no cloud call was made
    summary = network_monitor.get_summary()
    assert summary["external_calls_attempted"] == 0


def test_network_monitor_records_local_vision_call(monkeypatch, sample_jpg):
    """13. Test network monitor records local 127.0.0.1 call for Vision."""
    init_local_calls = network_monitor.get_summary()["local_calls"]

    def mock_http_post(self, url, **kwargs):
        class MockResp:
            def raise_for_status(self):
                pass
            def json(self):
                return {
                    "response": '{"description": "ok", "objects": [], "findings": [], "warnings": [], "confidence": "medium"}'
                }
        return MockResp()

    import httpx
    monkeypatch.setattr(httpx.Client, "post", mock_http_post)
    monkeypatch.setattr(LocalVisionModel, "_check_model_availability", lambda self: None)

    task = AgentTask(agent_name="vision", instruction="Inspect")
    ctx = AgentContext(task=task, files=[str(sample_jpg)])

    vision_adapter(ctx)

    new_local_calls = network_monitor.get_summary()["local_calls"]
    assert new_local_calls > init_local_calls


def test_planner_vision_routing(sample_png, sample_multipage_pdf):
    """14. Test Planner dynamic routing for visual requests."""
    planner = TaskPlanner()

    # Image request
    plan = planner.plan(
        user_request="Inspect this equipment photograph and check for tag markings",
        files=[str(sample_png)],
    )
    assert plan.intent == "VISION"
    assert "vision" in plan.planned_agents

    # P&ID drawing PDF request
    plan_pid = planner.plan(
        user_request="Analyze this P&ID diagram drawing for pump connections",
        files=[str(sample_multipage_pdf)],
    )
    assert plan_pid.intent == "VISION"
    assert "vision" in plan_pid.planned_agents
