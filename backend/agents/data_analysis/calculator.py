"""
Advanced Statistical Calculations and Structured Analysis Specification for Sovereign AI Workbench.

Extends standard data calculations with:
- Structured analysis metadata (rows, columns, missing values, duplicates)
- Descriptive summary statistics (count, mean, std, min, q25, median, q75, max)
- Interquartile Range (IQR) based outlier / anomaly detection
- Linear and monotonic trend detection for ordered/time-series data
- Pairwise Pearson correlation analysis across numeric dimensions
- Threshold evaluation and equipment grouping heuristics
- Purely deterministic local processing (no cloud, no hallucinations)
"""

import math
from typing import Any, Literal
import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Calculation(StrictModel):
    output: str = Field(min_length=1)
    operation: Literal[
        "add",
        "subtract",
        "multiply",
        "divide",
        "percentage",
    ]
    # A string refers to a column; a number is a constant.
    left: str | float
    right: str | float


class ChartSpec(StrictModel):
    kind: Literal["line", "bar", "scatter", "histogram"]
    x: str
    y: str | None = None
    title: str = ""

    @model_validator(mode="after")
    def validate_axes(self):
        if self.kind != "histogram" and self.y is None:
            raise ValueError(f"{self.kind} requires a y column.")
        if self.y == self.x:
            raise ValueError("Use different x and y columns.")
        return self


class AnalysisSpec(StrictModel):
    numeric_columns: list[str] = Field(default_factory=list)
    date_column: str | None = None
    date_format: str | None = None

    calculations: list[Calculation] = Field(
        default_factory=list,
        max_length=50,
    )

    group_by: str | None = None
    aggregation: Literal[
        "sum", "mean", "median", "min", "max", "count"
    ] = "sum"

    # None: all numeric columns; []: disable trends.
    trend_columns: list[str] | None = None

    charts: list[ChartSpec] = Field(
        default_factory=list,
        max_length=12,
    )
    default_chart: bool = True


def require_columns(frame: pd.DataFrame, columns: list[str]) -> None:
    missing = sorted(set(columns) - set(frame.columns))
    if missing:
        raise ValueError(f"Missing columns: {missing}")


def numeric_series(series: pd.Series) -> pd.Series:
    converted = pd.to_numeric(series, errors="coerce")
    return converted.astype("float64").replace(
        [np.inf, -np.inf], np.nan
    )


def is_numeric(series: pd.Series) -> bool:
    return (
        pd.api.types.is_numeric_dtype(series)
        and not pd.api.types.is_bool_dtype(series)
    )


def prepare_data(
    frame: pd.DataFrame,
    spec: AnalysisSpec,
) -> tuple[pd.DataFrame, list[str]]:
    frame = frame.copy()
    warnings = []

    require_columns(frame, spec.numeric_columns)

    if spec.date_column:
        require_columns(frame, [spec.date_column])

        if spec.date_column in spec.numeric_columns:
            raise ValueError(
                "A column cannot be both a date and a numeric column."
            )

        original = frame[spec.date_column]

        if is_numeric(original):
            raise ValueError(
                "Numeric date encodings are ambiguous. Convert them "
                "to dates explicitly before analysis."
            )

        parsed = pd.to_datetime(
            original,
            format=spec.date_format,
            errors="coerce",
            utc=True,
        )

        invalid = int((original.notna() & parsed.isna()).sum())

        if invalid:
            warnings.append(
                f"{spec.date_column}: {invalid} invalid date value(s) "
                "were replaced with missing values."
            )

        frame[spec.date_column] = parsed

    for column in frame.columns:
        if column == spec.date_column:
            continue

        original = frame[column]

        if column in spec.numeric_columns or is_numeric(original):
            if pd.api.types.is_datetime64_any_dtype(original):
                raise ValueError(
                    f"Cannot convert datetime column '{column}' "
                    "to an analytical numeric column."
                )

            converted = numeric_series(original)
            invalid = int((original.notna() & converted.isna()).sum())

            if invalid:
                warnings.append(
                    f"{column}: {invalid} invalid/nonfinite numeric "
                    "value(s) were replaced with missing values."
                )

            frame[column] = converted

    def operand(value: str | float) -> pd.Series:
        if isinstance(value, str):
            require_columns(frame, [value])
            if not is_numeric(frame[value]):
                raise ValueError(
                    f"'{value}' is not numeric. Add it to numeric_columns "
                    "if numeric conversion is intended."
                )
            return numeric_series(frame[value])

        return pd.Series(float(value), index=frame.index)

    for calculation in spec.calculations:
        if calculation.output in frame.columns:
            raise ValueError(
                f"Calculation would overwrite '{calculation.output}'."
            )

        left = operand(calculation.left)
        right = operand(calculation.right)

        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            if calculation.operation == "add":
                result = left + right
            elif calculation.operation == "subtract":
                result = left - right
            elif calculation.operation == "multiply":
                result = left * right
            else:
                zeros = int(right.eq(0).sum())

                if zeros:
                    warnings.append(
                        f"{calculation.output}: {zeros} zero "
                        "denominator(s) produced missing results."
                    )

                result = left / right.replace(0, np.nan)

                if calculation.operation == "percentage":
                    result *= 100

        infinite = int(np.isinf(result.to_numpy()).sum())

        if infinite:
            warnings.append(
                f"{calculation.output}: {infinite} overflow result(s) "
                "were replaced with missing values."
            )

        frame[calculation.output] = result.replace(
            [np.inf, -np.inf], np.nan
        )

    return frame, warnings


def statistics(frame: pd.DataFrame) -> dict[str, Any]:
    """Calculate comprehensive summary statistics for all numeric columns."""
    output = {}

    for column in frame.columns:
        if not is_numeric(frame[column]):
            continue

        series = numeric_series(frame[column]).dropna()

        output[column] = {
            "count": int(len(series)),
            "missing": int(len(frame) - len(series)),
            "sum": round(float(series.sum()), 4) if len(series) else None,
            "mean": round(float(series.mean()), 4) if len(series) else None,
            "std": round(float(series.std(ddof=1)), 4) if len(series) > 1 else None,
            "min": round(float(series.min()), 4) if len(series) else None,
            "q25": round(float(series.quantile(0.25)), 4) if len(series) else None,
            "median": round(float(series.median()), 4) if len(series) else None,
            "q75": round(float(series.quantile(0.75)), 4) if len(series) else None,
            "max": round(float(series.max()), 4) if len(series) else None,
        }

    return output


def detect_trends(
    frame: pd.DataFrame,
    columns: list[str],
    date_column: str | None = None,
) -> dict[str, Any]:
    """
    Detect statistical trend direction (increasing, decreasing, stable)
    using ordinary least squares slope over time or row order.
    """
    require_columns(frame, columns)

    if date_column:
        require_columns(frame, [date_column])
        dates = frame[date_column]
        origin = dates.min()

        if pd.isna(origin):
            x_values = np.full(len(frame), np.nan)
        else:
            x_values = (
                (dates - origin).dt.total_seconds() / 86400
            ).to_numpy(dtype=float)

        unit = "day"
    else:
        x_values = np.arange(len(frame), dtype=float)
        unit = "row_position"

    output = {}

    for column in columns:
        if not is_numeric(frame[column]):
            raise ValueError(
                f"Trend column '{column}' must be numeric."
            )

        y_values = numeric_series(frame[column]).to_numpy()
        valid = np.isfinite(x_values) & np.isfinite(y_values)

        x = x_values[valid]
        y = y_values[valid]

        if len(x) < 3 or np.unique(x).size < 2:
            output[column] = {
                "status": "insufficient_data",
                "valid_points": int(len(x)),
            }
            continue

        order = np.argsort(x, kind="stable")
        x, y = x[order], y[order]

        with np.errstate(over="ignore", invalid="ignore"):
            centered_x = x - x.mean()
            centered_y = y - y.mean()

            denom = float(np.dot(centered_x, centered_x))
            if denom == 0:
                output[column] = {
                    "status": "insufficient_variance",
                    "valid_points": int(len(x)),
                }
                continue

            slope = float(np.dot(centered_x, centered_y) / denom)
            predictions = y.mean() + slope * centered_x
            residual_sum = float(np.sum((y - predictions) ** 2))
            total_sum = float(np.sum(centered_y ** 2))

        if not np.isfinite([slope, residual_sum, total_sum]).all():
            output[column] = {
                "status": "numerical_error",
                "valid_points": int(len(x)),
            }
            continue

        tolerance = (
            1e-6
            * max(1.0, float(np.max(np.abs(y))))
            / max(1.0, float(np.ptp(x)))
        )

        direction = (
            "stable"
            if abs(slope) <= tolerance
            else "increasing"
            if slope > 0
            else "decreasing"
        )

        output[column] = {
            "status": "calculated",
            "valid_points": int(len(x)),
            "direction": direction,
            "slope": round(slope, 6),
            "slope_per": unit,
            "r_squared": (
                round(float(np.clip(1 - residual_sum / total_sum, 0, 1)), 4)
                if total_sum > 0
                else 0.0
            ),
            "first_value": round(float(y[0]), 4),
            "last_value": round(float(y[-1]), 4),
            "note": "Descriptive statistical trend indicator, not engineering certification.",
        }

    return output


def detect_anomalies(frame: pd.DataFrame, numeric_cols: list[str] | None = None) -> list[dict[str, Any]]:
    """
    Detect statistical outliers using Interquartile Range (IQR = Q3 - Q1).
    Outliers defined as values < (Q1 - 1.5 * IQR) or > (Q3 + 1.5 * IQR).
    """
    cols = numeric_cols or [c for c in frame.columns if is_numeric(frame[c])]
    anomalies: list[dict[str, Any]] = []

    for col in cols:
        s = numeric_series(frame[col]).dropna()
        if len(s) < 4:
            continue

        q25 = float(s.quantile(0.25))
        q75 = float(s.quantile(0.75))
        iqr = q75 - q25

        if iqr == 0:
            continue

        lower_bound = q25 - 1.5 * iqr
        upper_bound = q75 + 1.5 * iqr

        outliers = frame[(frame[col] < lower_bound) | (frame[col] > upper_bound)]
        if not outliers.empty:
            for idx, row in outliers.head(10).iterrows():
                val = float(row[col])
                bound_exceeded = "high" if val > upper_bound else "low"
                threshold = round(upper_bound if bound_exceeded == "high" else lower_bound, 4)
                
                context_info = {}
                for key_cand in ["equipment", "equipment_id", "equipment_name", "tag", "timestamp"]:
                    if key_cand in frame.columns:
                        context_info[key_cand] = str(row[key_cand])

                anomalies.append({
                    "column": col,
                    "row_index": int(idx),
                    "value": round(val, 4),
                    "bound_exceeded": bound_exceeded,
                    "threshold": threshold,
                    "context": context_info,
                    "note": f"Statistical outlier: {val} exceeds 1.5*IQR threshold ({threshold})"
                })

    return anomalies


def compute_correlations(frame: pd.DataFrame, numeric_cols: list[str] | None = None) -> dict[str, dict[str, float]]:
    """Compute pairwise Pearson correlation coefficients for numeric columns."""
    cols = numeric_cols or [c for c in frame.columns if is_numeric(frame[c])]
    if len(cols) < 2:
        return {}

    clean_df = frame[cols].apply(pd.to_numeric, errors="coerce")
    corr_matrix = clean_df.corr(method="pearson")

    result: dict[str, dict[str, float]] = {}
    for col_a in cols:
        result[col_a] = {}
        for col_b in cols:
            val = corr_matrix.loc[col_a, col_b]
            if pd.notna(val) and math.isfinite(val):
                result[col_a][col_b] = round(float(val), 4)

    return result
