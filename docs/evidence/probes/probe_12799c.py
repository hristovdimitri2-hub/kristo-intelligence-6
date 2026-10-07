# -*- coding: utf-8 -*-
"""Read-only: Render logs in tight windows around 04.10 11:24 (both TZs)."""
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

WINDOWS = [
    ("08:20:00Z", "08:30:00Z", "= 11:24 EEST (local UTC+3)"),
    ("11:20:00Z", "11:30:00Z", "= 11:24 UTC"),
]

for hm0, hm1, label in WINDOWS:
    print(f"=== 2026-10-04 {hm0}-{hm1} {label}", flush=True)
    r = requests.get(
        f"{BASE}/logs",
        params={"ownerId": OWNER, "resource": SERVICE, "limit": "1000",
                "startTime": f"2026-10-04T{hm0}",
                "endTime": f"2026-10-04T{hm1}"},
        headers=H, timeout=90)
    print("HTTP", r.status_code)
    try:
        data = r.json()
        entries = data if isinstance(data, list) else (
            data.get("logs") or data.get("entries") or [])
        print("n entries:", len(entries))
        for e in entries:
            msg = ((e.get("message") or e.get("line") or str(e))
                   if isinstance(e, dict) else str(e))
            ts = (e.get("timestamp") or e.get("createdAt") or "")
            low = msg.lower()
            if any(k in low for k in ("sentinel", "github", "pr", "fetch",
                                      "warn", "error", "fail", "limit",
                                      "deploy", "starting")):
                print("  ", ts, "|", msg[:260])
    except Exception as exc:
        print("parse err:", str(exc)[:150], "|", r.text[:300])
print("DONE", flush=True)
