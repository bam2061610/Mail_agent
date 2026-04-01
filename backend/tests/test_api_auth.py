def test_auth_login_and_me(client, admin_user):
    login = client.post("/api/auth/login", json={"email": admin_user.email, "password": "admin123"})
    assert login.status_code == 200
    token = login.json()["access_token"]
    me = client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["user"]["email"] == admin_user.email


def test_auth_rejects_bad_credentials(client, admin_user):
    response = client.post("/api/auth/login", json={"email": admin_user.email, "password": "wrong"})
    assert response.status_code == 401
