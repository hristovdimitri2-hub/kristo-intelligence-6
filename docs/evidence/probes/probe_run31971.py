# -*- coding: utf-8 -*-
"""Read-only: locate GitHub Actions run NUMBER 31971 (UI numbering) in
punkpeye/awesome-mcp-servers + enumerate author repos as fallback."""
from __future__ import annotations

import sys
import time

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

H = {"Accept": "application/vnd.github+json",
     "User-Agent": "readonly-probe"}
API = "https://api.github.com"
WANT = 31971


def get(path, **kw):
    r = requests.get(f"{API}{path}", headers=H, timeout=30, **kw)
    return r.status_code, (r.json() if r.headers.get(
        "content-type", "").startswith("application/json") else r.text)


def hunt(repo: str, pages: int) -> bool:
    for page in range(1, pages + 1):
        st, d = get(f"/repos/{repo}/actions/runs",
                    params={"per_page": 100, "page": page})
        if st != 200 or not isinstance(d, dict):
            print(f"{repo} page{page}: HTTP {st}")
            return False
        runs = d.get("workflow_runs") or []
        if not runs:
            return False
        nums = [r.get("run_number") or 0 for r in runs]
        print(f"{repo} page{page}: run_number window"
              f" {max(nums)}..{min(nums)} (n={len(runs)})")
        for r in runs:
            if r.get("run_number") == WANT:
                print(f"FOUND {WANT} in {repo}:")
                print(f"   name={r.get('name')!r} event={r.get('event')}"
                      f" status={r.get('status')}"
                      f" conclusion={r.get('conclusion')}")
                print(f"   created={r.get('created_at')}"
                      f" updated={r.get('updated_at')}")
                print(f"   actor={(r.get('actor') or {}).get('login')}"
                      f" branch={r.get('head_branch')}"
                      f" sha={str(r.get('head_sha'))[:10]}")
                print(f"   display={r.get('display_title','')!r}")
                print(f"   url={r.get('html_url')}")
                return True
        if page == pages:
            print(f"{repo}: {WANT} not in pages 1-{pages}")
    return False


WANT = 31971
REPO = "punkpeye/awesome-mcp-servers"
CREATED = "2026-09-27..2026-09-30"

# wait out the unauthenticated rate limit (max ~500s)
rl = requests.get(f"{API}/rate_limit", headers=H, timeout=20).json()
core = (rl.get("resources") or {}).get("core") or {}
now = int(time.time())
wait = int(core.get("reset") or 0) - now + 8
print(f"rate: remaining={core.get('remaining')} wait={wait}s")
if core.get("remaining", 1) == 0 and 0 < wait <= 500:
    time.sleep(wait)
    rl = requests.get(f"{API}/rate_limit", headers=H,
                      timeout=20).json()
    core = (rl.get("resources") or {}).get("core") or {}
    print(f"after wait: remaining={core.get('remaining')}")

for page in (1, 2, 3, 4):
    r = requests.get(f"{API}/repos/{REPO}/actions/runs",
                     headers=H, timeout=30,
                     params={"per_page": 100, "page": page,
                             "created": CREATED})
    print(f"page{page}: HTTP {r.status_code}"
          f" remaining={r.headers.get('X-RateLimit-Remaining')}"
          f" reset={r.headers.get('X-RateLimit-Reset')}")
    if r.status_code != 200:
        print(r.text[:200])
        break
    runs = (r.json() or {}).get("workflow_runs") or []
    if not runs:
        print("no more runs")
        break
    nums = [x.get("run_number") or 0 for x in runs]
    print(f"  window {max(nums)}..{min(nums)} n={len(runs)}")
    for x in runs:
        if x.get("run_number") == WANT:
            print(f"FOUND {WANT}:")
            print(f"   name={x.get('name')!r} workflow={x.get('path')!r}")
            print(f"   event={x.get('event')} status={x.get('status')}"
                  f" conclusion={x.get('conclusion')}")
            print(f"   created={x.get('created_at')}"
                  f" updated={x.get('updated_at')}")
            print(f"   actor={(x.get('actor') or {}).get('login')}"
                  f" branch={x.get('head_branch')}"
                  f" sha={str(x.get('head_sha'))[:10]}")
            print(f"   display={x.get('display_title','')!r}")
            print(f"   url={x.get('html_url')}")
            break
    else:
        if page == 4:
            print("31971 not found in 27-30.09 window")
            break
        continue
    break
print("DONE", flush=True)

