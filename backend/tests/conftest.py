from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app import config as app_config
from app.db import Base, create_tables, get_db
from app.models.email import Email
from app.services import (
    attachment_service,
    digest_service,
    diagnostics_service,
    mailbox_service,
    preference_profile,
    rule_engine,
    template_service,
)
from app.services.user_service import create_user


@pytest.fixture()
def isolated_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    data_dir = tmp_path / "data"
    backups_dir = data_dir / "backups"
    attachments_dir = data_dir / "attachments"
    data_dir.mkdir(parents=True, exist_ok=True)
    backups_dir.mkdir(parents=True, exist_ok=True)
    attachments_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(app_config, "SETTINGS_FILE_PATH", data_dir / "settings.local.json")
    monkeypatch.setattr(rule_engine, "RULES_FILE_PATH", data_dir / "rules.json")
    monkeypatch.setattr(template_service, "TEMPLATES_FILE_PATH", data_dir / "templates.json")
    monkeypatch.setattr(mailbox_service, "MAILBOXES_FILE_PATH", data_dir / "mailboxes.json")
    monkeypatch.setattr(preference_profile, "PREFERENCE_PROFILE_PATH", data_dir / "preference_profile.json")
    monkeypatch.setattr(digest_service, "STATE_FILE_PATH", data_dir / "digest_state.json")
    monkeypatch.setattr(attachment_service, "ATTACHMENTS_ROOT", attachments_dir)

    monkeypatch.setattr(diagnostics_service, "BACKEND_DIR", tmp_path)
    monkeypatch.setattr(diagnostics_service, "DATA_DIR", data_dir)
    monkeypatch.setattr(diagnostics_service, "ATTACHMENTS_DIR", attachments_dir)
    monkeypatch.setattr(diagnostics_service, "BACKUPS_DIR", backups_dir)
    monkeypatch.setattr(diagnostics_service, "OPS_STATUS_FILE_PATH", data_dir / "ops_status.json")

    return {
        "root": tmp_path,
        "data_dir": data_dir,
        "backups_dir": backups_dir,
        "attachments_dir": attachments_dir,
    }


@pytest.fixture()
def db_session(isolated_paths: dict[str, Path], monkeypatch: pytest.MonkeyPatch) -> Generator[Session, None, None]:
    db_file = isolated_paths["data_dir"] / "test.sqlite3"
    database_url = f"sqlite:///{db_file.as_posix()}"
    app_config.settings.database_url = database_url

    test_engine = create_engine(database_url, connect_args={"check_same_thread": False})
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

    import app.db as app_db

    monkeypatch.setattr(app_db, "engine", test_engine)
    monkeypatch.setattr(app_db, "SessionLocal", TestSessionLocal)

    Base.metadata.drop_all(bind=test_engine)
    Base.metadata.create_all(bind=test_engine)
    create_tables()

    session = TestSessionLocal()
    try:
        yield session
    finally:
        session.close()
        test_engine.dispose()


@pytest.fixture()
def client(db_session: Session, monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    import app.main as main_module

    monkeypatch.setattr(main_module, "start_scheduler", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(main_module, "stop_scheduler", lambda *_args, **_kwargs: None)

    def _override_get_db() -> Generator[Session, None, None]:
        yield db_session

    main_module.app.dependency_overrides[get_db] = _override_get_db
    try:
        with TestClient(main_module.app) as test_client:
            yield test_client
    finally:
        main_module.app.dependency_overrides.clear()


@pytest.fixture()
def admin_user(db_session: Session):
    return create_user(
        db_session=db_session,
        email="admin@example.com",
        full_name="Admin User",
        password="admin123",
        role="admin",
    )


@pytest.fixture()
def operator_user(db_session: Session):
    return create_user(
        db_session=db_session,
        email="operator@example.com",
        full_name="Operator User",
        password="operator123",
        role="operator",
    )


@pytest.fixture()
def admin_auth_headers(client: TestClient, admin_user) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"email": admin_user.email, "password": "admin123"})
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def operator_auth_headers(client: TestClient, operator_user) -> dict[str, str]:
    response = client.post("/api/auth/login", json={"email": operator_user.email, "password": "operator123"})
    assert response.status_code == 200
    token = response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture()
def sample_email(db_session: Session) -> Email:
    item = Email(
        message_id="<sample-1@test>",
        thread_id="<sample-1@test>",
        subject="Supplier quotation request",
        sender_email="sales@supplier.com",
        sender_name="Supplier Sales",
        recipients_json='[{"email":"procurement@orhun.local","name":"Procurement"}]',
        cc_json="[]",
        body_text="Hello, please find quotation details attached.",
        folder="inbox",
        direction="inbound",
        status="new",
        priority="high",
        category="RFQ",
        requires_reply=True,
        ai_analyzed=False,
        mailbox_id="mb-default",
        mailbox_name="Default",
        mailbox_address="procurement@orhun.local",
    )
    db_session.add(item)
    db_session.commit()
    db_session.refresh(item)
    return item
