from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.user import User
from app.services.auth_service import hash_password, validate_password_strength

VALID_ROLES = {"admin", "manager", "operator", "viewer"}


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
    db_session.commit()
    db_session.refresh(user)
    return user


def ensure_default_admin() -> None:
    # Import lazily so tests/runtime use the active global database session.
    from app.db import open_global_session

    db = open_global_session()
    try:
        existing = db.query(User).count()
        if existing > 0:
            return
        admin = User(
            email="admin@orhun.local",
            full_name="Default Admin",
            password_hash=hash_password("admin123"),
            role="admin",
            is_active=True,
        )
        db.add(admin)
        db.commit()
    finally:
        db.close()
