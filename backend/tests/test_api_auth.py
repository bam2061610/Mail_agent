from datetime import datetime, timedelta, timezone

from app.models.session_token import SessionToken
from app.services.auth_service import cleanup_expired_session_tokens


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


def test_auth_logout_revokes_session_token(client, db_session, admin_user):
    login = client.post("/api/auth/login", json={"email": admin_user.email, "password": "admin123"})
    assert login.status_code == 200
    token = login.json()["access_token"]
    assert db_session.query(SessionToken).filter(SessionToken.token == token).first() is not None

    logout = client.post("/api/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert logout.status_code == 200
    assert db_session.query(SessionToken).filter(SessionToken.token == token).first() is None


def test_cleanup_expired_session_tokens(db_session, admin_user):
    expired = SessionToken(
        token="expired-token",
        user_id=admin_user.id,
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
    )
    active = SessionToken(
        token="active-token",
        user_id=admin_user.id,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    db_session.add_all([expired, active])
    db_session.commit()

    removed = cleanup_expired_session_tokens(db_session)
    assert removed == 1
    assert db_session.query(SessionToken).filter(SessionToken.token == "expired-token").first() is None
    assert db_session.query(SessionToken).filter(SessionToken.token == "active-token").first() is not None
