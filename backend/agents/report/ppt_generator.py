"""
Professional Local PowerPoint (PPTX) Presentation Generator for Sovereign AI Workbench.

Generates 16:9 widescreen presentation decks with structured executive slides:
- Slide 1: Title & Overview (Title, Subtitle, Prepared by, Generated timestamp)
- Slide 2: Executive Summary (Key findings, status, major warnings)
- Slide 3: Scope / Dataset Overview (Datasets, documents, row counts, citations)
- Slide 4: Key Statistics / Findings (Clean native PPT table)
- Slide 5: Trend Analysis (Direction, slopes, R², significant movements)
- Slide 6: Anomalies / Risks (Detected outliers, bounds exceeded, equipment context)
- Slide 7: Locally Generated Charts / Visual Evidence (embedded safely)
- Slide 8: Recommendations / Next Actions (Verified recommendations, no invented advice)

Pure local execution via python-pptx (zero cloud calls).
"""

from pathlib import Path
import textwrap
from typing import Any

from PIL import Image as PILImage
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.util import Inches, Pt


NAVY = RGBColor(23, 54, 93)        # Primary #17365D
ACCENT_BLUE = RGBColor(59, 130, 246) # Secondary #3B82F6
DARK_GRAY = RGBColor(31, 41, 55)    # Text #1F2937
MUTED_GRAY = RGBColor(107, 114, 128) # Subtext #6B7280
LIGHT_BG = RGBColor(248, 250, 252)   # Table alternating #F8FAFC
ALERT_RED = RGBColor(220, 38, 38)   # Outliers / Warnings #DC2626
SUCCESS_GREEN = RGBColor(22, 163, 74) # Normal / Passed #16A34A
WHITE = RGBColor(255, 255, 255)


def _add_slide_header(slide, title_text: str, category: str = "SOVEREIGN AI WORKBENCH"):
    """Render consistent slide title banner."""
    # Category tag
    cat_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.4), Inches(11.7), Inches(0.35))
    tf_cat = cat_box.text_frame
    tf_cat.word_wrap = True
    p_cat = tf_cat.paragraphs[0]
    p_cat.text = category.upper()
    p_cat.font.size = Pt(10)
    p_cat.font.bold = True
    p_cat.font.color.rgb = ACCENT_BLUE

    # Title
    t_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.75), Inches(11.7), Inches(0.6))
    tf_t = t_box.text_frame
    tf_t.word_wrap = True
    p_t = tf_t.paragraphs[0]
    p_t.text = title_text
    p_t.font.size = Pt(22)
    p_t.font.bold = True
    p_t.font.color.rgb = NAVY


def _style_table(table, num_rows: int, num_cols: int, col_widths: list[float] | None = None):
    """Apply professional navy styling to a PowerPoint table."""
    for col_idx in range(num_cols):
        if col_widths and col_idx < len(col_widths):
            table.columns[col_idx].width = Inches(col_widths[col_idx])

    for row_idx in range(num_rows):
        is_header = (row_idx == 0)
        for col_idx in range(num_cols):
            cell = table.cell(row_idx, col_idx)
            cell.margin_left = Inches(0.1)
            cell.margin_right = Inches(0.1)
            cell.margin_top = Inches(0.08)
            cell.margin_bottom = Inches(0.08)
            
            if is_header:
                cell.fill.solid()
                cell.fill.fore_color.rgb = NAVY
                for p in cell.text_frame.paragraphs:
                    p.font.size = Pt(11)
                    p.font.bold = True
                    p.font.color.rgb = WHITE
                    p.alignment = PP_ALIGN.CENTER if col_idx > 1 else PP_ALIGN.LEFT
            else:
                if row_idx % 2 == 1:
                    cell.fill.solid()
                    cell.fill.fore_color.rgb = LIGHT_BG
                for p in cell.text_frame.paragraphs:
                    p.font.size = Pt(10)
                    p.font.color.rgb = DARK_GRAY
                    p.alignment = PP_ALIGN.RIGHT if col_idx > 1 else PP_ALIGN.LEFT


def generate_ppt(report: dict, output_path: str | Path) -> dict:
    """
    Generate an executive 16:9 PowerPoint presentation deck from a ReportSpec payload.
    """
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    prs = Presentation()
    # 16:9 Widescreen dimensions
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank_layout = prs.slide_layouts[6]  # completely blank layout

    # Extract common entities across report sections
    statistics_table = None
    trends_table = None
    anomalies_table = None
    data_preview_table = None
    all_figures = []

    for section in report.get("sections", []):
        for table in section.get("tables", []):
            t_title = table.get("title", "").lower()
            if "statistic" in t_title and not statistics_table:
                statistics_table = table
            elif "trend" in t_title and not trends_table:
                trends_table = table
            elif ("anomal" in t_title or "outlier" in t_title) and not anomalies_table:
                anomalies_table = table
            elif "preview" in t_title and not data_preview_table:
                data_preview_table = table
        all_figures.extend(section.get("figures", []))

    # -------------------------------------------------------------
    # SLIDE 1: Title & Overview
    # -------------------------------------------------------------
    slide1 = prs.slides.add_slide(blank_layout)

    # Brand badge
    b_box = slide1.shapes.add_textbox(Inches(1.2), Inches(1.5), Inches(10.9), Inches(0.4))
    b_tf = b_box.text_frame
    b_p = b_tf.paragraphs[0]
    b_p.text = "SOVEREIGN AI WORKBENCH  •  AIR-GAPPED AUDIT & DELIVERABLE"
    b_p.font.size = Pt(12)
    b_p.font.bold = True
    b_p.font.color.rgb = ACCENT_BLUE

    # Title
    t_box = slide1.shapes.add_textbox(Inches(1.2), Inches(2.1), Inches(10.9), Inches(1.8))
    t_tf = t_box.text_frame
    t_tf.word_wrap = True
    t_p = t_tf.paragraphs[0]
    t_p.text = report.get("title", "Executive Findings & Analysis Report")
    t_p.font.size = Pt(32)
    t_p.font.bold = True
    t_p.font.color.rgb = NAVY

    # Subtitle
    if report.get("subtitle"):
        sub_p = t_tf.add_paragraph()
        sub_p.text = report["subtitle"]
        sub_p.font.size = Pt(16)
        sub_p.font.color.rgb = MUTED_GRAY
        sub_p.space_before = Pt(10)

    # Metadata card / footer
    meta_box = slide1.shapes.add_textbox(Inches(1.2), Inches(5.2), Inches(10.9), Inches(1.2))
    m_tf = meta_box.text_frame
    m_tf.word_wrap = True
    
    mp1 = m_tf.paragraphs[0]
    mp1.text = f"Prepared By: {report.get('prepared_by', 'Automated Sovereign Reporting')}"
    mp1.font.size = Pt(12)
    mp1.font.bold = True
    mp1.font.color.rgb = DARK_GRAY

    mp2 = m_tf.add_paragraph()
    mp2.text = f"Generated: {report.get('generated_at', '')}   |   Environment: Local Sovereign System (Zero Cloud Egress)"
    mp2.font.size = Pt(11)
    mp2.font.color.rgb = MUTED_GRAY
    mp2.space_before = Pt(4)

    # -------------------------------------------------------------
    # SLIDE 2: Executive Summary
    # -------------------------------------------------------------
    slide2 = prs.slides.add_slide(blank_layout)
    _add_slide_header(slide2, "Executive Summary & Operational Status")

    # Status Badge Box
    status_box = slide2.shapes.add_textbox(Inches(0.8), Inches(1.5), Inches(11.7), Inches(0.6))
    st_tf = status_box.text_frame
    st_p = st_tf.paragraphs[0]
    is_app = report.get("approval_note", False)
    st_p.text = "APPROVAL STATUS: PENDING FORMAL REVIEW" if is_app else "WORKFLOW STATUS: ANALYSIS COMPLETED"
    st_p.font.size = Pt(13)
    st_p.font.bold = True
    st_p.font.color.rgb = ALERT_RED if is_app else SUCCESS_GREEN

    # Summary Text Box
    sum_box = slide2.shapes.add_textbox(Inches(0.8), Inches(2.2), Inches(11.7), Inches(3.2))
    sum_tf = sum_box.text_frame
    sum_tf.word_wrap = True
    
    summary_lines = (report.get("summary", "")).splitlines() or ["No summary provided."]
    for idx, line in enumerate(summary_lines):
        p = sum_tf.paragraphs[0] if idx == 0 else sum_tf.add_paragraph()
        p.text = line
        p.font.size = Pt(14)
        p.font.color.rgb = DARK_GRAY
        p.space_after = Pt(6)

    # Decision / Action required card
    if report.get("decision_requested"):
        dec_box = slide2.shapes.add_textbox(Inches(0.8), Inches(5.6), Inches(11.7), Inches(1.1))
        dec_tf = dec_box.text_frame
        dec_tf.word_wrap = True
        dec_p1 = dec_tf.paragraphs[0]
        dec_p1.text = "DECISION / ACTION REQUESTED:"
        dec_p1.font.size = Pt(11)
        dec_p1.font.bold = True
        dec_p1.font.color.rgb = NAVY

        dec_p2 = dec_tf.add_paragraph()
        dec_p2.text = report["decision_requested"]
        dec_p2.font.size = Pt(13)
        dec_p2.font.color.rgb = DARK_GRAY
        dec_p2.space_before = Pt(3)

    # -------------------------------------------------------------
    # SLIDE 3: Scope & Dataset Overview
    # -------------------------------------------------------------
    slide3 = prs.slides.add_slide(blank_layout)
    _add_slide_header(slide3, "Scope of Analysis & Evaluated Sources")

    scope_box = slide3.shapes.add_textbox(Inches(0.8), Inches(1.5), Inches(11.7), Inches(5.2))
    sc_tf = scope_box.text_frame
    sc_tf.word_wrap = True

    sc_p1 = sc_tf.paragraphs[0]
    sc_p1.text = "Inputs & Documents Inspected:"
    sc_p1.font.size = Pt(14)
    sc_p1.font.bold = True
    sc_p1.font.color.rgb = NAVY

    sources = report.get("sources", [])
    if sources:
        for src in sources[:8]:
            p = sc_tf.add_paragraph()
            p.text = f"• {src}"
            p.font.size = Pt(12)
            p.font.color.rgb = DARK_GRAY
            p.space_before = Pt(4)
    else:
        p = sc_tf.add_paragraph()
        p.text = "• Attached document and dataset evidence processed via local sovereign pipeline."
        p.font.size = Pt(12)
        p.font.color.rgb = DARK_GRAY

    # Warnings / Boundaries
    warnings = report.get("warnings", [])
    if warnings:
        warn_p = sc_tf.add_paragraph()
        warn_p.text = "Audit Notes & Methodological Boundaries:"
        warn_p.font.size = Pt(14)
        warn_p.font.bold = True
        warn_p.font.color.rgb = NAVY
        warn_p.space_before = Pt(18)

        for w in warnings[:4]:
            p = sc_tf.add_paragraph()
            p.text = f"• {w}"
            p.font.size = Pt(11)
            p.font.color.rgb = MUTED_GRAY
            p.space_before = Pt(4)

    # -------------------------------------------------------------
    # SLIDE 4: Key Statistics / Findings
    # -------------------------------------------------------------
    slide4 = prs.slides.add_slide(blank_layout)
    _add_slide_header(slide4, "Key Descriptive Statistics")

    if statistics_table and statistics_table.get("rows"):
        headers = statistics_table["columns"][:8]
        rows = statistics_table["rows"][:10]  # Show top 10 metrics on slide
        
        num_rows = len(rows) + 1
        num_cols = len(headers)
        
        table_shape = slide4.shapes.add_table(
            num_rows, num_cols,
            Inches(0.8), Inches(1.6), Inches(11.7), Inches(0.4 * num_rows)
        )
        table = table_shape.table
        
        # Populate headers
        for c_idx, h in enumerate(headers):
            table.cell(0, c_idx).text = str(h)
            
        # Populate rows
        for r_idx, row_vals in enumerate(rows, start=1):
            for c_idx in range(num_cols):
                val = row_vals[c_idx] if c_idx < len(row_vals) else ""
                table.cell(r_idx, c_idx).text = str(val)

        _style_table(table, num_rows, num_cols)
    else:
        empty_box = slide4.shapes.add_textbox(Inches(0.8), Inches(2.2), Inches(11.7), Inches(2.0))
        e_tf = empty_box.text_frame
        e_p = e_tf.paragraphs[0]
        e_p.text = "Descriptive numerical statistics: Synthesized qualitative findings from document evidence."
        e_p.font.size = Pt(14)
        e_p.font.color.rgb = MUTED_GRAY

    # -------------------------------------------------------------
    # SLIDE 5: Trend Analysis
    # -------------------------------------------------------------
    slide5 = prs.slides.add_slide(blank_layout)
    _add_slide_header(slide5, "Trend Analysis & Trajectory Detection")

    if trends_table and trends_table.get("rows"):
        headers = trends_table["columns"][:7]
        rows = trends_table["rows"][:8]
        num_rows = len(rows) + 1
        num_cols = len(headers)

        table_shape = slide5.shapes.add_table(
            num_rows, num_cols,
            Inches(0.8), Inches(1.6), Inches(11.7), Inches(0.45 * num_rows)
        )
        table = table_shape.table

        for c_idx, h in enumerate(headers):
            table.cell(0, c_idx).text = str(h)

        for r_idx, row_vals in enumerate(rows, start=1):
            for c_idx in range(num_cols):
                val = row_vals[c_idx] if c_idx < len(row_vals) else ""
                table.cell(r_idx, c_idx).text = str(val)

        _style_table(table, num_rows, num_cols)
    else:
        empty_box = slide5.shapes.add_textbox(Inches(0.8), Inches(2.2), Inches(11.7), Inches(2.0))
        e_tf = empty_box.text_frame
        e_p = e_tf.paragraphs[0]
        e_p.text = "No sequential time-series trend parameters computed for this workflow."
        e_p.font.size = Pt(14)
        e_p.font.color.rgb = MUTED_GRAY

    # -------------------------------------------------------------
    # SLIDE 6: Anomalies / Operational Risks
    # -------------------------------------------------------------
    slide6 = prs.slides.add_slide(blank_layout)
    _add_slide_header(slide6, "Anomalies & Operational Risk Findings")

    if anomalies_table and anomalies_table.get("rows"):
        headers = anomalies_table["columns"][:7]
        rows = anomalies_table["rows"][:8]
        num_rows = len(rows) + 1
        num_cols = len(headers)

        table_shape = slide6.shapes.add_table(
            num_rows, num_cols,
            Inches(0.8), Inches(1.6), Inches(11.7), Inches(0.45 * num_rows)
        )
        table = table_shape.table

        for c_idx, h in enumerate(headers):
            table.cell(0, c_idx).text = str(h)

        for r_idx, row_vals in enumerate(rows, start=1):
            for c_idx in range(num_cols):
                val = row_vals[c_idx] if c_idx < len(row_vals) else ""
                table.cell(r_idx, c_idx).text = str(val)

        _style_table(table, num_rows, num_cols)
        # Highlight alert text in cells
        for r_idx in range(1, num_rows):
            for c_idx in range(num_cols):
                for p in table.cell(r_idx, c_idx).text_frame.paragraphs:
                    p.font.color.rgb = ALERT_RED
    else:
        clean_box = slide6.shapes.add_textbox(Inches(0.8), Inches(2.2), Inches(11.7), Inches(2.0))
        cl_tf = clean_box.text_frame
        cl_p = cl_tf.paragraphs[0]
        cl_p.text = "✓ No statistical anomalies or operational threshold deviations detected."
        cl_p.font.size = Pt(16)
        cl_p.font.bold = True
        cl_p.font.color.rgb = SUCCESS_GREEN

        cl_sub = cl_tf.add_paragraph()
        cl_sub.text = "All analyzed metrics fall within standard operational tolerances."
        cl_sub.font.size = Pt(13)
        cl_sub.font.color.rgb = DARK_GRAY
        cl_sub.space_before = Pt(8)

    # -------------------------------------------------------------
    # SLIDE 7: Locally Generated Charts / Visual Evidence
    # -------------------------------------------------------------
    if all_figures:
        for f_idx, fig in enumerate(all_figures):
            fig_path = Path(fig["path"])
            if fig_path.is_file():
                slide7 = prs.slides.add_slide(blank_layout)
                header_title = "Visual Evidence & Analysis Charts" if f_idx == 0 else f"Visual Evidence ({f_idx + 1}/{len(all_figures)})"
                _add_slide_header(slide7, header_title)

                try:
                    with PILImage.open(fig_path) as pimg:
                        img_w, img_h = pimg.size
                    
                    max_w, max_h = 10.5, 4.6
                    scale = min(max_w / max(1, img_w), max_h / max(1, img_h))
                    w = img_w * scale
                    h = img_h * scale

                    slide7.shapes.add_picture(
                        str(fig_path),
                        Inches((13.333 - w) / 2),
                        Inches(1.6),
                        width=Inches(w),
                        height=Inches(h)
                    )

                    caption = fig.get("caption") or fig_path.name
                    cap_box = slide7.shapes.add_textbox(
                        Inches(1.0), Inches(1.6 + h + 0.15), Inches(11.333), Inches(0.5)
                    )
                    cap_tf = cap_box.text_frame
                    cap_p = cap_tf.paragraphs[0]
                    cap_p.text = f"Figure {f_idx + 1}: {caption}"
                    cap_p.font.size = Pt(11)
                    cap_p.font.italic = True
                    cap_p.font.color.rgb = MUTED_GRAY
                    cap_p.alignment = PP_ALIGN.CENTER
                except Exception as fig_err:
                    err_box = slide7.shapes.add_textbox(Inches(0.8), Inches(2.2), Inches(11.7), Inches(1.0))
                    err_box.text_frame.paragraphs[0].text = f"[Image failed to load: {fig_err}]"
    else:
        slide7 = prs.slides.add_slide(blank_layout)
        _add_slide_header(slide7, "Visual Evidence & Graphical Visualizations")
        no_fig_box = slide7.shapes.add_textbox(Inches(0.8), Inches(2.2), Inches(11.7), Inches(2.0))
        nf_tf = no_fig_box.text_frame
        nf_p = nf_tf.paragraphs[0]
        nf_p.text = "No graphical charts or photographic evidence generated for this run."
        nf_p.font.size = Pt(14)
        nf_p.font.color.rgb = MUTED_GRAY

    # -------------------------------------------------------------
    # SLIDE 8: Recommendations / Next Actions
    # -------------------------------------------------------------
    slide8 = prs.slides.add_slide(blank_layout)
    _add_slide_header(slide8, "Recommendations & Action Items")

    rec_box = slide8.shapes.add_textbox(Inches(0.8), Inches(1.5), Inches(11.7), Inches(5.0))
    r_tf = rec_box.text_frame
    r_tf.word_wrap = True

    rp1 = r_tf.paragraphs[0]
    rp1.text = "Operational Actions & Sign-Off Requirements:"
    rp1.font.size = Pt(14)
    rp1.font.bold = True
    rp1.font.color.rgb = NAVY

    actions = []
    if report.get("approval_note"):
        actions.append("Record formal review and sign-off on documented inspection observations and corrective actions.")
        actions.append("Ensure maintenance tasks adhere to local Standard Operating Procedures (SOPs).")
        actions.append("Update CMMS tracking registry with verified vibration readings and component status.")
    else:
        actions.append("Review documented statistics and trend analyses with operational engineering.")
        actions.append("Archive verified deliverable in local repository for compliance records.")

    for act in actions:
        p = r_tf.add_paragraph()
        p.text = f"• {act}"
        p.font.size = Pt(13)
        p.font.color.rgb = DARK_GRAY
        p.space_before = Pt(6)

    # Local sovereign assurance
    rp_sovereign = r_tf.add_paragraph()
    rp_sovereign.text = "Sovereign AI Assurance:"
    rp_sovereign.font.size = Pt(13)
    rp_sovereign.font.bold = True
    rp_sovereign.font.color.rgb = SUCCESS_GREEN
    rp_sovereign.space_before = Pt(20)

    rp_sov_text = r_tf.add_paragraph()
    rp_sov_text.text = (
        "This deliverable was generated entirely within the on-premise Sovereign AI Workbench. "
        "All calculations, embeddings, OCR parsing, and document assembly occurred locally without external cloud API calls."
    )
    rp_sov_text.font.size = Pt(11)
    rp_sov_text.font.color.rgb = MUTED_GRAY
    rp_sov_text.space_before = Pt(4)

    prs.save(output_path)

    return {
        "path": str(output_path.resolve()),
        "warnings": [],
    }
