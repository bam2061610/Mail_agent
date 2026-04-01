from app.models.email import Email
from app.services.rule_engine import apply_rules_to_email, create_rule, list_rules


def test_rule_engine_applies_priority_and_focus(db_session):
    create_rule(
        {
            "name": "Supplier high priority",
            "conditions": {"sender_domain": "supplier.com"},
            "actions": {"set_priority": "high", "move_to_focus": True},
        }
    )
    email = Email(
        message_id="<rule-1@test>",
        subject="RFQ request",
        sender_email="sales@supplier.com",
        folder="inbox",
        direction="inbound",
        status="new",
    )
    db_session.add(email)
    db_session.flush()

    result = apply_rules_to_email(db_session, email, source="test")
    assert result.matched_rules
    assert "set_priority" in result.applied_actions
    assert email.priority == "high"
    assert email.focus_flag is True


def test_rule_engine_mark_spam_then_never_spam_protects(db_session):
    create_rule(
        {
            "name": "Newsletters to spam",
            "order": 1,
            "conditions": {"sender_email": "promo@ads.com"},
            "actions": {"mark_spam": True},
        }
    )
    create_rule(
        {
            "name": "Trusted ads domain",
            "order": 2,
            "conditions": {"sender_domain": "ads.com"},
            "actions": {"never_spam": True},
        }
    )
    assert len(list_rules()) >= 2

    email = Email(
        message_id="<rule-2@test>",
        subject="Promo",
        sender_email="promo@ads.com",
        folder="inbox",
        direction="inbound",
        status="new",
    )
    db_session.add(email)
    db_session.flush()
    apply_rules_to_email(db_session, email, source="test")
    assert email.is_spam is False
