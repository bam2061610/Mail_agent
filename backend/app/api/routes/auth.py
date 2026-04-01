import json

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.action_log import ActionLog
from app.models.user import User
from app.schemas.system import AuthLoginRequest, AuthLoginResponse, AuthMeResponse, OperationStatusResponse, UserResponse
from app.services.auth_service import (
    authenticate_user,
    create_session_token,
    get_current_user,
    revoke_session_token,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/login", response_model=AuthLoginResponse)
def login(request: AuthLoginRequest, db: Session = Depends(get_db)) -> AuthLoginResponse:
    user = authenticate_user(db, request.email, request.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    token = create_session_token(user)
    db.add(
        ActionLog(
            user_id=user.id,
            action_type="login",
            actor=user.email,
            details_json=json.dumps({"role": user.role}, ensure_ascii=False),
        )
    )
    db.commit()
    return AuthLoginResponse(access_token=token, user=UserResponse.model_validate(user))


@router.post("/logout", response_model=OperationStatusResponse)
def logout(
    authorization: str | None = Header(default=None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OperationStatusResponse:
    token = None
    if authorization:
        parts = authorization.strip().split(" ", 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":
            token = parts[1].strip()
    if token:
        revoke_session_token(token)
    db.add(
        ActionLog(
            user_id=current_user.id,
            action_type="logout",
            actor=current_user.email,
            details_json=json.dumps({}, ensure_ascii=False),
        )
    )
    db.commit()
    return OperationStatusResponse()


@router.get("/me", response_model=AuthMeResponse)
def me(current_user: User = Depends(get_current_user)) -> AuthMeResponse:
    return AuthMeResponse(user=UserResponse.model_validate(current_user))

