from app.config import Settings, get_effective_settings, get_safe_settings_view


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
