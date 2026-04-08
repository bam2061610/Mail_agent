from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from collections.abc import Callable
from types import SimpleNamespace

from sqlalchemy.orm import Session

from app.exceptions import SetupError
from app.schemas.system import SetupAiConfig, SetupCompleteRequest, SetupMailboxConfig
from app.services.deepseek_client import call_deepseek_chat
from app.services.imap_scanner import connect_imap
from app.services.mailbox_service import create_mailbox_with_session, to_runtime_mailbox
from app.services.settings_service import is_setup_completed, mark_setup_completed, save_runtime_settings
from app.services.smtp_sender import test_smtp_connection
from app.services.user_service import create_user, get_user_by_email

logger = logging.getLogger(__name__)
SETUP_VALIDATION_TTL_SECONDS = 15 * 60
_validation_cache_lock = threading.Lock()
_validated_setup_payloads: dict[str, dict[str, float]] = {
    "ai": {},
    "mailbox": {},
}


def test_ai_configuration(payload: SetupAiConfig) -> None:
    try:
        call_deepseek_chat(
            system_prompt="Reply with a compact JSON object that includes a boolean field named ok.",
            user_payload='Return {"ok": true}.',
            config=SimpleNamespace(
                deepseek_api_key=payload.deepseek_api_key,
                openai_api_key=payload.deepseek_api_key,
                deepseek_model=payload.deepseek_model,
                deepseek_base_url=payload.deepseek_base_url,
                ai_timeout_seconds=30,
                ai_max_retries=1,
            ),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("AI setup test failed", exc_info=True)
        raise SetupError(f"AI configuration test failed: {exc}") from exc
    _remember_successful_validation("ai", payload.model_dump())


def test_mailbox_configuration(payload: SetupMailboxConfig) -> None:
    runtime_mailbox = to_runtime_mailbox(
        {
            "id": "setup-mailbox",
            "name": payload.name or payload.email_address,
            "email_address": payload.email_address,
            "imap_host": payload.imap_host,
            "imap_port": payload.imap_port,
            "imap_username": payload.imap_username or payload.email_address,
            "imap_password": payload.imap_password,
            "smtp_host": payload.smtp_host,
            "smtp_port": payload.smtp_port,
            "smtp_username": payload.smtp_username or payload.email_address,
            "smtp_password": payload.smtp_password,
            "smtp_use_tls": payload.smtp_use_tls,
            "smtp_use_ssl": payload.smtp_use_ssl,
            "enabled": payload.enabled,
            "is_default_outgoing": payload.is_default_outgoing,
        }
    )
    connection = None
    try:
        connection = connect_imap(runtime_mailbox)
        status, _ = connection.select("INBOX", readonly=True)
        if status != "OK":
            raise SetupError("IMAP inbox access failed")
        test_smtp_connection(runtime_mailbox)
    except SetupError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.warning("Mailbox setup test failed", exc_info=True)
        raise SetupError(f"Mailbox configuration test failed: {exc}") from exc
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                logger.warning("IMAP connection close failed during setup", exc_info=True)
            try:
                connection.logout()
            except Exception:
                logger.warning("IMAP connection logout failed during setup", exc_info=True)
    _remember_successful_validation("mailbox", payload.model_dump())


def complete_setup(db: Session, payload: SetupCompleteRequest) -> None:
    if is_setup_completed(db):
        raise SetupError("Setup has already been completed")
    if get_user_by_email(db, payload.admin.email):
        raise SetupError("An admin user with this email already exists")

    _validate_or_reuse_successful_check("ai", payload.ai.model_dump(), lambda: test_ai_configuration(payload.ai))
    _validate_or_reuse_successful_check(
        "mailbox",
        payload.mailbox.model_dump(),
        lambda: test_mailbox_configuration(payload.mailbox),
    )

    save_runtime_settings(
        db,
        {
            "deepseek_api_key": payload.ai.deepseek_api_key,
            "deepseek_model": payload.ai.deepseek_model,
            "deepseek_base_url": payload.ai.deepseek_base_url,
            "ai_analysis_enabled": payload.ai_analysis_enabled,
            "scheduler_interval_minutes": payload.scheduler_interval_minutes,
            "followup_overdue_days": payload.followup_overdue_days,
            "max_emails_per_scan": payload.max_emails_per_scan,
        },
    )
    create_user(
        db_session=db,
        email=payload.admin.email,
        full_name=payload.admin.full_name or payload.admin.email,
        password=payload.admin.password,
        role="admin",
    )
    create_mailbox_with_session(
        db,
        {
            "name": payload.mailbox.name or payload.mailbox.email_address,
            "email_address": payload.mailbox.email_address,
            "imap_host": payload.mailbox.imap_host,
            "imap_port": payload.mailbox.imap_port,
            "imap_username": payload.mailbox.imap_username or payload.mailbox.email_address,
            "imap_password": payload.mailbox.imap_password,
            "smtp_host": payload.mailbox.smtp_host,
            "smtp_port": payload.mailbox.smtp_port,
            "smtp_username": payload.mailbox.smtp_username or payload.mailbox.email_address,
            "smtp_password": payload.mailbox.smtp_password,
            "smtp_use_tls": payload.mailbox.smtp_use_tls,
            "smtp_use_ssl": payload.mailbox.smtp_use_ssl,
            "enabled": payload.mailbox.enabled,
            "is_default_outgoing": payload.mailbox.is_default_outgoing,
        },
    )
    mark_setup_completed(db, completed=True)
    db.commit()
    clear_setup_validation_cache()


def clear_setup_validation_cache() -> None:
    with _validation_cache_lock:
        for kind in _validated_setup_payloads:
            _validated_setup_payloads[kind].clear()


def _validate_or_reuse_successful_check(
    kind: str,
    payload: dict[str, object],
    validator: Callable[[], None],
) -> None:
    if _has_recent_successful_validation(kind, payload):
        logger.info("Reusing recent successful %s setup validation", kind)
        return
    validator()


def _remember_successful_validation(kind: str, payload: dict[str, object]) -> None:
    fingerprint = _build_validation_fingerprint(payload)
    expires_at = time.monotonic() + SETUP_VALIDATION_TTL_SECONDS
    with _validation_cache_lock:
        bucket = _validated_setup_payloads[kind]
        _prune_expired_validations(bucket)
        bucket[fingerprint] = expires_at


def _has_recent_successful_validation(kind: str, payload: dict[str, object]) -> bool:
    fingerprint = _build_validation_fingerprint(payload)
    with _validation_cache_lock:
        bucket = _validated_setup_payloads[kind]
        _prune_expired_validations(bucket)
        expires_at = bucket.get(fingerprint)
        return expires_at is not None and expires_at > time.monotonic()


def _prune_expired_validations(bucket: dict[str, float]) -> None:
    now = time.monotonic()
    expired = [fingerprint for fingerprint, expires_at in bucket.items() if expires_at <= now]
    for fingerprint in expired:
        bucket.pop(fingerprint, None)


def _build_validation_fingerprint(payload: dict[str, object]) -> str:
    normalized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
