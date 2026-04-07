from pathlib import Path

from sqlalchemy import create_engine, inspect

from app import config as app_config


def test_create_tables_runs_alembic_for_global_and_account_databases(isolated_paths, monkeypatch):
    import app.db as app_db

    db_file = isolated_paths["data_dir"] / "migration-test.sqlite3"
    database_url = f"sqlite:///{db_file.as_posix()}"
    monkeypatch.setattr(app_config.settings, "database_url", database_url, raising=False)
    monkeypatch.setattr(app_db, "_discover_mailbox_ids", lambda: ["default", "mailbox-a"])
    app_db.dispose_database_engines()

    global_engine = create_engine(database_url, connect_args={"check_same_thread": False})
    with global_engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE emails (id INTEGER PRIMARY KEY)")
        connection.exec_driver_sql("CREATE TABLE runtime_settings (id INTEGER PRIMARY KEY)")
        connection.exec_driver_sql("CREATE TABLE tasks (id INTEGER PRIMARY KEY)")
        connection.exec_driver_sql("CREATE TABLE attachments (id INTEGER PRIMARY KEY)")
        connection.exec_driver_sql("CREATE TABLE action_log (id INTEGER PRIMARY KEY)")

    mailbox_db_path = Path(isolated_paths["data_dir"]) / "account_dbs" / "mailbox-a" / "mail_agent.db"
    mailbox_db_path.parent.mkdir(parents=True, exist_ok=True)
    mailbox_engine = create_engine(f"sqlite:///{mailbox_db_path.as_posix()}", connect_args={"check_same_thread": False})
    with mailbox_engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE emails (id INTEGER PRIMARY KEY)")

    try:
        app_db.create_tables()

        global_inspector = inspect(global_engine)
        runtime_setting_columns = {column["name"] for column in global_inspector.get_columns("runtime_settings")}
        assert "summary_language" in runtime_setting_columns
        assert "run_background_jobs" in runtime_setting_columns
        assert "ai_auto_spam_enabled" in runtime_setting_columns
        assert "alembic_version" in global_inspector.get_table_names()

        mailbox_inspector = inspect(mailbox_engine)
        email_columns = {column["name"] for column in mailbox_inspector.get_columns("emails")}
        assert "mailbox_id" in email_columns
        assert "imap_uid" in email_columns
        assert "sent_review_summary" in email_columns
        assert "alembic_version" in mailbox_inspector.get_table_names()

        default_db_path = Path(isolated_paths["data_dir"]) / "account_dbs" / "default" / "mail_agent.db"
        assert default_db_path.exists()
    finally:
        global_engine.dispose()
        mailbox_engine.dispose()
