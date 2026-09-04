from __future__ import annotations

import stripe

from graphcode.config import settings
from graphcode.saas.billing import create_checkout_session, handle_webhook_event, parse_webhook_event


def test_checkout_stub_when_no_stripe_key(monkeypatch):
    monkeypatch.setattr(settings, "stripe_secret_key", "")
    result = create_checkout_session("pro", org_id=1)
    assert result["mode"] == "stub"
    assert result["checkout_url"] == "/app/usage?session=test_ok"


def test_checkout_defaults_free_plan_to_pro(monkeypatch):
    monkeypatch.setattr(settings, "stripe_secret_key", "")
    result = create_checkout_session("free", org_id=1)
    assert result["plan"] == "pro"


def test_checkout_calls_real_stripe_when_key_configured(monkeypatch):
    monkeypatch.setattr(settings, "stripe_secret_key", "sk_test_fake")
    monkeypatch.setattr(settings, "public_base_url", "http://localhost:8000")

    captured = {}

    class FakeSession:
        url = "https://checkout.stripe.com/test-session"
        id = "cs_test_123"

    def fake_create(**kwargs):
        captured.update(kwargs)
        return FakeSession()

    monkeypatch.setattr(stripe.checkout.Session, "create", staticmethod(fake_create))

    result = create_checkout_session("pro", org_id=42)
    assert result["mode"] == "test"
    assert result["checkout_url"] == "https://checkout.stripe.com/test-session"
    assert captured["client_reference_id"] == "42"
    assert captured["mode"] == "subscription"


def test_parse_webhook_event_requires_configured_secret(monkeypatch):
    monkeypatch.setattr(settings, "stripe_webhook_secret", "")
    try:
        parse_webhook_event(b"{}", "sig")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_parse_webhook_event_rejects_bad_signature(monkeypatch):
    monkeypatch.setattr(settings, "stripe_webhook_secret", "whsec_test")
    try:
        parse_webhook_event(b'{"type": "checkout.session.completed"}', "bad-sig")
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_handle_webhook_event_upgrades_org_on_checkout_completed():
    event = {
        "type": "checkout.session.completed",
        "data": {"object": {"client_reference_id": "7", "customer": "cus_abc"}},
    }
    calls = []
    result = handle_webhook_event(event, lambda org_id, cust, plan: calls.append((org_id, cust, plan)))
    assert result == {"received": True, "type": "checkout.session.completed"}
    assert calls == [(7, "cus_abc", "pro")]


def test_handle_webhook_event_ignores_other_event_types():
    event = {"type": "invoice.paid", "data": {"object": {}}}
    calls = []
    result = handle_webhook_event(event, lambda *a: calls.append(a))
    assert result == {"received": True, "type": "invoice.paid"}
    assert calls == []
