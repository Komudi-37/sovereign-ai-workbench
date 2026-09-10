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

        # Default: embed charts generated under the application's outputs.
        self.allowed_image_roots = [
            Path(root).expanduser().resolve()
            for root in (
                allowed_image_roots
                if allowed_image_roots is not None
                else ["outputs"]
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
                                {"column": column, **values}
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
                                {"column": column, **values}
                                for column, values in trends.items()
                                if isinstance(values, dict)
                            ],
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

            # OCR or an unknown agent schema: retain an explicit excerpt.
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

        report = ReportSpec(
            title="Consolidated Results Report",
            summary=(
                f"Requested deliverable: {request}\n\n"
                "This report assembles the available upstream results. "
                "It does not independently verify their correctness."
            ),
            sections=sections,
            sources=list(dict.fromkeys(sources)),
            warnings=list(dict.fromkeys(warnings)),
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
        # This is a convenience heuristic, not a full language planner.
        instruction = context.task.instruction.lower()
        formats = []

        patterns = {
            "docx": r"\b(word|docx)\b",
            "pdf": r"\bpdf\b",
            "xlsx": r"\b(excel|xlsx)\b",
            "pptx": r"\b(powerpoint|ppt|pptx)\b",
        }

        for extension, pattern in patterns.items():
            if re.search(pattern, instruction):
                formats.append(extension)

        if "approval note" in instruction:
            formats.append("approval_note")

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
