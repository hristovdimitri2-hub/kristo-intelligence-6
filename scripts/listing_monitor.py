"""Listing monitor — our own pulse on PayAPI Market (weekly protocol).

Tracks two things and alarms on change:
  1. Reliability band from GET /agent/get?id=<our slug>
     ({score, band, computed_at}) — lands when Chet's compute runs
  2. Our rank for the 8 terms agents actually type
     (eth, defi, signals, whale, rug, ondo, kaito, degen)

State is diffed against docs/monitor_state.json (previous run) so every
call prints exactly what MOVED. Weekly run, not daily — this is pulse,
not telemetry.

Usage:
    python scripts/listing_monitor.py            # run + diff + save state
    python scripts/listing_monitor.py --quiet    # exit 1 only on change
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Optional

import requests

BASE = "https://payapi.market"
OUR_SLUG = "kristo-intelligence-defi-signals-api"
TERMS = ["eth", "defi", "signals", "whale", "rug", "ondo", "kaito", "degen"]
STATE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                          "docs", "monitor_state.json")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.competitor_recon import (  # noqa: E402
    DEFAULT_RECEIVER,
    KNOWN_PAYERS,
    classify_transfers,
    fetch_incoming_transfers,
)


def receiver_scan() -> Optional[dict]:
    """Incoming USDC to OUR payTo, last 7 days, classified by taxonomy.

    Prints ONLY on the launch signal (external human payer > 0 — any payer
    that is not a known market verifier). Silence = nothing to report.
    """
    try:
        from web3 import Web3
        rpc_url = os.getenv("BASE_RPC_URL", "https://mainnet.base.org")
        w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 30}))
        latest = w3.eth.block_number
        from_b = max(1, latest - int(7 * 86400 / 2))
        transfers = fetch_incoming_transfers(
            rpc_url, DEFAULT_RECEIVER, from_block=from_b, to_block=latest)
        report = classify_transfers(transfers, known_payers=KNOWN_PAYERS)
        external = report.get("payers", [])
        if report.get("external_unique_payers", 0) > 0:
            total = report.get("total_usdc", 0)
            print("\n*** LAUNCH SIGNAL: external human/unknown payer detected ***")
            print(f"    external payers: {report['external_unique_payers']}  "
                  f"| payments: {report['total_txs']}  | total {total} USDC")
            for p in external[:10]:
                print(f"    {p['payer']}  {p['txs']} txs, {p['total_usdc']} USDC "
                      f"(avg {p['avg_usdc']})")
            if report.get("known_verifications"):
                print("    (known verifier canaries excluded from the above)")
            return report
        return None
    except Exception as exc:
        print(f"[receiver scan skipped: {str(exc)[:80]}]")
        return None


def fetch_state() -> dict:
    state: dict = {"reliability": None, "ranks": {}}
    g = requests.get(f"{BASE}/agent/get?id={OUR_SLUG}", timeout=20).json()
    rel = g.get("reliability") or {}
    state["reliability"] = {
        "score": rel.get("score"),
        "band": rel.get("band"),
        "computed_at": rel.get("computed_at"),
        "name": g.get("name"),
        "payment_verified": g.get("payment_verified"),
        "price_min": g.get("price_min"),
        "description": (g.get("description") or "")[:200],
    }
    for term in TERMS:
        try:
            r = requests.get(f"{BASE}/agent/search?q={term}", timeout=20).json()
            items = r if isinstance(r, list) else (
                r.get("results") or r.get("apis") or r.get("listings") or [])
            names = [x.get("name", "") for x in items]
            pos = next((i + 1 for i, n in enumerate(names)
                        if "kristo" in n.lower()), None)
            state["ranks"][term] = {"position": pos, "total": len(items)}
        except Exception as exc:
            state["ranks"][term] = {"error": str(exc)[:80]}
    return state


def diff(prev: dict, cur: dict) -> List[str]:
    changes = []
    p_rel, c_rel = prev.get("reliability") or {}, cur.get("reliability") or {}
    if p_rel.get("band") != c_rel.get("band"):
        changes.append(f"BAND: {p_rel.get('band')} -> {c_rel.get('band')} "
                       f"(score {p_rel.get('score')} -> {c_rel.get('score')})")
    if p_rel.get("description") != c_rel.get("description"):
        changes.append("DESCRIPTION CHANGED (title fix landed?)")
    if p_rel.get("price_min") != c_rel.get("price_min"):
        changes.append(f"PRICE: {p_rel.get('price_min')} -> {c_rel.get('price_min')}")
    p_ranks, c_ranks = prev.get("ranks") or {}, cur.get("ranks") or {}
    for term, c in c_ranks.items():
        p = (p_ranks.get(term) or {}).get("position")
        cp = c.get("position")
        if p != cp:
            changes.append(f"RANK q={term}: {p or 'absent'} -> {cp or 'absent'} "
                           f"({c.get('total')} results)")
    return changes


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true", help="print only changes")
    args = ap.parse_args()

    cur = fetch_state()
    prev = {}
    if os.path.exists(STATE_PATH):
        try:
            prev = json.load(open(STATE_PATH, encoding="utf-8"))
        except Exception:
            prev = {}

    rel = cur["reliability"]
    print(f"listing: {rel.get('name')}")
    print(f"reliability: band={rel.get('band')} score={rel.get('score')} "
          f"computed_at={rel.get('computed_at')}")
    for term, r in cur["ranks"].items():
        if "error" in r:
            print(f"q={term}: ERROR {r['error']}")
        else:
            print(f"q={term}: position={r['position'] or 'ABSENT'} "
                  f"of {r['total']}")

    changes = diff(prev, cur) if prev else []
    if changes:
        print("\n=== CHANGES vs previous run ===")
        for c in changes:
            print(" *", c)
    else:
        print("\n(no changes vs previous run)")

    with open(STATE_PATH, "w", encoding="utf-8") as fh:
        json.dump(cur, fh, indent=2, ensure_ascii=False)
    print(f"state saved: {STATE_PATH}")

    # Launch-signal scan: silent unless an external human payer shows up.
    receiver_scan()

    return 1 if (args.quiet and changes) else 0


if __name__ == "__main__":
    sys.exit(main())