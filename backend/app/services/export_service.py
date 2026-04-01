from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.csv_service import render_report_csv
from app.services.pdf_service import render_report_pdf


@dataclass(slots=True)
class ExportArtifact:
    filename: str
    media_type: str
    content: bytes


def export_report(report_payload: dict[str, Any], report_type: str, fmt: str) -> ExportArtifact:
    normalized = fmt.strip().lower()
    if normalized == "csv":
        content = render_report_csv(report_payload)
        return ExportArtifact(
            filename=f"{report_type}.csv",
            media_type="text/csv; charset=utf-8",
            content=content,
        )
    if normalized == "pdf":
        content = render_report_pdf(report_payload)
        return ExportArtifact(
            filename=f"{report_type}.pdf",
            media_type="application/pdf",
            content=content,
        )
    raise ValueError("Unsupported export format. Use csv or pdf.")
