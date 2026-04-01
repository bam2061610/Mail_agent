def test_admin_diagnostics_endpoints(client, admin_auth_headers):
    health = client.get("/api/admin/health", headers=admin_auth_headers)
    assert health.status_code == 200
    diagnostics = client.get("/api/admin/diagnostics", headers=admin_auth_headers)
    assert diagnostics.status_code == 200
    jobs = client.get("/api/admin/jobs", headers=admin_auth_headers)
    assert jobs.status_code == 200
    mailbox_status = client.get("/api/admin/mailboxes/status", headers=admin_auth_headers)
    assert mailbox_status.status_code == 200


def test_admin_backup_create_list_status_and_restore_guard(client, admin_auth_headers):
    create_resp = client.post(
        "/api/admin/backups/create",
        headers=admin_auth_headers,
        json={"include_attachments": False, "keep_last": 5},
    )
    assert create_resp.status_code == 200
    backup_name = create_resp.json()["backup_name"]

    list_resp = client.get("/api/admin/backups", headers=admin_auth_headers)
    assert list_resp.status_code == 200
    assert any(item["backup_name"] == backup_name for item in list_resp.json())

    status_resp = client.get("/api/admin/backups/status", headers=admin_auth_headers)
    assert status_resp.status_code == 200
    assert status_resp.json()["backups_count"] >= 1

    restore_guard = client.post(
        "/api/admin/backups/restore",
        headers=admin_auth_headers,
        json={"backup_name": backup_name, "confirmation": "WRONG"},
    )
    assert restore_guard.status_code == 400


def test_backup_and_diagnostics_services_smoke(db_session):
    from app.services.backup_service import create_backup, list_backups
    from app.services.diagnostics_service import collect_admin_health

    result = create_backup(include_attachments=False, keep_last=3, reason="test")
    assert result.backup_name.startswith("backup_")
    backups = list_backups()
    assert backups

    health = collect_admin_health(db_session, scheduler_running=False, test_mailboxes=False)
    assert health["overall_status"] in {"ok", "degraded"}
    assert "components" in health
