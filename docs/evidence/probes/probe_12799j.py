# -*- coding: utf-8 -*-
"""Read-only: tight 28.09 windows — the 08:24:40Z boot (=11:24:40 EEST)
and the guard boot 09:00:17Z. All sentinel/webhook/telegram lines."""
from __future__ import annotations

import sys

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = r"C:\Users\AlienWare\Desktop\проекти\kristo-intelligence-6"
SERVICE = "srv-d9maroe7bikc73adkaug"
OWNER = "tea-d6n5s3f5r7bs73cq"
KEY = open(ROOT + r"\secrets\render_api_key.txt",
           encoding="utf-8").read().strip()
H = {"Authorization": "Bearer " + KEY, "Accept": "application/json"}
BASE = "https://api.render.com/v1"

KEYS = ("sentinel", "webhook", "thread started", "bulletin", "baseline",
        "deploying", "directory", "fetch")

for day, h0, h1 in (("2026-09-28", "08:24:35", "08:26:30"),
                    ("2026-09-28", "09:00:10", "09:01:00")):
    r = requests.get(
        f"{BASE}/logs",
        params={"ownerId": OWNER, "resource": SERVICE, "limit": "500",
                "startTime": f"{day}T{h0}Z", "endTime": f"{day}T{h1}Z"},
        headers=H, timeout=90)
    data = r.json()
    entries = data if isinstance(data, list) else (
        data.get("logs") or data.get("entries") or [])
    print(f"=== {day} {h0[:8]}-{h1[:8]}Z n={len(entries)}")
    for e in entries:
        msg = ((e.get("message") or e.get("line") or str(e))
               if isinstance(e, dict) else str(e))
        if any(k in msg.lower() for k in KEYS):
            ts = (e.get("timestamp") or "")[11:19]
            print("  ", ts, "|", msg[:220])
print("DONE", flush=True)
