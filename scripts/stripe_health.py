"""Is Stripe actually able to take money? One command, real API data.

Written after the 14.09 test-payment incident: the checkout page showed
"Se produjo un error de procesamiento" and the answer was NOT in our code — the
Stripe account itself could not charge (`charges_enabled: false`,
`details_submitted: false`, every capability `inactive`). Nothing on our side
could have revealed that, and the Stripe Dashboard's session view does not shout
about it either, so this tool asks the API the questions that matter:

  1. Is the key valid, and is it live or test?
  2. CAN THE ACCOUNT CHARGE at all? (charges_enabled / capabilities / KYC state)
  3. Are our webhook endpoints registered, enabled and subscribed?
  4. What do the most recent sessions look like — did a PaymentIntent ever exist?

Secrets are never printed: only type, length and a masked tail.
Credential comes from the service's Render env (`STRIPE_API_KEY`, falling back to
`STRIPE_SECRET_KEY`), or from a `--key sk_live_...` argument.

Usage:
    python -X utf8 scripts/stripe_health.py
    python -X utf8 scripts/stripe_health.py --key sk_live_xxx
Exit code 0 only when the account can actually charge.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVICE = "srv-d9maroe7bikc73adkaug"


def _ts(sec) -> str:
    return datetime.fromtimestamp(sec or 0, tz=timezone.utc).strftime(
        "%Y-%m-%d %H:%M UTC")


def mask(v: str) -> str:
    v = (v or "").strip()
    if not v:
        return "EMPTY/UNSET"
    if v.startswith("whsec_"):
        return "whsec_ set (len %d, hex tail %s)" % (len(v), v[-4:])
    if v.startswith(("sk_live_", "sk_test_", "rk_live_", "rk_test_")):
        return "%s... set (len %d, tail %s)" % (v[:8], len(v), v[-4:])
    return "%s... set (len %d)" % (v[:6], len(v))


def render_env() -> dict:
    """Env vars of the Render service (paginated). Values are used, not shown."""
    path = os.path.join(ROOT, "secrets", "render_api_key.txt")
    if not os.path.exists(path):
        return {}
    key = open(path, encoding="utf-8").read().strip()
    headers = {"Authorization": "Bearer " + key, "Accept": "application/json"}
    out, cursor = {}, None
    for _ in range(10):
        params = {"limit": 100}
        if cursor:
            params["cursor"] = cursor
        r = requests.get("https://api.render.com/v1/services/%s/env-vars"
                         % SERVICE, headers=headers, timeout=90, params=params)
        if r.status_code != 200:
            break
        page = r.json()
        for item in page:
            ev = item.get("envVar", item)
            out[ev.get("key")] = ev.get("value")
        cursor = page[-1].get("cursor") if page else None
        if not cursor or len(page) < 100:
            break
    return out


def stripe_get(key: str, path: str, **params):
    flat = []
    for k, v in params.items():
        if isinstance(v, (list, tuple)):
            for item in v:
                flat.append((k if k.endswith("[]") else k + "[]", item))
        else:
            flat.append((k, v))
    r = requests.get("https://api.stripe.com/v1/" + path,
                     headers={"Authorization": "Bearer " + key},
                     params=flat, timeout=90)
    if r.status_code != 200:
        return {"_error": r.status_code, "_body": r.text[:400]}
    return r.json()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", default="")
    args = ap.parse_args()

    env = render_env()
    key = (args.key or env.get("STRIPE_API_KEY")
           or env.get("STRIPE_SECRET_KEY") or "").strip()
    whsec = (env.get("STRIPE_WEBHOOK_SECRET") or "").strip()

    print("=== credentials ===")
    print("    STRIPE_API_KEY        :", mask(env.get("STRIPE_API_KEY")
                                             or args.key))
    print("    STRIPE_WEBHOOK_SECRET :", mask(whsec)
          if env else "    (no Render access — pass --key)")
    if not key:
        print("!! no Stripe key available")
        return 2

    acct = stripe_get(key, "account")
    if "_error" in acct:
        print("!! key REJECTED by Stripe:", acct["_error"], acct["_body"])
        return 2
    mode = "LIVE" if key.startswith("sk_live") else "TEST"
    print("    key accepted          : account=%s mode=%s"
          % (acct.get("id"), mode))

    print("\n=== CAN THE ACCOUNT CHARGE? (the 14.09 blocker) ===")
    caps = acct.get("capabilities") or {}
    print("    charges_enabled       :", acct.get("charges_enabled"))
    print("    payouts_enabled       :", acct.get("payouts_enabled"))
    print("    details_submitted     :", acct.get("details_submitted"))
    print("    country / currency    :", acct.get("country"), "/",
          acct.get("default_currency"))
    print("    capabilities          :", json.dumps(caps))
    req = acct.get("requirements") or {}
    print("    disabled_reason       :", req.get("disabled_reason"))
    print("    currently_due         :", (req.get("currently_due") or [])[:8])
    can_charge = bool(acct.get("charges_enabled")
                      and caps.get("card_payments") == "active")

    print("\n=== webhook endpoints ===")
    wh = stripe_get(key, "webhook_endpoints", limit=10)
    if "_error" in wh:
        print("    list failed:", wh["_error"], wh["_body"])
    else:
        eps = wh.get("data", [])
        print("    registered:", len(eps))
        for e in eps:
            print("    - %s" % e.get("url"))
            print("        status=%s livemode=%s events=%s"
                  % (e.get("status"), e.get("livemode"),
                     ", ".join(e.get("enabled_events") or [])))
        if not eps:
            # Silence here is the expensive failure: Stripe charges the buyer and
            # our CRM/access automation never hears about it. Say it LOUDLY.
            print("    !! NO webhook endpoint is registered in THIS account — a")
            print("       real payment would be CHARGED and our side would never")
            print("       learn about it. Add this URL in the Dashboard")
            print("       (Developers → Webhooks), then paste its Signing secret")
            print("       into STRIPE_WEBHOOK_SECRET:")
            print("       https://kristo-intelligence-api.onrender.com"
                  "/api/webhooks/stripe")
            print("       events: checkout.session.completed (+ expired,")
            print("               async_payment_succeeded, payment_intent.payment_failed)")
            print("       The secret MUST come from the endpoint of the SAME")
            print("       account as the key — the secret does not travel with it.")

    print("\n=== the last 8 checkout sessions ===")
    sessions = stripe_get(key, "checkout/sessions", limit=8,
                          expand=["data.payment_intent"])
    for s in sessions.get("data", []):
        pi = s.get("payment_intent")
        pi_txt = (pi.get("id") + " status=" + str(pi.get("status"))
                  if isinstance(pi, dict) else str(pi))
        print("    %-20s %-9s %-7s %-9s pi=%s"
              % (_ts(s.get("created")), s.get("status"),
                 (s.get("amount_total") or 0) / 100.0, s.get("payment_status"),
                 pi_txt))
    if not sessions.get("data"):
        print("    (none)")

    print("\n=== verdict ===")
    if can_charge:
        print("    Stripe CAN charge. If a payment still fails, the cause is on")
        print("    the payment-method/bank side — read last_payment_error and")
        print("    charge.outcome for the session above.")
        return 0
    print("    Stripe CANNOT charge yet — nothing on our side can fix this.")
    print("    The hosted page refuses BEFORE creating a PaymentIntent, which")
    print("    is why the customer sees \"processing error\" and why the")
    print("    account has zero charges/PaymentIntents (never a bank decline).")
    print("    ACTION: finish Stripe onboarding (activate the account).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())