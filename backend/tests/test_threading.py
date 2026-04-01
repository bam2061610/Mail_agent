from app.services.imap_scanner import ParsedEmailMessage, resolve_thread_id


def _parsed(**kwargs):
    defaults = {
        "message_id": "<msg@example.com>",
        "source_message_id": "<msg@example.com>",
        "in_reply_to": None,
        "references": [],
        "thread_id": "",
        "subject": "s",
        "sender_email": "a@example.com",
        "sender_name": "A",
        "recipients": [],
        "cc": [],
        "date_received": None,
        "body_text": "text",
        "body_html": None,
        "attachments": [],
        "folder": "INBOX",
        "direction": "inbound",
        "fallback_message_id_used": False,
    }
    defaults.update(kwargs)
    return ParsedEmailMessage(**defaults)


def test_thread_resolution_prefers_in_reply_to():
    msg = _parsed(in_reply_to="<parent@example.com>", references=["<ref1@example.com>"])
    assert resolve_thread_id(msg) == "<parent@example.com>"


def test_thread_resolution_falls_back_to_references_then_message_id():
    msg = _parsed(in_reply_to=None, references=["<ref1@example.com>"], message_id="<self@example.com>")
    assert resolve_thread_id(msg) == "<ref1@example.com>"

    msg2 = _parsed(in_reply_to=None, references=[], message_id="<self@example.com>")
    assert resolve_thread_id(msg2) == "<self@example.com>"
