# -*- coding: utf-8 -*-
"""Read-only: STRICT filter — only sentinel/github/fetch lines, both windows."""
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

KEYS = ("sentinel", "github", "fetch failed", "pr check", "directory pr",
        "baseline", "watched")

for h0, h1, label in (
    ("08:00", "09:00", "08-09Z = 11:00-12:00 EEST"),
    ("11:00", "12:00", "11-12Z = 14:00-15:00 EEST / 11:24 UTC"),
):
    print(f"=== 2026-10-04T{h0}-T{h1} ({label})")
    r = requests.get(
        f"{BASE}/logs",
        params={"ownerId": OWNER, "resource": SERVICE, "limit": "1000",
                "startTime": f"2026-10-04T{h0}:00Z",
                "endTime": f"2026-10-04T{h1}:00Z"},
        headers=H, timeout=90)
    data = r.json()
    entries = data if isinstance(data, list) else (
        data.get("logs") or data.get("entries") or [])
    print("HTTP", r.status_code, "n entries:", len(entries))
    shown = 0
    for e in entries:
        msg = ((e.get("message") or e.get("line") or str(e))
               if isinstance(e, dict) else str(e))
        low = msg.lower()
        if any(k in low for k in KEYS):
            ts = (e.get("timestamp") or e.get("createdAt") or "")
            print("  ", ts[11:23], "|", msg[:200])
            shown += 1
    print("shown:", shown)
print("DONE", flush=True)
