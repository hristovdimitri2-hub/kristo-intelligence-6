from __future__ import annotations

import os
from typing import Any, Dict, Optional


class StripeCheckoutService:
    """Create Stripe Checkout sessions and verify signed webhook events."""

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

    def create_checkout_session(
        self,
        plan_key: str,
        customer_email: str,
        source: str = "website",
        campaign: str = "launch",
        telegram_chat_id: str = "",
        product_name: str = "",
        amount_usd: Optional[float] = None,
        agent_sku: str = "",
    ) -> Dict[str, Any]:
        resolved_amount = float(
            self._plan_amount(plan_key) if amount_usd is None else amount_usd
        )
        resolved_product_name = product_name or f"Kristo Intelligence {plan_key}"
        if not self.enabled or self._stripe is None:
            if not self._mock_payments_allowed():
                return {
                    "status": "checkout_error",
                    "provider": "stripe",
                    "error": "stripe_not_configured",
                }
            return {
                "status": "mock_checkout_ready",
                "provider": "mock",
                "checkout_id": f"mock_{plan_key}_{customer_email.lower().replace('@', '_at_').replace('.', '_')}",
                "customer_email": customer_email,
                "plan": plan_key,
                "amount_usd": resolved_amount,
                "source": source,
                "campaign": campaign,
                "agent_sku": agent_sku,
                "success_url": "/sales/checkout?status=success",
                "cancel_url": "/sales/checkout?status=cancelled",
            }

        public_url = os.getenv("APP_PUBLIC_URL", "").strip().rstrip("/")
        if not public_url:
            return {
                "status": "checkout_error",
                "provider": "stripe",
                "error": "app_public_url_not_configured",
            }

        metadata = {
            "app": "kristo-intelligence",
            "plan": plan_key,
            "source": source,
            "campaign": campaign,
        }
        if telegram_chat_id:
            metadata["telegram_chat_id"] = telegram_chat_id
        if agent_sku:
            metadata["agent_sku"] = agent_sku

        try:
            session = self._stripe.checkout.Session.create(
                mode="payment",
                customer_email=customer_email,
                line_items=[{"price_data": {"currency": "usd", "product_data": {"name": resolved_product_name}, "unit_amount": int(resolved_amount * 100)}, "quantity": 1}],
                metadata=metadata,
                success_url=f"{public_url}/sales/checkout?status=success&plan={plan_key}&session_id={{CHECKOUT_SESSION_ID}}",
                cancel_url=f"{public_url}/sales/checkout?status=cancelled&plan={plan_key}",
            )
            return {
                "status": "checkout_created",
                "provider": "stripe",
                "checkout_id": session.id,
                "customer_email": customer_email,
                "plan": plan_key,
                "amount_usd": resolved_amount,
                "agent_sku": agent_sku,
                "url": session.url,
            }
        except Exception:
            return {
                "status": "checkout_error",
                "provider": "stripe",
                "error": "stripe_checkout_creation_failed",
            }

    def create_catalog_checkout_session(
        self,
        agent_sku: str,
        product_name: str,
        amount_usd: float,
        customer_email: str,
        source: str = "catalog",
        campaign: str = "agent_catalog",
        telegram_chat_id: str = "",
    ) -> Dict[str, Any]:
        """Create a one-time Stripe Checkout for a 30-day agent entitlement."""
        return self.create_checkout_session(
            plan_key=f"agent:{agent_sku}",
            customer_email=customer_email,
            source=source,
            campaign=campaign,
            telegram_chat_id=telegram_chat_id,
            product_name=f"{product_name} — 30-day agent access",
            amount_usd=amount_usd,
            agent_sku=agent_sku,
        )

    def verify_webhook(self, payload: bytes, signature: str) -> Optional[Dict[str, Any]]:
        """Verify and decode a Stripe webhook using the configured signing secret."""
        if not self.webhook_secret or self._stripe is None:
            return None
        event = self._stripe.Webhook.construct_event(payload, signature, self.webhook_secret)
        if hasattr(event, "to_dict_recursive"):
            return event.to_dict_recursive()
        if hasattr(event, "to_dict"):
            return event.to_dict()
        return dict(event)

    def list_recent_completed_payments(self, limit: int = 25) -> Dict[str, Any]:
        """Return recent completed Checkout payments for the protected admin view."""
        if not self.enabled or self._stripe is None:
            return {"available": False, "payments": [], "reason": "stripe_not_configured"}

        try:
            payments = []
            requested_limit = max(1, min(limit, 100))
            starting_after = None

            while len(payments) < requested_limit:
                params = {"limit": 100}
                if starting_after:
                    params["starting_after"] = starting_after
                sessions = self._stripe.checkout.Session.list(**params)
                batch = list(getattr(sessions, "data", []) or [])
                if not batch:
                    break

                for session in batch:
                    if getattr(session, "payment_status", "") != "paid":
                        continue
                    metadata = getattr(session, "metadata", {}) or {}
                    customer_details = getattr(session, "customer_details", None)
                    payments.append(
                        {
                            "checkout_id": getattr(session, "id", ""),
                            "email": getattr(customer_details, "email", None)
                            or getattr(session, "customer_email", ""),
                            "amount_usd": float(getattr(session, "amount_total", 0) or 0) / 100,
                            "currency": (getattr(session, "currency", "usd") or "usd").upper(),
                            "plan": metadata.get("plan", ""),
                            "created": getattr(session, "created", None),
                            "provider": "stripe",
                            "payment_status": "paid",
                        }
                    )
                    if len(payments) >= requested_limit:
                        break

                if not getattr(sessions, "has_more", False):
                    break
                starting_after = getattr(batch[-1], "id", None)
                if not starting_after:
                    break
            return {"available": True, "payments": payments}
        except Exception:
            return {"available": False, "payments": [], "reason": "stripe_list_unavailable"}

    @staticmethod
    def _mock_payments_allowed() -> bool:
        return os.getenv("KRISTO_ALLOW_MOCK_PAYMENTS", "").strip().lower() in {"1", "true", "yes"}

    def _plan_amount(self, plan_key: str) -> float:
        pricing = {
            "starter": 29.0,
            "pro": 79.0,
            "api": 149.0,
        }
        return pricing.get(plan_key, 79.0)
