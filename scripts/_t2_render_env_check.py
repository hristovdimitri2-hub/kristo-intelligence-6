"""Табло 2.0 — read the production env + recent logs (so the RPC behaviour is
observed, not guessed). Read-only; never prints the API key."""
import os
import sys

import requests

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

KEY = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "secrets", "render_api_key.txt"), encoding="utf-8").read().strip()
H = {"Authorization": f"Bearer {KEY}", "Accept": "application/json"}

svcs = requests.get("https://api.render.com/v1/services?limit=20", headers=H,
                    timeout=60).json()
print("=== services ===")
target = None
for item in svcs:
    s = item.get("service", item)
    print(f"  {s['id']}  {s['name']:38} {s.get('type')}  {s.get('serviceDetails',{}).get('url','')}")
    if s.get("name") == "kristo-intelligence-api":
        target = s

if not target:
    sys.exit("no kristo service found")
sid = target["id"]
print(f"\n=== env vars of {target['name']} (interesting keys only) ===")
env = requests.get(f"https://api.render.com/v1/services/{sid}/env-vars",
                   headers=H, timeout=60).json()
watch = ("RPC", "CHUNK", "WHALEFLOW", "WHALE", "SALES", "CONFIRMATION",
         "RETRO", "SCAN", "DISABLE_BACKGROUND", "ADMIN")
for item in env:
    e = item.get("envVar", item)
    k = e.get("key", "")
    if any(w in k.upper() for w in watch):
        print(f"  {k} = {e.get('value')}")

det = requests.get(f"https://api.render.com/v1/services/{sid}", headers=H,
                   timeout=60).json()
d = det.get("serviceDetails", det)
print("\n=== how it is started ===")
for key in ("startCommand", "buildCommand", "env", "plan", "region",
            "numInstances", "autoDeploy", "healthCheckPath"):
    if key in d:
        print(f"  {key} = {d[key]}")
plans = requests.get(f"https://api.render.com/v1/services/{sid}/instances",
                     headers=H, timeout=60)
print("  instances:", plans.status_code, plans.text[:200] if plans.status_code != 200 else "ok")

owner = target.get("ownerId") or svcs[0].get("owner", {}).get("id")
print("\n=== recent logs (whale / scan / RPC lines) ===")
try:
    lg = requests.get("https://api.render.com/v1/logs", headers=H, timeout=90,
                      params={"ownerId": owner, "resource": sid, "limit": 200,
                              "direction": "backward"}).json()
    logs = lg.get("logs") or lg
    # Are the loops duplicated RIGHT NOW, minutes after the deploy? A deploy
    # overlap (old instance still draining) would duplicate only in that window.
    counts = {}
    for entry in logs:
        msg = str(entry.get("message", entry))
        for key in ("Dashboard scan loop started", "Whale flow scan loop started",
                    "Keep-alive thread started", "Whale flow increment failed",
                    "Log scan failed for blocks", "Verified-sales seed"):
            if key in msg:
                counts.setdefault(key, []).append(msg[:150])
    for key, items in counts.items():
        print(f"\n  [{key}] x{len(items)}")
        for msg in items[:6]:
            print("    " + msg)
except Exception as exc:
    print("  log fetch failed:", type(exc).__name__, str(exc)[:200])
