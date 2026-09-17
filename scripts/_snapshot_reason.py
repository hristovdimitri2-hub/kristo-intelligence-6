"""Read the newest Stripe snapshot-feed failure from OUR log (read-only)."""
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

tags = ("snapshot refresh failed", "stripe_list", "Stripe payment snapshot",
        "Available payment methods", "No valid payment")
hits = [l for l in lines if any(t.lower() in l.lower() for t in tags)]
print("=== snapshot-feed failures in the retained log (%d) ===" % len(hits))
for line in hits[:6]:
    print("   ", line[:300])
print("\n=== what the Stripe SDK calls returned ===")
for line in lines[:400]:
    if "checkout/sessions" in line and ("response_code=" in line):
        print("   ", line[:200])
