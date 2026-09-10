from pathlib import Path
import textwrap

from PIL import Image
from pptx import Presentation
from pptx.util import Inches, Pt


def generate_ppt(report: dict, output_path: str | Path) -> dict:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    presentation = Presentation()
    presentation.slide_width = Inches(13.333)
    presentation.slide_height = Inches(7.5)

    def add_text_slides(title: str, paragraphs: list[str]):
        lines = []

        for paragraph in paragraphs:
            for original_line in paragraph.splitlines() or [""]:
                wrapped = textwrap.wrap(
                    original_line,
                    width=88,
                    break_long_words=True,
                    replace_whitespace=False,
                )
                lines.extend(wrapped or [""])
            lines.append("")

        pages = [
            lines[index:index + 16]
            for index in range(0, len(lines), 16)
        ] or [[]]

        for page_number, page_lines in enumerate(pages, start=1):
            slide = presentation.slides.add_slide(
                presentation.slide_layouts[5]
            )

            slide.shapes.title.text = (
                title
                if len(pages) == 1
                else f"{title} ({page_number}/{len(pages)})"
            )

            slide.shapes.title.text_frame.paragraphs[0].font.size = Pt(26)

            box = slide.shapes.add_textbox(
                Inches(0.6),
                Inches(1.4),
                Inches(12.1),
                Inches(5.5),
            )

            frame = box.text_frame
            frame.word_wrap = False
            frame.clear()

            for index, line in enumerate(page_lines):
                paragraph = (
                    frame.paragraphs[0]
                    if index == 0
                    else frame.add_paragraph()
                )
                paragraph.text = line
                paragraph.font.size = Pt(16)
                paragraph.space_after = Pt(2)

    title_slide = presentation.slides.add_slide(
        presentation.slide_layouts[0]
    )
    title_slide.shapes.title.text = report["title"]

    title_slide.placeholders[1].text = (
        f"{report['subtitle']}\n"
        f"Prepared by: {report['prepared_by']}\n"
        f"{report['generated_at']}"
    )

    if report["approval_note"]:
        add_text_slides(
            "Approval Note — Pending Approval",
            [
                "This presentation does not constitute approval.",
                f"Decision requested: {report['decision_requested']}",
                "Approver: Not supplied",
                "Decision: Not recorded",
            ],
        )

    if report["summary"]:
        add_text_slides(
            "Executive Summary",
            [report["summary"]],
        )

    for section in report["sections"]:
        if section["paragraphs"]:
            add_text_slides(
                section["heading"],
                section["paragraphs"],
            )

        for table in section["tables"]:
            paragraphs = []

            for row_index, row in enumerate(table["rows"], start=1):
                paragraphs.append(
                    f"Row {row_index}: "
                    + "; ".join(
                        f"{column}: {value}"
                        for column, value in zip(
                            table["columns"],
                            row,
                        )
                    )
                )

            if table["note"]:
                paragraphs.append(table["note"])

            add_text_slides(
                table["title"],
                paragraphs,
            )

        for figure in section["figures"]:
            slide = presentation.slides.add_slide(
                presentation.slide_layouts[5]
            )
            slide.shapes.title.text = section["heading"]

            with Image.open(figure["path"]) as image:
                image_width, image_height = image.size

            max_width = 12.0
            max_height = 5.3
            scale = min(
                max_width / image_width,
                max_height / image_height,
            )

            width = image_width * scale
            height = image_height * scale

            slide.shapes.add_picture(
                figure["path"],
                Inches((13.333 - width) / 2),
                Inches(1.35),
                width=Inches(width),
                height=Inches(height),
            )

            if figure["caption"]:
                add_text_slides(
                    "Figure Notes",
                    [figure["caption"]],
                )

    if report["sources"]:
        add_text_slides("Sources and References", report["sources"])

    if report["warnings"]:
        add_text_slides("Limitations and Review Notes", report["warnings"])

    presentation.save(output_path)

    return {
        "path": str(output_path.resolve()),
        "warnings": [
            "PowerPoint tables are rendered as paginated row text. "
            "Review slide layout before presenting."
        ],
    }
