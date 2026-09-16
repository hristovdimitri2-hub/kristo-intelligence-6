"""Wait for the new build to go live, then run the final checks again."""
from __future__ import annotations

import os
import subprocess
import time

import requests

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KEY = open(os.path.join(ROOT, "secrets", "render_api_key.txt"),
           encoding="utf-8").read().strip()
RH = {"Authorization": "Bearer " + KEY, "Accept": "application/json"}
SID = "srv-d9maroe7bikc73adkaug"
WANT = "b69fdec"

for attempt in range(40):
    deploys = requests.get(f"https://api.render.com/v1/services/{SID}/deploys",
                           headers=RH, timeout=90, params={"limit": 1}).json()
    d = deploys[0].get("deploy", deploys[0])
    commit = ((d.get("commit") or {}).get("id") or "")[:7]
    print("   %ds: live=%s (%s)" % (attempt * 15, commit, d.get("status")),
          flush=True)
    if commit == WANT and d.get("status") == "live":
        print("   the new build is live ✅")
        break
    time.sleep(15)
else:
    print("   TTL: still not live — running the checks anyway")
    raise SystemExit(1)

print(subprocess.run(["python", "-X", "utf8",
                      os.path.join(ROOT, "scripts", "_final_stripe_check.py")],
                     cwd=ROOT, capture_output=True, text=True,
                     encoding="utf-8").stdout)