import json

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_global_db
from app.models.action_log import ActionLog
from app.models.user import User
from app.schemas.system import (
    OperationStatusResponse,
    UserCreateRequest,
    UserResetPasswordRequest,
    UserResponse,
    UserUpdateRequest,
)
from app.services.permission_service import require_admin
from app.services.user_service import (
    create_user,
    disable_user,
    get_user_by_id,
    list_users,
    reset_user_password,
    update_user,
)

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("", response_model=list[UserResponse])
def get_users(
    db: Session = Depends(get_global_db),
    current_user: User = Depends(require_admin()),
) -> list[User]:
    users = list_users(db)
    _log_user_action(db, current_user, "users_listed", {"count": len(users)})
    return users


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user_route(
    request: UserCreateRequest,
    db: Session = Depends(get_global_db),
    current_user: User = Depends(require_admin()),
) -> User:
    try:
        user = create_user(db, **request.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _log_user_action(
        db,
        current_user,
        "user_created",
        {"user_id": user.id, "email": user.email, "role": user.role},
    )
    return user


@router.put("/{user_id}", response_model=UserResponse)
def update_user_route(
    user_id: int,
    request: UserUpdateRequest,
    db: Session = Depends(get_global_db),
    current_user: User = Depends(require_admin()),
) -> User:
    user = _load_user_or_404(db, user_id)
    try:
        updated = update_user(db, user, request.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _log_user_action(
        db,
        current_user,
        "user_updated",
        {"user_id": updated.id, "email": updated.email, "role": updated.role},
    )
    return updated


@router.post("/{user_id}/disable", response_model=UserResponse)
def disable_user_route(
    user_id: int,
    db: Session = Depends(get_global_db),
    current_user: User = Depends(require_admin()),
) -> User:
    user = _load_user_or_404(db, user_id)
    if user.id == current_user.id:
        raise HTTPException(status_code=400, detail="You cannot disable your own account")

    updated = disable_user(db, user)
    _log_user_action(db, current_user, "user_disabled", {"user_id": updated.id, "email": updated.email})
    return updated


@router.post("/{user_id}/reset-password", response_model=OperationStatusResponse)
def reset_password_route(
    user_id: int,
    request: UserResetPasswordRequest,
    db: Session = Depends(get_global_db),
    current_user: User = Depends(require_admin()),
) -> OperationStatusResponse:
    user = _load_user_or_404(db, user_id)
    try:
        reset_user_password(db, user, request.new_password)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    _log_user_action(db, current_user, "user_password_reset", {"user_id": user.id, "email": user.email})
    return OperationStatusResponse()


def _load_user_or_404(db: Session, user_id: int) -> User:
    user = get_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    return user


def _log_user_action(db: Session, actor: User, action_type: str, payload: dict) -> None:
    db.add(
        ActionLog(
            user_id=actor.id,
            action_type=action_type,
            actor=actor.email,
            details_json=json.dumps(payload, ensure_ascii=False),
        )
    )
    db.commit()
