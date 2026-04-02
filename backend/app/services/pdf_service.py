from __future__ import annotations

import io
import html
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


DEFAULT_MARGIN = 36  # 0.5 inch
MAX_ROWS = 120
MAX_CELL_LENGTH = 420


def render_report_pdf(report_payload: dict[str, Any]) -> bytes:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("reportlab package is required for PDF export") from exc

    base_font, bold_font = _resolve_fonts(pdfmetrics, TTFont)

    output = io.BytesIO()
    doc = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=DEFAULT_MARGIN,
        rightMargin=DEFAULT_MARGIN,
        topMargin=DEFAULT_MARGIN,
        bottomMargin=DEFAULT_MARGIN,
        title="Orhun Mail Agent report",
        author="Orhun Mail Agent",
    )
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="ReportBody",
            parent=styles["BodyText"],
            fontName=base_font,
            fontSize=9,
            leading=12,
            wordWrap="CJK",
        )
    )
    styles.add(
        ParagraphStyle(
            name="ReportHeading2",
            parent=styles["Heading2"],
            fontName=bold_font,
            fontSize=14,
            leading=18,
        )
    )
    styles.add(
        ParagraphStyle(
            name="ReportHeading3",
            parent=styles["Heading3"],
            fontName=bold_font,
            fontSize=11,
            leading=14,
        )
    )
    styles.add(
        ParagraphStyle(
            name="ReportCaption",
            parent=styles["Italic"],
            fontName=base_font,
            fontSize=8,
            leading=10,
            wordWrap="CJK",
        )
    )
    elements = []

    title = f"Orhun Mail Agent Report: {report_payload.get('report_type', 'unknown')}"
    elements.append(Paragraph(_p(title), styles["ReportHeading2"]))
    elements.append(Paragraph(_p(f"Generated at: {report_payload.get('generated_at', '')}"), styles["ReportBody"]))
    elements.append(Spacer(1, 10))

    summary = report_payload.get("summary", {}) or {}
    if summary:
        elements.append(Paragraph("Summary", styles["ReportHeading3"]))
        summary_data: list[list[Any]] = [
            [
                Paragraph(_p("Metric"), styles["ReportBody"]),
                Paragraph(_p("Value"), styles["ReportBody"]),
            ]
        ]
        for key, value in summary.items():
            summary_data.append(
                [
                    Paragraph(_p(str(key)), styles["ReportBody"]),
                    Paragraph(_p(_short(value)), styles["ReportBody"]),
                ]
            )

        content_width = A4[0] - doc.leftMargin - doc.rightMargin
        table = LongTable(summary_data, repeatRows=1, colWidths=[content_width * 0.34, content_width * 0.66], hAlign="LEFT")
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2f7")),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d3dae6")),
                    ("FONTNAME", (0, 0), (-1, 0), bold_font),
                    ("FONTNAME", (0, 1), (-1, -1), base_font),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 4),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ]
            )
        )
        elements.append(table)
        elements.append(Spacer(1, 10))

    rows = report_payload.get("rows", []) or []
    elements.append(Paragraph("Rows", styles["ReportHeading3"]))
    if rows:
        headers = sorted({key for row in rows if isinstance(row, dict) for key in row.keys()})
        if not headers:
            headers = ["value"]

        content_width = A4[0] - doc.leftMargin - doc.rightMargin
        col_width = max(content_width / len(headers), 70)
        row_data: list[list[Any]] = [[Paragraph(_p(header), styles["ReportBody"]) for header in headers]]
        for row in rows[:MAX_ROWS]:
            row_data.append(
                [Paragraph(_p(_short(row.get(header))), styles["ReportBody"]) for header in headers]
            )
        table = LongTable(row_data, repeatRows=1, colWidths=[col_width] * len(headers), hAlign="LEFT")
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2f7")),
                    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#d3dae6")),
                    ("FONTNAME", (0, 0), (-1, 0), bold_font),
                    ("FONTNAME", (0, 1), (-1, -1), base_font),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 5),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
                    ("TOPPADDING", (0, 0), (-1, -1), 3),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ]
            )
        )
        elements.append(table)
        if len(rows) > MAX_ROWS:
            elements.append(Spacer(1, 8))
            elements.append(
                Paragraph(
                    _p(f"Rows truncated in PDF preview: {len(rows) - MAX_ROWS} more rows."),
                    styles["ReportCaption"],
                )
            )
    else:
        elements.append(Paragraph("No rows for selected filters.", styles["ReportBody"]))

    doc.build(elements)
    return output.getvalue()


def _short(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    if len(text) <= MAX_CELL_LENGTH:
        return text
    return text[: MAX_CELL_LENGTH - 3] + "..."


def _p(value: str) -> str:
    return html.escape(value).replace("\n", "<br/>")


def _resolve_fonts(pdfmetrics, ttfont_cls) -> tuple[str, str]:
    registered = set(pdfmetrics.getRegisteredFontNames())
    if "OMA-Base" in registered and "OMA-Bold" in registered:
        return "OMA-Base", "OMA-Bold"

    base_candidates = _candidate_font_paths(
        env_key="OMA_PDF_FONT_PATH",
        fallbacks=[
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/dejavu/DejaVuSans.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/segoeui.ttf",
            "C:/Windows/Fonts/tahoma.ttf",
        ],
    )
    bold_candidates = _candidate_font_paths(
        env_key="OMA_PDF_FONT_BOLD_PATH",
        fallbacks=[
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/seguisb.ttf",
            "C:/Windows/Fonts/tahomabd.ttf",
        ],
    )

    base_path = _first_existing_path(base_candidates)
    bold_path = _first_existing_path(bold_candidates)
    if base_path and bold_path:
        pdfmetrics.registerFont(ttfont_cls("OMA-Base", str(base_path)))
        pdfmetrics.registerFont(ttfont_cls("OMA-Bold", str(bold_path)))
        return "OMA-Base", "OMA-Bold"

    logger.warning("Unicode TTF fonts were not found for PDF export, falling back to Helvetica")
    return "Helvetica", "Helvetica-Bold"


def _candidate_font_paths(*, env_key: str, fallbacks: list[str]) -> list[Path]:
    candidates: list[Path] = []
    env_value = os.getenv(env_key, "").strip()
    if env_value:
        candidates.append(Path(env_value))
    candidates.extend(Path(item) for item in fallbacks)
    return candidates


def _first_existing_path(candidates: list[Path]) -> Path | None:
    for item in candidates:
        if item.exists() and item.is_file():
            return item
    return None
