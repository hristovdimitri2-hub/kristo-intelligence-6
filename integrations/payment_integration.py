from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class Plan:
    name: str
    price_usd: float
    description: str
    access_level: str


class SalesCheckout:
    """Checkout abstraction for launch-ready sales flow.

    This implementation gives a real, runtime-safe contract for payment status
    and can be connected to Stripe, Checkout Sessions, or wallet-based payment
    verification without altering the core app.
    """

    def __init__(self):
        self.plans = {
            "starter": Plan(
                name="Starter",
                price_usd=29.0,
                description="Basic market bulletin and signal access",
                access_level="basic",
            ),
            "pro": Plan(
                name="Pro",
                price_usd=79.0,
                description="VIP Telegram access + premium analysis",
                access_level="vip",
            ),
            "api": Plan(
                name="API Access",
                price_usd=149.0,
                description="Market intelligence API access",
                access_level="api",
            ),
        }
        self.checkout_sessions: Dict[str, Dict[str, object]] = {}

    def get_plan(self, key: str) -> Optional[Plan]:
        return self.plans.get(key)

    def get_all_plans(self) -> Dict[str, Plan]:
        return self.plans

    def build_checkout_payload(self, plan_key: str, customer_email: str) -> Dict[str, object]:
        plan = self.get_plan(plan_key)
        if plan is None:
            raise ValueError(f"Unknown plan: {plan_key}")

        checkout_id = f"chk_{plan_key}_{customer_email.lower().replace('@', '_at_').replace('.', '_')}_{abs(hash(plan_key + customer_email))}"
        payload = {
            "checkout_id": checkout_id,
            "customer_email": customer_email,
            "plan": plan.name,
            "plan_key": plan_key,
            "price_usd": plan.price_usd,
            "description": plan.description,
            "access_level": plan.access_level,
            "status": "pending_checkout",
            "provider": "stripe_or_wallet",
            "checkout_url": f"/sales/checkout?plan={plan_key}",
        }
        self.checkout_sessions[checkout_id] = payload
        return payload

    def mark_paid(self, checkout_id: str, payment_provider: str, tx_hash: Optional[str] = None) -> Dict[str, object]:
        session = self.checkout_sessions.get(checkout_id)
        if session is None:
            raise ValueError(f"Unknown checkout session: {checkout_id}")

        session["status"] = "paid"
        session["payment_provider"] = payment_provider
        session["tx_hash"] = tx_hash
        session["paid_at"] = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
        return dict(session)

    def get_session(self, checkout_id: str) -> Optional[Dict[str, object]]:
        return self.checkout_sessions.get(checkout_id)

    def create_payment_intent(self, plan_key: str, customer_email: str) -> Dict[str, object]:
        payload = self.build_checkout_payload(plan_key, customer_email)
        payload["status"] = "ready_for_payment"
        return payload
