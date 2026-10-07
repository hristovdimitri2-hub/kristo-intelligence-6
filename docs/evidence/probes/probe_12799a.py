# -*- coding: utf-8 -*-
"""Read-only: services, deploys, pr_watch_state row for #12799 diagnosis."""
from __future__ import annotations

import base64
import json
import os
import sys
import time

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = r"C:\Users\AlienWare\Desktop\проекти\kristo-intelligence-6"
SERVICE = "srv-d9maroe7bikc73adkaug"
OWNER = "tea-d6n5s3f5r7bs73cq"
KEY = open(os.path.join(ROOT, "secrets", "render_api_key.txt"),
           encoding="utf-8").read().strip()
H = {"Authorization": "Bearer " + KEY, "Accept": "application/json"}
BASE = "https://api.render.com/v1"

INNER = (
    "import json, os, psycopg\n"
    "from psycopg.rows import dict_row\n"
    "with psycopg.connect(os.environ['DATABASE_URL'], row_factory=dict_row,"
    " connect_timeout=15) as conn, conn.cursor() as cur:\n"
    "    cur.execute(\"SELECT pr_key, status, mergeable_state, updated_at "
    "FROM pr_watch_state ORDER BY pr_key\")\n"
    "    print('PR_WATCH_ROWS:', json.dumps([dict(r) for r in"
    " cur.fetchall()], default=str))\n"
)


def deploys_and_services() -> None:
    r = requests.get(f"{BASE}/services?limit=20", headers=H, timeout=60)
    print("SERVICES HTTP", r.status_code)
    for it in (r.json() or []):
        s = it.get("service") or it
        repo = s.get("repo")
        print("  ", s.get("id"), "|", s.get("type"), "|", s.get("name"),
              "| branch=", s.get("branch"),
              "| repo=", repo.get("url") if isinstance(repo, dict) else repo)
    r = requests.get(f"{BASE}/services/{SERVICE}/deploys?limit=8",
                     headers=H, timeout=60)
    data = r.json()
    if isinstance(data, list):
        items = data
    else:
        items = data.get("deploys") or []
    items = [(x.get("deploy") or x) if isinstance(x, dict) else x
             for x in items]
    print("DEPLOYS HTTP", r.status_code, "n=", len(items))
    for d in items:
        print("  ", d.get("id"), "|", d.get("status"), "| commit=",
              str(d.get("commit"))[:12], "| created=", d.get("createdAt"),
              "| finished=", d.get("finishedAt"))


def db_row() -> None:
    url = ""
    items = requests.get(f"{BASE}/services/{SERVICE}/env-vars?limit=100",
                         headers=H, timeout=60).json()
    for item in items:
        ev = item.get("envVar", item)
        if ev.get("key") == "DATABASE_URL":
            url = (ev.get("value") or "").strip()
    if not url:
        print("no DATABASE_URL")
        return
    try:
        import psycopg
        from psycopg.rows import dict_row
        conn = psycopg.connect(url, row_factory=dict_row, connect_timeout=10)
        with conn, conn.cursor() as cur:
            cur.execute("SELECT pr_key, status, mergeable_state, updated_at "
                        "FROM pr_watch_state ORDER BY pr_key")
            print("DIRECT_ROWS:",
                  json.dumps([dict(r) for r in cur.fetchall()], default=str))
        return
    except Exception as exc:
        print("direct failed:", type(exc).__name__, str(exc)[:100])
    payload = base64.b64encode(INNER.encode()).decode()
    r = requests.post(f"{BASE}/services/{SERVICE}/jobs", headers=H, json={
        "startCommand": f"echo {payload} | base64 -d | python -X utf8 -"},
        timeout=90)
    job = r.json()
    job_id = (job.get("job") or job).get("id")
    print("JOB:", r.status_code, job_id, flush=True)
    if not job_id:
        print(json.dumps(job)[:400])
        return
    for i in range(45):
        time.sleep(4)
        info = requests.get(f"{BASE}/services/{SERVICE}/jobs/{job_id}",
                            headers=H, timeout=60).json()
        j = info.get("job") or info
        state = j.get("status") or j.get("state")
        ll = requests.get(f"{BASE}/logs?ownerId={OWNER}&resource={job_id}",
                          headers=H, timeout=60)
        txt = ""
        try:
            entries = ll.json()
            if isinstance(entries, dict):
                entries = entries.get("logs") or entries.get("entries") or []
            txt = "\n".join(
                (e.get("message") or e.get("line") or str(e))
                if isinstance(e, dict) else str(e) for e in entries)
        except Exception:
            pass
        if "PR_WATCH_ROWS" in txt:
            for line in txt.splitlines():
                if "PR_WATCH_ROWS" in line:
                    print(line.strip())
            return
        if state and str(state).lower() in {"succeeded", "failed",
                                            "canceled", "success",
                                            "completed"}:
            print("JOB STATE:", state)
            for line in txt.splitlines()[-20:]:
                print("  |", line[:300])
            return
        if i % 5 == 0:
            print(f"  poll {i}: state={state}", flush=True)
    print("JOB TIMEOUT, state=", state)


if __name__ == "__main__":
    deploys_and_services()
    db_row()
    print("DONE", flush=True)
