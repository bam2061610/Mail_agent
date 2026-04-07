from pathlib import Path


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


def test_backup_restore_preserves_account_databases_and_preference_profile(isolated_paths, db_session):
    from app.db import dispose_database_engines, open_account_session
    from app.models.email import Email
    from app.services.backup_service import create_backup, restore_backup
    from app.services.preference_profile import rebuild_preference_profile

    mailbox_db = open_account_session("mailbox-a")
    try:
        mailbox_db.add(
            Email(
                message_id="<backup-mailbox-a@test>",
                thread_id="backup-thread-a",
                subject="Mailbox-specific email",
                sender_email="a@example.com",
                body_text="Important mailbox content",
                folder="inbox",
                direction="inbound",
                status="new",
            )
        )
        mailbox_db.commit()
    finally:
        mailbox_db.close()

    rebuild_preference_profile(db_session)

    result = create_backup(include_attachments=False, keep_last=3, reason="test")
    backup_dir = Path(result.backup_path)
    account_db_backup = backup_dir / "account_dbs" / "mailbox-a" / "mail_agent.db"
    preference_profile_backup = backup_dir / "config" / "preference_profile.json"

    assert account_db_backup.exists()
    assert preference_profile_backup.exists()

    live_account_db = isolated_paths["data_dir"] / "account_dbs" / "mailbox-a" / "mail_agent.db"
    assert live_account_db.exists()
    dispose_database_engines()
    live_account_db.unlink()
    preference_profile_path = isolated_paths["data_dir"] / "preference_profile.json"
    preference_profile_path.unlink()

    restore = restore_backup(
        backup_name=result.backup_name,
        confirmation=f"RESTORE {result.backup_name}",
        restore_attachments=False,
        create_safety_backup=False,
    )

    assert restore.restored_database is True
    assert live_account_db.exists()
    assert preference_profile_path.exists()

    restored_account_db = open_account_session("mailbox-a")
    try:
        restored_email = restored_account_db.query(Email).filter(Email.message_id == "<backup-mailbox-a@test>").first()
        assert restored_email is not None
        assert restored_email.subject == "Mailbox-specific email"
    finally:
        restored_account_db.close()
