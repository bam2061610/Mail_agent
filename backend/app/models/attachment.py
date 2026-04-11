from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Attachment(Base):
    __tablename__ = "attachments"
    __table_args__ = (
        UniqueConstraint("email_id", "content_hash", name="uq_attachments_email_content_hash"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email_id: Mapped[int] = mapped_column(ForeignKey("emails.id"), nullable=False, index=True)
    filename: Mapped[str | None] = mapped_column(String(500), nullable=True, index=True)
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    content_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    content_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_inline: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    local_storage_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)

    @property
    def storage_mode(self) -> str:
        return "local" if self.local_storage_path else "imap"
