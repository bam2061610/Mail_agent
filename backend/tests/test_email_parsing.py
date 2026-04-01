from app.services.imap_scanner import extract_bodies, parse_email_message


def test_parse_email_message_extracts_headers_and_bodies():
    raw = (
        b"Message-ID: <id-1@example.com>\r\n"
        b"In-Reply-To: <root@example.com>\r\n"
        b"References: <root@example.com>\r\n"
        b"Subject: Test Subject\r\n"
        b"From: Sender Name <sender@example.com>\r\n"
        b"To: Receiver <receiver@example.com>\r\n"
        b"Date: Tue, 01 Apr 2026 10:00:00 +0000\r\n"
        b"MIME-Version: 1.0\r\n"
        b"Content-Type: multipart/alternative; boundary=abc\r\n\r\n"
        b"--abc\r\nContent-Type: text/plain; charset=utf-8\r\n\r\nPlain body\r\n"
        b"--abc\r\nContent-Type: text/html; charset=utf-8\r\n\r\n<html>HTML body</html>\r\n"
        b"--abc--\r\n"
    )
    parsed = parse_email_message(raw)
    assert parsed.message_id == "<id-1@example.com>"
    assert parsed.in_reply_to == "<root@example.com>"
    assert parsed.thread_id == "<root@example.com>"
    assert parsed.sender_email == "sender@example.com"
    assert parsed.body_text and "Plain body" in parsed.body_text
    assert parsed.body_html and "HTML body" in parsed.body_html


def test_message_id_fallback_generated_when_missing():
    raw = (
        b"Subject: Missing Message Id\r\n"
        b"From: test@example.com\r\n"
        b"To: r@example.com\r\n"
        b"Date: Tue, 01 Apr 2026 10:00:00 +0000\r\n\r\n"
        b"Body here"
    )
    parsed = parse_email_message(raw)
    assert parsed.message_id.startswith("<generated-")
    assert parsed.fallback_message_id_used is True


def test_extract_bodies_singlepart():
    from email import message_from_bytes

    msg = message_from_bytes(
        b"Content-Type: text/plain; charset=utf-8\r\n\r\nHello text",
    )
    body_text, body_html = extract_bodies(msg)
    assert body_text == "Hello text"
    assert body_html is None
