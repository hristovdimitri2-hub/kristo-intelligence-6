# -*- coding: utf-8 -*-
"""Read-only: 28.09 pre-guard window — boots + possible alert echo.
Windows: 07:15-07:30Z (37de33d boot), 08:05-08:35Z (df95882 boots incl.
08:24:40Z = 11:24:40 EEST), 08:55-09:15Z (guard deploy boot).
Keys: sentinel, thread started, webhook, telegram, github, fetch, baseline.
"""
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

KEYS = ("sentinel", "thread started", "webhook", "telegram",
        "github", "fetch", "baseline", "deploy")

for h0, h1 in (("07:15:00", "07:30:00"), ("08:05:00", "08:35:00"),
               ("08:55:00", "09:15:00")):
    r = requests.get(
        f"{BASE}/logs",
        params={"ownerId": OWNER, "resource": SERVICE, "limit": "1000",
                "startTime": f"2026-09-28T{h0}Z",
                "endTime": f"2026-09-28T{h1}Z"},
        headers=H, timeout=90)
    data = r.json()
    entries = data if isinstance(data, list) else (
        data.get("logs") or data.get("entries") or [])
    print(f"=== 28.09 {h0[:5]}-{h1[:5]}Z n={len(entries)}")
    for e in entries:
        msg = ((e.get("message") or e.get("line") or str(e))
               if isinstance(e, dict) else str(e))
        if any(k in msg.lower() for k in KEYS):
            ts = (e.get("timestamp") or "")[11:19]
            print("  ", ts, "|", msg[:230])
print("DONE", flush=True)
