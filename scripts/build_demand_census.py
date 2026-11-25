# -*- coding: utf-8 -*-
"""Build the x402 demand census snapshot from the production ledger.

WHAT THIS IS FOR. `GET /api/v1/demand-census` is a paid route that serves a
document about the DEMAND side of this service: every user agent that ever
reached our paywall, when it first and last arrived, how often it was challenged
and delivered, and whether it was ever associated with a settled payment —
alongside the aggregate counts, the money, the credential attempts, and the REAL
window the source data covers. `docs/X402_DEMAND_CENSUS.md` publishes the
aggregate; the per-agent table is what a buyer pays $0.25 for.

WHY IT IS BUILT OFFLINE. Counting it per request would mean three full
aggregates over `request_log` (1.2M rows in the retention window) on every paid
call, on a 0.1-CPU instance — the exact reads `scripts/inbound_traffic_audit.py`
measures in tens of seconds. So the route reads a file and this script is the
only thing that writes it.

READ PATH: this reuses the established read-only job path rather than inventing
one. It posts a one-off job to the Render service through
`secrets/render_api_key.txt` (the same mechanism as
`scripts/inbound_traffic_audit.py` and `scripts/evidence_packet.py`), the job
runs inside the service with `DATABASE_URL` and `psycopg`, and it returns its
answer through the job's OWN logs. EVERY STATEMENT IS A SELECT. Nothing here
writes to the database, and no key value is ever printed.

That transport needed one addition, and it is not cosmetic: the log viewer
truncates a line at 100,000 characters, and a row per agent is the one payload
in this repository that is bigger than that. The first real run died on
`Unterminated string starting at ... char 99991` — a truncated document, sold
for $0.25. So the job deflates and chunks its answer and this script
re-assembles it; see `_db`.

THE ONE THING THAT IS NOT A PROOF, AND IS NOT PRESENTED AS ONE. `ever_paid`
says an agent was ASSOCIATED with a settled payment. A request-log row carries
no wallet, so the two ends cannot be joined exactly; what can be measured is
that an agent received a 200 on the SAME path within 90 seconds of a settled
credential (`payment_attempts`, which begins 2026-11-08) or of a guard's
`delivered_at` (`payment_guards`, when that table is present). That is a
necessary condition, not an identity, and the document says so in `method`.

WINDOWS ARE MEASURED, NEVER ASSUMED. `request_log` retains 30 days,
`payment_attempts` only starts on 08.11.2026 and `onchain_sales` goes back to
02.09 — three different spans, so each is reported as MIN/MAX of the rows
actually found rather than as "30 days".

Usage:
    python scripts/build_demand_census.py                 # write snapshots/demand_census.json
    python scripts/build_demand_census.py --print         # ... and print the document
    python scripts/build_demand_census.py --dry-run       # print the SQL, call nothing
    python scripts/build_demand_census.py --out other.json
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import zlib
from datetime import datetime, timezone

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVICE = os.environ.get("RENDER_SERVICE_ID", "srv-d9maroe7bikc73adkaug")

# `snapshots/`, NOT `data/`. The snapshot is a deliverable that has to reach the
# running service; `.gitignore` treats `data/` as local runtime state, so a
# snapshot written there never leaves the machine that built it and the route
# answers 503 forever. See the same reasoning at _DEMAND_CENSUS_SNAPSHOT_PATH.
DEFAULT_OUT = os.path.join(ROOT, "snapshots", "demand_census.json")

#: How close a delivered 200 must sit to a settled credential to be called an
#: association. Wide enough for a minute boundary or a slow facilitator, narrow
#: enough that two unrelated events on one path are not stitched together.
MATCH_WINDOW = "90 seconds"

#: The label used for a request that carried no user agent at all. A row with an
#: empty name is still a row, and dropping it would make the totals disagree
#: with the ledger.
NO_AGENT = "(none)"


def paid_paths() -> list:
    """Every path the paywall charges for, from main's own declaration.

    Read from the single source of truth rather than retyped here: the whole
    point of the `challenged`/`delivered` columns is that they count the paid
    routes, and a second hand-kept list would eventually count a different set.
    """
    os.environ.setdefault("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    sys.path.insert(0, ROOT)
    import main

    return sorted(main.X402_PAID_ENDPOINTS)


def _sql_array(values) -> str:
    """A SQL ARRAY literal. Values are our own route paths, quoted defensively."""
    quoted = ", ".join("'" + str(v).replace("'", "''") + "'" for v in values)
    return "ARRAY[%s]::text[]" % quoted


def queries(paths) -> dict:
    """Every statement, name -> SELECT. There is no write anywhere in this map."""
    paid = _sql_array(paths)
    served = ("SELECT COALESCE(NULLIF(user_agent, ''), '%s') AS ua, path, "
              "ts::timestamptz AS t FROM request_log "
              "WHERE status_code = 200 AND path = ANY(%s)" % (NO_AGENT, paid))
    window_join = ("s.t >= p.t - INTERVAL '%s' AND s.t <= p.t + INTERVAL '%s'"
                   % (MATCH_WINDOW, MATCH_WINDOW))
    # ONE STATEMENT PER TABLE, and that is a correctness rule rather than a
    # style one. These ledgers are LIVE — the service takes ~30,000 requests a
    # day — so two statements about one table do not agree to the row, and the
    # first real run of this generator proved it: it counted `request_log` twice
    # and the document's total was three requests short of the sum of its own
    # per-agent rows. Every count and every window below therefore comes from
    # the SAME rows it describes, so a buyer can re-add the rows and land on the
    # headline exactly.
    return {
        # `SUM(COUNT(*)) OVER ()` is the grand total in the same pass as the
        # groups, which is what makes the rows add up to the total by
        # construction rather than by luck.
        "agents": (
            "SELECT COALESCE(NULLIF(user_agent, ''), '%s') AS user_agent, "
            "COUNT(*) AS requests, MIN(ts) AS first_seen, MAX(ts) AS last_seen, "
            "COUNT(*) FILTER (WHERE status_code = 402 AND path = ANY(%s)) "
            "AS challenged, "
            "COUNT(*) FILTER (WHERE status_code = 200 AND path = ANY(%s)) "
            "AS delivered, "
            "SUM(COUNT(*)) OVER () AS total_requests "
            "FROM request_log GROUP BY 1" % (NO_AGENT, paid, paid)),

        "payments_by_class": (
            "SELECT COALESCE(payer_class, '') AS payer_class, "
            "COALESCE(payer_label, '') AS payer_label, "
            "COUNT(*) AS n, SUM(amount_usdc) AS usdc, "
            "MIN(ts) AS first_ts, MAX(ts) AS last_ts "
            "FROM onchain_sales GROUP BY 1, 2 ORDER BY 3 DESC"),

        "attempts_by_outcome": (
            "SELECT outcome, COUNT(*) AS n, COUNT(DISTINCT payer) AS payers, "
            "MIN(ts) AS first_ts, MAX(ts) AS last_ts "
            "FROM payment_attempts GROUP BY 1 ORDER BY 2 DESC"),

        "attempts_payers": (
            "SELECT COUNT(DISTINCT payer) AS payers FROM payment_attempts"),

        # The association, not the proof — see the module docstring. A settled
        # credential names the PATH it settled for, so the two sides can be
        # compared path-to-path and then by time.
        "agents_paid_attempts": (
            "WITH served AS (%s), settled AS ("
            "SELECT path, ts::timestamptz AS t FROM payment_attempts "
            "WHERE outcome = 'settled') "
            "SELECT s.ua AS user_agent, COUNT(*) AS matches "
            "FROM served s JOIN settled p ON p.path = s.path AND %s "
            "GROUP BY 1" % (served, window_join)),
    }


def guards_query(paths) -> str:
    """The `payment_guards` association, which a deployment may not have.

    Kept in its own statement — rather than inlined into `queries` — so a table
    that is missing is a recorded fact instead of a failed run: the generator
    names the sources it actually had in `method`, because "no agent ever paid"
    and "we could not see the payment half of the ledger" are very different
    answers to a buyer, and only one of them is about the market.
    """
    paid = _sql_array(paths)
    served = ("SELECT COALESCE(NULLIF(user_agent, ''), '%s') AS ua, path, "
              "ts::timestamptz AS t FROM request_log "
              "WHERE status_code = 200 AND path = ANY(%s)" % (NO_AGENT, paid))
    return ("WITH served AS (%s), guards AS ("
            "SELECT endpoint AS path, delivered_at::timestamptz AS t "
            "FROM payment_guards WHERE delivered_at IS NOT NULL) "
            "SELECT s.ua AS user_agent, COUNT(*) AS matches "
            "FROM served s JOIN guards p ON p.path = s.path "
            "AND s.t >= p.t - INTERVAL '%s' AND s.t <= p.t + INTERVAL '%s' "
            "GROUP BY 1" % (served, MATCH_WINDOW, MATCH_WINDOW))


def _key() -> str:
    with open(os.path.join(ROOT, "secrets", "render_api_key.txt"),
              encoding="utf-8") as handle:
        return handle.read().strip()


def assert_select_only(sql: dict) -> None:
    """Refuse to send anything that is not a SELECT.

    The read-only guarantee is worth more than a comment: every statement here
    is checked before it crosses the network, so a later edit that adds an
    UPDATE, a DELETE or an `INSERT ... SELECT` fails locally instead of running
    against production. `WITH` is allowed because a CTE is a SELECT.
    """
    for name, statement in sql.items():
        head = statement.lstrip().split(None, 1)[0].upper() if statement.strip() else ""
        if head not in ("SELECT", "WITH"):
            raise SystemExit(
                "refusing to run %s: every statement must be a SELECT, got %r"
                % (name, head))


def _db(sql: dict, service: str = SERVICE) -> dict:
    """Run SELECTs through the established one-off Render job (read-only).

    The same shape as `scripts/inbound_traffic_audit.py`, including the reason
    its poll loop does not stop at a terminal job state: the job reaches
    `succeeded` BEFORE its last log line is queryable, and stopping there loses
    a payload that was written correctly.

    WHY THE PAYLOAD ARRIVES COMPRESSED AND IN CHUNKS. The transport is one log
    LINE, and the log viewer truncates a line at 100,000 characters. The other
    two audit scripts never noticed because their answers are summaries; this
    document's whole product is a row per agent, so it passes that ceiling —
    measured on the first real run, 24.11.2026:

        json.decoder.JSONDecodeError: Unterminated string starting at:
        line 1 column 99992 (char 99991)

    A truncated line is not a small failure: it is a missing document sold for
    $0.25. So the job deflates the JSON, base64s it, and prints it as numbered
    chunks the reader re-assembles, which keeps the payload bounded by the DATA
    rather than by the log viewer.
    """
    assert_select_only(sql)
    inner = '''
import base64, json, os, zlib, psycopg
from psycopg.rows import dict_row
SQL = __SQL__
CHUNK = 40000
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
blob = base64.b64encode(zlib.compress(
    json.dumps(out, default=str, separators=(",", ":")).encode(), 6)).decode()
parts = [blob[i:i + CHUNK] for i in range(0, len(blob), CHUNK)] or [""]
for index, part in enumerate(parts, 1):
    print("DC %d/%d %s" % (index, len(parts), part))
'''
    inner = inner.replace("__SQL__", json.dumps(sql))
    payload = base64.b64encode(inner.encode()).decode()
    key = _key()
    created = requests.post(
        "https://api.render.com/v1/services/%s/jobs" % service,
        headers={"Authorization": "Bearer " + key, "Accept": "application/json",
                 "Content-Type": "application/json"},
        json={"startCommand": "echo %s | base64 -d | python -X utf8 -" % payload},
        timeout=90)
    job = created.json()
    job_id = (job.get("job") or job).get("id")
    if not job_id:
        raise SystemExit("job create failed: " + json.dumps(job)[:300])

    terminal_seen = 0
    chunks = {}
    expected = None
    for _ in range(60):
        time.sleep(5)
        # A POLL THAT DIES ON ONE SLOW RESPONSE IS A POLL THAT DIES. This loop
        # asks the Render API ~100 times over five minutes, and a single 60s
        # ReadTimeout did kill a real run on 24.11.2026 — after the job had
        # completed and printed its payload, which is the worst moment to throw
        # it away. A transport error is a reason to ask again, not to stop.
        try:
            info = requests.get(
                "https://api.render.com/v1/services/%s/jobs/%s"
                % (service, job_id),
                headers={"Authorization": "Bearer " + key,
                         "Accept": "application/json"}, timeout=60).json()
            logs = requests.get(
                "https://api.render.com/v1/logs?ownerId=%s&resource=%s"
                % (service, job_id),
                headers={"Authorization": "Bearer " + key,
                         "Accept": "application/json"}, timeout=60).json()
        except requests.RequestException as exc:
            print("warning: poll failed (%s); retrying" % type(exc).__name__,
                  file=sys.stderr)
            continue
        state = str((info.get("job") or info).get("status")
                    or (info.get("job") or info).get("state") or "").lower()
        entries = logs if isinstance(logs, list) else (
            logs.get("logs") or logs.get("entries") or [])
        for entry in entries:
            line = ((entry.get("message") or entry.get("line") or str(entry))
                    if isinstance(entry, dict) else str(entry))
            parsed = _chunk(line)
            if parsed is not None:
                index, total, part = parsed
                chunks[index] = part
                expected = total
        if expected is not None and len(chunks) >= expected:
            return _decode_chunks(chunks, expected, job_id)
        if state in {"succeeded", "failed", "canceled"}:
            # The job is over and its logs have stopped changing — but a
            # terminal state is not proof that the LAST line is queryable yet,
            # so read a few more times before giving up. See the docstring.
            terminal_seen += 1
            if terminal_seen >= 4:
                break
    raise SystemExit(
        "no complete DC payload from job %s (got %d of %s chunks)"
        % (job_id, len(chunks), expected))


def _chunk(line: str):
    """`DC <index>/<total> <base64>` as (index, total, part), else None."""
    if not line.startswith("DC "):
        return None
    head, _, part = line[3:].partition(" ")
    index, _, total = head.partition("/")
    if not index.isdigit() or not total.isdigit():
        return None
    return int(index), int(total), part.strip()


def _decode_chunks(chunks: dict, total: int, job_id: str) -> dict:
    """Re-assemble, inflate and parse the payload the job chunked."""
    missing = [i for i in range(1, total + 1) if i not in chunks]
    if missing:
        raise SystemExit("job %s never printed chunks %s" % (job_id, missing))
    blob = "".join(chunks[i] for i in range(1, total + 1))
    try:
        return json.loads(zlib.decompress(base64.b64decode(blob)))
    except (ValueError, zlib.error) as exc:
        raise SystemExit(
            "job %s printed %d chunk(s) that do not decode (%s); the log "
            "viewer truncates long lines, so this is a transfer failure rather "
            "than a query failure" % (job_id, total, type(exc).__name__))


def _rows(rows: dict, name: str) -> list:
    """The rows of one query, or [] when the query failed or the table is gone.

    A failed statement is a fact about the deployment (a table this build does
    not have), not a reason to write a document with invented numbers in it —
    so the caller records what was missing and the figures that depend on it
    stay empty.
    """
    value = rows.get(name)
    if not isinstance(value, list):
        return []
    return [row for row in value if isinstance(row, dict) and "error" not in row]


def _failed(rows: dict, name: str):
    value = rows.get(name)
    if isinstance(value, list) and value and isinstance(value[0], dict):
        return value[0].get("error")
    return None


def _instant(value):
    """One ledger timestamp as an aware datetime, or None if it is not one.

    Two formats reach this function because the ledger is not uniform: `ts` is
    text in `YYYY-MM-DD HH:MM:SS` form in most tables and psycopg hands back a
    real datetime where the column is a timestamp. Both are normalised to UTC
    before a span is measured, so a day count cannot drift with the reader's
    timezone.
    """
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("T", " ")
    if text.endswith("Z"):
        text = text[:-1]
    for fmt in ("%Y-%m-%d %H:%M:%S.%f%z", "%Y-%m-%d %H:%M:%S%z",
                "%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S"):
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        return (parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc))
    return None


def _window(rows: list, count_key: str, output_key: str = "") -> dict:
    """A measured window over a row set, never an assumed one.

    The count and the span come from the SAME rows, which is the whole point:
    `totals.requests` and the `agents` list must add up to each other, and a
    window computed from a second query would describe a slightly different
    ledger — see the note on `queries`. MIN/MAX are taken on the raw values
    because every row of one column arrives in one format, and parsed only to
    turn the span into a number of days.
    """
    total = sum(int(row.get(count_key) or 0) for row in rows)
    firsts = [row.get("first_ts") for row in rows if row.get("first_ts")]
    lasts = [row.get("last_ts") for row in rows if row.get("last_ts")]
    first = min(firsts) if firsts else None
    last = max(lasts) if lasts else None
    start, end = _instant(first), _instant(last)
    return {output_key or count_key: total,
            "first_ts": None if first is None else str(first),
            "last_ts": None if last is None else str(last),
            "days": (round((end - start).total_seconds() / 86400.0, 2)
                     if start and end else None)}


def build_document(rows: dict, paths, generated_at: str, guard_error=None) -> dict:
    """Shape the query results into the document the paid route serves.

    Pure: it takes query rows and returns the payload, so the shape can be
    tested against fixtures without touching production and without a database.
    """
    agent_rows = _rows(rows, "agents")
    paid_by_attempts = {r["user_agent"]: int(r.get("matches") or 0)
                        for r in _rows(rows, "agents_paid_attempts")}
    paid_by_guards = {r["user_agent"]: int(r.get("matches") or 0)
                      for r in _rows(rows, "agents_paid_guards")}

    agents = []
    for row in agent_rows:
        name = row.get("user_agent") or NO_AGENT
        agents.append({
            "user_agent": name,
            "first_seen": None if row.get("first_seen") is None
            else str(row["first_seen"]),
            "last_seen": None if row.get("last_seen") is None
            else str(row["last_seen"]),
            "requests": int(row.get("requests") or 0),
            "challenged": int(row.get("challenged") or 0),
            "delivered": int(row.get("delivered") or 0),
            "ever_paid": bool(paid_by_attempts.get(name)
                              or paid_by_guards.get(name)),
        })
    agents.sort(key=lambda a: (-a["requests"], a["user_agent"]))

    class_rows = _rows(rows, "payments_by_class")
    by_class = [{
        "payer_class": row.get("payer_class") or "",
        "payer_label": row.get("payer_label") or "",
        "count": int(row.get("n") or 0),
        "total_usdc": round(float(row.get("usdc") or 0), 6),
    } for row in class_rows]
    by_class.sort(key=lambda row: (-row["count"], row["payer_class"]))

    outcome_rows = _rows(rows, "attempts_by_outcome")
    by_outcome = [{
        "outcome": row.get("outcome") or "",
        "count": int(row.get("n") or 0),
        "distinct_payers": int(row.get("payers") or 0),
    } for row in outcome_rows]

    payer_rows = _rows(rows, "attempts_payers")
    distinct_payers = int(payer_rows[0].get("payers") or 0) if payer_rows else 0

    sources = ["settled credentials in payment_attempts"]
    if guard_error:
        sources.append("payment_guards UNAVAILABLE (%s)" % str(guard_error)[:80])
    elif "agents_paid_guards" not in rows:
        sources.append("payment_guards not queried")
    elif _rows(rows, "agents_paid_guards"):
        sources.append("payment_guards.delivered_at")
    else:
        sources.append("payment_guards present, no delivered_at match")

    # Each window is computed from the SAME rows the section it describes was
    # built from, so the document cannot contradict itself. See the note on
    # `queries` for the three-request drift that taught us this.
    request_window = _window(
        [{"first_ts": a["first_seen"], "last_ts": a["last_seen"],
          "requests": a["requests"]} for a in agents], "requests")
    sales_window = _window(class_rows, "n", "payments")
    attempts_window = _window(outcome_rows, "n", "attempts")

    return {
        "generated_at": generated_at,
        "window": {
            "requests": request_window,
            "sales": sales_window,
            "attempts": attempts_window,
        },
        "totals": {
            # The sum of the rows in `agents`, by construction — a buyer who
            # re-adds the list lands here. The ledger is live, so a second
            # COUNT(*) could differ by the requests that arrived in between, and
            # a document that disagrees with itself is worse than a count taken
            # one statement earlier.
            "requests": request_window["requests"],
            "distinct_user_agents": len(agents),
            "agents_challenged_on_paid_routes":
                sum(1 for a in agents if a["challenged"] > 0),
            "agents_delivered_on_paid_routes":
                sum(1 for a in agents if a["delivered"] > 0),
            "agents_ever_paid": sum(1 for a in agents if a["ever_paid"]),
        },
        "payments": {
            "count": sum(row["count"] for row in by_class),
            "total_usdc": round(sum(row["total_usdc"] for row in by_class), 6),
            "by_payer_class": by_class,
        },
        "attempts": {
            "count": sum(row["count"] for row in by_outcome),
            "distinct_payers": distinct_payers,
            "by_outcome": by_outcome,
        },
        "agents": agents,
        "method": (
            "Read-only SELECTs over the production ledger (request_log, "
            "onchain_sales, payment_attempts), run offline by "
            "scripts/build_demand_census.py; this route only serves the file. "
            "%d paid paths, so `challenged`/`delivered` count 402/200 on any "
            "path in main.X402_PAID_ENDPOINTS or its aliases. `totals` is "
            "derived from the `agents` list, so the rows can be re-added to "
            "check it. `ever_paid` is an ASSOCIATION, not a proof — a request "
            "row carries no wallet, so it is set when the agent got a 200 on "
            "the SAME path within 90 seconds of a settled credential (%s). "
            "Every window is MIN/MAX of the rows actually found, never an "
            "assumed 30 days." % (len(paths), "; ".join(sources))),
    }


def main_cli(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", default=DEFAULT_OUT,
                        help="where to write the snapshot (default %s)" % DEFAULT_OUT)
    parser.add_argument("--print", dest="show", action="store_true",
                        help="print the document to stdout as well")
    parser.add_argument("--dry-run", action="store_true",
                        help="print the SQL and the output path, call nothing")
    parser.add_argument("--service", default=SERVICE,
                        help="Render service id to run the read job on")
    args = parser.parse_args(argv)

    paths = paid_paths()
    sql = queries(paths)
    sql["agents_paid_guards"] = guards_query(paths)

    if args.dry_run:
        print("paid paths (%d): %s" % (len(paths), ", ".join(paths)))
        print("output: %s" % args.out)
        for name, statement in sql.items():
            print("\n-- %s\n%s" % (name, statement))
        return 0

    raw = _db(sql, service=args.service)
    guard_error = _failed(raw, "agents_paid_guards")
    if guard_error:
        print("warning: payment_guards association unavailable: %s" % guard_error,
              file=sys.stderr)

    document = build_document(
        raw, paths,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        guard_error=guard_error)

    directory = os.path.dirname(os.path.abspath(args.out))
    if directory:
        os.makedirs(directory, exist_ok=True)
    # newline="\n" and explicit UTF-8: the Windows default would write CRLF and
    # the snapshot is compared byte-for-byte by the deployment, not by a person.
    with open(args.out, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(document, handle, ensure_ascii=False, indent=2, sort_keys=False)
        handle.write("\n")

    window = document["window"]
    print("wrote %s (%d bytes)" % (args.out, os.path.getsize(args.out)))
    print("  requests   : %d over %s -> %s (%s days)"
          % (window["requests"]["requests"], window["requests"]["first_ts"],
             window["requests"]["last_ts"], window["requests"]["days"]))
    print("  sales      : %d over %s -> %s"
          % (window["sales"]["payments"], window["sales"]["first_ts"],
             window["sales"]["last_ts"]))
    print("  attempts   : %d over %s -> %s"
          % (window["attempts"]["attempts"], window["attempts"]["first_ts"],
             window["attempts"]["last_ts"]))
    print("  agents     : %d rows, %d challenged, %d delivered, %d ever paid"
          % (document["totals"]["distinct_user_agents"],
             document["totals"]["agents_challenged_on_paid_routes"],
             document["totals"]["agents_delivered_on_paid_routes"],
             document["totals"]["agents_ever_paid"]))
    if args.show:
        print(json.dumps(document, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main_cli())
