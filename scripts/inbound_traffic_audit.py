# -*- coding: utf-8 -*-
"""Inbound traffic audit — STRICTLY READ-ONLY (SELECTs only).

Answers the question the dashboard cannot: WHO has actually called this service,
from where, and when — and, separately, who actually PAID.

`request_log` keeps 30 days, so round 1 reports the table's real span rather than
assuming one. Round 2 joins the money table to the request ledger by time, so a
sale can be attributed to the user agent that made it.

Usage:
    python scripts/inbound_traffic_audit.py          # round 1: who calls us
    python scripts/inbound_traffic_audit.py --set2   # round 2: who pays us

Emits ONE JSON on stdout. No writes, no deploy, no key values printed.
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
SERVICE = os.environ.get("RENDER_SERVICE_ID", "srv-d9maroe7bikc73adkaug")

# Round 1 — the shape of the demand. Every statement is a SELECT.
ROUND1 = {
    "span": "SELECT COUNT(*) AS rows, MIN(ts) AS first_ts, MAX(ts) AS last_ts FROM request_log",

    "by_source": "SELECT source, COUNT(*) AS n, MIN(ts) AS first_ts, MAX(ts) AS last_ts "
                 "FROM request_log GROUP BY source ORDER BY n DESC",

    "per_day": "SELECT substr(ts, 1, 10) AS day, COUNT(*) AS n "
               "FROM request_log GROUP BY 1 ORDER BY 1 DESC",

    "per_day_source": "SELECT substr(ts, 1, 10) AS day, source, COUNT(*) AS n "
                      "FROM request_log GROUP BY 1, 2 ORDER BY 1 DESC, 3 DESC",

    "top_user_agents": "SELECT user_agent, COUNT(*) AS n, MIN(ts) AS first_ts, MAX(ts) AS last_ts "
                       "FROM request_log GROUP BY user_agent ORDER BY n DESC LIMIT 30",

    # The commercial question: does anyone reach a paid route other than us?
    "challenged_by_agent": "SELECT user_agent, COUNT(*) AS n, MIN(ts) AS first_ts, MAX(ts) AS last_ts "
                           "FROM request_log WHERE path LIKE '/api/%%' AND status_code = 402 "
                           "GROUP BY user_agent ORDER BY n DESC LIMIT 30",

    "delivered_by_agent": "SELECT user_agent, COUNT(*) AS n, MIN(ts) AS first_ts, MAX(ts) AS last_ts "
                          "FROM request_log WHERE path LIKE '/api/%%' AND status_code = 200 "
                          "GROUP BY user_agent ORDER BY n DESC LIMIT 30",

    "referers": "SELECT referer, COUNT(*) AS n FROM request_log "
                "WHERE referer IS NOT NULL AND referer <> '' "
                "GROUP BY referer ORDER BY n DESC LIMIT 30",

    "top_paths": "SELECT path, COUNT(*) AS n FROM request_log GROUP BY path ORDER BY n DESC LIMIT 25",

    "sales": "SELECT COUNT(*) AS n, MIN(ts) AS first_ts, MAX(ts) AS last_ts FROM onchain_sales",
}

# Round 2 — the money and the two funnels (API and MCP).
#
# WHY THERE IS NO LATERAL JOIN HERE. The first attempt at attribution joined every
# sale to the nearest request in a 6-minute window. That is a nested loop over a
# 1.2M-row table per sale, and the job was killed before it printed anything: an
# audit that times out teaches nothing. The cheap shape — read the money rows, read
# the status mix, compare by eye — answers the same question in seconds.
ROUND2 = {
    # Read the raw rows rather than assume a schema: this table moved once already.
    "sales_sample": "SELECT * FROM onchain_sales ORDER BY ts DESC LIMIT 30",

    "sales_per_month": "SELECT substr(ts, 1, 7) AS month, COUNT(*) AS n, SUM(amount_usdc) AS usdc "
                       "FROM onchain_sales GROUP BY 1 ORDER BY 1 DESC",

    "sales_per_day": "SELECT substr(ts, 1, 10) AS day, COUNT(*) AS n FROM onchain_sales "
                     "GROUP BY 1 ORDER BY 1 DESC LIMIT 90",

    # The API funnel, by outcome rather than by agent: which routes are challenged
    # and which are delivered, and how few of each ever become a payment.
    "api_status_by_path": "SELECT path, status_code, COUNT(*) AS n FROM request_log "
                          "WHERE path LIKE '/api/%%' GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 40",

    # The MCP funnel. `/mcp` is the second-busiest path on the service.
    "mcp_status_by_path": "SELECT path, status_code, COUNT(*) AS n FROM request_log "
                          "WHERE path LIKE '/mcp%%' GROUP BY 1, 2 ORDER BY 3 DESC LIMIT 20",

    "mcp_by_agent": "SELECT user_agent, COUNT(*) AS n, MAX(ts) AS last_ts FROM request_log "
                    "WHERE path LIKE '/mcp%%' GROUP BY 1 ORDER BY 2 DESC LIMIT 20",

    # How many DISTINCT third parties ever reach a paywall? A single crawler with a
    # loop looks like demand until you count the distinct agents behind it.
    "distinct_agents_challenged": "SELECT COUNT(DISTINCT user_agent) AS n FROM request_log "
                                  "WHERE path LIKE '/api/%%' AND status_code = 402",

    "distinct_agents_delivered": "SELECT COUNT(DISTINCT user_agent) AS n FROM request_log "
                                 "WHERE path LIKE '/api/%%' AND status_code = 200",
}


# Round 3 — the payer identity. `onchain_sales` already carries `payer_class` and
# `payer_label`, so the question "is every sale ours?" has a stored answer and does
# not need to be inferred from receipts.
ROUND3 = {
    "payers": "SELECT payer_class, payer_label, sender, COUNT(*) AS n, "
              "SUM(amount_usdc) AS usdc, MIN(ts) AS first_ts, MAX(ts) AS last_ts "
              "FROM onchain_sales GROUP BY 1, 2, 3 ORDER BY 4 DESC",

    "sources": "SELECT source, COUNT(*) AS n, SUM(amount_usdc) AS usdc, "
               "MIN(ts) AS first_ts, MAX(ts) AS last_ts "
               "FROM onchain_sales GROUP BY 1 ORDER BY 2 DESC",

    "sales_tx": "SELECT ts, tx_hash, amount_usdc, sender, payer_class, payer_label, source "
                "FROM onchain_sales ORDER BY ts DESC LIMIT 200",
}


# Round 4 — what the demand actually IS. 457 distinct user agents reached a paywall;
# if almost all of them are monitors, then the traffic is infrastructure telemetry
# and never was demand. Classify by name and count.
ROUND4 = {
    "tables": "SELECT table_name FROM information_schema.tables "
              "WHERE table_schema = 'public' ORDER BY 1",

    "agent_kinds": "SELECT CASE WHEN user_agent ~* "
                   "'probe|monitor|health|check|index|crawl|scan|uptime|bazaar|discovery|bot|status' "
                   "THEN 'monitor_or_crawler' ELSE 'other' END AS kind, "
                   "COUNT(DISTINCT user_agent) AS agents, COUNT(*) AS requests "
                   "FROM request_log GROUP BY 1 ORDER BY 2 DESC",

    # The same split, restricted to agents that reached a paywall.
    "challenged_kinds": "SELECT CASE WHEN user_agent ~* "
                        "'probe|monitor|health|check|index|crawl|scan|uptime|bazaar|discovery|bot|status' "
                        "THEN 'monitor_or_crawler' ELSE 'other' END AS kind, "
                        "COUNT(DISTINCT user_agent) AS agents, COUNT(*) AS requests "
                        "FROM request_log WHERE path LIKE '/api/%%' AND status_code = 402 "
                        "GROUP BY 1 ORDER BY 2 DESC",

    # The only money that was not ours, in full.
    "external_sales": "SELECT ts, tx_hash, sender, payer_class, payer_label, source, amount_usdc "
                      "FROM onchain_sales WHERE payer_class <> 'own_key' ORDER BY ts DESC LIMIT 100",

    # Total, for one honest number.
    "revenue": "SELECT COUNT(*) AS payments, ROUND(SUM(amount_usdc), 6) AS usdc_total, "
               "COUNT(*) FILTER (WHERE payer_class = 'own_key') AS ours, "
               "ROUND(SUM(amount_usdc) FILTER (WHERE payer_class = 'own_key'), 6) AS usdc_ours "
               "FROM onchain_sales",
}


# Round 5 — THE MISSING MIDDLE. `payment_attempts` sits between the 402 and the
# money: every agent that presented a credential lands there. `request_log` cannot
# say this, because a refusal and a success share a status code shape.
ROUND5 = {
    "attempts_columns": "SELECT column_name, data_type FROM information_schema.columns "
                        "WHERE table_name = 'payment_attempts' ORDER BY ordinal_position",

    "attempts_total": "SELECT COUNT(*) AS n FROM payment_attempts",

    "revenue": "SELECT COUNT(*) AS payments, SUM(amount_usdc) AS usdc_total FROM onchain_sales",

    "revenue_ours": "SELECT COUNT(*) AS payments, SUM(amount_usdc) AS usdc_total "
                    "FROM onchain_sales WHERE payer_class = 'own_key'",

    "guards_columns": "SELECT column_name, data_type FROM information_schema.columns "
                      "WHERE table_name = 'payment_guards' ORDER BY ordinal_position",

    "guard_events_kinds": "SELECT kind, COUNT(*) AS n, MIN(ts) AS first_ts, MAX(ts) AS last_ts "
                          "FROM guard_events GROUP BY 1 ORDER BY 2 DESC LIMIT 25",

    # 135 rows in total — the entire recorded history of anyone presenting a
    # credential to this service. `outcome` separates a refusal from a settlement.
    "attempts_outcomes": "SELECT outcome, COUNT(*) AS n, COUNT(DISTINCT payer) AS payers, "
                         "SUM(amount_usdc) AS usdc, MIN(ts) AS first_ts, MAX(ts) AS last_ts "
                         "FROM payment_attempts GROUP BY 1 ORDER BY 2 DESC",

    "attempts_by_day": "SELECT substr(ts, 1, 10) AS day, COUNT(*) AS n "
                       "FROM payment_attempts GROUP BY 1 ORDER BY 1 DESC LIMIT 60",

    "attempts_recent": "SELECT ts, path, outcome, payer, amount_usdc, detail "
                       "FROM payment_attempts ORDER BY ts DESC LIMIT 40",

    # The failures, in full. If a real buyer tried and the rail refused, this is a
    # lost sale rather than an absence of demand, and the two need separating.
    "attempts_failed": "SELECT ts, path, outcome, payer, amount_usdc, detail, tx_hash "
                       "FROM payment_attempts WHERE outcome <> 'settled' ORDER BY ts DESC LIMIT 60",

    # Every payer we have ever seen try, with their record.
    "attempt_payers": "SELECT payer, COUNT(*) AS tries, "
                      "COUNT(*) FILTER (WHERE outcome = 'settled') AS settled, "
                      "COUNT(*) FILTER (WHERE outcome = 'rejected') AS rejected, "
                      "COUNT(*) FILTER (WHERE outcome = 'settle_failed') AS failed, "
                      "MIN(ts) AS first_ts, MAX(ts) AS last_ts "
                      "FROM payment_attempts GROUP BY 1 ORDER BY 2 DESC",
}


def _key() -> str:
    with open(os.path.join(ROOT, "secrets", "render_api_key.txt"), encoding="utf-8") as fh:
        return fh.read().strip()


def _db(sql: dict) -> dict:
    inner = '''
import json, os, psycopg
from psycopg.rows import dict_row
SQL = __SQL__
out = {}
with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row,
                     connect_timeout=20) as conn, conn.cursor() as cur:
    for name, q in SQL.items():
        try:
            cur.execute(q)
            out[name] = [dict(r) for r in cur.fetchall()]
        except Exception as exc:
            conn.rollback()
            out[name] = [{"error": str(exc)[:300]}]
print("TA " + json.dumps(out, default=str, separators=(",", ":")))
'''
    inner = inner.replace("__SQL__", json.dumps(sql))
    payload = base64.b64encode(inner.encode()).decode()
    k = _key()
    r = requests.post(
        "https://api.render.com/v1/services/%s/jobs" % SERVICE,
        headers={"Authorization": "Bearer " + k, "Accept": "application/json",
                 "Content-Type": "application/json"},
        json={"startCommand": "echo %s | base64 -d | python -X utf8 -" % payload},
        timeout=90)
    job = r.json()
    job_id = (job.get("job") or job).get("id")
    if not job_id:
        raise SystemExit("job create failed: " + json.dumps(job)[:300])

    # The job reaches a terminal state BEFORE its last log line is queryable, so a
    # terminal state is not a reason to stop reading — it is a reason to keep
    # reading. Missing this cost one wasted run: the payload was there all along,
    # one poll after `succeeded`.
    terminal_seen = 0
    for _ in range(60):
        time.sleep(5)
        info = requests.get(
            "https://api.render.com/v1/services/%s/jobs/%s" % (SERVICE, job_id),
            headers={"Authorization": "Bearer " + k, "Accept": "application/json"},
            timeout=60).json()
        j2 = info.get("job") or info
        state = str(j2.get("status") or j2.get("state") or "").lower()
        ll = requests.get(
            "https://api.render.com/v1/logs?ownerId=%s&resource=%s" % (SERVICE, job_id),
            headers={"Authorization": "Bearer " + k, "Accept": "application/json"},
            timeout=60)
        entries = ll.json()
        if isinstance(entries, dict):
            entries = entries.get("logs") or entries.get("entries") or []
        for e in entries:
            line = (e.get("message") or e.get("line") or str(e)) if isinstance(e, dict) else str(e)
            if line.startswith("TA "):
                return json.loads(line[3:])
        if state in {"succeeded", "failed", "canceled"}:
            terminal_seen += 1
            if terminal_seen >= 4:
                break
    raise SystemExit("no TA payload from job " + str(job_id))


def main(argv) -> int:
    if "--set5" in argv:
        sql = ROUND5
    elif "--set4" in argv:
        sql = ROUND4
    elif "--set3" in argv:
        sql = ROUND3
    elif "--set2" in argv:
        sql = ROUND2
    else:
        sql = ROUND1
    data = _db(sql)
    print(json.dumps(data, indent=2, default=str, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

