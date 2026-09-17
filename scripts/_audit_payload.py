"""FINAL payment-path audit, part 1: the raw payload and the log (read-only).

No writes anywhere: only GETs against our own service, the Render log API and
Stripe's read endpoints.
"""
from __future__ import annotations

import json
import os
import time

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BASE = "https://kristo-intelligence-api.onrender.com"
SERVICE = "srv-d9maroe7bikc73adkaug"
OWNER = "tea-d9m96f9qjqt8s73erj60"


def render_logs(limit=500):
    key = open(os.path.join(ROOT, "secrets", "render_api_key.txt"),
               encoding="utf-8").read().strip()
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


data = requests.get(BASE + "/api/dashboard/data", timeout=90).json()
S = data.get("sections", {})
print("=== generated_at:", data.get("generated_at"))
print("=== section keys:", list(S))
print("\n=== onchain ===")
o = S.get("onchain", {})
print(json.dumps({k: v for k, v in o.items() if k != "history"},
                 ensure_ascii=False, indent=1)[:900])
print("   history rows:", len(o.get("history") or []))
for h in (o.get("history") or [])[:12]:
    print("    %s $%-7s %-9s %s" % (h.get("ts", "")[:19], h.get("amount_usdc"),
                                    h.get("payer_class"),
                                    (h.get("tx_hash") or "")[:20]))
print("\n=== crm_stripe ===")
print(json.dumps(S.get("crm_stripe"), ensure_ascii=False, indent=1)[:1200])
print("\n=== guards ===")
print(json.dumps(S.get("guards"), ensure_ascii=False, indent=1)[:1600])
print("\n=== routes ===")
print(json.dumps(S.get("routes"), ensure_ascii=False, indent=1)[:900])

print("\n=== the log: money events ===")
lines = render_logs()
tags = ("webhook", "checkout.session", "crm", "entitle", "agent_access",
        "sale", "paid", "token", "guards")
for line in lines:
    low = line.lower()
    if any(t in low for t in tags):
        print("   ", line[:210])