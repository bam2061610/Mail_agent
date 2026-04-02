import base64
import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.config import get_effective_settings
from app.db import get_db
from app.models.session_token import SessionToken
from app.models.user import User

TOKEN_TTL_HOURS = 24
PBKDF2_ITERATIONS = 210_000
PBKDF2_DIGEST = "sha256"
logger = logging.getLogger(__name__)


class PasswordValidationError(ValueError):
    """Raised when a password fails strength checks."""


def validate_password_strength(password: str) -> None:
    if not password:
        raise PasswordValidationError("Password is required")
    if len(password) < 8:
        raise PasswordValidationError("Password must be at least 8 characters long")


def hash_password(password: str) -> str:
    validate_password_strength(password)
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        PBKDF2_DIGEST,
        password.encode("utf-8"),
        bytes.fromhex(salt),
        PBKDF2_ITERATIONS,
    )
    return f"pbkdf2_{PBKDF2_DIGEST}${PBKDF2_ITERATIONS}${salt}${base64.b64encode(digest).decode('ascii')}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        prefix, iterations_text, salt, encoded_digest = password_hash.split("$", 3)
        if not prefix.startswith("pbkdf2_"):
            return False
        digest_name = prefix.removeprefix("pbkdf2_")
        iterations = int(iterations_text)
    except Exception:  # noqa: BLE001
        return False

    candidate = hashlib.pbkdf2_hmac(
        digest_name,
        password.encode("utf-8"),
        bytes.fromhex(salt),
        iterations,
    )
    expected = base64.b64decode(encoded_digest.encode("ascii"))
    return hmac.compare_digest(candidate, expected)


def create_session_token(db_session: Session, user: User) -> str:
    token = secrets.token_urlsafe(48)
    expires_at = datetime.now(timezone.utc) + timedelta(hours=TOKEN_TTL_HOURS)
    db_session.add(
        SessionToken(
            token=token,
            user_id=user.id,
            expires_at=expires_at,
        )
    )
    return token


def revoke_session_token(db_session: Session, token: str) -> None:
    db_session.query(SessionToken).filter(SessionToken.token == token).delete(synchronize_session=False)


def authenticate_user(db_session: Session, email: str, password: str) -> User | None:
    normalized = email.strip().lower()
    user = db_session.query(User).filter(User.email == normalized).first()
    if user is None or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    user.last_login_at = datetime.now(timezone.utc)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def get_user_by_token(db_session: Session, token: str) -> User | None:
    record = db_session.query(SessionToken).filter(SessionToken.token == token).first()
    if record is None:
        return None
    expires_at = _parse_dt(record.expires_at)
    if expires_at is None or expires_at < datetime.now(timezone.utc):
        db_session.delete(record)
        db_session.commit()
        return None
    user = db_session.query(User).filter(User.id == int(record.user_id), User.is_active.is_(True)).first()
    if user is None:
        db_session.delete(record)
        db_session.commit()
        return None
    return user


def cleanup_expired_session_tokens(db_session: Session, *, now: datetime | None = None) -> int:
    current_time = now or datetime.now(timezone.utc)
    removed = (
        db_session.query(SessionToken)
        .filter(SessionToken.expires_at < current_time)
        .delete(synchronize_session=False)
    )
    db_session.commit()
    return int(removed or 0)


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    token = _extract_bearer_token(authorization)
    if not token:
        user = _maybe_dev_single_user(db)
        if user is not None:
            return user
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    user = get_user_by_token(db, token)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    return user


def get_optional_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User | None:
    token = _extract_bearer_token(authorization)
    if token:
        return get_user_by_token(db, token)
    return _maybe_dev_single_user(db)


def _extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    parts = authorization.strip().split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        return None
    token = parts[1].strip()
    return token or None


def _maybe_dev_single_user(db_session: Session) -> User | None:
    settings = get_effective_settings()
    if getattr(settings, "app_env", "development") != "development" or not getattr(settings, "dev_auth_bypass", False):
        return None
    users = db_session.query(User).filter(User.is_active.is_(True)).order_by(User.id.asc()).limit(2).all()
    if len(users) == 1:
        logger.warning("Dev auth bypass: auto-authenticating as %s", users[0].email)
        return users[0]
    return None


def _parse_dt(value: datetime | str | None) -> datetime | None:
    if not value:
        return None
    parsed: datetime
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
