from __future__ import annotations

import io
import os
import re
import unicodedata
from html import escape
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    KeepTogether,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

TYPE_LABELS = {
    "lesson": "Lesson Plan",
    "activity": "Activity",
    "worksheet": "Worksheet",
    "assessment": "Assessment",
}

_MARKDOWN_PREFIX = re.compile(r"^\s{0,3}(#{1,6})\s+(.*)$")
_NUMBERED_ITEM = re.compile(r"^\s*(\d+)[.)]\s+(.*)$")
_BULLET_ITEM = re.compile(r"^\s*[-*•]\s+(.*)$")
_HEADING_BREAK_WORDS = ("ANSWER KEY", "TEACHER NOTES", "MARKING GUIDE")


class NumberedCanvasMixin:
    """Marker class retained for future page-count extensions."""


def _register_portable_fonts() -> tuple[str, str]:
    """Use a Unicode-capable system font when available, else PDF core fonts."""
    regular_candidates = [
        Path("C:/Windows/Fonts/arial.ttf"),
        Path("C:/Windows/Fonts/calibri.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"),
        Path("/Library/Fonts/Arial.ttf"),
    ]
    bold_candidates = [
        Path("C:/Windows/Fonts/arialbd.ttf"),
        Path("C:/Windows/Fonts/calibrib.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"),
        Path("/Library/Fonts/Arial Bold.ttf"),
    ]

    regular = next((path for path in regular_candidates if path.exists()), None)
    bold = next((path for path in bold_candidates if path.exists()), None)
    if regular is None:
        return "Helvetica", "Helvetica-Bold"

    try:
        if "TeacherOS-Regular" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("TeacherOS-Regular", str(regular)))
        if bold is not None and "TeacherOS-Bold" not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont("TeacherOS-Bold", str(bold)))
        return "TeacherOS-Regular", "TeacherOS-Bold" if bold is not None else "TeacherOS-Regular"
    except Exception:
        return "Helvetica", "Helvetica-Bold"


REGULAR_FONT, BOLD_FONT = _register_portable_fonts()


def _clean_inline_markdown(text: str) -> str:
    cleaned = text.replace("**", "").replace("`", "")
    return " ".join(cleaned.strip().split())


def _safe_filename(value: object, *, material_id: int) -> str:
    title = _clean_inline_markdown(str(value or "TeacherOS Material"))
    title = "".join(
        character
        for character in title
        if not (unicodedata.category(character) in {"So", "Sk"} and ord(character) > 255)
    )
    title = re.sub(r'[<>:"/\\|?*\x00-\x1F]', "", title)
    title = re.sub(r"\s+", " ", title).strip(" .")
    if not title:
        title = "TeacherOS Material"
    if len(title) > 70:
        title = title[:70].rstrip()
    return f"{title} - #{material_id}.pdf"


def _pdf_safe_text(value: object) -> str:
    """Keep teaching text readable while removing unsupported emoji glyphs."""
    text = str(value or "").replace("\u00a0", " ")
    replacements = {
        "✅": "[OK]",
        "❌": "[X]",
        "☐": "[ ]",
        "☑": "[x]",
        "✓": "[x]",
        "→": "->",
        "←": "<-",
        "–": "-",
        "—": "-",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)

    safe_characters: list[str] = []
    for character in text:
        category = unicodedata.category(character)
        if category in {"So", "Sk"} and ord(character) > 255:
            continue
        safe_characters.append(character)
    return "".join(safe_characters)


def _paragraph_text(value: object) -> str:
    """Escape user/AI content for ReportLab's XML-like Paragraph parser."""
    return escape(_pdf_safe_text(value), quote=False)


def _looks_like_heading(text: str) -> bool:
    if not text or len(text) > 95:
        return False
    letters = [character for character in text if character.isalpha()]
    if not letters:
        return False
    uppercase_ratio = sum(character.isupper() for character in letters) / len(letters)
    return uppercase_ratio >= 0.8 and not text.endswith((".", "?", "!"))


def _styles() -> dict[str, ParagraphStyle]:
    sample = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "TeacherOSTitle",
            parent=sample["Title"],
            fontName=BOLD_FONT,
            fontSize=19,
            leading=23,
            alignment=TA_CENTER,
            spaceAfter=5 * mm,
            textColor=colors.HexColor("#1F2937"),
        ),
        "subtitle": ParagraphStyle(
            "TeacherOSSubtitle",
            parent=sample["Normal"],
            fontName=BOLD_FONT,
            fontSize=10,
            leading=13,
            alignment=TA_CENTER,
            spaceAfter=4 * mm,
            textColor=colors.HexColor("#4B5563"),
        ),
        "heading1": ParagraphStyle(
            "TeacherOSHeading1",
            parent=sample["Heading1"],
            fontName=BOLD_FONT,
            fontSize=13,
            leading=16,
            spaceBefore=5 * mm,
            spaceAfter=2 * mm,
            textColor=colors.HexColor("#111827"),
            keepWithNext=True,
        ),
        "heading2": ParagraphStyle(
            "TeacherOSHeading2",
            parent=sample["Heading2"],
            fontName=BOLD_FONT,
            fontSize=11,
            leading=14,
            spaceBefore=3.5 * mm,
            spaceAfter=1.5 * mm,
            textColor=colors.HexColor("#1F2937"),
            keepWithNext=True,
        ),
        "body": ParagraphStyle(
            "TeacherOSBody",
            parent=sample["BodyText"],
            fontName=REGULAR_FONT,
            fontSize=9.6,
            leading=13.2,
            alignment=TA_LEFT,
            spaceAfter=2.2 * mm,
            textColor=colors.HexColor("#111827"),
            splitLongWords=True,
        ),
        "numbered": ParagraphStyle(
            "TeacherOSNumbered",
            parent=sample["BodyText"],
            fontName=REGULAR_FONT,
            fontSize=9.6,
            leading=13.2,
            leftIndent=7 * mm,
            firstLineIndent=-7 * mm,
            spaceAfter=1.8 * mm,
            textColor=colors.HexColor("#111827"),
        ),
        "bullet": ParagraphStyle(
            "TeacherOSBullet",
            parent=sample["BodyText"],
            fontName=REGULAR_FONT,
            fontSize=9.6,
            leading=13.2,
            leftIndent=7 * mm,
            firstLineIndent=-4 * mm,
            spaceAfter=1.8 * mm,
            textColor=colors.HexColor("#111827"),
        ),
        "metadata_label": ParagraphStyle(
            "TeacherOSMetadataLabel",
            parent=sample["Normal"],
            fontName=BOLD_FONT,
            fontSize=8.4,
            leading=10.5,
            textColor=colors.HexColor("#374151"),
        ),
        "metadata_value": ParagraphStyle(
            "TeacherOSMetadataValue",
            parent=sample["Normal"],
            fontName=REGULAR_FONT,
            fontSize=8.4,
            leading=10.5,
            textColor=colors.HexColor("#111827"),
        ),
    }


def _metadata_rows(material: dict[str, Any]) -> list[tuple[str, str]]:
    type_label = TYPE_LABELS.get(str(material.get("material_type") or ""), "Material")
    subtype = str(material.get("subtype") or "").strip()
    level = str(material.get("level") or "").strip()
    topic = str(material.get("topic") or "").strip()
    created_at = str(material.get("created_at") or "").strip()

    rows: list[tuple[str, str]] = [("Type", type_label)]
    if subtype and subtype.lower() != type_label.lower():
        rows.append(("Subtype", subtype))
    if level:
        rows.append(("CEFR level", level))
    if topic:
        rows.append(("Topic", topic))
    if created_at:
        rows.append(("Saved", f"{created_at[:16]} UTC"))

    metadata = material.get("metadata")
    if isinstance(metadata, dict):
        grammar = str(metadata.get("grammar") or "").strip()
        duration = metadata.get("duration_minutes")
        question_format = str(metadata.get("question_format") or "").strip()
        question_count = metadata.get("question_count")
        if grammar:
            rows.append(("Grammar", grammar))
        if isinstance(duration, int):
            rows.append(("Duration", f"{duration} minutes"))
        if question_format:
            rows.append(("Question format", question_format))
        if isinstance(question_count, int):
            rows.append(("Questions", str(question_count)))
    return rows


def _metadata_table(material: dict[str, Any], styles: dict[str, ParagraphStyle]) -> Table:
    rows = _metadata_rows(material)
    data = [
        [
            Paragraph(_paragraph_text(label), styles["metadata_label"]),
            Paragraph(_paragraph_text(value), styles["metadata_value"]),
        ]
        for label, value in rows
    ]
    table = Table(data, colWidths=[38 * mm, 129 * mm], hAlign="CENTER", repeatRows=0)
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F3F4F6")),
                ("GRID", (0, 0), (-1, -1), 0.45, colors.HexColor("#D1D5DB")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def _content_flowables(content: str, styles: dict[str, ParagraphStyle]) -> list[Any]:
    flowables: list[Any] = []
    section_break_added = False

    for raw_line in content.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = raw_line.strip()
        if not line:
            flowables.append(Spacer(1, 1.2 * mm))
            continue

        markdown_heading = _MARKDOWN_PREFIX.match(line)
        if markdown_heading:
            marker, heading_text = markdown_heading.groups()
            heading = _clean_inline_markdown(heading_text)
            if not section_break_added and any(word in heading.upper() for word in _HEADING_BREAK_WORDS):
                flowables.append(PageBreak())
                section_break_added = True
            style = styles["heading1"] if len(marker) <= 2 else styles["heading2"]
            flowables.append(Paragraph(_paragraph_text(heading), style))
            continue

        cleaned = _clean_inline_markdown(line)
        if _looks_like_heading(cleaned):
            if not section_break_added and any(word in cleaned.upper() for word in _HEADING_BREAK_WORDS):
                flowables.append(PageBreak())
                section_break_added = True
            title = cleaned.title() if cleaned.isupper() else cleaned
            flowables.append(Paragraph(_paragraph_text(title), styles["heading1"]))
            continue

        numbered = _NUMBERED_ITEM.match(cleaned)
        if numbered:
            number, item_text = numbered.groups()
            flowables.append(
                Paragraph(
                    f"{escape(number)}.&nbsp;&nbsp;{_paragraph_text(_clean_inline_markdown(item_text))}",
                    styles["numbered"],
                )
            )
            continue

        bullet = _BULLET_ITEM.match(cleaned)
        if bullet:
            flowables.append(
                Paragraph(
                    f"&#8226;&nbsp;&nbsp;{_paragraph_text(_clean_inline_markdown(bullet.group(1)))}",
                    styles["bullet"],
                )
            )
            continue

        flowables.append(Paragraph(_paragraph_text(cleaned), styles["body"]))

    return flowables


def _header_footer(canvas: Any, document: Any, *, material_id: int) -> None:
    canvas.saveState()
    page_width, page_height = A4

    canvas.setStrokeColor(colors.HexColor("#D1D5DB"))
    canvas.setLineWidth(0.5)
    canvas.line(18 * mm, page_height - 13 * mm, page_width - 18 * mm, page_height - 13 * mm)
    canvas.line(18 * mm, 13 * mm, page_width - 18 * mm, 13 * mm)

    canvas.setFont(BOLD_FONT, 7.8)
    canvas.setFillColor(colors.HexColor("#4B5563"))
    canvas.drawRightString(page_width - 18 * mm, page_height - 10 * mm, "TeacherOS - Classroom Material")

    canvas.setFont(REGULAR_FONT, 7.5)
    canvas.drawString(18 * mm, 9 * mm, f"Generated by TeacherOS | Library ID #{material_id}")
    canvas.drawRightString(page_width - 18 * mm, 9 * mm, f"Page {document.page}")
    canvas.restoreState()


def build_pdf_document(material: dict[str, Any], output: io.BytesIO) -> None:
    """Build a printable classroom-ready PDF into the supplied byte stream."""
    material_id = int(material.get("id") or 0)
    styles = _styles()

    document = BaseDocTemplate(
        output,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=str(material.get("title") or "TeacherOS Material"),
        author="TeacherOS",
        subject=TYPE_LABELS.get(str(material.get("material_type") or ""), "Classroom Material"),
    )
    frame = Frame(
        document.leftMargin,
        document.bottomMargin,
        document.width,
        document.height,
        id="TeacherOSFrame",
    )
    document.addPageTemplates(
        [
            PageTemplate(
                id="TeacherOSPage",
                frames=[frame],
                onPage=lambda canvas, doc: _header_footer(
                    canvas,
                    doc,
                    material_id=material_id,
                ),
            )
        ]
    )

    title = _clean_inline_markdown(str(material.get("title") or "TeacherOS Material"))
    subtitle = TYPE_LABELS.get(str(material.get("material_type") or ""), "Classroom Material")

    story: list[Any] = [
        Paragraph(_paragraph_text(title), styles["title"]),
        Paragraph(_paragraph_text(subtitle), styles["subtitle"]),
        KeepTogether([_metadata_table(material, styles), Spacer(1, 4 * mm)]),
    ]

    content = str(material.get("content") or "").strip()
    if content:
        story.extend(_content_flowables(content, styles))
    else:
        story.append(Paragraph("This saved material has no readable content.", styles["body"]))

    document.build(story)


def create_pdf_export(material: dict[str, Any]) -> tuple[io.BytesIO, str]:
    """Return an in-memory PDF stream and a safe download filename."""
    material_id = int(material.get("id") or 0)
    output = io.BytesIO()
    build_pdf_document(material, output)
    output.seek(0)
    filename = _safe_filename(material.get("title"), material_id=material_id)
    return output, filename
