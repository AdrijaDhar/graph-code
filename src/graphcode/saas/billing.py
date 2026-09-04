from __future__ import annotations

from typing import Callable

import stripe

from graphcode.config import settings
from graphcode.saas.usage import PLANS


def create_checkout_session(plan: str, org_id: int) -> dict:
    """Real Stripe test-mode Checkout when STRIPE_SECRET_KEY is set, else a $0 stub
    that mirrors the same response shape so the dashboard works either way."""
    if plan not in PLANS or plan == "free":
        plan = "pro"
    if not settings.stripe_secret_key:
        return {
            "mode": "stub",
            "plan": plan,
            "price": PLANS[plan]["price"],
            "checkout_url": "/app/usage?session=test_ok",
            "message": "Stripe test mode: no live charges. Set STRIPE_SECRET_KEY to enable real Checkout.",
        }
    stripe.api_key = settings.stripe_secret_key
    session = stripe.checkout.Session.create(
        mode="subscription",
        line_items=[
            {
                "price_data": {
                    "currency": "usd",
                    "product_data": {"name": f"Graph-Code {plan.title()} plan"},
                    "unit_amount": int(PLANS[plan]["price"] * 100),
                    "recurring": {"interval": "month"},
                },
                "quantity": 1,
            }
        ],
        client_reference_id=str(org_id),
        success_url=f"{settings.public_base_url}/app/usage?session=success",
        cancel_url=f"{settings.public_base_url}/app/usage?session=cancelled",
    )
    return {"mode": "test", "plan": plan, "checkout_url": session.url, "session_id": session.id}


def parse_webhook_event(payload: bytes, sig_header: str | None) -> dict:
    """Verify the Stripe webhook signature and return the parsed event.
    Raises ValueError if verification can't be performed or fails."""
    if not settings.stripe_webhook_secret:
        raise ValueError("STRIPE_WEBHOOK_SECRET not configured")
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, settings.stripe_webhook_secret)
    except (stripe.error.SignatureVerificationError, ValueError) as exc:
        raise ValueError(f"invalid webhook signature: {exc}") from exc
    return event


def handle_webhook_event(event: dict, on_checkout_completed: Callable[[int, str, str], None]) -> dict:
    """Dispatch a verified Stripe event. `on_checkout_completed(org_id, customer_id, plan)`
    is called to persist the upgrade — kept as a callback so this module has no DB dependency."""
    typ = event.get("type") or ""
    if typ == "checkout.session.completed":
        session = event["data"]["object"]
        org_id = session.get("client_reference_id")
        customer_id = session.get("customer") or ""
        if org_id:
            on_checkout_completed(int(org_id), customer_id, "pro")
    return {"received": True, "type": typ}
