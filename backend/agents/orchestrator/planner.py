"""
Intelligent Task Planner and Dynamic Agent Router for Sovereign AI Workbench.

Features:
- Deterministic and rule-based local planning (ZERO external/cloud LLM calls)
- File-type and intent-aware routing
- Structured multi-agent plan generation with dependencies
- Confidence scoring and explainable reasoning
- Full backward-compatibility with predefined named workflows
"""

import logging
import re
from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field

from agents.orchestrator.state import AgentTask

logger = logging.getLogger(__name__)

# File extension categories
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp"}
DATA_EXTENSIONS = {".csv", ".xlsx", ".xls", ".json"}
DOCUMENT_EXTENSIONS = {".pdf", ".docx", ".txt", ".pptx"}
CODE_EXTENSIONS = {".py", ".sh", ".sql", ".js"}

# Intent Keyword Sets
INTENT_KEYWORDS = {
    "INSPECTION": [
        "inspection", "inspect report", "approval note", "sop guidance",
        "corrective action", "maintenance inspection", "finding", "audit",
        "compliance", "formal approval", "work order approval"
    ],
    "DATA_ANALYSIS": [
        "analyze", "analysis", "csv", "excel", "dataset", "dataframe",
        "statistics", "statistical", "trend", "trends", "reading", "readings", "sensor data",
        "vibration reading", "telemetry", "descriptive statistics", "plot data",
        "abnormal", "anomaly", "anomalies", "equipment risk", "risk", "charts",
        "recommendations", "equipment data"
    ],
    "VISION": [
        "image", "photo", "picture", "visual", "p&id", "pid", "diagram",
        "camera", "drawing", "engineering drawing", "equipment photo", "inspect photograph"
    ],
    "CODING": [
        "python", "calculate", "script", "code", "sandbox", "formula",
        "compute", "computation", "algorithm", "repair code", "math",
        "write a script", "write code", "pressure drop"
    ],
    "KNOWLEDGE_SEARCH": [
        "sop", "standard", "procedure", "knowledge base", "internal documentation",
        "manual", "regulation", "maintenance procedure", "bearing failure",
        "what does the sop say", "what does the procedure say", "how to maintain"
    ],
    "DOCUMENT": [
        "ocr", "extract text", "read this document", "read this pdf",
        "scan", "text from", "parse document"
    ],
    "REPORT_GENERATION": [
        "report", "generate report", "create report", "approval note",
        "summary", "summarize", "docx", "pdf artifact", "generate document",
        "excel", "xlsx", "powerpoint", "pptx", "presentation", "slides", "slide deck",
        "spreadsheet", "workbook"
    ],
}


class PlannedTask(BaseModel):
    """A task step in a generated plan."""
    agent: str
    instruction: str
    depends_on: list[str] = Field(default_factory=list)


class ExecutionPlan(BaseModel):
    """Structured output from the Task Planner."""
    intent: str
    confidence: float
    explanation: str
    detected_signals: dict[str, Any] = Field(default_factory=dict)
    planned_agents: list[str] = Field(default_factory=list)
    tasks: list[AgentTask] = Field(default_factory=list)
    workflow_name: str = "custom"


class TaskPlanner:
    """
    Intelligent planner that analyzes requests, files, and intents
    to construct optimal multi-agent execution plans.
    """

    def plan(
        self,
        user_request: str,
        files: list[str] | None = None,
        requested_workflow: str | None = None,
    ) -> ExecutionPlan:
        """
        Produce a structured ExecutionPlan for the request.
        """
        files = files or []
        req_lower = user_request.lower()

        # Check file extensions
        file_exts = {Path(f).suffix.lower() for f in files if f}
        has_images = bool(file_exts & IMAGE_EXTENSIONS)
        has_data = bool(file_exts & DATA_EXTENSIONS)
        has_docs = bool(file_exts & DOCUMENT_EXTENSIONS)
        has_code = bool(file_exts & CODE_EXTENSIONS)

        detected_signals = {
            "file_count": len(files),
            "file_types": list(file_exts),
            "has_images": has_images,
            "has_data": has_data,
            "has_documents": has_docs,
            "has_code": has_code,
        }

        # If user explicitly requested a named workflow, build plan honoring it
        if requested_workflow and requested_workflow not in ["auto", "custom", ""]:
            return self._plan_for_named_workflow(requested_workflow, user_request, detected_signals)

        # Check for explicit negative constraints against report / approval note generation
        # e.g. "Do not generate a report or approval note", "no report", "without approval note"
        neg_report_pattern = r"(?:do not|don't|never|no|without|skip)\s+(?:generate|create|produce|make|write)?\s*(?:a|an)?\s*(?:report|approval note|note|document|artifact|excel|slides)?(?:\s+or\s+(?:report|approval note|note|document|artifact))?"
        req_cleaned = re.sub(neg_report_pattern, "", req_lower, flags=re.IGNORECASE)

        # Match keyword intents using filtered request text for report/inspection
        matched_intents = {}
        for intent_cat, keywords in INTENT_KEYWORDS.items():
            target_text = req_cleaned if intent_cat in ["INSPECTION", "REPORT_GENERATION"] else req_lower
            matches = [k for k in keywords if k in target_text]
            if matches:
                matched_intents[intent_cat] = matches

        detected_signals["matched_keywords"] = {k: len(v) for k, v in matched_intents.items()}

        # Check for explicit programming / coding instructions
        explicit_coding_patterns = [
            r"\bwrite\s+(?:a\s+)?(?:python|code|script|program)\b",
            r"\bexecute\s+(?:this\s+)?(?:code|script|program|python)\b",
            r"\bdebug\s+(?:this\s+)?(?:code|script|program|python)?\b",
            r"\bcreate\s+(?:a\s+)?program\b",
            r"\bcoding\s+task\b",
            r"\brun\s+(?:this\s+)?(?:script|code|python)\b",
            r"\bscript\.py\b",
            r"\busing\s+python\b",
        ]
        has_explicit_coding = bool(re.search(r"|".join(explicit_coding_patterns), req_lower))

        # -------------------------------------------------------------
        # Decision logic for multi-agent workflows
        # -------------------------------------------------------------

        # 1. Full Inspection Workflow
        # Signals: Inspection intent or (documents + SOP/compliance/approval/report intent)
        is_inspection = (
            "INSPECTION" in matched_intents
            or (has_docs and ("KNOWLEDGE_SEARCH" in matched_intents or "REPORT_GENERATION" in matched_intents))
            or ("inspection report" in req_cleaned and "approval note" in req_cleaned)
        )
        if is_inspection and not has_data and not has_code:
            tasks = [
                AgentTask(
                    agent_name="ocr",
                    instruction="Extract text, tables, and findings from the inspection document.",
                    depends_on=[],
                ),
                AgentTask(
                    agent_name="rag",
                    instruction="Retrieve relevant local SOP guidance, safety regulations, and compliance standards.",
                    depends_on=["ocr"],
                ),
                AgentTask(
                    agent_name="report",
                    instruction="Synthesize findings, verify evidence against SOP guidance, and generate formal approval note.",
                    depends_on=["ocr", "rag"],
                ),
            ]
            confidence = 0.96 if has_docs else 0.88
            explanation = "Detected Inspection & Approval workflow: extracting findings with OCR, matching SOP standards via RAG, and preparing formal approval deliverable."
            return ExecutionPlan(
                intent="INSPECTION",
                confidence=confidence,
                explanation=explanation,
                detected_signals=detected_signals,
                planned_agents=["ocr", "rag", "report"],
                tasks=tasks,
                workflow_name="full_inspection",
            )

        # 2. High-Priority Data Analysis Workflow
        # Signals: CSV / XLSX / XLS / JSON attached OR data analysis intent
        # Precedence rule: Tabular dataset queries take strict precedence over generic coding
        # unless explicit code generation/debugging instructions are present.
        is_data = (
            has_data
            or "DATA_ANALYSIS" in matched_intents
            or any(w in req_lower for w in [
                "csv", "dataframe", "trends", "statistics", "dataset",
                "telemetry", "abnormal", "anomaly", "equipment risk", "readings", "charts"
            ])
        )
        if is_data and not has_explicit_coding and not has_docs and not has_images:
            has_report_request = (
                "REPORT_GENERATION" in matched_intents
                or any(w in req_lower for w in [
                    "report", "deliverable", "deliverables", "summary",
                    "recommendation", "recommendations", "charts", "management",
                    "management-ready", "excel", "slides", "presentation", "overview"
                ])
                or has_data
            )
            if has_report_request:
                tasks = [
                    AgentTask(
                        agent_name="data_analysis",
                        instruction="Analyze tabular data, compute descriptive statistics, detect anomalies, identify trends, and evaluate equipment risks.",
                        depends_on=[],
                    ),
                    AgentTask(
                        agent_name="report",
                        instruction=f"Compile analysis results, summary statistics, anomalies, and generated charts into management report ({user_request}).",
                        depends_on=["data_analysis"],
                    ),
                ]
                planned_agents = ["data_analysis", "report"]
                wf_name = "data_analysis"
                explanation = "Detected Tabular Data Analysis workflow: processing numerical dataset for statistics, anomalies, and trends, and compiling comprehensive management report deliverables."
            else:
                tasks = [
                    AgentTask(
                        agent_name="data_analysis",
                        instruction="Analyze tabular data and compute descriptive statistics.",
                        depends_on=[],
                    ),
                ]
                planned_agents = ["data_analysis"]
                wf_name = "data_analysis"
                explanation = "Detected Tabular Data Analysis task: calculating descriptive statistics and trends."

            confidence = 0.96 if has_data else 0.88
            return ExecutionPlan(
                intent="DATA_ANALYSIS",
                confidence=confidence,
                explanation=explanation,
                detected_signals=detected_signals,
                planned_agents=planned_agents,
                tasks=tasks,
                workflow_name=wf_name,
            )

        # 3. Coding Agent & Sandbox Workflow
        # Signals: Explicit coding request, code files, or computational formula calculation without data
        is_coding = (
            has_explicit_coding
            or "CODING" in matched_intents
            or has_code
            or any(w in req_lower for w in ["calculate", "python", "script", "formula", "compute", "pressure drop", "average"])
        )
        if is_coding and not has_docs and not has_images and (not has_data or has_explicit_coding):
            has_report_request = "REPORT_GENERATION" in matched_intents
            if has_report_request:
                tasks = [
                    AgentTask(
                        agent_name="coding",
                        instruction=f"Generate Python code for: {user_request}. Execute securely in local sandbox.",
                        depends_on=[],
                    ),
                    AgentTask(
                        agent_name="report",
                        instruction="Generate a formal report summarizing computational output and code execution.",
                        depends_on=["coding"],
                    ),
                ]
                planned_agents = ["coding", "report"]
                explanation = "Detected Computational task with Report request: executing Python script in sandbox and generating deliverable report."
            else:
                tasks = [
                    AgentTask(
                        agent_name="coding",
                        instruction=f"Generate Python code for: {user_request}. Execute securely in local sandbox with automatic repair.",
                        depends_on=[],
                    ),
                ]
                planned_agents = ["coding"]
                explanation = "Detected Computational task: generating Python code with local LLM and executing within isolated sandbox."

            confidence = 0.95 if ("python" in req_lower or has_code or has_explicit_coding) else 0.90
            return ExecutionPlan(
                intent="CODING",
                confidence=confidence,
                explanation=explanation,
                detected_signals=detected_signals,
                planned_agents=planned_agents,
                tasks=tasks,
                workflow_name="coding",
            )

        # 4. Vision & Visual Inspection Workflow
        # Signals: Images attached or visual keywords (drawing, p&id, photograph, visual)
        is_vision = (
            has_images
            or "VISION" in matched_intents
            or any(w in req_lower for w in ["image", "photo", "drawing", "diagram", "p&id", "visual inspect"])
        )
        if is_vision and not has_data:
            has_report_request = "REPORT_GENERATION" in matched_intents or "summary" in req_lower or "report" in req_lower
            if has_report_request:
                tasks = [
                    AgentTask(
                        agent_name="vision",
                        instruction="Analyze equipment, diagrams, labels, and anomalies in visual assets.",
                        depends_on=[],
                    ),
                    AgentTask(
                        agent_name="report",
                        instruction="Generate formal engineering report from visual analysis findings.",
                        depends_on=["vision"],
                    ),
                ]
                planned_agents = ["vision", "report"]
                wf_name = "vision_report"
                explanation = "Detected Visual Inspection with Report request: analyzing image via local Vision model and formatting findings report."
            else:
                tasks = [
                    AgentTask(
                        agent_name="vision",
                        instruction="Analyze equipment, labels, and anomalies using local vision model.",
                        depends_on=[],
                    ),
                ]
                planned_agents = ["vision"]
                wf_name = "vision"
                explanation = "Detected Visual Inspection task: running local vision model on attached visual assets."

            confidence = 0.95 if has_images else 0.88
            return ExecutionPlan(
                intent="VISION",
                confidence=confidence,
                explanation=explanation,
                detected_signals=detected_signals,
                planned_agents=planned_agents,
                tasks=tasks,
                workflow_name=wf_name,
            )

        # 5. Pure Knowledge Search / SOP Retrieval (RAG)
        # Signals: SOP query, procedures, maintenance standards, threshold lookups
        is_rag_query = (
            "KNOWLEDGE_SEARCH" in matched_intents
            or any(w in req_lower for w in [
                "sop", "procedure", "standard", "manual", "bearing failure", "guidance",
                "vibration limit", "vibration velocity", "iso 10816", "threshold", "thresholds",
                "knowledge base", "alert levels", "maintenance standard"
            ])
        )
        if is_rag_query and not has_docs and not has_images and not has_data:
            tasks = [
                AgentTask(
                    agent_name="rag",
                    instruction=f"Search indexed knowledge base for: {user_request}",
                    depends_on=[],
                ),
            ]
            return ExecutionPlan(
                intent="KNOWLEDGE_SEARCH",
                confidence=0.92,
                explanation="Detected Knowledge Base query: retrieving relevant SOP guidelines and standards with citations.",
                detected_signals=detected_signals,
                planned_agents=["rag"],
                tasks=tasks,
                workflow_name="rag_search",
            )

        # 6. Document Text Extraction (OCR only)
        # Signals: Extract text, read document without synthesis requested
        is_ocr_only = (
            "DOCUMENT" in matched_intents
            and "REPORT_GENERATION" not in matched_intents
            and "KNOWLEDGE_SEARCH" not in matched_intents
        )
        if is_ocr_only and has_docs:
            tasks = [
                AgentTask(
                    agent_name="ocr",
                    instruction="Extract text and tables from attached document.",
                    depends_on=[],
                ),
            ]
            return ExecutionPlan(
                intent="DOCUMENT",
                confidence=0.94,
                explanation="Detected Document text extraction request: running local OCR on document pages.",
                detected_signals=detected_signals,
                planned_agents=["ocr"],
                tasks=tasks,
                workflow_name="ocr",
            )

        # 7. Default Document Pipeline
        if has_docs:
            tasks = [
                AgentTask(
                    agent_name="ocr",
                    instruction="Extract text from the attached document.",
                    depends_on=[],
                ),
                AgentTask(
                    agent_name="rag",
                    instruction="Index extracted text and search for relevant context.",
                    depends_on=["ocr"],
                ),
                AgentTask(
                    agent_name="report",
                    instruction="Generate a professional report from OCR and RAG results.",
                    depends_on=["ocr", "rag"],
                ),
            ]
            return ExecutionPlan(
                intent="INSPECTION",
                confidence=0.85,
                explanation="Default document pipeline selected: extracting text via OCR, retrieving relevant SOP context, and generating report.",
                detected_signals=detected_signals,
                planned_agents=["ocr", "rag", "report"],
                tasks=tasks,
                workflow_name="ocr_rag_report",
            )

        # 8. Fallback / General reasoning
        return ExecutionPlan(
            intent="GENERAL",
            confidence=0.75,
            explanation="Standard local reasoning request. Handled directly by local Ollama model.",
            detected_signals=detected_signals,
            planned_agents=[],
            tasks=[],
            workflow_name="chat",
        )

    def _plan_for_named_workflow(
        self,
        workflow_name: str,
        user_request: str,
        detected_signals: dict[str, Any],
    ) -> ExecutionPlan:
        """Map predefined workflow name directly to plan."""
        from agents.orchestrator.orchestrator import WORKFLOWS

        tasks = WORKFLOWS.get(workflow_name, [])
        planned_agents = [t.agent_name for t in tasks]

        intent_map = {
            "full_inspection": "INSPECTION",
            "ocr_rag_report": "INSPECTION",
            "ocr": "DOCUMENT",
            "data_analysis": "DATA_ANALYSIS",
            "vision": "VISION",
            "vision_report": "VISION",
            "coding": "CODING",
        }

        intent = intent_map.get(workflow_name, "CUSTOM")
        explanation = f"Executing explicitly requested workflow '{workflow_name}' ({' → '.join([a.upper() for a in planned_agents])})."

        return ExecutionPlan(
            intent=intent,
            confidence=1.0,
            explanation=explanation,
            detected_signals=detected_signals,
            planned_agents=planned_agents,
            tasks=tasks,
            workflow_name=workflow_name,
        )


# Global singleton instance
task_planner = TaskPlanner()
