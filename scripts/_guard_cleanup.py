# -*- coding: utf-8 -*-
"""Стъпка 4 (изчистване): премахване на НАТРУПАНИТЕ c2_reorg_detected дубликати.

Loop-ът (placeholder anchor '000…0' в payment_guards) генерираше събитие на
всеки watch цикъл — 1269+ записа за ЕДИН tx. Те са артефакт на бъга, не
история: оставянето им изкривява by_kind и dashboard-броячите.

Само DELETE върху guard_events (телеметрия) за kind='c2_reorg_detected' И
конкретния tx. payment_guards / payTo / цени / стражи — НЕ се пипат.
Изпълнява се в Render job (вътрешен DB хост).
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
OWNER = "tea-d6n5s3f5r7bs73cq5h30"
TX = "0x22c442992d33a5bd548f36f9a387e5541d4c81be309bff2cd608e277e96f52ab"

INNER = r"""
import json, os, psycopg
from psycopg.rows import dict_row
TX = %r
MODE = os.environ.get("MODE", "delete")
with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row,
                     connect_timeout=15) as conn, conn.cursor() as cur:
    cur.execute("SELECT count(*) AS n FROM guard_events "
                "WHERE kind='c2_reorg_detected'")
    before = cur.fetchone()["n"]
    cur.execute("SELECT count(DISTINCT tx_hash) AS n FROM guard_events "
                "WHERE kind='c2_reorg_detected'")
    txs = cur.fetchone()["n"]
    print("BEFORE:", json.dumps({"c2_reorg_detected": before, "txs": txs}))
    if MODE == "delete":
        cur.execute("DELETE FROM guard_events "
                    "WHERE kind='c2_reorg_detected' AND lower(tx_hash)=%%s",
                    (TX,))
        print("DELETED:", cur.rowcount)
        conn.commit()
    cur.execute("SELECT kind, count(*) AS n FROM guard_events "
                "GROUP BY kind ORDER BY n DESC")
    print("AFTER_BY_KIND:", json.dumps([dict(r) for r in cur.fetchall()]))
    cur.execute("SELECT count(*) AS n FROM payment_guards")
    print("PAYMENT_GUARDS_ROWS_UNTOUCHED:", cur.fetchone()["n"])
""" % TX


def run_job(mode: str) -> str:
    key = open(os.path.join(ROOT, "secrets", "render_api_key.txt"),
               encoding="utf-8").read().strip()
    h = {"Authorization": "Bearer " + key, "Accept": "application/json",
         "Content-Type": "application/json"}
    payload = base64.b64encode(INNER.encode()).decode()
    # MODE передаваме чрез wrapper-а, не чрез env на job-а ( API-то не го
    # поддържа надеждно) — print-ът го чете от околната среда на самата
    # команда.
    cmd = (f"echo {payload} | base64 -d > /tmp/_gc.py && "
           f"MODE={mode} python -X utf8 /tmp/_gc.py")
    r = requests.post(f"https://api.render.com/v1/services/{SERVICE}/jobs",
                      headers=h, json={"startCommand": cmd}, timeout=90)
    job = (r.json().get("job") or r.json())
    job_id = job.get("id")
    print(f"JOB[{mode}]: {r.status_code} id={job_id}")
    if not job_id:
        print(json.dumps(job)[:600])
        sys.exit(1)
    state = None
    for _ in range(40):
        time.sleep(5)
        jobs = requests.get(
            f"https://api.render.com/v1/services/{SERVICE}/jobs?limit=10",
            headers=h, timeout=60).json()
        jobs = [j.get("job", j) for j in
                (jobs if isinstance(jobs, list) else jobs.get("jobs", []))]
        mine = [j for j in jobs if j.get("id") == job_id]
        if mine:
            state = mine[0].get("status")
            if state in ("succeeded", "failed", "canceled"):
                break
    print("STATE:", state)
    logs = requests.get(
        "https://api.render.com/v1/logs"
        f"?limit=200&resource={job_id}&ownerId={OWNER}", headers=h, timeout=60)
    try:
        entries = logs.json().get("logs", [])
        out = "\n".join(e.get("message", "") for e in entries)
    except Exception:
        out = logs.text
    # Само редовете, които нашият скрипт е печатал (командният echo е шум).
    for line in out.splitlines():
        if line.startswith(("BEFORE:", "DELETED:", "AFTER_BY_KIND:",
                            "PAYMENT_GUARDS_ROWS_UNTOUCHED:")):
            print(line)
    return state or ""


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "delete"
    assert mode in ("delete", "select"), mode
    if run_job(mode) != "succeeded":
        sys.exit(1)
