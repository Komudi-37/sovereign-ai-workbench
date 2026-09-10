from pathlib import Path
import re

from openpyxl import Workbook
from openpyxl.drawing.image import Image
from openpyxl.styles import Alignment, Font, PatternFill


def _safe_cell(value: str) -> str:
    if value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def generate_excel(report: dict, output_path: str | Path) -> dict:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    workbook = Workbook()
    summary = workbook.active
    summary.title = "Report"

    used_names = {"Report"}

    def new_sheet(title):
        base = re.sub(r"[\[\]:*?/\\]", "_", title).strip("'")
        base = base[:31] or "Sheet"

        name = base
        suffix = 2

        while name.lower() in {item.lower() for item in used_names}:
            ending = f"_{suffix}"
            name = base[:31 - len(ending)] + ending
            suffix += 1

        used_names.add(name)
        return workbook.create_sheet(name)

    def write_text(sheet, row, column, text):
        # Excel has a 32,767-character cell limit. Continue long text
        # in following rows instead of silently truncating it.
        text = str(text)

        chunks = [
            text[index:index + 30_000]
            for index in range(0, len(text), 30_000)
        ] or [""]

        for chunk in chunks:
            cell = sheet.cell(row=row, column=column)
            cell.value = _safe_cell(chunk)
            cell.alignment = Alignment(
                wrap_text=True,
                vertical="top",
            )
            row += 1

        return row

    row = 1

    for label, value in [
        ("Title", report["title"]),
        ("Subtitle", report["subtitle"]),
        ("Prepared by", report["prepared_by"]),
        ("Generated at", report["generated_at"]),
        ("Summary", report["summary"]),
    ]:
        summary.cell(row, 1, label)
        row = write_text(summary, row, 2, value)

    if report["approval_note"]:
        for label, value in [
            ("Approval status", "PENDING APPROVAL"),
            ("Decision requested", report["decision_requested"]),
            ("Approver", "Not supplied"),
            ("Decision", "Not recorded"),
        ]:
            summary.cell(row, 1, label)
            row = write_text(summary, row, 2, value)

    figure_items = []

    for section in report["sections"]:
        row += 1
        summary.cell(row, 1, _safe_cell(section["heading"]))
        summary.cell(row, 1).font = Font(bold=True)
        row += 1

        for paragraph in section["paragraphs"]:
            row = write_text(summary, row, 2, paragraph)

        for table in section["tables"]:
            sheet = new_sheet(table["title"])

            for column, header in enumerate(table["columns"], start=1):
                cell = sheet.cell(1, column, _safe_cell(header))
                cell.font = Font(bold=True, color="FFFFFF")
                cell.fill = PatternFill(
                    "solid",
                    fgColor="17365D",
                )

            for row_number, values in enumerate(table["rows"], start=2):
                for column_number, value in enumerate(values, start=1):
                    sheet.cell(
                        row_number,
                        column_number,
                        _safe_cell(value),
                    )

            sheet.freeze_panes = "A2"

            if table["rows"]:
                sheet.auto_filter.ref = sheet.dimensions

            for column in sheet.columns:
                letter = column[0].column_letter
                sheet.column_dimensions[letter].width = 24

                for cell in column:
                    cell.alignment = Alignment(
                        wrap_text=True,
                        vertical="top",
                    )

            if table["note"]:
                write_text(
                    sheet,
                    len(table["rows"]) + 3,
                    1,
                    table["note"],
                )

        figure_items.extend(section["figures"])

    if figure_items:
        sheet = new_sheet("Figures")
        image_row = 1

        for figure in figure_items:
            sheet.cell(
                image_row,
                1,
                _safe_cell(figure["caption"]),
            )

            image = Image(figure["path"])
            scale = min(1.0, 850 / image.width, 500 / image.height)
            image.width *= scale
            image.height *= scale

            sheet.add_image(image, f"A{image_row + 1}")

            image_row += int(image.height / 20) + 5

    if report["sources"] or report["warnings"]:
        sheet = new_sheet("References")
        ref_row = 1

        for label, items in [
            ("Sources", report["sources"]),
            ("Warnings", report["warnings"]),
        ]:
            sheet.cell(ref_row, 1, label).font = Font(bold=True)
            ref_row += 1

            for item in items:
                ref_row = write_text(sheet, ref_row, 1, item)

        sheet.column_dimensions["A"].width = 100

    summary.column_dimensions["A"].width = 25
    summary.column_dimensions["B"].width = 100
    summary.freeze_panes = "B2"

    workbook.save(output_path)

    return {
        "path": str(output_path.resolve()),
        "warnings": [
            "Report table cells are exported as display text. "
            "Use the Data Analysis Agent's data exports for further "
            "numerical processing."
        ],
    }
