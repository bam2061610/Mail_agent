import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.action_log import ActionLog
from app.models.user import User
from app.schemas.system import (
    OperationStatusResponse,
    UserCreateRequest,
    UserResetPasswordRequest,
    UserResponse,
    UserUpdateRequest,
)
from app.services.auth_service import PasswordValidationError
from app.services.permission_service import require_permission
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
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manage_users")),
) -> list[UserResponse]:
    return [UserResponse.model_validate(item) for item in list_users(db)]


@router.post("", response_model=UserResponse)
def create_user_route(
    request: UserCreateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manage_users")),
) -> UserResponse:
    try:
        user = create_user(
            db_session=db,
            email=request.email,
            full_name=request.full_name,
            password=request.password,
            role=request.role,
            timezone=request.timezone,
            language=request.language,
        )
    except PasswordValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.add(
        ActionLog(
            user_id=current_user.id,
            action_type="user_created",
            actor=current_user.email,
            details_json=json.dumps({"target_user_id": user.id, "target_email": user.email, "role": user.role}, ensure_ascii=False),
        )
    )
    db.commit()
    return UserResponse.model_validate(user)


@router.put("/{user_id}", response_model=UserResponse)
def update_user_route(
    user_id: int,
    request: UserUpdateRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manage_users")),
) -> UserResponse:
    user = get_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    try:
        updated = update_user(db, user, request.model_dump(exclude_none=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.add(
        ActionLog(
            user_id=current_user.id,
            action_type="user_updated",
            actor=current_user.email,
            details_json=json.dumps({"target_user_id": updated.id}, ensure_ascii=False),
        )
    )
    db.commit()
    return UserResponse.model_validate(updated)


@router.post("/{user_id}/disable", response_model=UserResponse)
def disable_user_route(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manage_users")),
) -> UserResponse:
    user = get_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    disabled = disable_user(db, user)
    db.add(
        ActionLog(
            user_id=current_user.id,
            action_type="user_disabled",
            actor=current_user.email,
            details_json=json.dumps({"target_user_id": disabled.id}, ensure_ascii=False),
        )
    )
    db.commit()
    return UserResponse.model_validate(disabled)


@router.post("/{user_id}/reset-password", response_model=OperationStatusResponse)
def reset_password_route(
    user_id: int,
    request: UserResetPasswordRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_permission("manage_users")),
) -> OperationStatusResponse:
    user = get_user_by_id(db, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="User not found")
    try:
        reset_user_password(db, user, request.new_password)
    except PasswordValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    db.add(
        ActionLog(
            user_id=current_user.id,
            action_type="user_password_reset",
            actor=current_user.email,
            details_json=json.dumps({"target_user_id": user.id}, ensure_ascii=False),
        )
    )
    db.commit()
    return OperationStatusResponse()

