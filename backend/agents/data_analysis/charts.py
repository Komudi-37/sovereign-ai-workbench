from pathlib import Path
from threading import Lock

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from .calculator import (
    ChartSpec,
    is_numeric,
    numeric_series,
    require_columns,
)


_PLOT_LOCK = Lock()


class ChartGenerator:
    def create(
        self,
        frame: pd.DataFrame,
        spec: ChartSpec,
        output_path: Path,
    ) -> dict:
        columns = [spec.x] + ([spec.y] if spec.y else [])
        require_columns(frame, columns)

        data = frame[columns].copy()
        warnings = []

        numeric_columns = (
            [spec.x]
            if spec.kind == "histogram"
            else [spec.y]
        )

        if spec.kind == "scatter":
            numeric_columns.append(spec.x)

        for column in numeric_columns:
            if not is_numeric(data[column]):
                raise ValueError(
                    f"Chart column '{column}' must be numeric."
                )
            data[column] = numeric_series(data[column])

        data = data.dropna(subset=columns)

        if data.empty:
            raise ValueError("Chart has no valid rows.")

        if spec.kind == "bar":
            if data[spec.x].duplicated().any():
                raise ValueError(
                    "Bar categories repeat. Aggregate using group_by first."
                )

            if len(data) > 50:
                raise ValueError(
                    "Bar chart exceeds 50 categories. Filter or aggregate."
                )

        if spec.kind == "line" and (
            is_numeric(data[spec.x])
            or pd.api.types.is_datetime64_any_dtype(data[spec.x])
        ):
            data = data.sort_values(spec.x, kind="stable")

        if spec.kind in {"line", "scatter"} and len(data) > 10_000:
            positions = np.linspace(
                0, len(data) - 1, 10_000, dtype=int
            )
            data = data.iloc[positions]
            warnings.append(
                "Plot sampled to 10,000 points; calculations use all rows."
            )

        output_path.parent.mkdir(parents=True, exist_ok=True)

        with _PLOT_LOCK:
            figure, axis = plt.subplots(figsize=(10, 5))

            try:
                if spec.kind == "histogram":
                    axis.hist(
                        data[spec.x],
                        bins=30,
                        edgecolor="white",
                    )
                    axis.set_ylabel("Count")

                elif spec.kind == "scatter":
                    axis.scatter(
                        data[spec.x],
                        data[spec.y],
                        s=20,
                        alpha=0.7,
                    )
                    axis.set_ylabel(spec.y)

                elif spec.kind == "bar":
                    axis.bar(
                        data[spec.x].astype(str),
                        data[spec.y],
                    )
                    axis.set_ylabel(spec.y)
                    axis.tick_params(axis="x", rotation=45)

                else:
                    axis.plot(
                        data[spec.x],
                        data[spec.y],
                        linewidth=1.5,
                    )
                    axis.set_ylabel(spec.y)

                axis.set_xlabel(spec.x)
                axis.set_title(
                    spec.title
                    or (
                        f"Distribution of {spec.x}"
                        if spec.kind == "histogram"
                        else f"{spec.y} versus {spec.x}"
                    )
                )
                axis.grid(alpha=0.2)
                figure.tight_layout()
                figure.savefig(output_path, dpi=150)

            finally:
                plt.close(figure)

        return {
            "kind": spec.kind,
            "path": str(output_path.resolve()),
            "plotted_rows": int(len(data)),
            "warnings": warnings,
        }
