# -*- coding: utf-8 -*-
"""Read-only: finalize who/when edited #13219 evidence.
- run 36390969864 (= UI #31971): run_attempt / event / actors
- upstream workflow files (raw fetch, no API quota): trigger types
- current PR body (length + head) for description forensics."""
from __future__ import annotations

import sys

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
H = {"Accept": "application/vnd.github+json",
     "User-Agent": "readonly-probe"}
API = "https://api.github.com"
REPO = "punkpeye/awesome-mcp-servers"


def get(path, **kw):
    r = requests.get(f"{API}{path}", headers=H, timeout=30, **kw)
    return r.status_code, (r.json() if r.headers.get(
        "content-type", "").startswith("application/json") else r.text)


st, run = get(f"/repos/{REPO}/actions/runs/36390969864")
if st == 200 and isinstance(run, dict):
    print("RUN 31971 detail:")
    for k in ("run_number", "name", "path", "event", "status",
              "conclusion", "run_attempt", "run_started_at",
              "created_at", "updated_at", "display_title",
              "head_branch", "head_sha", "event"):
        if k in run:
            v = run.get(k)
            if k == "head_sha":
                v = str(v)[:12]
            print(f"   {k} = {v!r}")
    print("   actor =",
          (run.get("actor") or {}).get("login"))
    print("   triggering_actor =",
          (run.get("triggering_actor") or {}).get("login"))
    ws = run.get("workflow_id")
    print("   workflow_id =", ws)
else:
    print("run detail HTTP", st)

st, wf = get(f"/repos/{REPO}/contents/.github/workflows")
names = [x.get("name") for x in wf] if isinstance(wf, list) else []
print("\nworkflows:", ", ".join(names) or st)

for nm in names:
    if not any(t in nm for t in ("glama", "submission", "welcome")):
        continue
    url = (f"https://raw.githubusercontent.com/{REPO}/HEAD"
           f"/.github/workflows/{nm}")
    r = requests.get(url, headers={"User-Agent": "readonly-probe"},
                     timeout=30)
    txt = r.text
    if len(txt) > 4000:
        txt = txt[:4000]
    print(f"\n===== {nm} (HTTP {r.status_code}) =====")
    print(txt)

st, pr = get(f"/repos/{REPO}/pulls/13219")
if st == 200 and isinstance(pr, dict):
    body = pr.get("body") or ""
    print(f"\nPR BODY len={len(body)}")
    print(body[:1500])
print("\nDONE", flush=True)
