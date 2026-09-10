from hashlib import sha256
from pathlib import Path
from threading import Lock
from xml.sax.saxutils import escape
import os

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Image,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)


_FONT_LOCK = Lock()


def _font_name() -> tuple[str, list[str]]:
    configured = os.getenv("REPORT_PDF_FONT")

    candidates = (
        [Path(configured)]
        if configured
        else [
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
            Path("/usr/share/fonts/dejavu/DejaVuSans.ttf"),
            Path("C:/Windows/Fonts/arial.ttf"),
            Path("/Library/Fonts/Arial.ttf"),
        ]
    )

    for path in candidates:
        if path.is_file():
            name = "ReportFont_" + sha256(
                str(path.resolve()).encode()
            ).hexdigest()[:12]

            with _FONT_LOCK:
                if name not in pdfmetrics.getRegisteredFontNames():
                    pdfmetrics.registerFont(TTFont(name, str(path)))

            return name, []

    if configured:
        raise FileNotFoundError(
            f"REPORT_PDF_FONT does not exist: {configured}"
        )

    return "Helvetica", [
        "PDF used Helvetica. Non-Latin text requires a suitable "
        "REPORT_PDF_FONT TrueType font."
    ]


def generate_pdf(report: dict, output_path: str | Path) -> dict:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    font_name, warnings = _font_name()

    if font_name == "Helvetica":
        # Fail explicitly for unsupported Unicode rather than quietly
        # creating a PDF containing missing-glyph boxes.
        import json

        try:
            json.dumps(
                report,
                ensure_ascii=False,
            ).encode("cp1252")
        except UnicodeEncodeError as exc:
            raise ValueError(
                "This report contains Unicode text requiring a PDF font. "
                "Set REPORT_PDF_FONT to a suitable .ttf file."
            ) from exc

    styles = getSampleStyleSheet()

    body = ParagraphStyle(
        "ReportBody",
        parent=styles["BodyText"],
        fontName=font_name,
        fontSize=9,
        leading=13,
        spaceAfter=6,
        alignment=TA_LEFT,
        splitLongWords=True,
    )

    title_style = ParagraphStyle(
        "ReportTitle",
        parent=body,
        fontSize=20,
        leading=25,
        spaceAfter=16,
    )

    heading_style = ParagraphStyle(
        "ReportHeading",
        parent=body,
        fontSize=13,
        leading=17,
        spaceBefore=12,
        spaceAfter=8,
        textColor=colors.HexColor("#17365D"),
    )

    document = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        leftMargin=42,
        rightMargin=42,
        topMargin=42,
        bottomMargin=42,
        title=report["title"],
        author=report["prepared_by"],
    )

    story = []

    def paragraph(text: str, style=body):
        safe = escape(text).replace("\n", "<br/>")
        story.append(Paragraph(safe, style))

    paragraph(report["title"], title_style)

    if report["subtitle"]:
        paragraph(report["subtitle"])

    paragraph(
        f"Prepared by: {report['prepared_by']}\n"
        f"Generated at: {report['generated_at']}"
    )

    if report["approval_note"]:
        paragraph("Approval Note — PENDING APPROVAL", heading_style)
        paragraph(
            "This document is a request for review, not an approval "
            "or operational authorization."
        )
        paragraph(
            f"Decision requested: {report['decision_requested']}"
        )
        paragraph(
            "Approver: ____________________\n"
            "Decision: ____________________\n"
            "Date: ________________________"
        )

    if report["summary"]:
        paragraph("Executive Summary", heading_style)
        paragraph(report["summary"])

    for section in report["sections"]:
        paragraph(section["heading"], heading_style)

        for text in section["paragraphs"]:
            paragraph(text)

        for table in section["tables"]:
            paragraph(table["title"], heading_style)

            # Row-wise rendering is robust for wide tables and long cells.
            for row_number, row in enumerate(table["rows"], start=1):
                paragraph(f"Row {row_number}")

                for column, value in zip(table["columns"], row):
                    paragraph(f"{column}: {value}")

                story.append(Spacer(1, 5))

            if table["note"]:
                paragraph(table["note"])

        for figure in section["figures"]:
            with PILImage.open(figure["path"]) as image:
                width, height = image.size

            scale = min(
                document.width / width,
                (5.5 * inch) / height,
            )

            story.append(
                Image(
                    figure["path"],
                    width=width * scale,
                    height=height * scale,
                )
            )

            if figure["caption"]:
                paragraph(figure["caption"])

    if report["sources"]:
        paragraph("Sources and References", heading_style)
        for source in report["sources"]:
            paragraph(source)

    all_warnings = report["warnings"] + warnings

    if all_warnings:
        paragraph("Limitations and Review Notes", heading_style)
        for warning in all_warnings:
            paragraph(warning)

    def page_footer(canvas, doc):
        canvas.saveState()
        canvas.setFont(font_name, 8)
        canvas.drawRightString(
            A4[0] - 42,
            24,
            f"Page {doc.page}",
        )
        canvas.restoreState()

    document.build(
        story,
        onFirstPage=page_footer,
        onLaterPages=page_footer,
    )

    return {
        "path": str(output_path.resolve()),
        "warnings": warnings,
    }
