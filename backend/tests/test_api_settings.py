def test_settings_get_and_update_summary_language(client, admin_auth_headers):
    initial = client.get("/api/settings", headers=admin_auth_headers)
    assert initial.status_code == 200
    assert initial.json()["interface_language"] == "ru"
    assert initial.json()["summary_language"] == "ru"
    assert initial.json()["scan_since_date"] is None
    assert initial.json()["auto_spam_enabled"] is True

    update = client.post(
        "/api/settings",
        headers=admin_auth_headers,
        json={
            "interface_language": "tr",
            "summary_language": "tr",
            "scan_since_date": "2026-04-01T00:00:00Z",
            "signature": "Best regards",
            "auto_spam_enabled": False,
        },
    )
    assert update.status_code == 200
    updated_payload = update.json()
    assert updated_payload["interface_language"] == "tr"
    assert updated_payload["summary_language"] == "tr"
    assert updated_payload["scan_since_date"] == "2026-04-01T00:00:00Z"
    assert updated_payload["signature"] == "Best regards"
    assert updated_payload["auto_spam_enabled"] is False

    refetched = client.get("/api/settings", headers=admin_auth_headers)
    assert refetched.status_code == 200
    assert refetched.json()["interface_language"] == "tr"
    assert refetched.json()["summary_language"] == "tr"
    assert refetched.json()["scan_since_date"] == "2026-04-01T00:00:00Z"
    assert refetched.json()["auto_spam_enabled"] is False


def test_mailbox_connection_missing_returns_structured_error(client, admin_auth_headers):
    response = client.post("/api/mailboxes/missing-mailbox/test-connection", headers=admin_auth_headers)

    assert response.status_code == 404
    payload = response.json()
    assert payload["error_code"] == "mailbox_context_missing"
    assert payload["details"]["mailbox_id"] == "missing-mailbox"
