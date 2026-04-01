from __future__ import annotations

import csv
import io
from typing import Any


def render_report_csv(report_payload: dict[str, Any]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)

    writer.writerow(["report_type", report_payload.get("report_type", "")])
    writer.writerow(["generated_at", report_payload.get("generated_at", "")])
    writer.writerow([])
    writer.writerow(["summary"])
    summary = report_payload.get("summary", {}) or {}
    for key, value in summary.items():
        writer.writerow([key, _scalar(value)])
    writer.writerow([])

    rows = report_payload.get("rows", []) or []
    if rows:
        headers = sorted({key for row in rows if isinstance(row, dict) for key in row.keys()})
        writer.writerow(headers)
        for row in rows:
            writer.writerow([_scalar(row.get(header)) for header in headers])
    else:
        writer.writerow(["rows"])
        writer.writerow(["(empty)"])

    return buffer.getvalue().encode("utf-8-sig")


def _scalar(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    return str(value)
