import smtplib
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.utils import make_msgid


@dataclass(slots=True)
class SendReplyResult:
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
    if not to:
        raise ValueError("At least one recipient is required")
    if not config.smtp_host or not config.smtp_user or not config.smtp_password:
        raise ValueError("SMTP credentials are not fully configured")

    cc = cc or []
    bcc = bcc or []
    recipients = [address for address in [*to, *cc, *bcc] if address]
    if not recipients:
        raise ValueError("No valid recipients were provided")

    message = EmailMessage()
    message["From"] = config.smtp_user
    message["To"] = ", ".join(to)
    if cc:
        message["Cc"] = ", ".join(cc)
    message["Subject"] = subject
    if reply_to_message_id:
        message["In-Reply-To"] = reply_to_message_id
        reference_values = [*(references or []), reply_to_message_id]
        deduped = list(dict.fromkeys(reference_values))
        message["References"] = " ".join(deduped)
    message["Message-ID"] = make_msgid()
    message.set_content(body)

    try:
        _deliver_message(message, recipients, config)
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"SMTP send failed: {exc}") from exc

    return SendReplyResult(
        status="sent",
        message_id=message["Message-ID"],
        recipients=recipients,
        subject=subject,
    )


def _deliver_message(message: EmailMessage, recipients: list[str], config) -> None:
    context = ssl.create_default_context()

    if getattr(config, "smtp_use_ssl", False):
        with smtplib.SMTP_SSL(config.smtp_host, config.smtp_port, context=context, timeout=30) as server:
            server.login(config.smtp_user, config.smtp_password)
            server.send_message(message, to_addrs=recipients)
        return

    with smtplib.SMTP(config.smtp_host, config.smtp_port, timeout=30) as server:
        server.ehlo()
        if getattr(config, "smtp_use_tls", True):
            server.starttls(context=context)
            server.ehlo()
        server.login(config.smtp_user, config.smtp_password)
        server.send_message(message, to_addrs=recipients)
