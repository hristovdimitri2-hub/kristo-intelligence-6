# -*- coding: utf-8 -*-
"""Read-only: does the bot's webhook receive ANY update (incl. own posts)?
Sample 30-min slices across 04.10 + retry env-vars with ownerId.
"""
from __future__ import annotations

import sys

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = r"C:\Users\AlienWare\Desktop\проекти\kristo-intelligence-6"
KEY = open(ROOT + r"\secrets\render_api_key.txt",
           encoding="utf-8").read().strip()
H = {"Authorization": "Bearer " + KEY, "Accept": "application/json"}
BASE = "https://api.render.com/v1"
OWNER = "tea-d6n5s3f5r7bs73cq"
SERVICE = "srv-d9maroe7bikc73adkaug"

r = requests.get(f"{BASE}/services/{SERVICE}/env-vars",
                 params={"ownerId": OWNER, "limit": "200"},
                 headers=H, timeout=60)
print("ENV HTTP", r.status_code)
if r.status_code == 200:
    for it in r.json():
        ev = it.get("envVar") or {}
        k = ev.get("key", "")
        if k.startswith("TELEGRAM"):
            v = ev.get("value") or ""
            print("  ", k, "=", v if "CHAT" in k else v[:6] + "***")

KEYS = ("webhook", "report", "send failed", "sentinel")

slices = [
    ("06:00:00", "06:30:00"), ("09:00:00", "09:30:00"),
    ("11:55:00", "12:25:00"), ("14:55:00", "15:25:00"),
    ("17:55:00", "18:25:00"), ("20:55:00", "21:25:00"),
]
for h0, h1 in slices:
    r = requests.get(
        f"{BASE}/logs",
        params={"ownerId": OWNER, "resource": SERVICE, "limit": "1000",
                "startTime": f"2026-10-04T{h0}Z",
                "endTime": f"2026-10-04T{h1}Z"},
        headers=H, timeout=90)
    data = r.json()
    entries = data if isinstance(data, list) else (
        data.get("logs") or data.get("entries") or [])
    hits = []
    for e in entries:
        msg = ((e.get("message") or e.get("line") or str(e))
               if isinstance(e, dict) else str(e))
        if any(k in msg.lower() for k in KEYS):
            ts = (e.get("timestamp") or "")[11:19]
            hits.append(f"{ts} | {msg[:200]}")
    print(f"=== {h0[:5]}-{h1[:5]}Z n={len(entries)} hits={len(hits)}")
    for line in hits:
        print("  ", line)
print("DONE", flush=True)
