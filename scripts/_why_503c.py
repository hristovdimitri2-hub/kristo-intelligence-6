"""Newest-first: what did the RETRY say? (its error_message was cut off before)"""
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

tags = ("checkout/sessions", "FAILED", "error_message", "Managed", "retrying")
hits = [l for l in lines
        if any(t in l for t in tags) and "limit=100" not in l]
print("=== every POST + its response/error (%d hits) ===" % len(hits))
for line in hits[-14:]:
    print("   ", line[:300])
