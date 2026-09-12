"""
Professional Local Excel (XLSX) Deliverable Generator for Sovereign AI Workbench.

Generates structured multi-sheet workbooks with:
- Sheet 1: "Summary" (Metadata, Status, Executive Summary, Key Findings, Warnings)
- Sheet 2: "Statistics" (Descriptive statistics with proper numeric cell formatting)
- Sheet 3: "Trends" (Trend direction, slope, R², boundary values)
- Sheet 4: "Anomalies" (Statistical outliers, bounds exceeded, equipment context)
- Optional sheets: "Data Preview", "Figures" (embedded charts), "References"

Features:
- Frozen header rows and auto-filter on table sheets
- Auto-adjusted column widths
- Formula injection protection (_safe_cell for strings)
- Pure local execution via openpyxl (zero cloud calls)
"""

from pathlib import Path
import re
from typing import Any

from openpyxl import Workbook
from openpyxl.drawing.image import Image
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter


def _parse_numeric(val_str: str) -> int | float | None:
    """Attempt to parse string as integer or float, avoiding ID code corruption."""
    try:
        # Check integer first
        if val_str.isdigit() or (val_str.startswith("-") and val_str[1:].isdigit()):
            # Avoid stripping leading zero from codes like '007' or '0123'
            if len(val_str) > 1 and val_str.startswith("0"):
                return None
            return int(val_str)
        
        # Check float
        f = float(val_str)
        return f
    except (ValueError, TypeError):
        return None


def _safe_cell(value: Any) -> Any:
    """
    Ensure spreadsheet cell value is safe from formula injection.
    Numeric values (int, float) are written as native numbers.
    Strings starting with formula injection chars (=, +, -, @) are escaped with a leading quote.
    """
    if value is None:
        return ""
    if isinstance(value, (int, float)):
        return value

    val_str = str(value).strip()
    if not val_str:
        return ""

    num = _parse_numeric(val_str)
    if num is not None:
        return num

    # Formula injection protection for strings
    if val_str.startswith(("=", "+", "-", "@")):
        return "'" + val_str

    return val_str


def _format_cell_number(cell, header_name: str, val: Any) -> None:
    """Apply standard Excel number formatting based on column name and value type."""
    h_lower = header_name.lower()
    if isinstance(val, float):
        if any(term in h_lower for term in ("r2", "r²", "slope", "rate")):
            cell.number_format = "0.0000"
        elif any(term in h_lower for term in ("percent", "pct", "confidence")):
            cell.number_format = "0.0%"
        else:
            cell.number_format = "0.00"
    elif isinstance(val, int):
        if any(term in h_lower for term in ("count", "rows", "total", "missing", "sample")):
            cell.number_format = "#,##0"
        else:
            cell.number_format = "0"


def generate_excel(report: dict, output_path: str | Path) -> dict:
    """
    Generate an enterprise-grade XLSX report workbook from a ReportSpec payload.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    workbook = Workbook()
    
    # Styles
    navy_fill = PatternFill(start_color="17365D", end_color="17365D", fill_type="solid")
    header_font = Font(name="Segoe UI", size=11, bold=True, color="FFFFFF")
    bold_font = Font(name="Segoe UI", size=10, bold=True)
    regular_font = Font(name="Segoe UI", size=10)
    title_font = Font(name="Segoe UI", size=14, bold=True, color="17365D")
    
    alert_fill = PatternFill(start_color="FFF0F2", end_color="FFF0F2", fill_type="solid")
    alert_font = Font(name="Segoe UI", size=10, color="991B1B", bold=True)
    
    thin_side = Side(border_style="thin", color="E5E7EB")
    cell_border = Border(top=thin_side, bottom=thin_side, left=thin_side, right=thin_side)

    # -------------------------------------------------------------
    # Sheet 1: "Summary"
    # -------------------------------------------------------------
    summary = workbook.active
    summary.title = "Summary"
    used_sheet_names = {"Summary"}

    def new_sheet(title: str):
        # Clean sheet title to max 31 valid Excel chars
        base = re.sub(r"[\[\]:*?/\\]", "_", title).strip("'")
        base = base[:31] or "Sheet"
        name = base
        suffix = 2
        while name.lower() in {item.lower() for item in used_sheet_names}:
            ending = f"_{suffix}"
            name = base[:31 - len(ending)] + ending
            suffix += 1
        used_sheet_names.add(name)
        return workbook.create_sheet(name)

    def write_summary_field(sheet, row: int, label: str, value: Any):
        cell_lbl = sheet.cell(row=row, column=1, value=_safe_cell(label))
        cell_lbl.font = bold_font
        cell_lbl.alignment = Alignment(vertical="top")
        
        val_str = str(value) if value is not None else ""
        cell_val = sheet.cell(row=row, column=2, value=_safe_cell(val_str))
        cell_val.font = regular_font
        cell_val.alignment = Alignment(wrap_text=True, vertical="top")
        return row + 1

    # Write Title block
    s_row = 1
    summary.cell(s_row, 1, "REPORT SUMMARY & OVERVIEW").font = title_font
    s_row += 2

    metadata_fields = [
        ("Report Title", report.get("title", "Analysis Report")),
        ("Subtitle / Objective", report.get("subtitle", "")),
        ("Prepared By", report.get("prepared_by", "Sovereign AI Workbench")),
        ("Generated At", report.get("generated_at", "")),
        ("Workflow / Status", "PENDING FORMAL APPROVAL" if report.get("approval_note") else "COMPLETED"),
    ]
    if report.get("approval_note"):
        metadata_fields.extend([
            ("Decision Requested", report.get("decision_requested", "Review findings and record approval.")),
            ("Approver", "Not supplied (Pending Review)"),
            ("Approval Status", "Pending Review"),
        ])

    for label, val in metadata_fields:
        if val:
            s_row = write_summary_field(summary, s_row, label, val)

    s_row += 1
    summary.cell(s_row, 1, "Executive Summary:").font = bold_font
    s_row += 1
    
    summary_text = report.get("summary", "")
    for chunk in [summary_text[i:i+30000] for i in range(0, max(1, len(summary_text)), 30000)]:
        c = summary.cell(s_row, 1, _safe_cell(chunk))
        c.font = regular_font
        c.alignment = Alignment(wrap_text=True, vertical="top")
        summary.merge_cells(start_row=s_row, start_column=1, end_row=s_row, end_column=3)
        s_row += 1

    # Add warnings or key findings in Summary
    if report.get("warnings"):
        s_row += 1
        summary.cell(s_row, 1, "Review Warnings / Limitations:").font = bold_font
        s_row += 1
        for w in report["warnings"]:
            c = summary.cell(s_row, 1, f"• {_safe_cell(w)}")
            c.font = Font(name="Segoe UI", size=9, color="B45309")
            summary.merge_cells(start_row=s_row, start_column=1, end_row=s_row, end_column=3)
            s_row += 1

    summary.column_dimensions["A"].width = 28
    summary.column_dimensions["B"].width = 65
    summary.column_dimensions["C"].width = 25
    summary.freeze_panes = "B2"

    # -------------------------------------------------------------
    # Sheets 2-4 and other Data Tables
    # -------------------------------------------------------------
    def map_canonical_sheet_name(title: str) -> str:
        t = title.strip().lower()
        if "anomal" in t or "outlier" in t:
            return "Anomalies"
        if "trend" in t:
            return "Trends"
        if "statistic" in t:
            return "Statistics"
        if "preview" in t:
            return "Data Preview"
        return title[:31]

    figure_items = []

    for section in report.get("sections", []):
        for table in section.get("tables", []):
            canonical_name = map_canonical_sheet_name(table["title"])
            sheet = new_sheet(canonical_name)

            headers = table.get("columns", [])
            rows = table.get("rows", [])
            is_anomaly_sheet = (canonical_name == "Anomalies")

            # Header row styling
            sheet.row_dimensions[1].height = 26
            for col_idx, header in enumerate(headers, start=1):
                cell = sheet.cell(row=1, column=col_idx, value=_safe_cell(header))
                cell.font = header_font
                cell.fill = navy_fill
                cell.alignment = Alignment(horizontal="center" if col_idx > 2 else "left", vertical="center")
                cell.border = cell_border

            # Data rows
            for row_idx, row in enumerate(rows, start=2):
                sheet.row_dimensions[row_idx].height = 20
                for col_idx, raw_value in enumerate(row, start=1):
                    header_name = headers[col_idx - 1] if col_idx - 1 < len(headers) else ""
                    val = _safe_cell(raw_value)
                    cell = sheet.cell(row=row_idx, column=col_idx, value=val)
                    cell.font = regular_font
                    cell.border = cell_border
                    
                    # Numeric formatting
                    _format_cell_number(cell, header_name, val)

                    # Alignment
                    if isinstance(val, (int, float)):
                        cell.alignment = Alignment(horizontal="right", vertical="center")
                    else:
                        cell.alignment = Alignment(horizontal="left", vertical="center")

                    # Highlight anomalies if on Anomalies sheet
                    if is_anomaly_sheet:
                        cell.fill = alert_fill
                        if header_name.lower() in ("value", "bound", "threshold", "bound_direction"):
                            cell.font = alert_font

            # Frozen panes & auto-filter
            sheet.freeze_panes = "A2"
            if rows:
                sheet.auto_filter.ref = sheet.dimensions

            # Auto-adjust column widths
            for col in sheet.columns:
                col_letter = get_column_letter(col[0].column)
                max_len = 0
                for cell in col:
                    if cell.value:
                        lines = str(cell.value).split("\n")
                        max_len = max(max_len, max(len(l) for l in lines))
                sheet.column_dimensions[col_letter].width = max(14, min(max_len + 4, 42))

            # Table note if present
            if table.get("note"):
                note_row = len(rows) + 3
                n_cell = sheet.cell(row=note_row, column=1, value=_safe_cell(table["note"]))
                n_cell.font = Font(name="Segoe UI", size=9, italic=True, color="6B7280")

        figure_items.extend(section.get("figures", []))

    # -------------------------------------------------------------
    # Sheet: "Figures" (Embedded Local Charts)
    # -------------------------------------------------------------
    if figure_items:
        fig_sheet = new_sheet("Figures")
        fig_sheet.cell(1, 1, "LOCALLY GENERATED VISUALIZATIONS").font = title_font
        fig_row = 3

        for fig in figure_items:
            fig_path = Path(fig["path"])
            if fig_path.is_file():
                caption = fig.get("caption") or fig_path.name
                fig_sheet.cell(fig_row, 1, f"Figure: {_safe_cell(caption)}").font = bold_font
                fig_row += 1

                try:
                    img = Image(str(fig_path))
                    # Scale nicely to max 780x460
                    max_w, max_h = 780, 460
                    scale = min(1.0, max_w / max(1, img.width), max_h / max(1, img.height))
                    img.width = int(img.width * scale)
                    img.height = int(img.height * scale)

                    fig_sheet.add_image(img, f"A{fig_row}")
                    rows_spanned = max(15, int(img.height / 20) + 2)
                    fig_row += rows_spanned + 2
                except Exception as img_err:
                    fig_sheet.cell(fig_row, 1, f"[Image load warning: {img_err}]").font = regular_font
                    fig_row += 2

        fig_sheet.column_dimensions["A"].width = 90

    # -------------------------------------------------------------
    # Sheet: "References"
    # -------------------------------------------------------------
    if report.get("sources") or report.get("warnings"):
        ref_sheet = new_sheet("References")
        r_row = 1
        ref_sheet.cell(r_row, 1, "SOURCES, EVIDENCE & VERIFICATION REFERENCES").font = title_font
        r_row += 2

        if report.get("sources"):
            ref_sheet.cell(r_row, 1, "Data Sources & Document Citations:").font = bold_font
            r_row += 1
            for src in report["sources"]:
                ref_sheet.cell(r_row, 1, f"• {_safe_cell(src)}").font = regular_font
                r_row += 1
            r_row += 1

        if report.get("warnings"):
            ref_sheet.cell(r_row, 1, "Technical Limitations & Audit Notes:").font = bold_font
            r_row += 1
            for warn in report["warnings"]:
                ref_sheet.cell(r_row, 1, f"• {_safe_cell(warn)}").font = regular_font
                r_row += 1

        ref_sheet.column_dimensions["A"].width = 110

    workbook.save(output_path)

    return {
        "path": str(output_path.resolve()),
        "warnings": [],
    }
