from app.config import Settings, get_effective_settings, get_safe_settings_view, load_runtime_settings, save_runtime_settings


def test_settings_parse_debug():
    config = Settings(DEBUG="false")
    assert config.debug is False
    config2 = Settings(DEBUG="yes")
    assert config2.debug is True


def test_safe_settings_redacts_secrets():
    effective = get_effective_settings()
    effective.smtp_password = "secret"
    effective.imap_password = "secret"
    effective.openai_api_key = "secret"
    payload = get_safe_settings_view()
    assert "smtp_password" not in payload
    assert "imap_password" not in payload
    assert "openai_api_key" not in payload
    assert "has_smtp_password" in payload
    assert "auto_spam_enabled" in payload


def test_runtime_settings_persist_and_update(db_session):
    saved = save_runtime_settings(
        {
            "app_name": "Orhun Mail Agent",
            "imap_host": "imap.example.com",
            "imap_port": 993,
            "imap_user": "user@example.com",
            "imap_password": "secret",
            "smtp_host": "smtp.example.com",
            "smtp_port": 465,
            "smtp_user": "user@example.com",
            "smtp_password": "smtp-secret",
            "deepseek_base_url": "https://api.deepseek.com",
            "deepseek_model": "deepseek-chat",
            "interface_language": "en",
            "summary_language": "tr",
            "scan_since_date": "2026-04-01T00:00:00Z",
            "signature": "Best regards",
            "auto_spam_enabled": True,
            "cors_origins": ["http://localhost:3000"],
        }
    )
    assert saved["imap_host"] == "imap.example.com"
    assert saved["interface_language"] == "en"
    assert saved["summary_language"] == "tr"
    assert saved["scan_since_date"] == "2026-04-01T00:00:00Z"
    assert saved["signature"] == "Best regards"
    assert saved["auto_spam_enabled"] is True
    assert saved["cors_origins"] == ["http://localhost:3000"]

    loaded = load_runtime_settings()
    assert loaded["imap_host"] == "imap.example.com"
    assert loaded["smtp_password"] == "smtp-secret"
    assert loaded["interface_language"] == "en"
    assert loaded["summary_language"] == "tr"
    assert loaded["scan_since_date"] == "2026-04-01T00:00:00Z"
    assert loaded["auto_spam_enabled"] is True

    updated = save_runtime_settings({"imap_host": "imap.updated.example.com", "signature": "Updated sig"})
    assert updated["imap_host"] == "imap.updated.example.com"
    assert updated["signature"] == "Updated sig"

    effective = get_effective_settings()
    assert effective.imap_host == "imap.updated.example.com"
    assert effective.signature == "Updated sig"
    assert effective.interface_language == "en"
    assert effective.summary_language == "tr"
    assert effective.scan_since_date == "2026-04-01T00:00:00Z"
    assert effective.auto_spam_enabled is True
