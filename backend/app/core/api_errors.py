from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from fastapi import HTTPException


@dataclass(slots=True)
class ApiError(Exception):
    status_code: int
    error_code: str
    message: str
    details: dict[str, Any] | None = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "error_code": self.error_code,
            "message": self.message,
        }
        if self.details:
            payload["details"] = self.details
        return payload


def api_error(
    error_code: str,
    message: str,
    *,
    status_code: int = 400,
    details: dict[str, Any] | None = None,
) -> ApiError:
    return ApiError(status_code=status_code, error_code=error_code, message=message, details=details)


def infer_api_error_from_http_exception(exc: HTTPException) -> ApiError:
    status_code = int(exc.status_code or 500)
    detail = exc.detail

    if isinstance(detail, dict):
        error_code = str(detail.get("error_code") or _default_error_code(status_code))
        message = str(detail.get("message") or detail.get("detail") or _default_message(status_code, error_code))
        details = detail.get("details")
        return ApiError(status_code=status_code, error_code=error_code, message=message, details=details if isinstance(details, dict) else None)

    message = str(detail or _default_message(status_code, _default_error_code(status_code))).strip()
    error_code = _infer_error_code_from_message(status_code, message)
    return ApiError(status_code=status_code, error_code=error_code, message=message)


def _default_error_code(status_code: int) -> str:
    return {
        401: "auth_required",
        403: "forbidden",
        404: "not_found",
        409: "conflict",
        422: "validation_error",
        429: "rate_limited",
        500: "internal_error",
        502: "bad_gateway",
        503: "setup_required",
        504: "gateway_timeout",
    }.get(status_code, "request_failed")


def _default_message(status_code: int, error_code: str) -> str:
    if error_code == "setup_required":
        return "Setup is required before this request can be processed"
    if error_code == "auth_required":
        return "Authentication is required"
    if error_code == "email_not_found":
        return "Email not found"
    if error_code == "mailbox_context_missing":
        return "Mailbox context is missing"
    if error_code == "mailbox_context_mismatch":
        return "Mailbox context does not match the requested email"
    if error_code == "imap_move_failed":
        return "Failed to move email on IMAP server"
    if error_code == "imap_folder_resolution_failed":
        return "Failed to resolve IMAP folder"
    if error_code == "stale_lock_file":
        return "Background lock file is stale"
    if error_code == "data_dir_unavailable":
        return "DATA_DIR is unavailable"
    if error_code == "diagnostics_unavailable":
        return "Diagnostics are unavailable"
    return f"Request failed with HTTP {status_code}"


def _infer_error_code_from_message(status_code: int, message: str) -> str:
    lowered = message.lower()
    if status_code == 503 and "setup" in lowered:
        return "setup_required"
    if status_code == 401:
        return "auth_required"
    if "mailbox context is missing" in lowered or "unable to resolve mailbox for server-side move" in lowered:
        return "mailbox_context_missing"
    if "mailbox context" in lowered and "mismatch" in lowered:
        return "mailbox_context_mismatch"
    if "email not found" in lowered:
        return "email_not_found"
    if "imap folder" in lowered and "resolve" in lowered:
        return "imap_folder_resolution_failed"
    if "imap" in lowered and ("move" in lowered or "restore" in lowered or "confirm spam" in lowered):
        return "imap_move_failed"
    if "background lock" in lowered or "stale lock" in lowered:
        return "stale_lock_file"
    if "data_dir" in lowered or "data dir" in lowered:
        return "data_dir_unavailable"
    if "diagnostic" in lowered:
        return "diagnostics_unavailable"
    return _default_error_code(status_code)
