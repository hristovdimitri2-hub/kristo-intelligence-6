# -*- coding: utf-8 -*-
"""Стъпка 1 (read-only): SELECT на payment_guards реда зад c2_reorg_detected loop-а.

Никога не отпечатва DATABASE_URL/ключове — само резултатите от SELECT-ите.
Опитва DIRECT връзка от тази машина; при отказ (вътрешен Render хост) минава
през one-off Render job (същият механизъм като scripts/render_e2e.py gateway).

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
TX = "0x22c442992d33a5bd548f36f9a387e5541d4c81be309bff2cd608e277e96f52ab"

INNER = r"""
import json, os, psycopg
from psycopg.rows import dict_row
TX = %r
def q(cur, sql, args=()):
    cur.execute(sql, args)
    return [dict(r) for r in cur.fetchall()]
with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row,
                     connect_timeout=15) as conn, conn.cursor() as cur:
    print("BACKEND: postgres OK")
    print("ROW:", json.dumps(q(cur,
        "SELECT tx_hash, endpoint, payer, amount_usdc, consumed_at, "
        "block_number, block_hash FROM payment_guards WHERE lower(tx_hash)=%%s",
        (TX,)), default=str))
    print("ALL_CLAIMS:", json.dumps(q(cur,
        "SELECT tx_hash, endpoint, block_number, block_hash, consumed_at "
        "FROM payment_guards ORDER BY consumed_at DESC LIMIT 30"), default=str))
    print("EVENTS_FOR_TX:", json.dumps(q(cur,
        "SELECT kind, count(*) AS n, min(ts) AS first_ts, max(ts) AS last_ts "
        "FROM guard_events WHERE lower(tx_hash)=%%s GROUP BY kind", (TX,)),
        default=str))
    print("REORG_TOTAL:", json.dumps(q(cur,
        "SELECT count(*) AS n, count(DISTINCT tx_hash) AS txs "
        "FROM guard_events WHERE kind='c2_reorg_detected'"), default=str))
""" % TX


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
        for label, sql, args in [
            ("ROW",
             "SELECT tx_hash, endpoint, payer, amount_usdc, consumed_at, "
             "block_number, block_hash FROM payment_guards "
             "WHERE lower(tx_hash) = %s", (TX,)),
            ("ALL_CLAIMS",
             "SELECT tx_hash, endpoint, block_number, block_hash, consumed_at "
             "FROM payment_guards ORDER BY consumed_at DESC LIMIT 30", ()),
            ("EVENTS_FOR_TX",
             "SELECT kind, count(*) AS n, min(ts) AS first_ts, max(ts) AS last_ts "
             "FROM guard_events WHERE lower(tx_hash) = %s GROUP BY kind", (TX,)),
            ("REORG_TOTAL",
             "SELECT count(*) AS n, count(DISTINCT tx_hash) AS txs "
             "FROM guard_events WHERE kind = 'c2_reorg_detected'", ()),
        ]:
            cur.execute(sql, args)
            rows = [dict(r) for r in cur.fetchall()]
            print(f"{label}: {json.dumps(rows, default=str)}")
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
            f"https://api.render.com/v1/jobs/{job_id}",
            headers={"Authorization": "Bearer " + key,
                     "Accept": "application/json"}, timeout=60)
        info = lr.json()
        job2 = info.get("job") or info
        state = job2.get("status") or job2.get("state")
        ll = requests.get(
            f"https://api.render.com/v1/jobs/{job_id}/logs",
            headers={"Authorization": "Bearer " + key,
                     "Accept": "application/json"}, timeout=60)
        try:
            entries = ll.json()
            if isinstance(entries, dict):
                entries = entries.get("logs") or entries.get("entries") or []
            logs = "\n".join(
                str(e.get("message", e)) if isinstance(e, dict) else str(e)
                for e in entries)
        except Exception:
            pass
        if state in ("succeeded", "failed", "canceled"):
            print("STATE:", state)
            break
    print("--- JOB LOGS ---")
    print(logs or "(празни логове)")


if __name__ == "__main__":
    url = _env_database_url(_key())
    if not url:
        sys.exit("няма DATABASE_URL в Render env")
    if not direct_select(url):
        job_select()
