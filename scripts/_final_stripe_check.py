"""Final checks 2 + 3: the live checkout path and the REAL webhook delivery.

  * POST /sales/checkout → 303 to a real cs_live_… $29 session, verified at
    Stripe, then expired (audit email — no payment, no clutter);
  * create + expire a session and watch for the real Stripe delivery so the
    webhook secret can be judged on evidence, not on a self-signed dry-run.
"""
from __future__ import annotations

import os
import time

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEY = open(os.path.join(ROOT, "secrets", "render_api_key.txt"),
           encoding="utf-8").read().strip()
RH = {"Authorization": "Bearer " + KEY, "Accept": "application/json"}
SID = "srv-d9maroe7bikc73adkaug"
OWNER = "tea-d9m96f9qjqt8s73erj60"
BASE = "https://kristo-intelligence-api.onrender.com"


def render_env():
    for _ in range(6):
        try:
            out = {}
            for item in requests.get(
                    "https://api.render.com/v1/services/%s/env-vars?limit=100"
                    % SID, headers=RH, timeout=90).json():
                ev = item.get("envVar", item)
                out[ev.get("key")] = ev.get("value")
            return out
        except Exception:
            time.sleep(4)
    return {}


def logs(limit=200):
    d = requests.get("https://api.render.com/v1/logs", headers=RH, timeout=120,
                     params={"ownerId": OWNER, "resource": SID, "limit": limit,
                             "direction": "backward"}).json()
    return [str(e.get("message", e)).strip() for e in (d.get("logs") or [])]


env = render_env()
key = (env.get("STRIPE_API_KEY") or "").strip()
auth = {"Authorization": "Bearer " + key}

print("=== 2. the live checkout path ===")
post = requests.post(BASE + "/sales/checkout", timeout=90, allow_redirects=False,
                     data={"plan": "starter",
                           "email": "preflight-check@example.invalid"})
location = post.headers.get("Location", "")
print("   POST /sales/checkout → HTTP %d" % post.status_code)
if "cs_live_" not in location:
    print("   body:", post.text[:200])
    raise SystemExit(1)
session_id = "cs_live_" + location.split("cs_live_")[1].split("#")[0]
print("   session:", session_id)
detail = requests.get("https://api.stripe.com/v1/checkout/sessions/"
                      + session_id, headers=auth, timeout=60).json()
print("   verified: %s/%s | $%s %s | livemode=%s"
      % (detail.get("status"), detail.get("payment_status"),
         (detail.get("amount_total") or 0) / 100.0, detail.get("currency"),
         detail.get("livemode")))
print("   metadata:", detail.get("metadata"))

print("\n=== 3. webhook: real delivery test ===")
endpoints = requests.get("https://api.stripe.com/v1/webhook_endpoints",
                         headers=auth, timeout=60).json().get("data", [])
print("   endpoints in this account:", len(endpoints))
for ep in endpoints:
    print("    - %s | status=%s events=%s" % (ep.get("url"), ep.get("status"),
                                              ", ".join(ep.get("enabled_events")
                                                        or [])))
before = logs()
expire = requests.post("https://api.stripe.com/v1/checkout/sessions/%s/expire"
                       % session_id, headers=auth, timeout=60)
print("   expired the session: HTTP %d status=%s"
      % (expire.status_code, (expire.json() or {}).get("status")))

deliveries = []
for attempt in range(10):
    time.sleep(8)
    new = [m for m in logs() if m not in before]
    deliveries = [m for m in new if "webhooks/stripe" in m
                  or "Rejected Stripe webhook" in m]
    if deliveries:
        break
for line in deliveries[:6]:
    print("   ", line[:190])
accepted = [m for m in deliveries if '"POST /api/webhooks/stripe HTTP/1.1" 200' in m]
rejected = [m for m in deliveries if "invalid signature" in m]
print("\n   real deliveries: accepted=%d rejected=%d"
      % (len(accepted), len(rejected)))
if not endpoints:
    print("   → NO endpoint exists in this account, so Stripe has nothing to")
    print("     deliver. The secret in Render is still the OLD account's")
    print("     (tail %s) and cannot match a new one." % (env.get(
        "STRIPE_WEBHOOK_SECRET", "")[-4:]))
elif accepted and not rejected:
    print("   → the secret in Render MATCHES the endpoint ✅")
elif rejected and not accepted:
    print("   → MISMATCH ❌ (deliveries are being rejected)")