"""Can we take a REAL payment end to end? Three questions, real API data.

`stripe_health.py` answers "is the account able to charge?". This one answers the
next question, the one the owner actually asks before a test payment: **does the
money path work from click to webhook?**

  1. ACCOUNT   — the key's account, can it charge, how many webhook endpoints it has
  2. CHECKOUT  — POST /sales/checkout and verify the session AT STRIPE
                 (a 303 is not proof: the amount, currency and livemode are)
  3. WEBHOOK   — create + expire a session and look for the REAL delivery in our
                 logs (a self-signed dry-run proves nothing about Stripe's secret)

Written after 16.09, when every one of those three was broken at once and each
failure hid the next one: the account could finally charge, but the new account's
MANAGED PAYMENTS refused `payment_method_types` and then demanded a product tax
code, and the account had no webhook endpoint at all — so a real payment would
have been charged and our CRM would never have heard about it.

Sessions created here are expired immediately, so the owner's Stripe view stays
clean. Secrets are never printed (type, length, masked tail only).

Usage:
    python -X utf8 scripts/stripe_readiness.py
    python -X utf8 scripts/stripe_readiness.py --key sk_live_xxx
Exit code 0 only when all three answers are green.
"""
from __future__ import annotations

import argparse
import os
import time

import requests

from stripe_health import mask, render_env  # noqa: F401  (same directory)

SERVICE = "srv-d9maroe7bikc73adkaug"
OWNER = "tea-d9m96f9qjqt8s73erj60"
BASE = "https://kristo-intelligence-api.onrender.com"
CHECKOUT_URL = BASE + "/sales/checkout"


def _auth(key: str) -> dict:
    return {"Authorization": "Bearer " + key}


def stripe_get(key: str, path: str, **params):
    for _ in range(6):
        try:
            return requests.get("https://api.stripe.com/v1/" + path,
                                headers=_auth(key), params=params or None,
                                timeout=60).json()
        except Exception:
            time.sleep(5)
    return {}


def render_logs(limit: int = 300):
    """Our own service log (the only place a real Stripe delivery shows up)."""
    path = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "secrets", "render_api_key.txt")
    if not os.path.exists(path):
        return []
    key = open(path, encoding="utf-8").read().strip()
    for _ in range(4):
        try:
            d = requests.get(
                "https://api.render.com/v1/logs",
                headers={"Authorization": "Bearer " + key,
                         "Accept": "application/json"}, timeout=120,
                params={"ownerId": OWNER, "resource": SERVICE, "limit": limit,
                        "direction": "backward"}).json()
            return [str(e.get("message", e)).strip()
                    for e in (d.get("logs") or [])]
        except Exception:
            time.sleep(4)
    return []


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--key", default="")
    args = ap.parse_args()

    env = render_env()
    key = (args.key or env.get("STRIPE_API_KEY")
           or env.get("STRIPE_SECRET_KEY") or "").strip()
    whsec = (env.get("STRIPE_WEBHOOK_SECRET") or "").strip()
    results = {}

    print("=== 1. the account behind the key ===")
    if not key:
        print("    !! no key available (Render env unreadable and no --key)")
        return 2
    acct = stripe_get(key, "account")
    if "id" not in acct:
        print("    !! key REJECTED:", str(acct)[:200])
        return 2
    caps = acct.get("capabilities") or {}
    print("    account          : %s (%s)"
          % (acct.get("id"), "LIVE" if key.startswith("sk_live") else "TEST"))
    print("    charges_enabled  :", acct.get("charges_enabled"))
    print("    card_payments    :", caps.get("card_payments"))
    print("    key / secret     : %s · %s" % (mask(key), mask(whsec)))
    endpoints = stripe_get(key, "webhook_endpoints", limit=20).get("data", [])
    print("    webhook endpoints:", len(endpoints))
    for e in endpoints:
        print("      - %s (%s) events=%s"
              % (e.get("url"), e.get("status"),
                 ",".join(e.get("enabled_events") or [])))
    results["account"] = bool(acct.get("charges_enabled")
                              and caps.get("card_payments") == "active")
    results["endpoint"] = bool(endpoints)

    print("\n=== 2. the live checkout path ===")
    post = requests.post(CHECKOUT_URL, timeout=90, allow_redirects=False,
                         data={"plan": "starter",
                               "email": "readiness-check@example.invalid"})
    location = post.headers.get("Location", "")
    print("    POST /sales/checkout → HTTP %d" % post.status_code)
    results["checkout"] = False
    session_id = ""
    if post.status_code == 303 and "cs_" in location:
        session_id = location.split("/c/pay/")[-1].split("#")[0]
        print("    session:", session_id)
        detail = stripe_get(key, "checkout/sessions/" + session_id)
        amount = (detail.get("amount_total") or 0) / 100.0
        print("    verified AT STRIPE: status=%s payment_status=%s | $%.2f %s | "
              "livemode=%s" % (detail.get("status"), detail.get("payment_status"),
                               amount, detail.get("currency"),
                               detail.get("livemode")))
        results["checkout"] = bool(detail.get("livemode")
                                   and amount > 0 and detail.get("status"))
    else:
        print("    body:", post.text[:200])
        print("    → the failure reason is in OUR log: read the newest")
        print("      'Stripe checkout session creation FAILED' line.")

    print("\n=== 3. the webhook delivery (create + expire, then watch) ===")
    results["delivery"] = False
    if not session_id:
        print("    skipped: no session was created to expire.")
    else:
        before = render_logs()
        expired = requests.post(
            "https://api.stripe.com/v1/checkout/sessions/%s/expire" % session_id,
            headers=_auth(key), timeout=60)
        print("    expired the session: HTTP %d (%s)"
              % (expired.status_code, (expired.json() or {}).get("status")))
        if not endpoints:
            print("    !! NO endpoint in this account → Stripe has nothing to")
            print("       deliver, and the secret in Render belongs to another")
            print("       account. A real payment would be CHARGED with no sale")
            print("       ever reaching the CRM. See stripe_health.py for steps.")
        else:
            for _ in range(10):
                time.sleep(8)
                new = [m for m in render_logs() if m not in before]
                hits = [m for m in new if "webhooks/stripe" in m]
                if hits:
                    for line in hits[:4]:
                        print("    ", line[:190])
                    results["delivery"] = any(
                        '"POST /api/webhooks/stripe HTTP/1.1" 200' in m
                        for m in hits)
                    break
            else:
                print("    no delivery observed within ~80s (check the endpoint's")
                print("    event subscriptions and its Recent Deliveries tab).")

    print("\n=== VERDICT ===")
    for name in ("account", "checkout", "endpoint", "delivery"):
        print("    %-9s %s" % (name, "GREEN" if results.get(name) else "RED"))
    if results["account"] and results["checkout"] and results["delivery"]:
        print("    READY for a real test payment.")
        return 0
    print("    NOT READY: %s" % ", ".join(
        n for n in ("account", "checkout", "endpoint", "delivery")
        if not results.get(n)))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())