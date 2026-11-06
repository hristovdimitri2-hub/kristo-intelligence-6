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
    python scripts/listing_monitor.py            # run + diff + save state (~16s)
    python scripts/listing_monitor.py --quiet    # exit 1 only on change
    python scripts/listing_monitor.py --scan     # also scan the chain (~20 min)

Exit codes:
    0  ran, nothing moved
    1  ran, something moved (with --quiet)
    2  the saved baseline exists but could not be read, so NOTHING was compared

Code 2 exists because an unreadable baseline is not the same as a quiet one. The
comparison did not happen; we do not know what moved. Reporting that as "no
changes" would be a false all-clear from the one tool whose job is to notice.

Why the chain scan is opt-in (06.11):
    receiver_scan() reads seven days of Base blocks — roughly 302,400 of them — in
    chunks over a public RPC. That took over twenty minutes and made the whole
    tool look hung, so a tool whose entire purpose is to be run weekly was not
    being run at all. The listing diff, which is what this script is for, takes
    about sixteen seconds. The scan is now opt-in and its ABSENCE IS ANNOUNCED:
    a skipped scan must never read as "nobody paid", the same way an unreadable
    baseline must never read as "nothing changed".
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
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


def _glama_get(path: str, key: str,
               params: Optional[dict] = None) -> tuple[int, Optional[dict]]:
    """One authenticated GET against the Glama API -> (http_status, data).

    The status is returned because it is the difference between two facts that
    used to be recorded identically. This function previously answered ``None``
    for every failure, and the caller wrote ``or {}``, so a 404 ("no such
    listing") and a 200 with nothing in it ("the listing exists and Glama
    introspected no tools") both became ``tools: 0``.

    That mattered: /v1/servers/hristovdimitri2-hub/kristo-intelligence-6 answers
    **404 Server not found**, so for over a month this tool reported a missing
    listing as an empty one and nobody could tell the difference. status is 0
    when the request never completed.
    """
    try:
        r = requests.get(f"{GLAMA_BASE}{path}", params=params, timeout=25, headers={
            "Authorization": f"Bearer {key}", "Accept": "application/json"})
    except Exception:
        return 0, None
    if r.status_code != 200:
        return r.status_code, None
    try:
        return 200, r.json()
    except Exception:
        return r.status_code, None


def fetch_glama_state(key: str) -> dict:
    """Both listings + directory position, straight from the official API.

    `servers` is the directory entry (scores, attributes, tools Glama managed to
    introspect); `connector` is the hosted remote one (health + the tools from
    its most recent check). Positions come from /v1/servers?query=… — the same
    words agents type, so a move here is a real discovery move.

    Every block carries the status it was read at, so "absent" stays distinguishable
    from "empty". A block with ``status == 404`` means there is NO listing; a block
    with ``status == 200`` and no tools means there is one and it holds nothing.
    """
    state: dict = {"servers": {}, "connector": {}, "positions": {}}

    s_status, srv = _glama_get(f"/v1/servers/{GLAMA_SERVERS}", key)
    srv = srv or {}
    state["servers"] = {
        "status": s_status,
        "missing": s_status == 404,
        "quality_score": srv.get("qualityScore"),
        "spdx_license": srv.get("spdxLicense"),
        "tools": len(srv.get("tools") or []),
        "attributes": sorted(srv.get("attributes") or []),
        "boosted": srv.get("isBoosted"),
    }

    c_status, con = _glama_get(f"/v1/connectors/{GLAMA_CONNECTOR}", key)
    con = con or {}
    state["connector"] = {
        "status": c_status,
        "missing": c_status == 404,
        "quality_score": con.get("qualityScore"),
        "healthy": con.get("healthy"),
        "tool_count": con.get("toolCount"),
        "last_tested_at": con.get("lastTestedAt"),
        "transport": (con.get("connection") or {}).get("transport"),
        "attributes": sorted(con.get("attributes") or []),
    }

    for term in GLAMA_TERMS:
        p_status, data = _glama_get("/v1/servers", key,
                                    {"query": term, "first": 25})
        data = data or {}
        items = (data.get("servers") or data.get("items")
                 or data.get("results") or [])
        pos = next((i + 1 for i, it in enumerate(items)
                    if f"{it.get('namespace')}/{it.get('slug')}" == GLAMA_SERVERS),
                   None)
        state["positions"][term] = {"position": pos, "shown": len(items),
                                    "status": p_status}

    return state


def diff_glama(prev: dict, cur: dict) -> List[str]:
    """What moved on Glama since the previous run (silence = nothing moved)."""
    changes: List[str] = []
    for side, label in (("servers", "GLAMA servers"),
                        ("connector", "GLAMA connector")):
        p, c = prev.get(side) or {}, cur.get(side) or {}
        # `missing` and `status` are diffed too: a listing appearing or
        # disappearing is the single most important event this section can
        # report, and without these two fields a 404 turning into a real listing
        # would look like "tools: 0 -> 6" with no explanation of why.
        for field in ("missing", "status", "quality_score", "healthy",
                      "tool_count", "tools", "spdx_license", "boosted",
                      "transport"):
            if field in p and field in c and p[field] != c[field]:
                changes.append(f"{label} {field}: {p[field]} -> {c[field]}")
    p_pos, c_pos = prev.get("positions") or {}, cur.get("positions") or {}
    for term, c in c_pos.items():
        prev_entry = p_pos.get(term) or {}
        p = prev_entry.get("position")
        if p == c.get("position"):
            continue
        # A failed search is not an absent result. If the endpoint did not answer
        # 200 we do not know where we rank, and saying "absent" would report a
        # ranking drop that never happened — the same mistake as reading an
        # unreadable baseline as "nothing changed".
        if c.get("status") not in (200, None):
            changes.append(f"GLAMA rank q={term}: UNKNOWN — search returned "
                           f"HTTP {c.get('status')}, so no position was read")
            continue
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


# ── the baseline: read it honestly, write it atomically ────────────────────
# Three situations, deliberately NOT collapsed into one:
#   absent  — a first run; there is no baseline, and that is not an error
#   ok      — a usable baseline; diff against it
#   corrupt — the file is there but we cannot use it, so we do NOT know what
#             moved, and must not say that nothing did
BASELINE_ABSENT = "absent"
BASELINE_OK = "ok"
BASELINE_CORRUPT = "corrupt"
CORRUPT_EXIT_CODE = 2


def _read_baseline(path: str):
    """Return (status, baseline). Never raises, and never guesses.

    A file that parses but is not a non-empty object — a list, a bare value, an
    empty dict — is reported as corrupt rather than as "no baseline". It is not
    usable for a diff, and silently treating it as usable would produce exactly
    the false all-clear this function exists to prevent.
    """
    if not os.path.exists(path):
        return BASELINE_ABSENT, None
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        return BASELINE_CORRUPT, None
    if not isinstance(data, dict) or not data:
        return BASELINE_CORRUPT, None
    return BASELINE_OK, data


def _write_state(path: str, data: dict) -> None:
    """Write the baseline atomically: a temp file here, then one rename.

    The reader above has been taught to distrust a torn file; the writer must
    stop being able to create one. If this run dies mid-save, the previous
    baseline survives intact instead of being replaced by half a document.
    """
    directory = os.path.dirname(path) or "."
    if not os.path.isdir(directory):
        os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
        os.replace(tmp_path, path)
    except BaseException:
        # Never leave the temp file behind on the way out.
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--quiet", action="store_true", help="print only changes")
    # The chain scan is opt-in: it costs ~20 minutes and the listing diff that
    # this tool exists for costs ~16 seconds. Both spellings are accepted so a
    # caller can be explicit either way.
    scan_group = ap.add_mutually_exclusive_group()
    scan_group.add_argument(
        "--scan", dest="scan", action="store_true",
        help="also scan 7 days of Base blocks for incoming USDC (~20 min)")
    scan_group.add_argument(
        "--no-scan", dest="scan", action="store_false",
        help="skip the chain scan (the default)")
    ap.set_defaults(scan=False)
    args = ap.parse_args()

    cur = fetch_state()
    prev_status, prev = _read_baseline(STATE_PATH)
    baseline_corrupt = prev_status == BASELINE_CORRUPT
    if baseline_corrupt:
        # Loud, and before anything else, so it cannot be mistaken for a quiet
        # week. This is the one case where the tool must not sound calm.
        print("\n" + "!" * 72)
        print(f"BASELINE UNREADABLE: {STATE_PATH}")
        print("The file exists but could not be read as a baseline object, so the")
        print("comparison below did NOT happen. This is NOT 'no changes' - we do")
        print("not know what moved. A fresh baseline is saved at the end.")
        print("!" * 72)

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
        if g_s.get("missing"):
            print("\nglama servers: NO LISTING (HTTP 404 — Server not found). "
                  "This is not")
            print("  'a listing with 0 tools': there is nothing there to "
                  "introspect.")
            print("  Add it at https://glama.ai/mcp/servers (Add Server), then "
                  "claim it.")
        else:
            print(f"\nglama servers: status={g_s.get('status')} "
                  f"quality={g_s.get('quality_score')} "
                  f"license={g_s.get('spdx_license')} tools={g_s.get('tools')} "
                  f"boosted={g_s.get('boosted')}")
        if g_c.get("missing"):
            print("glama connector: NO LISTING (HTTP 404)")
        else:
            print(f"glama connector: status={g_c.get('status')} "
                  f"healthy={g_c.get('healthy')} "
                  f"score={g_c.get('quality_score')} "
                  f"tools={g_c.get('tool_count')} "
                  f"transport={g_c.get('transport')} "
                  f"last_tested={g_c.get('last_tested_at')}")
        for term, r in cur["glama"]["positions"].items():
            if r.get("status") not in (200, None):
                print(f"glama q={term}: UNKNOWN — search returned "
                      f"HTTP {r.get('status')}, so no position was read")
            else:
                print(f"glama q={term}: position={r['position'] or 'ABSENT'} "
                      f"of {r['shown']}")
    else:
        print("\nglama: SKIPPED — no key (set GLAMA_API_KEY or write "
              "secrets/glama_api_key.txt)")

    changes = diff(prev, cur) if prev else []
    if prev:
        changes += diff_glama(prev.get("glama") or {}, cur.get("glama") or {})
    if baseline_corrupt:
        print("\n(changes vs previous run: NOT COMPARED — the baseline was "
              "unreadable)")
    elif changes:
        print("\n=== CHANGES vs previous run ===")
        for c in changes:
            print(" *", c)
    else:
        print("\n(no changes vs previous run)")

    _write_state(STATE_PATH, cur)
    print(f"state saved: {STATE_PATH}")

    # Launch-signal scan: silent unless an external human payer shows up.
    # Opt-in, and the SKIP IS STATED OUT LOUD. A scan that did not happen must
    # never be readable as "nobody paid" — this script already carries that
    # lesson from 17.09, when every chunk 413'd and an empty week was reported.
    if args.scan:
        receiver_scan()
    else:
        # Stated positively: what was skipped, and what is therefore unknown.
        # An earlier draft ended with the words "this is NOT 'no payments'",
        # which read well but put the false claim into the output and tripped the
        # test that guards against exactly that. Say what did not happen instead
        # of quoting the wrong conclusion.
        print("\nreceiver scan: NOT RUN (pass --scan to run it, ~20 minutes).")
        print("  The 7-day on-chain window was NOT read, so no statement about "
              "incoming")
        print("  payments is being made here either way. The listing diff above "
              "is")
        print("  complete and unaffected; only the on-chain launch signal is "
              "missing.")

    if baseline_corrupt:
        return CORRUPT_EXIT_CODE
    return 1 if (args.quiet and changes) else 0


if __name__ == "__main__":
    sys.exit(main())