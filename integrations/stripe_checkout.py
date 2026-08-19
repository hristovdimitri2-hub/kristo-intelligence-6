from __future__ import annotations

import os
from typing import Any, Dict, Optional


class StripeCheckoutService:
    """Stripe-compatible checkout abstraction.

    If the `stripe` package is available and a real key is configured, this class
    uses it to create a payment session. Otherwise it becomes a safe local mock to
    keep the sales flow operational without breaking the app.
    """

    def __init__(self):
        self.api_key = os.getenv("STRIPE_API_KEY", "").strip()
        self.webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()
        self.enabled = bool(self.api_key)
        self._stripe = None

        if self.enabled:
            try:
                import stripe as stripe_mod  # type: ignore
                self._stripe = stripe_mod
                stripe_mod.api_key = self.api_key
            except Exception:
                self.enabled = False

    def create_checkout_session(self, plan_key: str, customer_email: str, source: str = "website", campaign: str = "launch") -> Dict[str, Any]:
        if not self.enabled or self._stripe is None:
            return {
                "status": "mock_checkout_ready",
                "provider": "mock",
                "checkout_id": f"mock_{plan_key}_{customer_email.lower().replace('@', '_at_').replace('.', '_')}",
                "customer_email": customer_email,
                "plan": plan_key,
                "amount_usd": self._plan_amount(plan_key),
                "source": source,
                "campaign": campaign,
                "success_url": "/sales/checkout?status=success",
                "cancel_url": "/sales/checkout?status=cancelled",
            }

        try:
            session = self._stripe.checkout.Session.create(
                mode="payment",
                customer_email=customer_email,
                line_items=[{"price_data": {"currency": "usd", "product_data": {"name": f"Kristo Intelligence {plan_key}"}, "unit_amount": int(self._plan_amount(plan_key) * 100)}, "quantity": 1}],
                metadata={"plan": plan_key, "source": source, "campaign": campaign},
                success_url=os.getenv("APP_PUBLIC_URL", "http://localhost:5000") + "/sales/checkout?status=success&plan=" + plan_key,
                cancel_url=os.getenv("APP_PUBLIC_URL", "http://localhost:5000") + "/sales/checkout?status=cancelled&plan=" + plan_key,
            )
            return {
                "status": "checkout_created",
                "provider": "stripe",
                "checkout_id": session.id,
                "customer_email": customer_email,
                "plan": plan_key,
                "amount_usd": self._plan_amount(plan_key),
                "url": session.url,
            }
        except Exception:
            return {
                "status": "mock_checkout_ready",
                "provider": "mock_fallback",
                "checkout_id": f"fallback_{plan_key}_{customer_email.lower().replace('@', '_at_').replace('.', '_')}",
                "customer_email": customer_email,
                "plan": plan_key,
                "amount_usd": self._plan_amount(plan_key),
            }

    def verify_webhook(self, payload: bytes, signature: str) -> Optional[Dict[str, Any]]:
        """Verify and decode a Stripe webhook using the configured signing secret."""
        if not self.webhook_secret or self._stripe is None:
            return None
        event = self._stripe.Webhook.construct_event(
            payload, signature, self.webhook_secret
        )
        return event.to_dict_recursive() if hasattr(event, "to_dict_recursive") else dict(event)

    def _plan_amount(self, plan_key: str) -> float:
        pricing = {
            "starter": 29.0,
            "pro": 79.0,
            "api": 149.0,
        }
        return pricing.get(plan_key, 79.0)
