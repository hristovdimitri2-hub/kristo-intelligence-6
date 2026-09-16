"""Point a NEW Stripe account's webhook at us, and store its signing secret.

The one thing that never travels: **the signing secret is bound to the account
that owns the endpoint**, so switching the API key to a new account ALWAYS
invalidates the old `whsec_` — and the failure is silent (Stripe gets a 400
`invalid_signature` from us and the sale never reaches the CRM). This script does
both halves in one go, and it is the procedure we now use whenever an account is
rotated:

  Step 1: POST /v1/webhook_endpoints in the account behind STRIPE_API_KEY and
          read the signing secret from the response — Stripe returns it ONCE,
          here, and never again.
  Step 2: PUT /v1/services/{service}/env-vars/STRIPE_WEBHOOK_SECRET with that
          secret (a SINGLE-KEY update: a full env replace could lose a variable),
          which triggers a deploy.

Guards, so it can never damage a working setup:
  * it refuses to create a second endpoint for this URL if one is already
    enabled in the account it is pointed at;
  * it aborts before touching Render if Stripe did not return a `whsec_`;
  * it reports the env var count and the untouched key, so a partial write is
    visible immediately.

Secrets are printed as type/length/masked tail only, never in full. Verify with
`python -X utf8 scripts/stripe_readiness.py` afterwards (it needs the deploy to be
live, and its third question — a REAL delivery observed in our log — is the only
proof that the secret matches).

Usage:
    python -X utf8 scripts/wire_stripe_webhook.py
"""
from __future__ import annotations

import os
import time

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVICE = "srv-d9maroe7bikc73adkaug"
URL = "https://kristo-intelligence-api.onrender.com/api/webhooks/stripe"
EVENTS = ["checkout.session.completed",
          "checkout.session.expired",
          "checkout.session.async_payment_succeeded",
          "payment_intent.payment_failed"]

render_key = open(os.path.join(ROOT, "secrets", "render_api_key.txt"),
                  encoding="utf-8").read().strip()
RH = {"Authorization": "Bearer " + render_key, "Accept": "application/json"}


def render_env():
    for _ in range(6):
        try:
            out = {}
            for item in requests.get(
                    "https://api.render.com/v1/services/%s/env-vars?limit=100"
                    % SERVICE, headers=RH, timeout=90).json():
                ev = item.get("envVar", item)
                out[ev.get("key")] = ev.get("value")
            return out
        except Exception:
            time.sleep(4)
    return {}


def mask_secret(v: str) -> str:
    v = (v or "").strip()
    return "whsec_… (len %d, tail %s)" % (len(v), v[-4:]) if v else "MISSING"


env = render_env()
stripe_key = (env.get("STRIPE_API_KEY") or env.get("STRIPE_SECRET_KEY") or "").strip()
auth = {"Authorization": "Bearer " + stripe_key}
old_secret = (env.get("STRIPE_WEBHOOK_SECRET") or "").strip()
print("Render BEFORE : %s" % mask_secret(old_secret))

print("\n=== 1. create the endpoint in the new account ===")
existing = requests.get("https://api.stripe.com/v1/webhook_endpoints",
                        headers=auth, params={"limit": 20}, timeout=60).json()
for ep in existing.get("data", []):
    print("   already there: %s | %s | %s"
          % (ep.get("id"), ep.get("url"), ep.get("status")))
    if ep.get("url") == URL and ep.get("status") == "enabled":
        print("   !! an endpoint for this URL already exists — NOT creating a")
        print("      second one (its secret cannot be read back; you would have")
        print("      to paste it in the Dashboard instead).")
        raise SystemExit(2)

created = requests.post(
    "https://api.stripe.com/v1/webhook_endpoints", headers=auth, timeout=60,
    data={"url": URL,
          "description": "kristo-intelligence-api — sales + refund signals",
          "enabled_events[]": EVENTS})
if created.status_code != 200:
    print("   FAILED: HTTP %d %s" % (created.status_code, created.text[:400]))
    raise SystemExit(1)
ep = created.json()
new_secret = (ep.get("secret") or "").strip()
print("   id      :", ep.get("id"))
print("   url     :", ep.get("url"))
print("   status  :", ep.get("status"), "| livemode:", ep.get("livemode"))
print("   events  :", ", ".join(ep.get("enabled_events") or []))
print("   secret  :", mask_secret(new_secret), "← returned ONCE, on creation")
if not new_secret.startswith("whsec_"):
    print("   !! no secret in the response — aborting before touching Render")
    raise SystemExit(1)

print("\n=== 2. replace STRIPE_WEBHOOK_SECRET in Render (single key) ===")
put = requests.put(
    "https://api.render.com/v1/services/%s/env-vars/STRIPE_WEBHOOK_SECRET"
    % SERVICE, headers=RH, timeout=90,
    json={"value": new_secret})
print("   PUT env-var → HTTP %d" % put.status_code)
if put.status_code not in (200, 201):
    print("   body:", put.text[:400])
    raise SystemExit(1)

after = render_env()
print("Render AFTER  : %s" % mask_secret(after.get("STRIPE_WEBHOOK_SECRET")))
print("   changed     :",
      after.get("STRIPE_WEBHOOK_SECRET") != old_secret,
      "| matches the new endpoint secret:",
      after.get("STRIPE_WEBHOOK_SECRET") == new_secret)
print("   key unchanged:", after.get("STRIPE_API_KEY") == env.get("STRIPE_API_KEY"))
print("   env var count unchanged:", len(after) == len(env),
      "(%d → %d)" % (len(env), len(after)))