from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.db import SessionLocal, create_tables
from app.models.contact import Contact
from app.models.email import Email
from app.models.task import Task
from app.services.user_service import create_user, get_user_by_email


def seed_demo_data() -> dict[str, int]:
    create_tables()
    db = SessionLocal()
    try:
        _ensure_demo_users(db)
        _clear_demo_records(db)

        now = datetime.now(timezone.utc)
        emails = [
            Email(
                message_id="<demo-supplier@test>",
                thread_id="<demo-supplier@test>",
                subject="RFQ for diagnostic equipment",
                sender_email="sales@medcon.com.tr",
                sender_name="Medcon Sales",
                recipients_json='[{"email":"ops@orhun.local","name":"Ops"}]',
                cc_json="[]",
                body_text="Please share your expected delivery timeline and pricing window.",
                folder="inbox",
                direction="inbound",
                status="new",
                priority="high",
                category="RFQ",
                requires_reply=True,
                ai_analyzed=True,
                ai_summary="Supplier asks for pricing timeline and delivery terms.",
                date_received=now - timedelta(hours=2),
            ),
            Email(
                message_id="<demo-finance@test>",
                thread_id="<demo-finance@test>",
                subject="Invoice clarification",
                sender_email="finance@partner.kz",
                sender_name="Finance Partner",
                recipients_json='[{"email":"ops@orhun.local","name":"Ops"}]',
                cc_json="[]",
                body_text="Please confirm payment date for invoice 1123.",
                folder="inbox",
                direction="inbound",
                status="read",
                priority="medium",
                category="Invoice",
                requires_reply=True,
                ai_analyzed=True,
                ai_summary="Finance asks for payment date confirmation.",
                date_received=now - timedelta(hours=5),
            ),
            Email(
                message_id="<demo-spam@test>",
                thread_id="<demo-spam@test>",
                subject="Weekly marketing digest",
                sender_email="news@newsletter.example",
                sender_name="Newsletter",
                recipients_json='[{"email":"ops@orhun.local","name":"Ops"}]',
                cc_json="[]",
                body_text="Promotional content.",
                folder="spam",
                direction="inbound",
                status="spam",
                priority="spam",
                category="Spam",
                is_spam=True,
                spam_source="ai",
                spam_reason="Marketing/newsletter pattern",
                requires_reply=False,
                ai_analyzed=True,
                date_received=now - timedelta(days=1),
            ),
        ]
        db.add_all(emails)
        db.flush()

        tasks = [
            Task(
                email_id=emails[0].id,
                thread_id=emails[0].thread_id,
                task_type="followup",
                title="Follow up supplier",
                state="waiting_reply",
                followup_started_at=now - timedelta(days=2),
            ),
        ]
        db.add_all(tasks)
        db.add(
            Contact(
                email="sales@medcon.com.tr",
                name="Medcon Sales",
                company="Medcon",
                preferred_language="en",
                emails_received_count=5,
                emails_sent_count=3,
                last_contact_at=now - timedelta(hours=2),
            )
        )
        db.commit()
        return {"emails": len(emails), "tasks": len(tasks), "contacts": 1}
    finally:
        db.close()


def reset_demo_data() -> dict[str, int]:
    create_tables()
    db = SessionLocal()
    try:
        deleted_tasks = db.query(Task).delete()
        deleted_emails = db.query(Email).delete()
        deleted_contacts = db.query(Contact).delete()
        db.commit()
        return {"emails_deleted": deleted_emails, "tasks_deleted": deleted_tasks, "contacts_deleted": deleted_contacts}
    finally:
        db.close()


def _ensure_demo_users(db) -> None:
    if get_user_by_email(db, "admin@orhun.local") is None:
        create_user(db, "admin@orhun.local", "Default Admin", "admin123", role="admin")
    if get_user_by_email(db, "operator@orhun.local") is None:
        create_user(db, "operator@orhun.local", "Demo Operator", "operator123", role="operator")


def _clear_demo_records(db) -> None:
    db.query(Task).filter(Task.thread_id.in_(["<demo-supplier@test>", "<demo-finance@test>", "<demo-spam@test>"])).delete(synchronize_session=False)
    db.query(Email).filter(Email.message_id.in_(["<demo-supplier@test>", "<demo-finance@test>", "<demo-spam@test>"])).delete(synchronize_session=False)
    db.query(Contact).filter(Contact.email == "sales@medcon.com.tr").delete(synchronize_session=False)
    db.commit()


if __name__ == "__main__":
    result = seed_demo_data()
    print(f"Seeded demo data: {result}")
