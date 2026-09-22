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
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_PATH = os.path.join(REPO_ROOT, "docs", "monitor_state.json")

# ── Glama (official MCP API — read-only, Bearer key) ───────────────────────
# The API exposes GETs only (see /api/mcp/openapi.json): it can READ both of
# our listings and our directory position, and cannot change anything. So this
# block is pulse, exactly like the PayAPI one — never an action.
GLAMA_BASE = "https://glama.ai/api/mcp"
GLAMA_SERVERS = "hristovdimitri2-hub/kristo-intelligence-6"
GLAMA_CONNECTOR = "com.onrender.kristo-intelligence-api/kristo-intelligence"
GLAMA_TERMS = ["defi", "signals"]
GLAMA_KEY_FILE = os.path.join(REPO_ROOT, "secrets", "glama_api_key.txt")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.competitor_recon import (  # noqa: E402
    DEFAULT_RECEIVER,
    KNOWN_PAYERS,
    classify_transfers,
    fetch_incoming_transfers,
    operator_repeats,
)


def receiver_scan() -> Optional[dict]:
    """Incoming USDC to OUR payTo, last 7 days, classified by taxonomy.

    Prints the launch signal (external human payer — anyone that is not a
    known market verifier) and ALWAYS prints the known-infrastructure
    heartbeat lines, so launch and heartbeat stay separate at a glance.
    Silence = nothing in either bucket.
    """
    try:
        from web3 import Web3
        rpc_url = os.getenv("BASE_RPC_URL", "https://mainnet.base.org")
        w3 = Web3(Web3.HTTPProvider(rpc_url, request_kwargs={"timeout": 30}))
        latest = w3.eth.block_number
        from_b = max(1, latest - int(7 * 86400 / 2))
        scan: dict = {}
        transfers = fetch_incoming_transfers(
            rpc_url, DEFAULT_RECEIVER, from_block=from_b, to_block=latest,
            stats=scan)
        report = classify_transfers(transfers, known_payers=KNOWN_PAYERS)
        external = report.get("payers", [])
        launch = report.get("external_unique_payers", 0) > 0
        # ALWAYS state what was actually READ. On 17.09 every chunk 413'd on the
        # public RPC and the pulse looked like an empty week — silence is not
        # proof that nobody paid.
        print(f"\nreceiver scan (7d, blocks {scan.get('from_block')}.."
              f"{scan.get('to_block')}): {scan.get('scanned_blocks')}/"
              f"{scan.get('requested_blocks')} blocks read in "
              f"{scan.get('chunks')} chunks ({scan.get('split_retries')} splits), "
              f"{len(transfers)} txs, rpc {scan.get('rpc_url')}")
        if not scan.get("complete"):
            print("[!] RECEIVER SCAN INCOMPLETE — the 7d window was NOT fully "
                  "read, so 'no payments' is NOT proven. Failed ranges: "
                  f"{scan.get('failed_ranges')[:5]} — re-run with a working "
                  "BASE_RPC_URL.")
        if launch:
            total = report.get("total_usdc", 0)
            print("\n*** LAUNCH SIGNAL: external human/unknown payer detected ***")
            print(f"    external payers: {report['external_unique_payers']}  "
                  f"| payments: {report['total_txs']}  | total {total} USDC")
            for p in external[:10]:
                print(f"    {p['payer']}  {p['txs']} txs, {p['total_usdc']} USDC "
                      f"(avg {p['avg_usdc']})")
        if report.get("known_verification_txs", 0) > 0:
            # Known infrastructure (canaries, samplers/crawlers) paying us =
            # heartbeat: we're IN the crawl set. Never a launch signal.
            # Printed ALWAYS (also alongside a launch signal) so the picture
            # stays complete: launch and heartbeat are separate lines.
            for k in report.get("known_verifications", []):
                print(f"HEARTBEAT (в набора): {k['label']} — {k['txs']} txs, "
                      f"{k['total_usdc']} USDC за 7d. Не е launch сигнал.")
        # ── WATCHLIST: second payment from a real-operator wallet = trigger ──
        for r in operator_repeats(transfers):
            print(f"\n*** OPERATOR REPEAT: {r['label']} — {r['txs']} txs, "
                  f"{r['total_usdc']} USDC (7d) → operator deal разговор ***")
        for r in _watchlist_alltime():
            print(f"*** OPERATOR REPEAT (all-time): {r['label']} — "
                  f"{r['txs']} плащания общо → operator deal разговор ***")
        _print_funnel()
        return report if launch else None
    except Exception as exc:
        print(f"[receiver scan skipped: {str(exc)[:80]}]")
        return None


def _watchlist_alltime() -> list[dict]:
    """All-time repeat check against the persistent dashboard store (live)."""
    try:
        d = requests.get(
            "https://kristo-intelligence-api.onrender.com/api/dashboard/data",
            timeout=30).json()
        history = d["sections"]["onchain"]["history"]
    except Exception:
        return []
    transfers = [{"payer": h["sender"], "amount_usdc": h["amount_usdc"]}
                 for h in history]
    # history is capped at 100 rows — enough for months at current volume
    return operator_repeats(transfers)


def _print_funnel() -> None:
    """Payment funnel per paid route: 'signal: X challenges → Y paid (Z%)'."""
    try:
        d = requests.get(
            "https://kristo-intelligence-api.onrender.com/api/dashboard/data",
            timeout=30).json()
        funnel = d["sections"]["requests"].get("funnel") or {}
    except Exception:
        return
    lines = []
    for path, f in funnel.items():
        challenges = f["challenges_today"]
        paid = f["paid_today"]
        rate = round(100.0 * paid / challenges, 1) if challenges else 0.0
        short = path.rsplit("/", 1)[-1]
        lines.append(f"    {short}: {challenges} challenges → {paid} paid "
                     f"({rate}% днес)")
    if any(f["challenges_today"] or f["paid_today"]
           for f in funnel.values()):
        print("\nФЪНЪЛ (днес, по маршрут):")
        for ln in lines:
            print(ln)


def glama_key() -> Optional[str]:
    """The Glama API key: GLAMA_API_KEY env wins, then secrets/glama_api_key.txt.

    Same model as secrets/render_api_key.txt — the file is gitignored, so the
    key never lands in the repo. No key simply means the block is skipped.
    """
    env = (os.getenv("GLAMA_API_KEY") or "").strip()
    if env:
        return env
    try:
        with open(GLAMA_KEY_FILE, encoding="utf-8") as fh:
            return fh.read().strip() or None
    except Exception:
        return None


def _glama_get(path: str, key: str, params: Optional[dict] = None) -> Optional[dict]:
    """One authenticated GET against the Glama API; None on any failure."""
    try:
        r = requests.get(f"{GLAMA_BASE}{path}", params=params, timeout=25, headers={
            "Authorization": f"Bearer {key}", "Accept": "application/json"})
        return r.json() if r.status_code == 200 else None
    except Exception:
        return None


def fetch_glama_state(key: str) -> dict:
    """Both listings + directory position, straight from the official API.

    `servers` is the directory entry (scores, attributes, tools Glama managed to
    introspect); `connector` is the hosted remote one (health + the tools from
    its most recent check). Positions come from /v1/servers?query=… — the same
    words agents type, so a move here is a real discovery move.
    """
    state: dict = {"servers": {}, "connector": {}, "positions": {}}

    srv = _glama_get(f"/v1/servers/{GLAMA_SERVERS}", key) or {}
    state["servers"] = {
        "quality_score": srv.get("qualityScore"),
        "spdx_license": srv.get("spdxLicense"),
        "tools": len(srv.get("tools") or []),
        "attributes": sorted(srv.get("attributes") or []),
        "boosted": srv.get("isBoosted"),
    }

    con = _glama_get(f"/v1/connectors/{GLAMA_CONNECTOR}", key) or {}
    state["connector"] = {
        "quality_score": con.get("qualityScore"),
        "healthy": con.get("healthy"),
        "tool_count": con.get("toolCount"),
        "last_tested_at": con.get("lastTestedAt"),
        "transport": (con.get("connection") or {}).get("transport"),
        "attributes": sorted(con.get("attributes") or []),
    }

    for term in GLAMA_TERMS:
        data = _glama_get("/v1/servers", key, {"query": term, "first": 25}) or {}
        items = (data.get("servers") or data.get("items")
                 or data.get("results") or [])
        pos = next((i + 1 for i, it in enumerate(items)
                    if f"{it.get('namespace')}/{it.get('slug')}" == GLAMA_SERVERS),
                   None)
        state["positions"][term] = {"position": pos, "shown": len(items)}

    return state


def diff_glama(prev: dict, cur: dict) -> List[str]:
    """What moved on Glama since the previous run (silence = nothing moved)."""
    changes: List[str] = []
    for side, label in (("servers", "GLAMA servers"),
                        ("connector", "GLAMA connector")):
        p, c = prev.get(side) or {}, cur.get(side) or {}
        for field in ("quality_score", "healthy", "tool_count", "tools",
                      "spdx_license", "boosted", "transport"):
            if field in p and field in c and p[field] != c[field]:
                changes.append(f"{label} {field}: {p[field]} -> {c[field]}")
    p_pos, c_pos = prev.get("positions") or {}, cur.get("positions") or {}
    for term, c in c_pos.items():
        p = (p_pos.get(term) or {}).get("position")
        if p != c.get("position"):
            changes.append(f"GLAMA rank q={term}: {p or 'absent'} -> "
                           f"{c.get('position') or 'absent'} ({c.get('shown')} shown)")
    return changes


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

    # ── Glama (read-only API; skipped entirely when there is no key) ────────
    g_key = glama_key()
    if g_key:
        cur["glama"] = fetch_glama_state(g_key)
        g_s, g_c = cur["glama"]["servers"], cur["glama"]["connector"]
        print(f"\nglama servers: quality={g_s.get('quality_score')} "
              f"license={g_s.get('spdx_license')} tools={g_s.get('tools')} "
              f"boosted={g_s.get('boosted')}")
        print(f"glama connector: healthy={g_c.get('healthy')} "
              f"score={g_c.get('quality_score')} tools={g_c.get('tool_count')} "
              f"transport={g_c.get('transport')} "
              f"last_tested={g_c.get('last_tested_at')}")
        for term, r in cur["glama"]["positions"].items():
            print(f"glama q={term}: position={r['position'] or 'ABSENT'} "
                  f"of {r['shown']}")
    else:
        print("\nglama: SKIPPED — no key (set GLAMA_API_KEY or write "
              "secrets/glama_api_key.txt)")

    changes = diff(prev, cur) if prev else []
    if prev:
        changes += diff_glama(prev.get("glama") or {}, cur.get("glama") or {})
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