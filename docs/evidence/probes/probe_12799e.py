# -*- coding: utf-8 -*-
"""Read-only: strict logs, tiny windows around both 11:24 candidates."""
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

KEYS = ("sentinel", "github", "fetch", "telegram", "directory",
        "baseline", "warn", "error", "pr_")

for start, end in (("2026-10-04T08:22:00Z", "2026-10-04T08:28:00Z"),
                   ("2026-10-04T11:22:00Z", "2026-10-04T11:28:00Z")):
    print(f"=== {start[11:16]}-{end[11:16]}Z")
    r = requests.get(
        f"{BASE}/logs",
        params={"ownerId": OWNER, "resource": SERVICE, "limit": "1000",
                "startTime": start, "endTime": end},
        headers=H, timeout=90)
    data = r.json()
    entries = data if isinstance(data, list) else (
        data.get("logs") or data.get("entries") or [])
    print("HTTP", r.status_code, "n:", len(entries))
    for e in entries:
        msg = ((e.get("message") or e.get("line") or str(e))
               if isinstance(e, dict) else str(e))
        if any(k in msg.lower() for k in KEYS):
            ts = (e.get("timestamp") or "")[11:23]
            print("  ", ts, "|", msg[:230])
print("DONE", flush=True)
