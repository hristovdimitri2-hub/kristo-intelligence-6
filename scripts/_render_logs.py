"""Render logs via ownerId + logs API (read-only)."""
import os

import requests

key = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "..", "secrets", "render_api_key.txt")).read().strip()
h = {"Authorization": f"Bearer {key}", "Accept": "application/json"}
owner = "tea-d6n5s3f5r7bs73cq"
r = requests.get(
    f"https://api.render.com/v1/logs?ownerId={owner}&limit=100&type=app",
    headers=h, timeout=30)
print("logs API:", r.status_code)
try:
    logs = r.json().get("logs", [])
    for e in logs[-30:]:
        msg = e.get("message", "")
        if any(k in msg.lower() for k in ("scan", "whale", "retro", "error",
                                          "fail", "warn", "sale")):
            print("  ", msg[:140])
except Exception as exc:
    print("parse ERR:", str(exc)[:100], "|", r.text[:200])