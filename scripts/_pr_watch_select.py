# -*- coding: utf-8 -*-
"""Read-only SELECT на pr_watch_state — редовете на Sentinel PR watcher-а.

Никога не отпечатва DATABASE_URL/ключове — само резултатите от SELECT-а.
Опитва DIRECT връзка от тази машина; при отказ (вътрешен Render хост) минава
през one-off Render job (същият механизъм като scripts/_guard_row_select.py).

Само SELECT — нито ред се променя.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import time

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVICE = "srv-d9maroe7bikc73adkaug"

INNER = r"""
import json, os, psycopg
from psycopg.rows import dict_row
def q(cur, sql, args=()):
    cur.execute(sql, args)
    return [dict(r) for r in cur.fetchall()]
with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row,
                     connect_timeout=15) as conn, conn.cursor() as cur:
    print("BACKEND: postgres OK")
    print("PR_WATCH_ROWS:", json.dumps(q(cur,
        "SELECT pr_key, status, mergeable_state, updated_at "
        "FROM pr_watch_state ORDER BY pr_key"), default=str))
    print("PR_WATCH_COUNT:", json.dumps(q(cur,
        "SELECT count(*) AS n FROM pr_watch_state"), default=str))
"""


def _key() -> str:
    return open(os.path.join(ROOT, "secrets", "render_api_key.txt"),
                encoding="utf-8").read().strip()


def _env_database_url(key: str) -> str:
    items = requests.get(
        f"https://api.render.com/v1/services/{SERVICE}/env-vars?limit=100",
        headers={"Authorization": "Bearer " + key, "Accept": "application/json"},
        timeout=90).json()
    for item in items:
        ev = item.get("envVar", item)
        if ev.get("key") == "DATABASE_URL":
            return (ev.get("value") or "").strip()
    return ""


def direct_select(url: str) -> bool:
    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError:
        print("psycopg не е наличен локално → опит през Render job")
        return False
    try:
        conn = psycopg.connect(url, row_factory=dict_row, connect_timeout=10)
    except Exception as exc:
        print(f"DIRECT връзка отказа ({type(exc).__name__}: {str(exc)[:120]}) "
              "→ опит през Render job")
        return False
    with conn, conn.cursor() as cur:
        print("BACKEND: postgres OK (direct)")
        cur.execute("SELECT pr_key, status, mergeable_state, updated_at "
                    "FROM pr_watch_state ORDER BY pr_key")
        rows = [dict(r) for r in cur.fetchall()]
        print("PR_WATCH_ROWS:", json.dumps(rows, default=str))
        cur.execute("SELECT count(*) AS n FROM pr_watch_state")
        print("PR_WATCH_COUNT:",
              json.dumps([dict(r) for r in cur.fetchall()], default=str))
    return True


def job_select() -> None:
    key = _key()
    payload = base64.b64encode(INNER.encode()).decode()
    r = requests.post(
        f"https://api.render.com/v1/services/{SERVICE}/jobs",
        headers={"Authorization": "Bearer " + key,
                 "Accept": "application/json",
                 "Content-Type": "application/json"},
        json={"startCommand": f"echo {payload} | base64 -d | python -X utf8 -"},
        timeout=90)
    job = r.json()
    job_id = (job.get("job") or job).get("id")
    print("JOB:", r.status_code, "id=", job_id)
    if not job_id:
        print(json.dumps(job)[:600])
        sys.exit(1)
    logs = ""
    for _ in range(40):
        time.sleep(5)
        lr = requests.get(
            f"https://api.render.com/v1/services/{SERVICE}/jobs/{job_id}",
            headers={"Authorization": "Bearer " + key,
                     "Accept": "application/json"}, timeout=60)
        info = lr.json()
        job2 = info.get("job") or info
        state = job2.get("status") or job2.get("state")
        ll = requests.get(
            f"https://api.render.com/v1/logs?ownerId={SERVICE}&resource={job_id}",
            headers={"Authorization": "Bearer " + key,
                     "Accept": "application/json"}, timeout=60)
        try:
            entries = ll.json()
            if isinstance(entries, dict):
                entries = entries.get("logs") or entries.get("entries") or []
            logs = "\n".join(
                (e.get("message") or e.get("line") or str(e)) if isinstance(e, dict)
                else str(e) for e in entries)
        except Exception:
            pass
        if state and str(state).lower() in {"succeeded", "failed", "canceled",
                                            "completed", "success"}:
            break
    print("STATE:", state)
    for line in logs.splitlines():
        if "PR_WATCH" in line or "BACKEND" in line:
            print(line.strip())


def main() -> int:
    key = _key()
    url = _env_database_url(key)
    if not url:
        print("DATABASE_URL не е намерен в Render env")
        return 1
    if not direct_select(url):
        job_select()
    return 0


if __name__ == "__main__":
    sys.exit(main())