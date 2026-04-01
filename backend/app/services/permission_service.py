from collections.abc import Callable

from fastapi import Depends, HTTPException, status

from app.models.user import User
from app.services.auth_service import get_current_user

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "admin": {
        "read",
        "send_email",
        "update_status",
        "spam_review",
        "manage_settings",
        "manage_mailboxes",
        "manage_rules",
        "manage_users",
        "assign_items",
        "view_digest",
        "run_scan",
        "run_sent_review",
        "admin_ops",
    },
    "manager": {
        "read",
        "send_email",
        "update_status",
        "spam_review",
        "manage_rules",
        "assign_items",
        "view_digest",
        "run_scan",
        "run_sent_review",
    },
    "operator": {
        "read",
        "send_email",
        "update_status",
        "spam_review",
        "view_digest",
        "run_scan",
    },
    "viewer": {
        "read",
        "view_digest",
    },
}


def has_permission(user: User, permission: str) -> bool:
    permissions = ROLE_PERMISSIONS.get(user.role, set())
    return permission in permissions


def require_permission(permission: str) -> Callable[[User], User]:
    def _dependency(current_user: User = Depends(get_current_user)) -> User:
        if not has_permission(current_user, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission required: {permission}",
            )
        return current_user

    return _dependency


def require_admin() -> Callable[[User], User]:
    return require_permission("admin_ops")
