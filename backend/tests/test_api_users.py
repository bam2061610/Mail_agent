from app.services.user_service import create_user, reset_user_password


def test_users_route_removed(client, admin_auth_headers):
    response = client.get("/api/users", headers=admin_auth_headers)
    assert response.status_code == 404


def test_create_user_rejects_weak_password(db_session):
    try:
        create_user(
            db_session=db_session,
            email="weak@example.com",
            full_name="Weak Password",
            password="1234567",
            role="operator",
        )
        raise AssertionError("Expected weak password validation to fail")
    except ValueError as exc:
        assert str(exc) == "Password must be at least 8 characters long"


def test_reset_password_rejects_weak_password(db_session, admin_user):
    try:
        reset_user_password(db_session, admin_user, "1234567")
        raise AssertionError("Expected weak password validation to fail")
    except ValueError as exc:
        assert str(exc) == "Password must be at least 8 characters long"
