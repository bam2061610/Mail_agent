from app.models.user import User
from app.services.permission_service import has_permission


def test_permission_matrix_basic():
    admin = User(email="a@a", full_name="a", password_hash="x", role="admin", is_active=True)
    viewer = User(email="v@v", full_name="v", password_hash="x", role="viewer", is_active=True)
    assert has_permission(admin, "manage_users") is False
    assert has_permission(admin, "assign_items") is False
    assert has_permission(viewer, "manage_users") is False
    assert has_permission(viewer, "read") is True
    assert has_permission(viewer, "send_email") is False


def test_operator_cannot_access_admin_ops(client, operator_auth_headers):
    response = client.get("/api/admin/health", headers=operator_auth_headers)
    assert response.status_code == 403
