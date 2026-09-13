"""Priority-0 diagnosis: 14h-later sales state + Render scan logs (read-only)."""
import os

import json
import os

import requests

key = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "..", "secrets", "render_api_key.txt")).read().strip()
h = {"Authorization": f"Bearer {key}", "Accept": "application/json"}
SID = "srv-d9maroe7bikc73adkaug"

print("=== 1. LIVE dashboard (14h later) ===")
d = requests.get("https://kristo-intelligence-api.onrender.com/api/dashboard/data",
                 timeout=40).json()
o = d["sections"]["onchain"]
print("total:", o["total_usdc"], "/", o["total_count"], "| external:",
      o["external_payers"], "| wm:", o["last_scanned_block"])
print("by_class:", o["by_class"])
for hh in o["history"]:
    print("  %s  $%-8s %-9s %s  tx=%s" % (
        hh["ts"][:19], hh["amount_usdc"], hh["payer_class"],
        hh["sender"][:14], hh["tx_hash"][:22]))

print("\n=== 2. Render logs (scan loop alive?) ===")
svc = requests.get(f"https://api.render.com/v1/services/{SID}", headers=h,
                   timeout=30).json()
owner = (svc.get("ownerId") or svc.get("service", {}).get("ownerId") or "")
print("ownerId:", owner[:20] if owner else "(missing)")
if owner:
    r = requests.get(
        f"https://api.render.com/v1/logs?ownerId={owner}&limit=100&type=app",
        headers=h, timeout=30)
    print("logs API:", r.status_code)
    for e in r.json().get("logs", [])[-30:]:
        msg = e.get("message", "")
        if any(k in msg.lower() for k in ("scan", "whale", "retro", "error",
                                          "fail", "warning", "sale")):
            print("  ", msg[:130])