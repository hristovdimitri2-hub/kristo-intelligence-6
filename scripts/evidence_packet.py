# -*- coding: utf-8 -*-
"""Evidence packet for a paid call — STRICTLY READ-ONLY (SELECTs + public RPC).

Usage:
  python scripts/evidence_packet.py --at "2026-09-23T02:27:03"
  python scripts/evidence_packet.py --request-id <X-Request-Id>

Emits ONE JSON: request / response / acceptance / settlement / linkage.
No writes, no deploy, no key values ever printed.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time

import requests

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SERVICE = "srv-d9maroe7bikc73adkaug"
RPC = "https://mainnet.base.org"
TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
AUTH_USED_TOPIC = "0x98de503528ee59b575ef0c0a2576a82497bfc029a5685b209e9ec333479b10a5"


def _key() -> str:
    with open(os.path.join(ROOT, "secrets", "render_api_key.txt"), encoding="utf-8") as fh:
        return fh.read().strip()


def _db_fetch(at_iso: str) -> dict:
    """SELECTs via the established one-off Render job path (read-only)."""
    inner = '''
import json, os, psycopg
from psycopg.rows import dict_row
AT = __AT__
out = {}
with psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row,
                     connect_timeout=15) as conn, conn.cursor() as cur:
    def q(sql, args=()):
        cur.execute(sql, args)
        return [dict(r) for r in cur.fetchall()]
    out["sales"] = q("SELECT * FROM onchain_sales WHERE ts::timestamptz BETWEEN "
                     "(%s || 'Z')::timestamptz - INTERVAL '45 seconds' AND "
                     "(%s || 'Z')::timestamptz + INTERVAL '45 seconds' ORDER BY ts LIMIT 3",
                     (AT, AT))
    tx = out["sales"][0]["tx_hash"] if out["sales"] else None
    out["claim"] = q("SELECT * FROM payment_guards WHERE lower(tx_hash)=lower(%s)", (tx,)) if tx else []
    out["events"] = q("SELECT ts, kind, endpoint, detail FROM guard_events WHERE tx_hash ILIKE %s ORDER BY ts LIMIT 10", ('%' + tx[-16:] if tx else '%none%',))
    out["requests"] = q("SELECT id, ts, method, path, status_code, user_agent FROM request_log "
                        "WHERE ts::timestamptz BETWEEN (%s || 'Z')::timestamptz - INTERVAL '15 seconds' AND "
                        "(%s || 'Z')::timestamptz + INTERVAL '30 seconds' AND path LIKE '/api/%%' "
                        "ORDER BY ABS(EXTRACT(EPOCH FROM (ts::timestamptz - (%s || 'Z')::timestamptz))) LIMIT 6",
                        (AT, AT, AT))
    print("EP " + json.dumps(out, default=str, separators=(",", ":")))
'''
    inner = inner.replace("__AT__", repr(at_iso))
    k = _key()
    payload = base64.b64encode(inner.encode()).decode()
    r = requests.post(f"https://api.render.com/v1/services/{SERVICE}/jobs",
        headers={"Authorization": "Bearer " + k, "Accept": "application/json",
                 "Content-Type": "application/json"},
        json={"startCommand": f"echo {payload} | base64 -d | python -X utf8 -"}, timeout=90)
    job = r.json(); job_id = (job.get("job") or job).get("id")
    if not job_id:
        raise SystemExit("job create failed: " + json.dumps(job)[:300])
    for _ in range(50):
        time.sleep(5)
        info = requests.get(f"https://api.render.com/v1/services/{SERVICE}/jobs/{job_id}",
            headers={"Authorization": "Bearer " + k, "Accept": "application/json"}, timeout=60).json()
        job2 = info.get("job") or info
        state = str(job2.get("status") or job2.get("state") or "").lower()
        ll = requests.get(f"https://api.render.com/v1/logs?ownerId={SERVICE}&resource={job_id}",
            headers={"Authorization": "Bearer " + k, "Accept": "application/json"}, timeout=60)
        entries = ll.json()
        if isinstance(entries, dict):
            entries = entries.get("logs") or entries.get("entries") or []
        for e in entries:
            line = (e.get("message") or e.get("line") or str(e)) if isinstance(e, dict) else str(e)
            if line.startswith("EP "):
                return json.loads(line[3:])
        if state in {"succeeded", "failed", "canceled"}:
            break
    raise SystemExit("no EP payload from job " + str(job_id))


def _receipt(tx: str) -> dict:
    """Public Base RPC — read-only receipt + relevant log indices."""
    body = {"jsonrpc": "2.0", "id": 1, "method": "eth_getTransactionReceipt", "params": [tx]}
    r = requests.post(RPC, json=body, timeout=30).json().get("result")
    if not r:
        return {"found": False}
    transfer, auth = None, None
    for lg in r.get("logs", []):
        topics = lg.get("topics") or []
        if topics and topics[0].lower() == TRANSFER_TOPIC and len(topics) >= 3:
            transfer = {
                "log_index": int(lg.get("logIndex", "0x0"), 16),
                "from": "0x" + topics[1][-40:],
                "to": "0x" + topics[2][-40:],
                "amount_atomic": int(lg.get("data", "0x0"), 16),
            }
        if topics and topics[0].lower() == AUTH_USED_TOPIC:
            auth = {
                "log_index": int(lg.get("logIndex", "0x0"), 16),
                "authorization_nonce": str(int(topics[2], 16)),
            }
    return {
        "found": True,
        "status": int(r.get("status", "0x0"), 16),
        "block_number": int(r.get("blockNumber", "0x0"), 16),
        "block_hash": r.get("blockHash"),
        "transfer_log": transfer,
        "authorization_used_log": auth,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--at", help="UTC timestamp, second precision, e.g. 2026-09-23T02:27:03")
    ap.add_argument("--request-id", help="X-Request-Id value")
    a = ap.parse_args()

    if a.request_id and not a.at:
        # X-Request-Id is generated in RAM + returned as a header only (since 22.09);
        # it is NOT persisted anywhere (ledger F7/F8) — honest packet:
        print(json.dumps({
            "found": False,
            "request": {"x_request_id": a.request_id,
                        "persistent_store": None,
                        "note": "X-Request-Id не се персистира (in-memory + header от 22.09); "
                                "използвай --at <UTC> за пълния packet."},
            "response": None, "acceptance": None, "settlement": None, "linkage": None,
        }, ensure_ascii=False, indent=2))
        return 2

    if not a.at:
        ap.error("need --at <UTC> или --request-id")

    rows = _db_fetch(a.at)
    sale = rows["sales"][0] if rows["sales"] else None
    tx = sale["tx_hash"] if sale else None
    claim = rows["claim"][0] if rows["claim"] else None
    events = rows["events"]
    reqs = rows["requests"]
    # prefer the200 among request candidates
    req = next((x for x in reqs if x["status_code"] == 200), reqs[0] if reqs else None)
    rcpt = _receipt(tx) if tx else {"found": False}

    packet = {
        "request": None if not req else {
            "timestamp_utc": req["ts"],
            "method": req["method"],
            "route": req["path"],
            "status": req["status_code"],
            "user_agent": req["user_agent"],
            "persistent_request_id": None,
            "x_request_id_note": "не се персистира (in-memory/header от 22.09)",
        },
        "response": None if not req else {
            "status": req["status_code"],
            "body_sha256": None,
            "body_sha256_note": "тялото на отговора не се съхранява (няма код за това — ledger F7/F8)",
            "delivered_at": (claim or {}).get("delivered_at"),
        },
        "acceptance": {
            "sale_row": None if not sale else {k: sale[k] for k in sale},
            "claim": None if not claim else {
                "endpoint": claim["endpoint"],
                "payer": claim["payer"],
                "consumed_at": claim["consumed_at"],
                "delivered_at": claim["delivered_at"],
            },
            "guard_events": events,
        },
        "settlement": {
            "tx_hash": tx,
            "block_number": rcpt.get("block_number"),
            "block_hash": rcpt.get("block_hash"),
            "receipt_status": rcpt.get("status"),
            "payer": (sale or {}).get("sender"),
            "amount_atomic": int(round(float((sale or {}).get("amount_usdc") or 0) * 1_000_000)),
            "amount_usdc": (sale or {}).get("amount_usdc"),
            "route": (claim or {}).get("endpoint") or (events[0]["endpoint"] if events else None),
            "authorization_nonce": ((rcpt.get("authorization_used_log") or {}).get("authorization_nonce")),
            "log_indices": {
                "transfer_log_index": (rcpt.get("transfer_log") or {}).get("log_index"),
                "authorization_used_log_index": (rcpt.get("authorization_used_log") or {}).get("log_index"),
            },
        },
        "linkage": (
            f"request {req['ts']} {req['method']} {req['path']} -> {req['status_code']}"
            if req else "request ЛИПСВА (покритието на request_log не стига до тази дата)"
        ) + (
            f" -> acceptance consumed={(claim or {}).get('consumed_at') or 'без claim'}"
            + (f", delivered={claim['delivered_at']}" if claim and claim.get("delivered_at") else ", delivered=—")
        ) + (
            f" -> settlement block={rcpt.get('block_hash') and rcpt.get('block_number')} tx={tx[:14] if tx else None}…"
        ),
    }
    print(json.dumps(packet, ensure_ascii=False, indent=2, default=str))
    return 0 if tx else 3


if __name__ == "__main__":
    sys.exit(main())
