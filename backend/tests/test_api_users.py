from app.services.user_service import create_user


def test_create_user_rejects_weak_password(client, admin_auth_headers):
    response = client.post(
        "/api/users",
        headers=admin_auth_headers,
        json={
            "email": "weak@example.com",
            "full_name": "Weak Password",
            "password": "1234567",
            "role": "operator",
        },
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "Password must be at least 8 characters long"


def test_reset_password_rejects_weak_password(client, db_session, admin_auth_headers):
    user = create_user(
        db_session=db_session,
        email="reset-target@example.com",
        full_name="Reset Target",
        password="strongpass123",
        role="operator",
    )

    response = client.post(
        f"/api/users/{user.id}/reset-password",
        headers=admin_auth_headers,
        json={"new_password": "1234567"},
    )
    assert response.status_code == 422
    assert response.json()["detail"] == "Password must be at least 8 characters long"
