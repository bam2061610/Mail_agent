from app.schemas.contact import ContactDetail, ContactShort
from app.schemas.email import (
    EmailCreateDraftRequest,
    EmailDetail,
    EmailListItem,
    EmailUpdateStatusRequest,
)
from app.schemas.system import ErrorResponse, HealthResponse

__all__ = [
    "ContactDetail",
    "ContactShort",
    "EmailCreateDraftRequest",
    "EmailDetail",
    "EmailListItem",
    "EmailUpdateStatusRequest",
    "ErrorResponse",
    "HealthResponse",
]
