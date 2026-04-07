from app.models.user import User
from app.services.user_service import create_user, reset_user_password


def test_users_list_returns_existing_users(client, admin_auth_headers, admin_user, operator_user):
    response = client.get("/api/users", headers=admin_auth_headers)

    assert response.status_code == 200
    emails = [item["email"] for item in response.json()]
    assert admin_user.email in emails
    assert operator_user.email in emails


def test_users_list_requires_admin(client, operator_auth_headers):
    response = client.get("/api/users", headers=operator_auth_headers)

    assert response.status_code == 403


def test_create_user_via_api_persists_normalized_fields(client, admin_auth_headers, db_session):
    response = client.post(
        "/api/users",
        headers=admin_auth_headers,
        json={
            "email": " NEW.USER@Example.com ",
            "full_name": "New User",
            "password": "securepass123",
            "role": "manager",
            "timezone": "Asia/Almaty",
            "language": "ru",
        },
    )

    assert response.status_code == 201
    payload = response.json()
    assert payload["email"] == "new.user@example.com"
    assert payload["role"] == "manager"
    assert payload["timezone"] == "Asia/Almaty"
    assert payload["language"] == "ru"

    stored_user = db_session.query(User).filter(User.email == "new.user@example.com").first()
    assert stored_user is not None
    assert stored_user.full_name == "New User"


def test_create_user_rejects_duplicate_email(client, admin_auth_headers, admin_user):
    response = client.post(
        "/api/users",
        headers=admin_auth_headers,
        json={
            "email": admin_user.email,
            "full_name": "Duplicate User",
            "password": "securepass123",
            "role": "operator",
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "User with this email already exists"


def test_update_user_via_api_updates_profile_fields(client, admin_auth_headers, operator_user, db_session):
    response = client.put(
        f"/api/users/{operator_user.id}",
        headers=admin_auth_headers,
        json={
            "full_name": "Updated Operator",
            "role": "viewer",
            "timezone": "UTC",
            "language": "en",
            "is_active": True,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["full_name"] == "Updated Operator"
    assert payload["role"] == "viewer"
    assert payload["timezone"] == "UTC"
    assert payload["language"] == "en"

    db_session.refresh(operator_user)
    assert operator_user.full_name == "Updated Operator"
    assert operator_user.role == "viewer"


def test_disable_user_via_api_deactivates_target(client, admin_auth_headers, operator_user, db_session):
    response = client.post(f"/api/users/{operator_user.id}/disable", headers=admin_auth_headers)

    assert response.status_code == 200
    assert response.json()["is_active"] is False

    db_session.refresh(operator_user)
    assert operator_user.is_active is False


def test_disable_user_rejects_self_disable(client, admin_auth_headers, admin_user):
    response = client.post(f"/api/users/{admin_user.id}/disable", headers=admin_auth_headers)

    assert response.status_code == 400
    assert response.json()["detail"] == "You cannot disable your own account"


def test_reset_password_via_api_allows_login_with_new_password(client, admin_auth_headers, operator_user):
    reset = client.post(
        f"/api/users/{operator_user.id}/reset-password",
        headers=admin_auth_headers,
        json={"new_password": "newsecure123"},
    )

    assert reset.status_code == 200
    assert reset.json()["status"] == "ok"

    old_login = client.post("/api/auth/login", json={"email": operator_user.email, "password": "operator123"})
    assert old_login.status_code == 401

    new_login = client.post("/api/auth/login", json={"email": operator_user.email, "password": "newsecure123"})
    assert new_login.status_code == 200


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
