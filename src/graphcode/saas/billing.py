from __future__ import annotations

from graphcode.saas.usage import PLANS


def checkout_stub(plan: str) -> dict:
    """Stripe test-mode Checkout placeholder — no live charges."""
    if plan not in PLANS:
        plan = "pro"
    return {
        "mode": "test",
        "plan": plan,
        "price": PLANS[plan]["price"],
        "checkout_url": "/app/usage?session=test_ok",
        "message": "Stripe test mode: no live charges. Set STRIPE_SECRET_KEY to enable Checkout.",
    }


def handle_webhook(payload: dict) -> dict:
    typ = payload.get("type") or ""
    return {"received": True, "type": typ}
