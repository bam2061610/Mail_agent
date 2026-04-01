from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ContactShort(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    name: str | None = None
    company: str | None = None


class ContactDetail(ContactShort):
    preferred_language: str | None = None
    last_contact_at: datetime | None = None
    emails_received_count: int
    emails_sent_count: int
    notes: str | None = None
    created_at: datetime
    updated_at: datetime


class ContactListResponse(BaseModel):
    items: list[ContactShort]
    total: int
    limit: int
    offset: int
