"""Read the newest Stripe failure from our own log (after the fix)."""
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

for attempt in range(5):
    try:
        d = requests.get("https://api.render.com/v1/logs", headers=RH,
                         timeout=120, params={"ownerId": OWNER, "resource": SID,
                                              "limit": 400,
                                              "direction": "backward"}).json()
        lines = [str(e.get("message", e)).strip() for e in (d.get("logs") or [])]
        break
    except Exception:
        time.sleep(4)
else:
    raise SystemExit("no logs")

interesting = ("checkout/sessions", "Managed Payments", "FAILED",
               "error_message", "payment_method")
print("=== newest checkout-related lines (oldest first) ===")
for line in lines:
    if any(tag in line for tag in ("checkout/sessions", "FAILED", "error_message", "Managed")):
        print("   ", line[:230])
