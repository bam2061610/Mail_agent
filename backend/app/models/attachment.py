from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Attachment(Base):
    __tablename__ = "attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    email_id: Mapped[int] = mapped_column(ForeignKey("emails.id"), nullable=False, index=True)
    filename: Mapped[str | None] = mapped_column(String(500), nullable=True, index=True)
    content_type: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    content_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_inline: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    local_storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
