from email.message import EmailMessage

from app.models.email import Email
from app.services.attachment_service import extract_attachments, save_attachments


def test_attachment_extraction_and_save(db_session):
    msg = EmailMessage()
    msg["Subject"] = "Attachment test"
    msg.set_content("Body")
    msg.add_attachment(
        b"invoice-bytes",
        maintype="application",
        subtype="pdf",
        filename="invoice.pdf",
    )
    parsed = extract_attachments(msg)
    assert len(parsed) == 1
    assert parsed[0].filename == "invoice.pdf"

    email = Email(
        message_id="<att-1@test>",
        subject="Attachment email",
        sender_email="a@example.com",
        folder="inbox",
        direction="inbound",
        status="new",
    )
    db_session.add(email)
    db_session.flush()
    saved = save_attachments(db_session, email.id, "mb-test", parsed)
    db_session.commit()
    assert len(saved) == 1
    assert saved[0].filename == "invoice.pdf"
