"""
Orchestrator for Sovereign AI Workbench.

Receives a user task, determines which agents to run (from a workflow
definition or automatic routing), executes them in dependency order,
and collects results. All processing is local.
"""

import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from agents.orchestrator.state import AgentContext, AgentResult, AgentTask
from agents.orchestrator.registry import get_agent

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Predefined workflows
# ---------------------------------------------------------------------------

DATA_ANALYSIS_WORKFLOW = [
    AgentTask(
        agent_name="data_analysis",
        instruction="Analyze the attached data files and produce "
                    "descriptive statistics, trends, and charts.",
        depends_on=[],
    ),
    AgentTask(
        agent_name="report",
        instruction="Generate a report from the data analysis results.",
        depends_on=["data_analysis"],
    ),
]

VISION_WORKFLOW = [
    AgentTask(
        agent_name="vision",
        instruction="Analyze the attached images or PDF pages.",
        depends_on=[],
    ),
    AgentTask(
        agent_name="report",
        instruction="Generate a report from the vision analysis results.",
        depends_on=["vision"],
    ),
]

OCR_WORKFLOW = [
    AgentTask(
        agent_name="ocr",
        instruction="Extract text from the attached document using local OCR.",
        depends_on=[],
    ),
]

OCR_RAG_REPORT_WORKFLOW = [
    AgentTask(
        agent_name="ocr",
        instruction="Extract text from the attached document.",
        depends_on=[],
    ),
    AgentTask(
        agent_name="rag",
        instruction="Index the extracted text and search for relevant context.",
        depends_on=["ocr"],
    ),
    AgentTask(
        agent_name="report",
        instruction="Generate a professional report from OCR and RAG results.",
        depends_on=["ocr", "rag"],
    ),
]

FULL_INSPECTION_WORKFLOW = [
    AgentTask(
        agent_name="ocr",
        instruction="Extract text from the inspection document.",
        depends_on=[],
    ),
    AgentTask(
        agent_name="rag",
        instruction="Search the knowledge base for relevant SOPs and standards.",
        depends_on=["ocr"],
    ),
    AgentTask(
        agent_name="report",
        instruction="Generate an approval note based on inspection findings "
                    "and relevant SOPs/standards.",
        depends_on=["ocr", "rag"],
    ),
]

VISION_REPORT_WORKFLOW = [
    AgentTask(
        agent_name="vision",
        instruction="Analyze the attached images for equipment, labels, anomalies.",
        depends_on=[],
    ),
    AgentTask(
        agent_name="report",
        instruction="Generate a report from the visual analysis findings.",
        depends_on=["vision"],
    ),
]

# Map of workflow names to their task lists
WORKFLOWS: dict[str, list[AgentTask]] = {
    "data_analysis": DATA_ANALYSIS_WORKFLOW,
    "vision": VISION_WORKFLOW,
    "vision_report": VISION_REPORT_WORKFLOW,
    "ocr": OCR_WORKFLOW,
    "ocr_rag_report": OCR_RAG_REPORT_WORKFLOW,
    "full_inspection": FULL_INSPECTION_WORKFLOW,
}


# ---------------------------------------------------------------------------
# Automatic workflow routing
# ---------------------------------------------------------------------------

# File extension categories
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp"}
DATA_EXTENSIONS = {".csv", ".xlsx", ".xls", ".json"}
DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".txt", ".pptx"}


def auto_route(user_request: str, files: list[str]) -> str:
    """
    Automatically select the best workflow based on user request and file types.

    Uses keyword + file-type heuristics for the prototype.
    """
    request_lower = user_request.lower()

    # Determine file types present
    file_exts = {Path(f).suffix.lower() for f in files if f}
    has_images = bool(file_exts & IMAGE_EXTENSIONS)
    has_data = bool(file_exts & DATA_EXTENSIONS)
    has_documents = bool(file_exts & DOCUMENT_EXTENSIONS)

    # Keyword-based routing
    data_keywords = ["analyze", "analysis", "csv", "data", "chart", "trend",
                     "statistic", "anomal", "reading", "equipment data", "excel"]
    vision_keywords = ["image", "photo", "picture", "visual", "inspect",
                       "equipment photo", "p&id", "diagram", "camera"]
    ocr_keywords = ["read", "extract", "ocr", "scan", "text from"]
    rag_keywords = ["compare", "sop", "standard", "knowledge", "internal",
                    "approval", "compliance", "regulation", "manual"]
    report_keywords = ["report", "approval note", "generate", "document",
                       "prepare", "create", "summarize", "summary"]

    has_data_intent = any(k in request_lower for k in data_keywords)
    has_vision_intent = any(k in request_lower for k in vision_keywords)
    has_ocr_intent = any(k in request_lower for k in ocr_keywords)
    has_rag_intent = any(k in request_lower for k in rag_keywords)
    has_report_intent = any(k in request_lower for k in report_keywords)

    # Decision logic
    if has_data and (has_data_intent or not has_documents):
        return "data_analysis"

    if has_images and has_vision_intent:
        if has_report_intent:
            return "vision_report"
        return "vision"

    if has_documents and has_rag_intent and has_report_intent:
        return "full_inspection"

    if has_documents and has_ocr_intent:
        if has_rag_intent or has_report_intent:
            return "ocr_rag_report"
        return "ocr"

    if has_documents:
        if has_report_intent or has_rag_intent:
            return "ocr_rag_report"
        return "ocr"

    if has_images:
        return "vision"

    # Default: OCR + RAG + Report for documents, or data_analysis for data
    if has_data:
        return "data_analysis"

    return "ocr_rag_report"


# ---------------------------------------------------------------------------
# WorkflowResult
# ---------------------------------------------------------------------------

class WorkflowResult:
    """Collects the outcome of an entire workflow execution."""

    def __init__(self, workflow_name: str):
        self.workflow_name = workflow_name
        self.status = "pending"
        self.steps: list[dict] = []
        self.results: dict[str, AgentResult] = {}
        self.artifacts: list[str] = []
        self.warnings: list[str] = []
        self.errors: list[str] = []
        self.duration_ms: float = 0

    def to_dict(self) -> dict:
        return {
            "workflow_name": self.workflow_name,
            "status": self.status,
            "steps": self.steps,
            "agent_results": {
                name: result.model_dump(mode="json")
                for name, result in self.results.items()
            },
            "artifacts": self.artifacts,
            "warnings": self.warnings,
            "errors": self.errors,
            "duration_ms": round(self.duration_ms, 1),
        }


# ---------------------------------------------------------------------------
# Topological sort
# ---------------------------------------------------------------------------

def _topological_sort(tasks: list[AgentTask]) -> list[AgentTask]:
    """Sort tasks so that dependencies come before dependents."""
    task_map = {task.agent_name: task for task in tasks}
    all_names = set(task_map.keys())

    for task in tasks:
        unknown = set(task.depends_on) - all_names
        if unknown:
            raise ValueError(
                f"Agent '{task.agent_name}' depends on unknown agents: "
                f"{sorted(unknown)}"
            )

    # Kahn's algorithm
    in_degree = {name: 0 for name in all_names}
    for task in tasks:
        for dep in task.depends_on:
            in_degree[task.agent_name] += 1

    queue = [name for name, degree in in_degree.items() if degree == 0]
    sorted_names: list[str] = []

    while queue:
        queue.sort()
        current = queue.pop(0)
        sorted_names.append(current)

        for task in tasks:
            if current in task.depends_on:
                in_degree[task.agent_name] -= 1
                if in_degree[task.agent_name] == 0:
                    queue.append(task.agent_name)

    if len(sorted_names) != len(all_names):
        remaining = all_names - set(sorted_names)
        raise ValueError(f"Circular dependency detected among: {sorted(remaining)}")

    return [task_map[name] for name in sorted_names]


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

class Orchestrator:
    """Executes workflows by running agents in dependency order."""

    def run(
        self,
        user_request: str,
        files: list[str] | None = None,
        workflow_name: str = "auto",
        tasks: list[AgentTask] | None = None,
    ) -> WorkflowResult:
        """Execute a workflow."""
        files = files or []
        start_time = time.monotonic()

        # Auto-route if needed
        if workflow_name == "auto":
            workflow_name = auto_route(user_request, files)
            logger.info("Auto-routed to workflow: %s", workflow_name)

        # Resolve workflow tasks
        if tasks is not None:
            workflow_tasks = tasks
            workflow_name = workflow_name or "custom"
        else:
            if workflow_name not in WORKFLOWS:
                raise ValueError(
                    f"Unknown workflow: '{workflow_name}'. "
                    f"Available: {sorted(WORKFLOWS.keys())}"
                )
            workflow_tasks = WORKFLOWS[workflow_name]

        result = WorkflowResult(workflow_name=workflow_name)

        logger.info(
            "WORKFLOW START — name: %s, agents: %s, files: %d",
            workflow_name,
            [t.agent_name for t in workflow_tasks],
            len(files),
        )

        try:
            sorted_tasks = _topological_sort(workflow_tasks)
        except ValueError as exc:
            logger.error("Workflow validation failed: %s", exc)
            result.status = "failed"
            result.errors.append(str(exc))
            result.duration_ms = (time.monotonic() - start_time) * 1000
            return result

        completed_results: dict[str, AgentResult] = {}
        has_failures = False

        for task in sorted_tasks:
            step_start = time.monotonic()
            step_info = {
                "agent": task.agent_name,
                "instruction": task.instruction,
                "depends_on": task.depends_on,
                "status": "pending",
                "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }

            logger.info("AGENT START — %s", task.agent_name)

            # Check dependencies
            missing_deps = [
                dep for dep in task.depends_on
                if dep not in completed_results
            ]

            if missing_deps:
                error_msg = (
                    f"Skipped '{task.agent_name}' — upstream agent(s) "
                    f"failed: {missing_deps}"
                )
                logger.warning("AGENT SKIPPED — %s: %s", task.agent_name, error_msg)

                agent_result = AgentResult(
                    agent_name=task.agent_name,
                    status="skipped",
                    summary=error_msg,
                    errors=[error_msg],
                )
                step_info["status"] = "skipped"
                step_info["error"] = error_msg
                has_failures = True

                result.results[task.agent_name] = agent_result
                result.errors.append(error_msg)
                result.steps.append(step_info)
                continue

            # Look up adapter
            try:
                adapter = get_agent(task.agent_name)
            except (KeyError, RuntimeError) as exc:
                error_msg = str(exc)
                logger.error("AGENT ERROR — %s: %s", task.agent_name, error_msg)

                agent_result = AgentResult(
                    agent_name=task.agent_name,
                    status="failed",
                    errors=[error_msg],
                )
                step_info["status"] = "failed"
                step_info["error"] = error_msg
                has_failures = True

                result.results[task.agent_name] = agent_result
                result.errors.append(error_msg)
                result.steps.append(step_info)
                continue

            if adapter is None:
                error_msg = (
                    f"Agent '{task.agent_name}' is registered as a "
                    "placeholder and not yet implemented."
                )
                logger.warning("AGENT SKIPPED — %s: placeholder", task.agent_name)

                agent_result = AgentResult(
                    agent_name=task.agent_name,
                    status="skipped",
                    summary=error_msg,
                    warnings=[error_msg],
                )
                step_info["status"] = "skipped"
                step_info["warning"] = error_msg
                has_failures = True

                result.results[task.agent_name] = agent_result
                result.warnings.append(error_msg)
                result.steps.append(step_info)
                continue

            # Build context
            context = AgentContext(
                task=task,
                user_request=user_request,
                files=files,
                dependencies={
                    dep: completed_results[dep]
                    for dep in task.depends_on
                    if dep in completed_results
                },
            )

            # Execute
            try:
                agent_result = adapter(context)

                if not agent_result.agent_name:
                    agent_result.agent_name = task.agent_name

                step_duration = (time.monotonic() - step_start) * 1000

                logger.info(
                    "AGENT COMPLETE — %s (%.0f ms, %d artifacts)",
                    task.agent_name,
                    step_duration,
                    len(agent_result.artifacts),
                )

                step_info["status"] = "completed"
                step_info["duration_ms"] = round(step_duration, 1)
                step_info["summary"] = agent_result.summary
                step_info["artifact_count"] = len(agent_result.artifacts)

                completed_results[task.agent_name] = agent_result
                result.results[task.agent_name] = agent_result
                result.artifacts.extend(agent_result.artifacts)
                result.warnings.extend(agent_result.warnings)

            except Exception as exc:
                step_duration = (time.monotonic() - step_start) * 1000
                error_msg = f"{type(exc).__name__}: {exc}"

                logger.error(
                    "AGENT ERROR — %s (%.0f ms): %s",
                    task.agent_name, step_duration, error_msg,
                )

                agent_result = AgentResult(
                    agent_name=task.agent_name,
                    status="failed",
                    summary=f"Agent failed: {error_msg}",
                    errors=[error_msg],
                )

                step_info["status"] = "failed"
                step_info["duration_ms"] = round(step_duration, 1)
                step_info["error"] = error_msg
                has_failures = True

                result.results[task.agent_name] = agent_result
                result.errors.append(f"[{task.agent_name}] {error_msg}")

            result.steps.append(step_info)

        # Final status
        total_duration = (time.monotonic() - start_time) * 1000
        result.duration_ms = total_duration

        if not has_failures:
            result.status = "completed"
        elif completed_results:
            result.status = "partial"
        else:
            result.status = "failed"

        logger.info(
            "WORKFLOW COMPLETE — %s, status: %s, duration: %.0f ms, "
            "agents: %d/%d completed",
            workflow_name, result.status, total_duration,
            len(completed_results), len(sorted_tasks),
        )

        return result
