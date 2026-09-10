import argparse
from dataclasses import dataclass, field
import json
import math
import os
from pathlib import Path
from uuid import uuid4

import numpy as np
import pandas as pd

from .calculator import (
    AnalysisSpec,
    ChartSpec,
    detect_trends,
    is_numeric,
    prepare_data,
    require_columns,
    statistics,
)
from .charts import ChartGenerator


@dataclass
class Dataset:
    name: str
    frame: pd.DataFrame
    source: dict = field(default_factory=dict)


def json_safe(value):
    """Return strict JSON-compatible analytical output."""
    if isinstance(value, dict):
        return {
            str(key): json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]

    if isinstance(value, np.generic):
        return json_safe(value.item())

    if value is pd.NA or value is pd.NaT:
        return None

    if isinstance(value, float) and not math.isfinite(value):
        return None

    if isinstance(value, pd.Timestamp):
        return value.isoformat()

    if isinstance(value, Path):
        return str(value)

    return value


def preview(frame: pd.DataFrame) -> list[dict]:
    return json.loads(
        frame.head(20).to_json(
            orient="records",
            date_format="iso",
        )
    )


def safe_csv(frame: pd.DataFrame, path: Path) -> None:
    """
    Escape formula-like strings in CSV exports.
    Actual numeric negative values are not changed.
    """
    def escape(value):
        if isinstance(value, str) and value.lstrip().startswith(
            ("=", "+", "-", "@")
        ):
            return "'" + value
        return value

    exported = frame.copy()
    exported.columns = [escape(str(c)) for c in exported.columns]

    for column in exported.columns:
        if (
            pd.api.types.is_object_dtype(exported[column])
            or pd.api.types.is_string_dtype(exported[column])
        ):
            exported[column] = exported[column].map(escape)

    exported.to_csv(path, index=False)


class DataAnalysisAgent:
    SUPPORTED_FILES = {".csv", ".xlsx", ".xls", ".json"}

    def __init__(
        self,
        output_directory: str = "outputs/data_analysis",
        max_rows: int = 200_000,
        max_file_bytes: int = 100 * 1024 * 1024,
        max_datasets: int = 30,
    ):
        if min(max_rows, max_file_bytes, max_datasets) <= 0:
            raise ValueError("Resource limits must be positive.")

        self.output_directory = Path(output_directory)
        self.max_rows = max_rows
        self.max_file_bytes = max_file_bytes
        self.max_datasets = max_datasets
        self.chart_generator = ChartGenerator()

    def validate_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            raise ValueError("Dataset has no data rows.")

        if len(frame) > self.max_rows:
            raise ValueError(
                f"Dataset exceeds max_rows={self.max_rows}."
            )

        result = frame.copy()
        result.columns = [str(c).strip() for c in result.columns]

        if any(not column for column in result.columns):
            raise ValueError("Column names cannot be blank.")

        if result.columns.duplicated().any():
            raise ValueError("Duplicate column names are not supported.")

        # This agent expects scalar tabular cells.
        for column in result.columns:
            if result[column].map(
                lambda value: isinstance(
                    value, (dict, list, tuple, set)
                )
            ).any():
                raise ValueError(
                    f"Column '{column}' contains nested values. "
                    "Flatten the data before analysis."
                )

        return result

    def load_file(
        self,
        filename: str | Path,
        *,
        sheets: list[str] | None = None,
        separator: str = ",",
        encoding: str = "utf-8-sig",
        csv_dtypes: dict | None = None,
    ) -> list[Dataset]:
        path = Path(filename).expanduser().resolve()

        if not path.is_file():
            raise FileNotFoundError(path)

        if path.stat().st_size > self.max_file_bytes:
            raise ValueError(f"{path.name} exceeds max_file_bytes.")

        extension = path.suffix.lower()

        if extension not in self.SUPPORTED_FILES:
            raise ValueError(f"Unsupported data format: {extension}")

        datasets = []

        if extension == ".csv":
            frame = pd.read_csv(
                path,
                sep=separator,
                encoding=encoding,
                dtype=csv_dtypes,
                nrows=self.max_rows + 1,
            )
            datasets.append(
                Dataset(
                    path.stem,
                    self.validate_frame(frame),
                    {"file": str(path)},
                )
            )

        elif extension in {".xlsx", ".xls"}:
            with pd.ExcelFile(path) as workbook:
                selected = (
                    workbook.sheet_names
                    if sheets is None
                    else sheets
                )

                if not selected:
                    raise ValueError("No Excel sheets selected.")

                unknown = set(selected) - set(workbook.sheet_names)
                if unknown:
                    raise ValueError(
                        f"Unknown Excel sheets: {sorted(unknown)}"
                    )

                if len(selected) > self.max_datasets:
                    raise ValueError("Too many Excel sheets.")

                for sheet in selected:
                    frame = workbook.parse(
                        sheet_name=sheet,
                        nrows=self.max_rows + 1,
                    )

                    datasets.append(
                        Dataset(
                            f"{path.stem}:{sheet}",
                            self.validate_frame(frame),
                            {
                                "file": str(path),
                                "sheet": sheet,
                                "warnings": [
                                    "Excel formulas are not recalculated; "
                                    "cached workbook values are used."
                                ],
                            },
                        )
                    )

        else:
            payload = json.loads(
                path.read_text(encoding=encoding)
            )

            records = (
                payload.get("records")
                if isinstance(payload, dict)
                else payload
            )

            if (
                not isinstance(records, list)
                or not records
                or not all(isinstance(row, dict) for row in records)
            ):
                raise ValueError(
                    "JSON must contain a nonempty list of row objects "
                    "or {'records': [...]}."
                )

            datasets.append(
                Dataset(
                    path.stem,
                    self.validate_frame(pd.DataFrame(records)),
                    {"file": str(path)},
                )
            )

        return datasets

    def from_ocr_documents(
        self,
        documents: list[dict],
        *,
        first_row_is_header: bool = True,
    ) -> list[Dataset]:
        datasets = []

        for document in documents:
            for page in document.get("pages", []):
                for index, table in enumerate(
                    page.get("tables", []), start=1
                ):
                    rows = table.get("rows") or []
                    if not rows:
                        continue

                    width = max(len(row) for row in rows)
                    rows = [
                        list(row) + [None] * (width - len(row))
                        for row in rows
                    ]

                    if first_row_is_header:
                        raw_headers, body = rows[0], rows[1:]
                    else:
                        raw_headers = [None] * width
                        body = rows

                    headers = []
                    used = set()

                    for column_index, value in enumerate(raw_headers):
                        base = (
                            str(value).strip()
                            if value is not None
                            else ""
                        ) or f"column_{column_index + 1}"

                        name = base
                        suffix = 2

                        while name in used:
                            name = f"{base}_{suffix}"
                            suffix += 1

                        headers.append(name)
                        used.add(name)

                    frame = pd.DataFrame(body, columns=headers)
                    frame = frame.replace(
                        r"^\s*$", np.nan, regex=True
                    )

                    # OCR values are usually strings. Convert a column only
                    # if every nonmissing value is numeric and it does not
                    # appear to contain leading-zero identifiers.
                    for column in frame.columns:
                        present = frame[column].dropna().astype(str)

                        if present.empty:
                            continue

                        leading_zero = present.str.match(
                            r"^[+-]?0\d+$"
                        ).any()

                        converted = pd.to_numeric(
                            frame[column], errors="coerce"
                        )

                        if (
                            not leading_zero
                            and converted.notna().sum()
                            == frame[column].notna().sum()
                        ):
                            frame[column] = converted

                    datasets.append(
                        Dataset(
                            name=(
                                f"{document.get('file_name', 'document')}:"
                                f"page_{page.get('page_number')}:table_{index}"
                            ),
                            frame=self.validate_frame(frame),
                            source={
                                "file": document.get("source_path"),
                                "page_number": page.get("page_number"),
                                "table_id": table.get("id"),
                                "warnings": (
                                    list(page.get("warnings") or [])
                                    + list(table.get("warnings") or [])
                                    + [
                                        "OCR-derived values require review.",
                                        f"first_row_is_header="
                                        f"{first_row_is_header}",
                                    ]
                                ),
                            },
                        )
                    )

        if len(datasets) > self.max_datasets:
            raise ValueError("Too many OCR tables.")

        return datasets

    def analyze(
        self,
        dataset: Dataset,
        spec: AnalysisSpec | None = None,
    ) -> dict:
        spec = AnalysisSpec.model_validate(
            (spec or AnalysisSpec()).model_dump()
        )

        original = self.validate_frame(dataset.frame)
        frame, warnings = prepare_data(original, spec)

        warnings = (
            list(dataset.source.get("warnings") or [])
            + warnings
        )

        numeric_columns = [
            column
            for column in frame.columns
            if is_numeric(frame[column])
        ]

        trend_columns = (
            [
                column
                for column in numeric_columns
                if column != spec.group_by
            ]
            if spec.trend_columns is None
            else spec.trend_columns
        )

        trends = detect_trends(
            frame,
            trend_columns,
            spec.date_column,
        )

        if trend_columns and not spec.date_column:
            warnings.append(
                "Trends use row order, not elapsed time."
            )

        grouped = None

        if spec.group_by:
            require_columns(frame, [spec.group_by])

            value_columns = [
                column
                for column in numeric_columns
                if column != spec.group_by
            ]

            if not value_columns:
                raise ValueError(
                    "Grouping requires numeric value columns."
                )

            groups = frame.groupby(
                spec.group_by,
                dropna=False,
                sort=False,
                observed=True,
            )[value_columns]

            if spec.aggregation == "sum":
                grouped = groups.sum(min_count=1).reset_index()
            else:
                grouped = groups.agg(
                    spec.aggregation
                ).reset_index()

            warnings.append(
                "Grouped aggregation applies to every numeric non-key "
                "column. Verify that aggregating ratios or identifiers "
                "is meaningful."
            )

        chart_frame = grouped if grouped is not None else frame
        chart_specs = list(spec.charts)

        if not chart_specs and spec.default_chart:
            chart_numeric = [
                column
                for column in chart_frame.columns
                if is_numeric(chart_frame[column])
                and column != spec.group_by
            ]

            if chart_numeric:
                y = chart_numeric[0]

                if (
                    spec.date_column
                    and spec.date_column in chart_frame.columns
                ):
                    chart_specs = [
                        ChartSpec(
                            kind="line",
                            x=spec.date_column,
                            y=y,
                        )
                    ]
                else:
                    chart_specs = [
                        ChartSpec(kind="histogram", x=y)
                    ]

        run_directory = self.output_directory / uuid4().hex
        run_directory.mkdir(parents=True, exist_ok=False)

        charts = [
            self.chart_generator.create(
                chart_frame,
                chart_spec,
                run_directory / f"chart_{index}.png",
            )
            for index, chart_spec in enumerate(chart_specs, start=1)
        ]

        data_path = run_directory / "analyzed_data.csv"
        safe_csv(frame, data_path)

        artifacts = [
            str(data_path.resolve()),
            *[chart["path"] for chart in charts],
        ]

        if grouped is not None:
            grouped_path = run_directory / "grouped_data.csv"
            safe_csv(grouped, grouped_path)
            artifacts.append(str(grouped_path.resolve()))

        summary_path = run_directory / "analysis.json"
        artifacts.append(str(summary_path.resolve()))

        result = json_safe(
            {
                "dataset": dataset.name,
                "source": dataset.source,
                "specification": spec.model_dump(mode="json"),
                "row_count": int(len(frame)),
                "columns": {
                    column: str(dtype)
                    for column, dtype in frame.dtypes.items()
                },
                "missing_values": {
                    column: int(count)
                    for column, count in frame.isna().sum().items()
                },
                "duplicate_rows": int(frame.duplicated().sum()),
                "statistics": statistics(frame),
                "trends": trends,
                "preview": preview(frame),
                "grouped_preview": (
                    preview(grouped) if grouped is not None else None
                ),
                "charts": charts,
                "warnings": warnings,
                "artifacts": artifacts,
            }
        )

        summary_path.write_text(
            json.dumps(
                result,
                indent=2,
                ensure_ascii=False,
                allow_nan=False,
            ),
            encoding="utf-8",
        )

        return result


def data_analysis_adapter(context):
    """
    Adapter for the orchestrator implemented earlier.

    Optional DATA_ANALYSIS_SPEC points to a trusted, server-configured
    AnalysisSpec JSON file. It is applied to each dataset.
    """
    from agents.orchestrator.state import AgentResult

    agent = DataAnalysisAgent()
    datasets = []

    for filename in context.files:
        if Path(filename).suffix.lower() in agent.SUPPORTED_FILES:
            datasets.extend(agent.load_file(filename))

    for dependency in context.dependencies.values():
        documents = dependency.data.get("documents", [])

        if isinstance(documents, list):
            datasets.extend(
                agent.from_ocr_documents(
                    documents,
                    first_row_is_header=True,
                )
            )

        records = dependency.data.get("records")

        if isinstance(records, list) and records:
            datasets.append(
                Dataset(
                    name="upstream_records",
                    frame=pd.DataFrame(records),
                    source={"type": "upstream_agent"},
                )
            )

    if not datasets:
        raise ValueError(
            "No supported datasets or extracted OCR tables received."
        )

    if len(datasets) > agent.max_datasets:
        raise ValueError("Combined input exceeds max_datasets.")

    spec_path = os.getenv("DATA_ANALYSIS_SPEC")

    spec = (
        AnalysisSpec.model_validate_json(
            Path(spec_path).read_text(encoding="utf-8")
        )
        if spec_path
        else AnalysisSpec()
    )

    results = [
        agent.analyze(dataset, spec)
        for dataset in datasets
    ]

    return AgentResult(
        summary=(
            f"Analyzed {len(results)} dataset(s) and created "
            f"{sum(len(item['charts']) for item in results)} chart(s)."
        ),
        data={
            "datasets": results,
            "execution_mode": (
                "configured_specification"
                if spec_path
                else "descriptive_defaults"
            ),
            "notes": [
                "This adapter does not interpret arbitrary natural-language "
                "calculations. Custom operations require AnalysisSpec."
            ],
        },
        artifacts=[
            artifact
            for result in results
            for artifact in result["artifacts"]
        ],
    )


def main():
    parser = argparse.ArgumentParser(
        description="Local data analysis agent"
    )

    parser.add_argument("--files", nargs="+", required=True)
    parser.add_argument("--spec", default=None)
    parser.add_argument("--sheets", nargs="+", default=None)
    parser.add_argument("--separator", default=",")
    parser.add_argument("--encoding", default="utf-8-sig")
    parser.add_argument(
        "--output-dir",
        default="outputs/data_analysis",
    )

    args = parser.parse_args()

    spec = (
        AnalysisSpec.model_validate_json(
            Path(args.spec).read_text(encoding="utf-8")
        )
        if args.spec
        else AnalysisSpec()
    )

    agent = DataAnalysisAgent(
        output_directory=args.output_dir
    )

    datasets = []

    for filename in args.files:
        datasets.extend(
            agent.load_file(
                filename,
                sheets=args.sheets,
                separator=args.separator,
                encoding=args.encoding,
            )
        )

    if len(datasets) > agent.max_datasets:
        raise ValueError("Too many datasets.")

    for dataset in datasets:
        result = agent.analyze(dataset, spec)

        print(f"\nDataset: {result['dataset']}")
        print(f"Rows: {result['row_count']}")

        for warning in result["warnings"]:
            print(f"Warning: {warning}")

        for artifact in result["artifacts"]:
            print(f"Output: {artifact}")


if __name__ == "__main__":
    main()
