# -*- coding: utf-8 -*-
"""Read-only: Render service logs around 2026-10-04 11:24 alert window."""
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

KEYS = ("sentinel", "pr ", "12799", "fetch", "directory", "deploy",
        "starting", "watch", "baseline", "rate limit", "github",
        "watched", "error", "warn")

for start, end, label in (
    ("2026-10-04T08:00:00Z", "2026-10-04T10:00:00Z", "W1 08-10Z (11:24 EEST)"),
    ("2026-10-04T11:00:00Z", "2026-10-04T12:00:00Z", "W2 11-12Z (11:24 UTC)"),
):
    print(f"=== {label}", flush=True)
    r = requests.get(
        f"{BASE}/logs",
        params={"ownerId": OWNER, "resource": SERVICE, "limit": "500",
                "startTime": start, "endTime": end},
        headers=H, timeout=90)
    print("HTTP", r.status_code)
    try:
        data = r.json()
        entries = data if isinstance(data, list) else (
            data.get("logs") or data.get("entries") or [])
        print("n entries:", len(entries))
        hits = 0
        for e in entries:
            msg = ((e.get("message") or e.get("line") or str(e))
                   if isinstance(e, dict) else str(e))
            low = msg.lower()
            if any(k in low for k in KEYS):
                ts = (e.get("timestamp") or e.get("createdAt")
                      or e.get("id") or "")
                print("  ", ts, "|", msg[:240])
                hits += 1
        print("hits:", hits)
    except Exception as exc:
        print("parse err:", str(exc)[:150], "|", r.text[:300])
print("DONE", flush=True)
