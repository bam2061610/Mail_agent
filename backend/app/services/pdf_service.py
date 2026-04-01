from __future__ import annotations

import io
from typing import Any


def render_report_pdf(report_payload: dict[str, Any]) -> bytes:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("reportlab package is required for PDF export") from exc

    output = io.BytesIO()
    doc = SimpleDocTemplate(output, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = []

    title = f"Orhun Mail Agent Report: {report_payload.get('report_type', 'unknown')}"
    elements.append(Paragraph(title, styles["Heading2"]))
    elements.append(Paragraph(f"Generated at: {report_payload.get('generated_at', '')}", styles["BodyText"]))
    elements.append(Spacer(1, 10))

    summary = report_payload.get("summary", {}) or {}
    if summary:
        elements.append(Paragraph("Summary", styles["Heading3"]))
        data = [["Metric", "Value"]] + [[str(key), _short(value)] for key, value in summary.items()]
        table = Table(data, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ]
            )
        )
        elements.append(table)
        elements.append(Spacer(1, 10))

    rows = report_payload.get("rows", []) or []
    elements.append(Paragraph("Rows", styles["Heading3"]))
    if rows:
        headers = sorted({key for row in rows if isinstance(row, dict) for key in row.keys()})
        data = [headers]
        for row in rows[:120]:
            data.append([_short(row.get(header)) for header in headers])
        table = Table(data, repeatRows=1)
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ]
            )
        )
        elements.append(table)
        if len(rows) > 120:
            elements.append(Spacer(1, 8))
            elements.append(Paragraph(f"Rows truncated in PDF preview: {len(rows) - 120} more rows.", styles["Italic"]))
    else:
        elements.append(Paragraph("No rows for selected filters.", styles["BodyText"]))

    doc.build(elements)
    return output.getvalue()


def _short(value: Any) -> str:
    if value is None:
        return ""
    text = str(value)
    if len(text) <= 120:
        return text
    return text[:117] + "..."
