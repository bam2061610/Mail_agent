import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import make_msgid

from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.exceptions import SmtpError
from app.services.imap_mailbox_actions import append_sent_copy_to_imap

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class SendReplyResult:
    status: str
    message_id: str
    recipients: list[str]
    subject: str
    error: str | None = None


@dataclass(slots=True)
class SendEmailResult:
    status: str
    message_id: str
    recipients: list[str]
    subject: str
    error: str | None = None


def send_reply(
    to: list[str],
    subject: str,
    body: str,
    reply_to_message_id: str | None,
    config,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
    references: list[str] | None = None,
) -> SendReplyResult:
    to_addresses = _normalize_recipients(to)
    if not to_addresses:
        raise ValueError("At least one recipient is required")
    smtp_username = getattr(config, "smtp_username", None) or getattr(config, "smtp_user", None)
    if not config.smtp_host or not smtp_username or not config.smtp_password:
        raise ValueError("SMTP credentials are not fully configured")

    cc_addresses = _normalize_recipients(cc)
    bcc_addresses = _normalize_recipients(bcc)
    recipients = list(dict.fromkeys([*to_addresses, *cc_addresses, *bcc_addresses]))
    if not recipients:
        raise ValueError("No valid recipients were provided")

    message = EmailMessage()
    message["From"] = getattr(config, "email_address", None) or smtp_username
    message["To"] = ", ".join(to_addresses)
    if cc_addresses:
        message["Cc"] = ", ".join(cc_addresses)
    message["Subject"] = subject
    if reply_to_message_id:
        message["In-Reply-To"] = reply_to_message_id
        reference_values = [*(references or []), reply_to_message_id]
        deduped = list(dict.fromkeys(reference_values))
        message["References"] = " ".join(deduped)
    message["Message-ID"] = make_msgid()
    message.set_content(body)

    _send_message(message, recipients, config, subject, to_addresses, cc_addresses, bcc_addresses)
    return SendReplyResult(
        status="sent",
        message_id=message["Message-ID"],
        recipients=recipients,
        subject=subject,
    )


def send_email(
    *,
    to: list[str],
    subject: str,
    body: str,
    config,
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
) -> SendEmailResult:
    to_addresses = _normalize_recipients(to)
    if not to_addresses:
        raise ValueError("At least one recipient is required")
    smtp_username = getattr(config, "smtp_username", None) or getattr(config, "smtp_user", None)
    if not config.smtp_host or not smtp_username or not config.smtp_password:
        raise ValueError("SMTP credentials are not fully configured")

    cc_addresses = _normalize_recipients(cc)
    bcc_addresses = _normalize_recipients(bcc)
    recipients = list(dict.fromkeys([*to_addresses, *cc_addresses, *bcc_addresses]))
    if not recipients:
        raise ValueError("No valid recipients were provided")

    message = EmailMessage()
    message["From"] = getattr(config, "email_address", None) or smtp_username
    message["To"] = ", ".join(to_addresses)
    if cc_addresses:
        message["Cc"] = ", ".join(cc_addresses)
    message["Subject"] = subject
    message["Message-ID"] = make_msgid()
    message.set_content(body)

    _send_message(message, recipients, config, subject, to_addresses, cc_addresses, bcc_addresses)
    return SendEmailResult(
        status="sent",
        message_id=message["Message-ID"],
        recipients=recipients,
        subject=subject,
    )


def test_smtp_connection(config) -> None:
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    smtp_username = getattr(config, "smtp_username", None) or getattr(config, "smtp_user", None)
    if not getattr(config, "smtp_host", None) or not smtp_username or not getattr(config, "smtp_password", None):
        raise SmtpError("SMTP credentials are not fully configured")

    try:
        if getattr(config, "smtp_use_ssl", False):
            with smtplib.SMTP_SSL(
                config.smtp_host,
                config.smtp_port,
                context=context,
                timeout=30,
            ) as server:
                server.login(smtp_username, config.smtp_password)
                return

        with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=30) as server:
            server.ehlo()
            if getattr(config, "smtp_use_tls", True):
                server.starttls(context=context)
                server.ehlo()
            server.login(smtp_username, config.smtp_password)
    except smtplib.SMTPAuthenticationError as exc:
        logger.warning("SMTP authentication failed during connection test", exc_info=True)
        raise SmtpError("SMTP authentication failed") from exc
    except (smtplib.SMTPException, OSError) as exc:
        logger.warning("SMTP connection test failed", exc_info=True)
        raise SmtpError(str(exc)) from exc


def _send_message(
    message: EmailMessage,
    recipients: list[str],
    config,
    subject: str,
    to_addresses: list[str],
    cc_addresses: list[str],
    bcc_addresses: list[str],
) -> None:
    try:
        _deliver_message(message, recipients, config)
        try:
            append_sent_copy_to_imap(config, message, folder_kind="sent")
        except Exception:
            logger.warning(
                "SMTP send succeeded but IMAP sent-copy append failed: host=%s subject=%s",
                getattr(config, "smtp_host", None),
                subject,
                exc_info=True,
            )
    except SmtpError as exc:
        logger.warning(
            "SMTP send failed: host=%s to=%s cc=%s bcc_count=%s subject=%s",
            getattr(config, "smtp_host", None),
            to_addresses,
            cc_addresses,
            len(bcc_addresses),
            subject,
            exc_info=True,
        )
        raise exc


@retry(
    retry=retry_if_exception_type(SmtpError),
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    reraise=True,
)
def _deliver_message(message: EmailMessage, recipients: list[str], config) -> None:
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    smtp_username = getattr(config, "smtp_username", None) or getattr(config, "smtp_user", None)
    if not getattr(config, "smtp_host", None) or not smtp_username or not getattr(config, "smtp_password", None):
        raise SmtpError("SMTP credentials are not fully configured")

    try:
        if getattr(config, "smtp_use_ssl", False):
            with smtplib.SMTP_SSL(
                config.smtp_host,
                config.smtp_port,
                context=context,
                timeout=30,
            ) as server:
                server.login(smtp_username, config.smtp_password)
                server.send_message(message, to_addrs=recipients)
            return

        with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=30) as server:
            server.ehlo()
            if getattr(config, "smtp_use_tls", True):
                server.starttls(context=context)
                server.ehlo()
            server.login(smtp_username, config.smtp_password)
            server.send_message(message, to_addrs=recipients)
    except smtplib.SMTPAuthenticationError as exc:
        raise SmtpError("SMTP authentication failed") from exc
    except (smtplib.SMTPException, OSError) as exc:
        raise SmtpError(str(exc)) from exc


def _normalize_recipients(addresses: list[str] | None) -> list[str]:
    if not addresses:
        return []
    cleaned: list[str] = []
    for item in addresses:
        value = (item or "").strip()
        if not value or value in cleaned:
            continue
        cleaned.append(value)
    return cleaned
