from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, Optional

log = logging.getLogger(__name__)

#: Env names that may hold the SECRET key, in priority order.
#: `STRIPE_API_KEY` is what this service has always read; `STRIPE_SECRET_KEY` is
#: Stripe's own name for the same thing and is what people naturally type. On
#: 14.09 the owner set a value under the second name — and nothing happened, with
#: no error anywhere, because the code only ever looked at the first. Reading
#: both removes that silent-failure trap for good.
_KEY_ENV_NAMES = ("STRIPE_API_KEY", "STRIPE_SECRET_KEY")

#: A real secret key starts with one of these. A value like `mk_1U5Q…` is the ID
#: of a key, NOT the key itself: Stripe answers 401 "This looks like the ID of an
#: API key rather than the key itself" and every checkout dies with 503. Catching
#: it at BOOT turns a silent payment failure into a visible warning.
_KEY_PREFIXES = ("sk_", "rk_")

_KEY_RE = re.compile(r"(sk_(?:live|test)_|rk_(?:live|test)_|whsec_)[A-Za-z0-9_\-]{4,}")


def redact(text: Any) -> str:
    """Strip any key-shaped token before it can reach a log line."""
    return _KEY_RE.sub(lambda m: m.group(1) + "***", str(text))


class StripeCheckoutService:
    """Create Stripe Checkout sessions and verify signed webhook events."""

    def __init__(self):
        self.api_key = ""
        self.key_source = ""            # WHICH env name supplied the key
        for _name in _KEY_ENV_NAMES:
            _value = os.getenv(_name, "").strip()
            if _value:
                self.api_key, self.key_source = _value, _name
                break
        self.webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET", "").strip()
        # True when there is no key at all (that is "not configured", a different
        # problem) or when the key at least LOOKS like a secret key.
        self.key_format_ok = (not self.api_key
                              or self.api_key.startswith(_KEY_PREFIXES))
        # Live/test ONLY — never a character of the key itself, so these logs can
        # be pasted anywhere without leaking a credential.
        self.key_mode = ("live" if "_live_" in self.api_key[:10]
                         else "test" if "_test_" in self.api_key[:10]
                         else "unknown")
        self.enabled = bool(self.api_key)
        self._stripe = None

        if not self.api_key:
            log.info("Stripe: none of %s is set → checkout is disabled.",
                     "/".join(_KEY_ENV_NAMES))
        elif not self.key_format_ok:
            # Name the SHAPE, never the value: the point is that the owner
            # recognises "I pasted the key's ID".
            shape = ("a key ID (mk_…)" if self.api_key.startswith("mk_")
                     else "an unrecognised prefix")
            log.warning(
                "Stripe: %s holds %s, not a secret key (%d chars). Secret keys "
                "start with sk_ / rk_ — every checkout will fail until the real "
                "value is pasted into that variable.",
                self.key_source, shape, len(self.api_key))
        else:
            log.info("Stripe: secret key loaded from %s (mode=%s, %d chars).",
                     self.key_source, self.key_mode, len(self.api_key))

        if self.enabled:
            try:
                import stripe as stripe_mod  # type: ignore
                self._stripe = stripe_mod
                stripe_mod.api_key = self.api_key
            except Exception as exc:
                log.warning("Stripe: the library is unavailable (%s) — checkout "
                            "disabled.", exc)
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
                # Explicit card payment type: live-mode accounts reject
                # sessions without it when no dashboard payment methods are
                # activated ("No valid payment method types ...").
                payment_method_types=["card"],
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
        except Exception as exc:
            # The provider's own message is the ONLY thing that explains a failed
            # checkout. Swallowing it (until 14.09 this bare `except` returned a
            # generic "stripe_checkout_creation_failed" and logged nothing) left
            # the owner staring at a 503 with no reason anywhere — the diagnosis
            # had to be reconstructed from the Stripe API by hand.
            log.warning(
                "Stripe checkout session creation FAILED for plan=%s: %s: %s "
                "(code=%s, param=%s)",
                plan_key, type(exc).__name__, redact(exc),
                redact(getattr(exc, "code", "") or ""),
                redact(getattr(exc, "param", "") or ""))
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
        except Exception as exc:
            # Same lesson as the checkout path: "unavailable" with no reason made
            # a broken key/feed invisible. Say what the provider said.
            log.warning("Stripe payment snapshot refresh failed: %s: %s",
                        type(exc).__name__, redact(exc))
            return {"available": False, "payments": [],
                    "reason": "stripe_list_unavailable"}

    @staticmethod
    def _mock_payments_allowed() -> bool:
        return os.getenv("KRISTO_ALLOW_MOCK_PAYMENTS", "").strip().lower() in {"1", "true", "yes"}

    def _plan_amount(self, plan_key: str) -> float:
        """Amount for a plan, read from the SINGLE price source (audit A5).

        These literals used to be duplicated here AND in
        `payment_integration.SalesCheckout` — the same drift class that let the
        dashboard advertise /api/sales at $0.05 while the 402 demanded $0.005.
        """
        from integrations.payment_integration import PLAN_PRICES
        return float(PLAN_PRICES.get(plan_key, PLAN_PRICES["pro"]))
