import logging
import secrets
from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.models.session_token import SessionToken
from app.models.user import User
from app.services.auth_service import hash_password, validate_password_strength

VALID_ROLES = {"admin", "manager", "operator", "viewer"}
logger = logging.getLogger(__name__)


def list_users(db_session: Session) -> list[User]:
    return db_session.query(User).order_by(User.id.asc()).all()


def get_user_by_id(db_session: Session, user_id: int) -> User | None:
    return db_session.query(User).filter(User.id == user_id).first()


def get_user_by_email(db_session: Session, email: str) -> User | None:
    return db_session.query(User).filter(User.email == email.strip().lower()).first()


def create_user(
    db_session: Session,
    email: str,
    full_name: str,
    password: str,
    role: str = "operator",
    timezone: str | None = None,
    language: str | None = None,
) -> User:
    normalized_role = role.strip().lower()
    if normalized_role not in VALID_ROLES:
        raise ValueError("Unsupported role")
    normalized_email = email.strip().lower()
    if not normalized_email:
        raise ValueError("Email is required")
    if get_user_by_email(db_session, normalized_email):
        raise ValueError("User with this email already exists")
    validate_password_strength(password)

    user = User(
        email=normalized_email,
        full_name=full_name.strip() or normalized_email,
        password_hash=hash_password(password),
        role=normalized_role,
        is_active=True,
        timezone=timezone,
        language=language,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def update_user(db_session: Session, user: User, payload: dict) -> User:
    if "email" in payload and payload["email"]:
        candidate = payload["email"].strip().lower()
        if candidate != user.email and get_user_by_email(db_session, candidate):
            raise ValueError("User with this email already exists")
        user.email = candidate
    if "full_name" in payload and payload["full_name"] is not None:
        user.full_name = str(payload["full_name"]).strip() or user.full_name
    if "role" in payload and payload["role"]:
        role = str(payload["role"]).strip().lower()
        if role not in VALID_ROLES:
            raise ValueError("Unsupported role")
        user.role = role
    if "timezone" in payload:
        user.timezone = payload["timezone"]
    if "language" in payload:
        user.language = payload["language"]
    if "is_active" in payload and payload["is_active"] is not None:
        user.is_active = bool(payload["is_active"])
    user.updated_at = datetime.now(timezone.utc)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def disable_user(db_session: Session, user: User) -> User:
    user.is_active = False
    user.updated_at = datetime.now(timezone.utc)
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)
    return user


def reset_user_password(db_session: Session, user: User, new_password: str) -> User:
    validate_password_strength(new_password)
    user.password_hash = hash_password(new_password)
    user.updated_at = datetime.now(timezone.utc)
    db_session.add(user)
    db_session.flush()
    db_session.query(SessionToken).filter(SessionToken.user_id == user.id).delete(synchronize_session=False)
    db_session.commit()
    db_session.refresh(user)
    return user


def ensure_default_admin() -> None:
    # Import lazily so tests/runtime use the active global database session.
    from app.db import open_global_session

    if not settings.bootstrap_default_admin:
        return

    db = open_global_session()
    try:
        existing = db.query(User).count()
        if existing > 0:
            return

        bootstrap_email = settings.bootstrap_admin_email.strip().lower() or "admin@orhun.local"
        bootstrap_name = settings.bootstrap_admin_full_name.strip() or "Bootstrap Admin"
        bootstrap_password = settings.bootstrap_admin_password.strip()
        generated_password = None
        if not bootstrap_password:
            generated_password = secrets.token_urlsafe(12)
            bootstrap_password = generated_password

        admin = User(
            email=bootstrap_email,
            full_name=bootstrap_name,
            password_hash=hash_password(bootstrap_password),
            role="admin",
            is_active=True,
        )
        db.add(admin)
        db.commit()

        if generated_password:
            logger.warning(
                "Bootstrap admin created for empty instance: email=%s password=%s",
                bootstrap_email,
                generated_password,
            )
        else:
            logger.warning("Bootstrap admin created for empty instance: email=%s", bootstrap_email)
    except IntegrityError:
        db.rollback()
    finally:
        db.close()
