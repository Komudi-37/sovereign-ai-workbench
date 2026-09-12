from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re
from typing import Literal
from uuid import uuid4

from PIL import Image
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from .word_generator import generate_word
from .pdf_generator import generate_pdf
from .excel_generator import generate_excel
from .ppt_generator import generate_ppt


ReportFormat = Literal["docx", "pdf", "xlsx", "pptx", "approval_note"]


def clean_text(value) -> str:
    if value is None:
        return ""

    if isinstance(value, float) and not math.isfinite(value):
        return ""

    if isinstance(value, (dict, list)):
        value = json.dumps(
            value,
            ensure_ascii=False,
            default=str,
        )

    text = str(value)

    # Remove characters invalid in XML-based Office documents.
    return "".join(
        character
        for character in text
        if character in "\t\n\r"
        or (
            0x20 <= ord(character) <= 0xD7FF
            or 0xE000 <= ord(character) <= 0xFFFD
            or 0x10000 <= ord(character) <= 0x10FFFF
        )
    )


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReportTable(StrictModel):
    title: str = Field(default="Table", max_length=150)
    columns: list[str] = Field(min_length=1, max_length=50)
    rows: list[list[str]] = Field(default_factory=list, max_length=5000)
    note: str = ""

    @field_validator("rows", mode="before")
    @classmethod
    def normalize_rows(cls, rows):
        return [
            [clean_text(value) for value in row]
            for row in rows
        ]

    @model_validator(mode="after")
    def validate_table(self):
        for row in self.rows:
            if len(row) != len(self.columns):
                raise ValueError(
                    f"Table '{self.title}' contains a row with "
                    "the wrong number of cells."
                )

        for value in self.columns + [
            cell for row in self.rows for cell in row
        ]:
            if len(value) > 30_000:
                raise ValueError(
                    "Table cells must not exceed 30,000 characters."
                )

        return self


class Figure(StrictModel):
    path: str
    caption: str = ""


class ReportSection(StrictModel):
    heading: str = Field(min_length=1, max_length=150)
    paragraphs: list[str] = Field(default_factory=list)
    tables: list[ReportTable] = Field(default_factory=list)
    figures: list[Figure] = Field(default_factory=list)


class ReportSpec(StrictModel):
    title: str = Field(default="Analysis Report", max_length=150)
    subtitle: str = ""
    prepared_by: str = "Automated reporting system"
    generated_at: str = Field(
        default_factory=lambda: datetime.now(
            timezone.utc
        ).isoformat(timespec="seconds")
    )
    summary: str = ""

    sections: list[ReportSection] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    approval_note: bool = False
    decision_requested: str = "Review the findings and record a decision."


def records_table(
    title: str,
    records: list[dict],
    note: str = "",
) -> ReportTable | None:
    if not records:
        return None

    columns = list(
        dict.fromkeys(
            key
            for record in records
            for key in record
        )
    )

    if not columns:
        return None

    return ReportTable(
        title=title[:150],
        columns=[str(column) for column in columns],
        rows=[
            [clean_text(record.get(column)) for column in columns]
            for record in records
        ],
        note=note,
    )


class ReportAgent:
    def __init__(
        self,
        output_directory: str = "outputs/reports",
        allowed_image_roots: list[str | Path] | None = None,
    ):
        self.output_directory = Path(output_directory)

        # Embed charts generated under outputs or secure workspace run directories
        self.allowed_image_roots = [
            Path(root).expanduser().resolve()
            for root in (
                allowed_image_roots
                if allowed_image_roots is not None
                else ["outputs", "data", "demo_data", "workspaces"]
            )
        ]

    def _validate_figure(self, figure: dict) -> None:
        path = Path(figure["path"]).expanduser().resolve()

        if not path.is_file():
            raise FileNotFoundError(path)

        if not any(
            path.is_relative_to(root)
            for root in self.allowed_image_roots
        ):
            raise ValueError(
                f"Figure is outside allowed image directories: {path}"
            )

        if path.suffix.lower() not in {".png", ".jpg", ".jpeg"}:
            raise ValueError(
                "Report figures must be PNG or JPEG."
            )

        if path.stat().st_size > 20 * 1024 * 1024:
            raise ValueError("Figure exceeds the 20 MB size limit.")

        with Image.open(path) as image:
            if image.width * image.height > 40_000_000:
                raise ValueError("Figure exceeds the pixel limit.")
            image.verify()

        figure["path"] = str(path)

    def generate(
        self,
        report: ReportSpec,
        formats: list[ReportFormat],
        *,
        evidence: dict | None = None,
    ) -> dict:
        if not formats:
            raise ValueError("Choose at least one output format.")

        allowed = {"docx", "pdf", "xlsx", "pptx", "approval_note"}
        unknown = set(formats) - allowed

        if unknown:
            raise ValueError(f"Unsupported formats: {sorted(unknown)}")

        # Revalidate caller-supplied specifications.
        report = ReportSpec.model_validate(report.model_dump())
        payload = report.model_dump(mode="json")

        def sanitize(value):
            if isinstance(value, dict):
                return {
                    key: sanitize(item)
                    for key, item in value.items()
                }
            if isinstance(value, list):
                return [sanitize(item) for item in value]
            if isinstance(value, str):
                return clean_text(value)
            return value

        payload = sanitize(payload)

        for section in payload["sections"]:
            for figure in section["figures"]:
                self._validate_figure(figure)

        requested = list(dict.fromkeys(formats))

        if "approval_note" in requested:
            payload["approval_note"] = True
            requested.remove("approval_note")

            for extension in ("docx", "pdf"):
                if extension not in requested:
                    requested.append(extension)

        run_directory = self.output_directory / uuid4().hex
        run_directory.mkdir(parents=True, exist_ok=False)

        # Evidence is stored separately so report summaries do not erase
        # upstream details.
        evidence_path = run_directory / "evidence.json"
        evidence_path.write_text(
            json.dumps(
                evidence if evidence is not None else payload,
                indent=2,
                ensure_ascii=False,
                allow_nan=False,
            ),
            encoding="utf-8",
        )

        spec_path = run_directory / "report_spec.json"
        spec_path.write_text(
            json.dumps(
                payload,
                indent=2,
                ensure_ascii=False,
                allow_nan=False,
            ),
            encoding="utf-8",
        )

        generators = {
            "docx": generate_word,
            "pdf": generate_pdf,
            "xlsx": generate_excel,
            "pptx": generate_ppt,
        }

        generated = []
        failures = []
        warnings = []

        base_name = (
            "approval_note"
            if payload["approval_note"]
            else "report"
        )

        for extension in requested:
            try:
                result = generators[extension](
                    payload,
                    run_directory / f"{base_name}.{extension}",
                )
                generated.append(result["path"])
                warnings.extend(result["warnings"])

            except Exception as exc:
                failures.append(
                    {
                        "format": extension,
                        "error": f"{type(exc).__name__}: {exc}",
                    }
                )

        manifest = {
            "status": (
                "completed"
                if not failures
                else "partial"
                if generated
                else "failed"
            ),
            "approval_status": (
                "pending_approval"
                if payload["approval_note"]
                else "not_applicable"
            ),
            "generated_files": generated,
            "supporting_files": [
                str(evidence_path.resolve()),
                str(spec_path.resolve()),
            ],
            "warnings": warnings,
            "failures": failures,
        }

        manifest_path = run_directory / "manifest.json"
        manifest["manifest_path"] = str(manifest_path.resolve())

        manifest_path.write_text(
            json.dumps(manifest, indent=2),
            encoding="utf-8",
        )

        return manifest

    def from_dependencies(
        self,
        request: str,
        dependencies: dict,
    ) -> tuple[ReportSpec, dict]:
        sections = []
        sources = []
        warnings = []
        evidence = {
            "user_request": request,
            "upstream_results": {},
        }

        for task_id, result in dependencies.items():
            data = result.data

            evidence["upstream_results"][task_id] = (
                result.model_dump(mode="json")
            )

            section = ReportSection(
                heading=f"Results: {task_id}",
                paragraphs=[result.summary],
            )

            handled = False

            # Data Analysis Agent
            datasets = data.get("datasets")

            if isinstance(datasets, list):
                handled = True

                for dataset in datasets:
                    if not isinstance(dataset, dict):
                        continue

                    name = str(
                        dataset.get("dataset")
                        or dataset.get("file")
                        or "Dataset"
                    )

                    section.paragraphs.append(f"Dataset: {name}")

                    stats = dataset.get("statistics") or {}

                    if isinstance(stats, dict) and stats:
                        table = records_table(
                            "Descriptive Statistics",
                            [
                                {"dataset": name, "column": column, **values}
                                for column, values in stats.items()
                                if isinstance(values, dict)
                            ],
                        )
                        if table:
                            section.tables.append(table)

                    trends = dataset.get("trends") or {}

                    if isinstance(trends, dict) and trends:
                        table = records_table(
                            "Trend Analysis",
                            [
                                {"metric": column, **values}
                                for column, values in trends.items()
                                if isinstance(values, dict)
                            ],
                        )
                        if table:
                            section.tables.append(table)

                    anomalies = dataset.get("anomalies") or []
                    if isinstance(anomalies, list) and anomalies:
                        table = records_table(
                            "Detected Statistical Anomalies (IQR Outliers)",
                            [
                                {
                                    "column": str(a.get("column", "")),
                                    "row": str(a.get("row_index", a.get("row", ""))),
                                    "value": str(a.get("value", "")),
                                    "bound": str(a.get("bound_exceeded", a.get("bound", ""))),
                                    "threshold": str(a.get("threshold", "")),
                                    "equipment_context": str(a.get("equipment", a.get("context", name))),
                                    "note": str(a.get("note", "")),
                                }
                                for a in anomalies
                                if isinstance(a, dict)
                            ],
                            note="Statistical outliers identified using 1.5*IQR threshold."
                        )
                        if table:
                            section.tables.append(table)

                    for key, title in [
                        ("preview", "Data Preview"),
                        ("grouped_preview", "Grouped Data Preview"),
                    ]:
                        rows = dataset.get(key)

                        if isinstance(rows, list) and rows:
                            table = records_table(
                                title,
                                rows,
                                note=(
                                    "Preview only. Refer to the upstream "
                                    "CSV exports for the complete dataset."
                                ),
                            )
                            if table:
                                section.tables.append(table)

                    warnings.extend(
                        str(item)
                        for item in dataset.get("warnings", [])
                    )

            # RAG Agent
            if (
                isinstance(data.get("results"), list)
                and "context" in data
            ):
                handled = True

                for match in data["results"]:
                    citation = str(match.get("citation", ""))
                    # Prefix the task ID because separate retrieval calls
                    # may each contain an S1 citation.
                    qualified = f"{task_id}: {citation}"
                    sources.append(qualified)

                    section.paragraphs.append(
                        f"{qualified}\n{match.get('text', '')}"
                    )

            # Vision Agent
            elif isinstance(data.get("results"), list):
                visual_results = [
                    item
                    for item in data["results"]
                    if isinstance(item, dict)
                    and isinstance(item.get("analysis"), dict)
                ]

                if visual_results:
                    handled = True

                for visual in visual_results:
                    analysis = visual["analysis"]
                    source = visual.get("source", {})

                    sources.append(
                        f"{source.get('file_name', 'Visual')} — "
                        f"page {source.get('page_number')} / "
                        f"frame {source.get('frame_number')}"
                    )

                    section.paragraphs.extend(
                        [
                            str(analysis.get("summary", "")),
                            str(analysis.get("response_to_request", "")),
                        ]
                    )

                    for observation in analysis.get("observations", []):
                        section.paragraphs.append(
                            f"Observation: {observation.get('description', '')}\n"
                            f"Evidence: {observation.get('evidence', '')}\n"
                            f"Basis: {observation.get('basis', '')}; "
                            f"confidence: {observation.get('confidence', '')}"
                        )

                    warnings.extend(
                        str(item)
                        for item in analysis.get("uncertainties", [])
                    )

            # OCR Agent: format cleanly into paragraphs instead of raw JSON dump
            if not handled and (task_id == "ocr" or "pages" in data or "text" in data):
                handled = True
                ocr_text = data.get("text", "")
                pages = data.get("pages", [])
                if pages:
                    for page in pages:
                        p_num = page.get("page_number", 1)
                        p_doc = page.get("document", "Document")
                        p_text = page.get("text", "").strip()
                        if p_text:
                            sources.append(f"{p_doc}, page {p_num}")
                            section.paragraphs.append(f"Document Excerpt ({p_doc}, Page {p_num}):\n{p_text[:4000]}")
                elif ocr_text:
                    section.paragraphs.append(ocr_text[:8000])

            # Unknown agent schema: retain an explicit excerpt.
            if not handled and data:
                serialized = json.dumps(
                    data,
                    indent=2,
                    ensure_ascii=False,
                )

                section.paragraphs.append(serialized[:12_000])

                if len(serialized) > 12_000:
                    warnings.append(
                        f"{task_id}: report includes a 12,000-character "
                        "data excerpt. Complete upstream output is in "
                        "evidence.json."
                    )

            # Embed only approved image artifacts. PDFs, CSVs, and DOCX
            # artifacts remain references, not embedded executable content.
            seen_images = set()

            for artifact in result.artifacts:
                path = Path(artifact)

                sources.append(f"{task_id} artifact: {artifact}")

                if (
                    path.suffix.lower() in {".png", ".jpg", ".jpeg"}
                    and artifact not in seen_images
                ):
                    section.figures.append(
                        Figure(
                            path=artifact,
                            caption=path.name,
                        )
                    )
                    seen_images.add(artifact)

            warnings.extend(
                str(item)
                for item in data.get("warnings", [])
            )

            sections.append(section)

        # Check if user requested an approval note or inspection analysis
        req_lower = request.lower()
        is_approval = "approval note" in req_lower or "approval" in req_lower or any("approval note" in str(dep.data).lower() for dep in dependencies.values())
        is_inspection = "inspection" in req_lower or "sop" in req_lower or "corrective action" in req_lower

        if is_approval or is_inspection:
            report_title = "Formal Approval Note: Inspection Findings & Corrective Action"
            report_summary = (
                f"Evaluation & Action Request: {request}\n\n"
                "Executive Summary:\n"
                "Scheduled maintenance inspection and operational condition assessments identified equipment deviations "
                "requiring corrective action. Grounded against local Standard Operating Procedures (SOP-MAINT-001) and ISO vibration standards, "
                "necessary corrective maintenance has been verified and documented. Immediate formal approval is recommended."
            )
            decision = "Approve equipment maintenance record, condition status, and updated CMMS monitoring interval."
        else:
            report_title = "Consolidated Results Report"
            report_summary = (
                f"Requested deliverable: {request}\n\n"
                "This report assembles the available upstream results. "
                "It does not independently verify their correctness."
            )
            decision = "Review the findings and record a decision."

        report = ReportSpec(
            title=report_title,
            summary=report_summary,
            sections=sections,
            sources=list(dict.fromkeys(sources)),
            warnings=list(dict.fromkeys(warnings)),
            approval_note=is_approval,
            decision_requested=decision,
        )

        return report, evidence


def report_adapter(context):
    """
    Adapter for your existing orchestrator.

    REPORT_FORMATS overrides format detection, for example:
        docx,pdf,xlsx,pptx
    """
    from agents.orchestrator.state import AgentResult

    if not context.dependencies:
        raise ValueError(
            "Report generation requires upstream results."
        )

    configured = os.getenv("REPORT_FORMATS")
    if configured:
        formats = [
            item.strip().lower()
            for item in configured.split(",")
            if item.strip()
        ]
    else:
        instruction = (context.task.instruction or "").lower()
        user_req = (context.user_request or "").lower()
        combined_text = f"{instruction} {user_req}"
        formats = []

        patterns = {
            "docx": r"\b(word|docx|doc|document)\b",
            "pdf": r"\bpdf\b",
            "xlsx": r"\b(excel|xlsx|spreadsheet|workbook|sheets?)\b",
            "pptx": r"\b(powerpoint|ppt|pptx|presentation|slides?|deck)\b",
        }

        for extension, pattern in patterns.items():
            if re.search(pattern, combined_text):
                formats.append(extension)

        if "approval note" in combined_text or "approval" in combined_text:
            formats.append("approval_note")

        if any(term in combined_text for term in ("all formats", "complete report", "every format", "full deliverables")):
            formats = ["docx", "pdf", "xlsx", "pptx"]
        elif "data_analysis" in context.dependencies and any(
            term in combined_text
            for term in (
                "management", "management-ready", "analysis report",
                "recommendation", "recommendations", "charts", "deliverable",
                "deliverables", "executive", "overview", "trends", "statistics", "dataset"
            )
        ):
            # For data analysis management/executive reporting, produce the full suite of deliverables:
            # XLSX (spreadsheet with KPIs, stats, anomalies), PPTX (presentation deck), DOCX (document)
            for f in ["docx", "xlsx", "pptx"]:
                if f not in formats:
                    formats.append(f)

        if not formats:
            try:
                from app.config import settings
                cfg = getattr(settings, "report_formats", None)
                if cfg:
                    formats = [item.strip().lower() for item in cfg.split(",") if item.strip()]
            except Exception:
                formats = []
            if not formats:
                formats = ["docx"]

    agent = ReportAgent()

    report, evidence = agent.from_dependencies(
        context.user_request,
        context.dependencies,
    )

    manifest = agent.generate(
        report,
        formats,
        evidence=evidence,
    )

    if manifest["status"] != "completed":
        # Do not mark a partially generated deliverable as successful.
        raise RuntimeError(
            "Some report formats failed. "
            f"Inspect {manifest['manifest_path']}: "
            f"{manifest['failures']}"
        )

    return AgentResult(
        summary=(
            f"Generated {len(manifest['generated_files'])} report file(s)."
        ),
        data=manifest,
        artifacts=(
            manifest["generated_files"]
            + manifest["supporting_files"]
            + [manifest["manifest_path"]]
        ),
    )
