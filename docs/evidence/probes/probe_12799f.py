# -*- coding: utf-8 -*-
"""Read-only: full deploy commit SHAs + extra Render resources (cron/worker)."""
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

r = requests.get(f"{BASE}/services", params={"ownerId": OWNER},
                 headers=H, timeout=60)
data = r.json()
svcs = data if isinstance(data, list) else data.get("services", [])
print("SERVICES n=", len(svcs))
for s in svcs:
    print("  ", s.get("id"), s.get("type"), s.get("name"),
          s.get("repo", {}).get("branch"))

for path in ("/cronjobs", "/workers", "/static-sites"):
    try:
        rr = requests.get(f"{BASE}{path}",
                          params={"ownerId": OWNER}, headers=H, timeout=60)
        dd = rr.json() if rr.status_code == 200 else rr.text[:200]
        items = dd if isinstance(dd, list) else []
        print(f"{path}: HTTP {rr.status_code} n={len(items)}")
        for it in items:
            o = it if isinstance(it, dict) else {}
            print("   ", o.get("id"),
                  o.get("name") or o.get("staticSite", {}).get("name"),
                  str(o.get("ownerId"))[:16])
    except Exception as exc:
        print(path, "ERR", exc)

r = requests.get(f"{BASE}/services/{SERVICE}/deploys",
                 params={"limit": "20"}, headers=H, timeout=60)
print("DEPLOYS HTTP", r.status_code)
for it in (r.json() if r.status_code == 200 else []):
    d = it.get("deploy") if isinstance(it, dict) else {}
    if not d:
        continue
    commit = d.get("commit") or {}
    print("  ", d.get("id"), "|", d.get("status"),
          "|", commit.get("id"), "|", commit.get("message", "")[:60],
          "|", d.get("finishedAt") or d.get("createdAt"))
print("DONE", flush=True)
