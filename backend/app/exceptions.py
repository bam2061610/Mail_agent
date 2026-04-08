class MailAgentError(Exception):
    """Base application exception."""


class ImapError(MailAgentError):
    """Raised for IMAP connection and mailbox interaction failures."""


class SmtpError(MailAgentError):
    """Raised for SMTP delivery and connection failures."""


class AiError(MailAgentError):
    """Raised for AI provider and inference failures."""


class SetupError(MailAgentError):
    """Raised for first-run setup failures."""


class NotFoundError(MailAgentError):
    """Raised when an expected record is missing."""


class PermissionError(MailAgentError):
    """Raised when an operation is not permitted."""
