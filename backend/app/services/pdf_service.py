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


REPORT_TYPE_LABELS: dict[str, str] = {
    "activity": "Отчёт об активности",
    "followups": "Отчёт по ожиданиям",
    "sent_review": "Отчёт по исходящим",
    "team_activity": "Отчёт по команде",
}

SUMMARY_KEY_LABELS: dict[str, str] = {
    "sent_emails_count": "Отправлено писем",
    "received_emails_count": "Получено писем",
    "active_threads": "Активных тредов",
    "closed_threads": "Закрытых тредов",
    "waiting_threads": "В ожидании",
    "overdue_followups": "Просрочено",
    "spam_count": "Спам",
    "restored_from_spam_count": "Восстановлено из спама",
    "total_threads": "Всего тредов",
    "waiting_threads": "В ожидании",
    "overdue_threads": "Просрочено",
    "total_sent": "Всего отправлено",
    "verdict_counts": "Вердикты",
    "problematic_count": "Проблемных",
    "common_issues": "Частые проблемы",
    "users_with_activity": "Пользователей с активностью",
    "total_actions": "Всего действий",
    "total_sent_replies": "Всего отправлено ответов",
}

ROW_HEADER_LABELS: dict[str, str] = {
    "email_id": "ID",
    "thread_id": "Тред",
    "subject": "Тема",
    "sender": "Отправитель",
    "mailbox": "Ящик",
    "status": "Статус",
    "priority": "Приоритет",
    "category": "Категория",
    "waiting_days": "Дней ожидания",
    "assigned_user": "Назначено",
    "last_activity_at": "Посл. активность",
    "task_id": "Задача",
    "state": "Состояние",
    "expected_reply_by": "Ожидание до",
    "verdict": "Вердикт",
    "summary": "Сводка",
    "score": "Оценка",
    "reviewed_at": "Проверено",
    "user_id": "Пользователь",
    "user_email": "Email",
    "user_name": "Имя",
    "role": "Роль",
    "actions_count": "Действий",
    "sent_replies_count": "Ответов",
    "top_actions": "Топ действий",
    "last_action_at": "Посл. действие",
}

# Select only the most useful columns per report type for a readable PDF
REPORT_COLUMNS: dict[str, list[str]] = {
    "activity": ["subject", "sender", "status", "priority", "waiting_days"],
    "followups": ["subject", "sender", "state", "waiting_days", "expected_reply_by"],
    "sent_review": ["subject", "verdict", "summary", "score"],
    "team_activity": ["user_name", "user_email", "role", "actions_count", "sent_replies_count"],
}


def render_report_pdf(report_payload: dict[str, Any]) -> bytes:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.ttfonts import TTFont
        from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError("reportlab package is required for PDF export") from exc

    base_font, bold_font = _resolve_fonts(pdfmetrics, TTFont)

    output = io.BytesIO()
    page_size = landscape(A4)
    doc = SimpleDocTemplate(
        output,
        pagesize=page_size,
        leftMargin=DEFAULT_MARGIN,
        rightMargin=DEFAULT_MARGIN,
        topMargin=DEFAULT_MARGIN,
        bottomMargin=DEFAULT_MARGIN,
        title="Orhun Mail Agent — отчёт",
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

    report_type = report_payload.get("report_type", "unknown")
    title_label = REPORT_TYPE_LABELS.get(report_type, report_type)
    title = f"Orhun Mail Agent — {title_label}"
    elements.append(Paragraph(_p(title), styles["ReportHeading2"]))
    elements.append(Paragraph(_p(f"Дата: {report_payload.get('generated_at', '')}"), styles["ReportBody"]))
    elements.append(Spacer(1, 10))

    summary = report_payload.get("summary", {}) or {}
    if summary:
        elements.append(Paragraph("Краткая сводка", styles["ReportHeading3"]))
        summary_data: list[list[Any]] = [
            [
                Paragraph(_p("Показатель"), styles["ReportBody"]),
                Paragraph(_p("Значение"), styles["ReportBody"]),
            ]
        ]
        for key, value in summary.items():
            label = SUMMARY_KEY_LABELS.get(key, key)
            display_value = _format_summary_value(value)
            summary_data.append(
                [
                    Paragraph(_p(str(label)), styles["ReportBody"]),
                    Paragraph(_p(display_value), styles["ReportBody"]),
                ]
            )

        content_width = page_size[0] - doc.leftMargin - doc.rightMargin
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
    elements.append(Paragraph("Данные", styles["ReportHeading3"]))
    if rows:
        preferred_columns = REPORT_COLUMNS.get(report_type)
        if preferred_columns:
            headers = [col for col in preferred_columns if any(isinstance(row, dict) and col in row for row in rows)]
        else:
            headers = sorted({key for row in rows if isinstance(row, dict) for key in row.keys()})
        if not headers:
            headers = ["value"]

        content_width = page_size[0] - doc.leftMargin - doc.rightMargin
        col_width = max(content_width / len(headers), 70)
        header_labels = [ROW_HEADER_LABELS.get(h, h) for h in headers]
        row_data: list[list[Any]] = [[Paragraph(_p(label), styles["ReportBody"]) for label in header_labels]]
        for row in rows[:MAX_ROWS]:
            row_data.append(
                [Paragraph(_p(_short(row.get(header), max_len=200)), styles["ReportBody"]) for header in headers]
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
                    _p(f"Показано {MAX_ROWS} из {len(rows)} строк."),
                    styles["ReportCaption"],
                )
            )
    else:
        elements.append(Paragraph("Нет данных для выбранных фильтров.", styles["ReportBody"]))

    doc.build(elements)
    return output.getvalue()


def _format_summary_value(value: Any) -> str:
    """Format a summary value for display, handling dicts and lists."""
    if value is None:
        return "—"
    if isinstance(value, dict):
        return ", ".join(f"{k}: {v}" for k, v in value.items())
    if isinstance(value, list):
        items = []
        for item in value[:10]:
            if isinstance(item, (list, tuple)) and len(item) == 2:
                items.append(f"{item[0]}: {item[1]}")
            else:
                items.append(str(item))
        return ", ".join(items) if items else "—"
    return str(value)


def _short(value: Any, max_len: int = MAX_CELL_LENGTH) -> str:
    if value is None:
        return ""
    text = str(value)
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


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
