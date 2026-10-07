# -*- coding: utf-8 -*-
"""Read-only GitHub GETs: open PRs by hristovdimitri2-hub in
punkpeye/awesome-mcp-servers + full #13219 status/CI/comments/events."""
from __future__ import annotations

import sys

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

H = {"Accept": "application/vnd.github+json",
     "User-Agent": "readonly-probe"}
REPO = "punkpeye/awesome-mcp-servers"
API = "https://api.github.com"


def get(path, **kw):
    extra = kw.pop("headers", None) or {}
    r = requests.get(f"{API}{path}", headers={**H, **extra},
                     timeout=30, **kw)
    return r.status_code, (r.json() if r.headers.get(
        "content-type", "").startswith("application/json") else r.text)


# search API — author-scoped, immune to pagination
st, sr = get("/search/issues",
             params={"q": f"repo:{REPO} is:pr is:open"
                           " author:hristovdimitri2-hub",
                     "per_page": 100})
print("SEARCH open PRs by author: HTTP", st,
      "total=", sr.get("total_count") if isinstance(sr, dict) else "?")
for it in (sr.get("items") or []) if isinstance(sr, dict) else []:
    print(f"  #{it['number']} | {it['title'][:90]}"
          f" | created={it['created_at']} | updated={it['updated_at']}")


# 1) open PRs by our author
st, prs = get(f"/repos/{REPO}/pulls?state=open&per_page=100")
print("OPEN PRS HTTP", st, "n=", len(prs) if isinstance(prs, list) else "?")
mine = [p for p in prs
        if (p.get("user") or {}).get("login", "").lower()
        == "hristovdimitri2-hub"]
for p in mine:
    print(f"  #{p['number']} | {p['title'][:90]} | created={p['created_at']}"
          f" | updated={p['updated_at']} | draft={p.get('draft')}")
print("mine-n =", len(mine))

# also search ALL states closed for completeness? -> no, task: open only.

# 2) #13219 details
st, pr = get(f"/repos/{REPO}/pulls/13219")
print("\n#13219 HTTP", st, "| state=", pr.get("state"),
      "| merged=", pr.get("merged"),
      "| mergeable_state=", pr.get("mergeable_state"),
      "| updated=", pr.get("updated_at"),
      "| head=", (pr.get("head") or {}).get("sha", "")[:10],
      "| user=", (pr.get("user") or {}).get("login"))

sha = (pr.get("head") or {}).get("sha") or ""
st, chk = get(f"/repos/{REPO}/commits/{sha}/check-runs")
runs = chk.get("check_runs") if isinstance(chk, dict) else None
if runs is not None:
    print("CHECK-RUNS n=", chk.get("total_count"))
    for c in runs:
        print(f"   {c.get('name')} | {c.get('status')} | {c.get('conclusion')}"
              f" | {c.get('completed_at')}")
st, cs = get(f"/repos/{REPO}/commits/{sha}/status")
if isinstance(cs, dict):
    print("COMBINED STATUS:", cs.get("state"),
          "n=", len(cs.get("statuses") or []))
    for s in (cs.get("statuses") or [])[:8]:
        print(f"   {s.get('context')} | {s.get('state')} | {s.get('updated_at')}")

# 3) comments (Frank/bots?)
st, cmts = get(f"/repos/{REPO}/issues/13219/comments?per_page=100")
print("\nCOMMENTS n=", len(cmts) if isinstance(cmts, list) else st)
for c in (cmts if isinstance(cmts, list) else []):
    au = (c.get("user") or {}).get("login", "?")
    print(f"   {c.get('created_at')} | {au} | {c.get('body','')[:110]!r}")

# 4) events (labels, renames, edits)
st, evs = get(f"/repos/{REPO}/issues/13219/events?per_page=100")
print("\nEVENTS n=", len(evs) if isinstance(evs, list) else st)
for e in (evs if isinstance(evs, list) else []):
    print(f"   {e.get('created_at')} | {(e.get('actor') or {}).get('login')}"
          f" | {e.get('event')} | {e.get('label',{}).get('name','')}"
          f" | {e.get('rename',{}).get('from','')}"
          f" -> {e.get('rename',{}).get('to','')}"
          f" | {(e.get('commit_id') or '')[:8]}")

# 5) timeline (richer: renamed/edited/etc.)
st, tl = get(f"/repos/{REPO}/issues/13219/timeline?per_page=100",
             headers={**H,
                      "Accept": "application/vnd.github.mockingbird-preview+json"})
print("\nTIMELINE HTTP", st,
      "n=", len(tl) if isinstance(tl, list) else "?")
if isinstance(tl, list):
    for e in tl:
        ev = e.get("event")
        if ev in ("renamed", "edited", "labeled", "unlabeled",
                  "commented", "committed", "converted_to_draft",
                  "ready_for_review", "closed", "reopened", "merged",
                  "review_requested", "base_ref_changed"):
            who = (e.get("actor") or e.get("user") or {}).get("login", "?")
            extra = ""
            if ev == "renamed":
                extra = (f" from {e.get('rename',{}).get('from','')!r}"
                         f" to {e.get('rename',{}).get('to','')!r}")
            if ev == "edited":
                extra = f" assoc={e.get('author_association','')}"
            if ev == "commented":
                extra = f" {e.get('body','')[:80]!r}"
            if ev == "labeled":
                extra = f" label={e.get('label',{}).get('name')}"
            if ev == "committed":
                who = (e.get("author") or {}).get("login", "?")
                extra = (f" sha={str(e.get('sha',''))[:8]}"
                         f" {str(e.get('message') or '')[:70]!r}")
            print(f"   {e.get('created_at')} | {who} | {ev}{extra}")

# 6) referenced run #31971 (which repo?)
for repo in (REPO, "hristovdimitri2-hub/kristo-intelligence-6",
             "hristovdimitri2-hub/kristo-travel-api"):
    st, run = get(f"/repos/{repo}/actions/runs/31971")
    if st == 200 and isinstance(run, dict):
        print(f"\nRUN 31971 in {repo}: name={run.get('name')!r} "
              f"event={run.get('event')} status={run.get('status')} "
              f"conclusion={run.get('conclusion')} "
              f"created={run.get('created_at')} "
              f"branch={run.get('head_branch')} "
              f"display={run.get('display_title','')!r}")
    else:
        print(f"RUN 31971 in {repo}: HTTP {st}")
print("DONE", flush=True)
