from app.models.user import User
from app.services.auth_service import verify_password
from app.services.user_service import ensure_default_admin


def test_ensure_default_admin_skips_when_bootstrap_disabled(db_session, monkeypatch):
    import app.services.user_service as user_service

    monkeypatch.setattr(user_service.settings, "bootstrap_default_admin", False, raising=False)
    monkeypatch.setattr(user_service.settings, "bootstrap_admin_email", "disabled@example.com", raising=False)
    monkeypatch.setattr(user_service.settings, "bootstrap_admin_password", "securepass123", raising=False)

    ensure_default_admin()

    assert db_session.query(User).count() == 0


def test_ensure_default_admin_uses_configured_credentials(db_session, monkeypatch):
    import app.services.user_service as user_service

    monkeypatch.setattr(user_service.settings, "bootstrap_default_admin", True, raising=False)
    monkeypatch.setattr(user_service.settings, "bootstrap_admin_email", "bootstrap@example.com", raising=False)
    monkeypatch.setattr(user_service.settings, "bootstrap_admin_password", "securepass123", raising=False)
    monkeypatch.setattr(user_service.settings, "bootstrap_admin_full_name", "Bootstrap Root", raising=False)

    ensure_default_admin()
    ensure_default_admin()

    created = db_session.query(User).filter(User.email == "bootstrap@example.com").all()
    assert len(created) == 1
    assert created[0].role == "admin"
    assert created[0].full_name == "Bootstrap Root"
    assert verify_password("securepass123", created[0].password_hash) is True
