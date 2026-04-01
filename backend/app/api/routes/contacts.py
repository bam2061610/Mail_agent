from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.contact import Contact
from app.models.user import User
from app.schemas.contact import ContactListResponse
from app.services.permission_service import require_permission

router = APIRouter(prefix="/api/contacts", tags=["contacts"])


@router.get("", response_model=ContactListResponse)
def list_contacts(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("read")),
) -> ContactListResponse:
    total = db.query(Contact).count()
    items = (
        db.query(Contact)
        .order_by(Contact.last_contact_at.desc().nullslast(), Contact.id.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    return ContactListResponse(items=items, total=total, limit=limit, offset=offset)
