"""
Discovery blueprint: x402 / OpenAPI / llms.txt / MCP / health endpoints.

These routes are the machine-readable discovery layer for AI agents and
monitoring. They are intentionally free (no x402 paywall) so the service
can be indexed and health-checked without payment.

Routes extracted from main.py (audit item #5, 2026-08-24):
  - GET /health
  - GET /.well-known/x402.json
  - GET /openapi.json
  - GET /llms.txt
  - GET /mcp.json
  - GET /api/mcp/manifest

Lazy import pattern: shared state and helpers live in main.py; each route
imports them at request time to avoid circular imports at module load.
"""
from __future__ import annotations

import html
import json
import logging
import os
import queue
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone

from flask import Blueprint, Response, jsonify, request

discovery_bp = Blueprint("discovery", __name__)


# ── Test-suite facts published on /validation ──────────────────────────────
# ONE place, deliberately. These two values used to be typed twice — once into
# the JSON facts block and once into the HTML panel — so /validation could (and
# did) keep advertising "550/550 tests green, last run 2026-10-30" long after the
# suite had grown past it. On a page whose entire job is to state facts someone
# can check, a stale count is the worst possible defect.
#
# UPDATE BOTH VALUES TOGETHER. tests/test_visibility_seo.py fails if the number
# falls behind the suite actually collected.
SUITE_TESTS_PASSED = 1389
SUITE_LAST_RUN = "2026-11-12"

#: The uptime window this page publishes, as a dated measurement — not a live
#: counter. It lives here, next to the suite figures and for the same reason: the
#: page used to type "23 of 23 days green" into the HTML as well as into the JSON
#: facts, so the two could disagree, and the number never said when those 23 days
#: ended. Both read these now, and a test moves them to prove the HTML follows the
#: data rather than coincidentally matching it.
UPTIME_DAYS_GREEN = 23
UPTIME_DAYS_TOTAL = 23
UPTIME_MEASURED_TO = "2026-10-19"

#: The version this service reports about ITSELF — in the OpenAPI document, in
#: the MCP `initialize` handshake, and, through the generator, in the published
#: `server.json`. It used to be three different numbers at once: the OpenAPI
#: document said 6.0.0, the MCP handshake said 1.0.0, and `server.json` — the
#: artifact a registry actually publishes — said 6.2.0. A registry, an MCP
#: client or an agent that compares versions therefore saw us as OLDER than we
#: are and had no reason to re-read anything we had changed. That is a
#: visibility bug, not a cosmetic one.
#:
#: The x402 protocol version lives beside it in the manifest and is a different
#: thing; it is not this.
SERVICE_VERSION = "6.2.0"


def _sample_disclaimer(endpoint: str) -> str:
    """The price a free sample quotes must be the price its route charges.

    Every /sample route used to carry a typed "$0.005 USDC" in this sentence.
    When /api/v1/whaleflow moved to the $0.003 tier the other five were updated
    and that one was not, so the free sample handed to a prospective buyer
    overquoted the product by 67% — and a sample's disclaimer is the first thing
    that buyer reads. Generated from the price map now, so it cannot drift again.
    """
    from main import BASE_FEE_AMOUNT_USDC, X402_PRICE_MAP

    price = float(X402_PRICE_MAP.get(endpoint, BASE_FEE_AMOUNT_USDC))
    return ("Static example of the response schema for discovery and agents; live "
            "values require a paid call ($%.3f USDC, x402 on Base)." % price)


def _dearest_route_price() -> float:
    """The most expensive paid route — generated, never typed into prose."""
    from main import REAL_X402_ROUTES

    return max(float(route["price_usdc"]) for route in REAL_X402_ROUTES)


def _cheapest_route_price() -> float:
    """The cheapest paid route — generated, never typed into prose.

    A single flat "price per call" cannot be true for six routes with two
    different prices. When one has to be quoted anyway (an older field kept for
    compatibility, a headline, a tier), it must be the CHEAPEST, because the two
    ways of being wrong are not symmetrical: understating makes a payer send too
    little and get an honest 401 with their money untouched, while overstating
    makes them send too much and it is NOT refunded. The 402 response always
    states the exact amount, so the headline only ever needs to not overstate.
    """
    from main import REAL_X402_ROUTES

    return min(float(route["price_usdc"]) for route in REAL_X402_ROUTES)


def _route_price(endpoint: str) -> float:
    """The paywall's price for ONE paid route, from the paywall's own map.

    `X402_FEE_USDC` / `MICRO_FEE_USDC` are flat aliases. Quoting one of them for
    a route the paywall prices differently advertises a number we do not charge,
    and both are environment-overridable, so the only safe source is
    `X402_PRICE_MAP` — the same dict `_x402_paywall` reads to build the 402.
    This is the rule `_mcp_tools` already followed; it is shared now so a new
    surface cannot quietly go back to the alias.
    """
    from main import X402_FEE_USDC, X402_PRICE_MAP

    return float(X402_PRICE_MAP.get(endpoint, X402_FEE_USDC))


#: How long a successful dashboard chain read stays evidence that the chain is
#: reachable. The scan loop runs every 60s (KRISTO_DASHBOARD_SCAN_INTERVAL, floor
#: 30), so ten minutes tolerates nine consecutive missed cycles: long enough not to
#: flicker on one slow RPC call, short enough that a genuinely dead chain stops
#: being reported as readable.
SALES_SCAN_FRESH_SECONDS = 600


def _fresh_stamp(raw, now=None) -> bool:
    """Is this ISO stamp recent enough to count as proof of life?

    A missing, empty, unparseable or future stamp is NOT proof. An absence must
    never be promoted into a healthy dependency — the rule this audit applies to
    every other surface, and the one /health broke on 07.11 by reading memory that
    could never hold the stamp in the first place.
    """
    if not raw:
        return False
    try:
        stamp = datetime.fromisoformat(str(raw))
    except (TypeError, ValueError):
        return False
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=timezone.utc)
    age = ((now or datetime.now(timezone.utc)) - stamp).total_seconds()
    return 0 <= age <= SALES_SCAN_FRESH_SECONDS


def _sales_scan_is_fresh(wallet: dict, now=None) -> bool:
    """Did the in-process dashboard scan read the chain recently enough?"""
    return _fresh_stamp(wallet.get("sales_scan_ok_at"), now)


def _dependency_state():
    """Read the two dependencies of this service, and say how they are.

    Returns (crm_ready, blockchain_ready, monitor_ready, wallet, backend), where
    `wallet` also carries the SHARED-store stamps under `shared_*` keys.

    THE ANSWER CANNOT COME FROM THIS PROCESS'S MEMORY ALONE (07.11). The
    recommended deployment runs the background loops in a SEPARATE worker process —
    scripts/worker.py's own diagram: web is HTTP-only
    (`KRISTO_DISABLE_BACKGROUND_THREADS=true`), worker is background-only
    (`KRISTO_WORKER_MODE=true`), and POSTGRES is the shared state. `_wallet_state`
    is process-local, so in that topology the web process's copy can never hold the
    monitor's or the scan's stamps, and /health reported `blockchain.ready: false`
    with `last_block_checked: 0` for over fifteen hours while the worker was
    demonstrably scanning that same chain every minute and writing
    `last_scanned_block` into Postgres. The alarm was about where we looked.

    So each answer is: this process's memory OR the shared store, whichever proves
    liveness. The `__main__` dance stays for the single-process case (the lazy
    `import main` copy keeps its defaults because the env guard skips its threads,
    and reading it reports a false "degraded").

    `blockchain_ready` answers "is the chain reachable" — the dependency, and what
    callers act on. `monitor_ready` answers "is the dedicated payment monitor
    running" — one component, with a redundant sibling. Reporting only the second
    as if it were the first cried wolf; reporting only the first would hide a real
    monitor failure. Both are published so neither can hide the other.

    Every read is defensive: this is the pair of endpoints that has to keep
    answering while the thing being read is broken, so a store that cannot report
    its own backend must not turn into an exception here.
    """
    import sys as _sys

    _entry = _sys.modules.get("__main__")
    if str(getattr(_entry, "__file__", "") or "").replace("\\", "/").rsplit("/", 1)[-1] == "main.py":
        _lock = _entry._lock
        _wallet_state = _entry._wallet_state
        crm_store = _entry.crm_store
        dashboard_db = getattr(_entry, "dashboard_db", None)
        heartbeat_keys = (
            getattr(_entry, "MONITOR_HEARTBEAT_KEY", "monitor_heartbeat_at"),
            getattr(_entry, "MONITOR_HEARTBEAT_BLOCK_KEY", "monitor_heartbeat_block"),
            getattr(_entry, "SALES_SCAN_HEARTBEAT_KEY", "sales_scan_heartbeat_at"),
        )
    else:
        from main import _lock, _wallet_state, crm_store, dashboard_db
        from main import (MONITOR_HEARTBEAT_KEY, MONITOR_HEARTBEAT_BLOCK_KEY,
                          SALES_SCAN_HEARTBEAT_KEY)
        heartbeat_keys = (MONITOR_HEARTBEAT_KEY, MONITOR_HEARTBEAT_BLOCK_KEY,
                          SALES_SCAN_HEARTBEAT_KEY)
    from config import BASE_CHAIN_ID

    try:
        crm_ready = bool(crm_store.is_healthy())
    except Exception:
        # An unreachable store answers "not ready", it does not take /health down.
        crm_ready = False
    with _lock:
        wallet = dict(_wallet_state)

    # The shared store, where the worker process publishes the same facts. Read
    # defensively and in one place: a store that cannot answer yields no evidence
    # rather than an exception on the endpoint the platform health-checks.
    monitor_key, monitor_block_key, scan_key = heartbeat_keys
    wallet["shared_monitor_heartbeat_at"] = None
    wallet["shared_monitor_heartbeat_block"] = None
    wallet["shared_sales_scan_heartbeat_at"] = None
    try:
        if dashboard_db is not None:
            wallet["shared_monitor_heartbeat_at"] = (
                dashboard_db.get_meta(monitor_key, "") or None)
            wallet["shared_monitor_heartbeat_block"] = (
                dashboard_db.get_meta(monitor_block_key, "") or None)
            wallet["shared_sales_scan_heartbeat_at"] = (
                dashboard_db.get_meta(scan_key, "") or None)
    except Exception:
        pass

    memory_monitor_ready = bool(
        wallet.get("rpc_connected")
        and wallet.get("chain_id") == BASE_CHAIN_ID
        and wallet.get("receiver_valid")
    )
    monitor_ready = bool(memory_monitor_ready
                         or _fresh_stamp(wallet.get("shared_monitor_heartbeat_at")))
    # The chain is readable if ANY scanner proves it, in ANY process.
    blockchain_ready = bool(
        monitor_ready
        or _sales_scan_is_fresh(wallet)
        or _fresh_stamp(wallet.get("shared_sales_scan_heartbeat_at"))
    )
    return (crm_ready, blockchain_ready, monitor_ready, wallet,
            getattr(crm_store, "backend", "unknown"))


@discovery_bp.route("/health")
def health():
    """Service liveness check (free, no paywall).

    Liveness, and only liveness: this answers 200 whenever the process is alive to
    answer it, which is what platform health checks (Render, Docker) and the
    keep-alive loop act on. The state of the two dependencies is reported in the
    body — `status` is "degraded", and `database`/`blockchain` say which one — so
    the sentinel still raises its Telegram alert on a change. Readiness, the thing
    that is genuinely false when a dependency is down, is /ready.

    Why the code changed (F-10 in docs/PERFORMANCE_AND_ARCHITECTURE_AUDIT.md, and
    the audit's own recommendation 9): this used to answer 503 when the database
    was unreachable. A restart cannot repair a database, so the only things a 503
    bought were a cold start and this service being marked down. Measured with the
    store unreachable: /health was the only endpoint of eighteen that changed —
    /validation, /llms.txt, /mcp.json, /sitemap.xml, /robots.txt, /agents.json,
    /openapi.json and /mcp all still answered 200, because none of them needs a
    database. Discovery is the surface that has to stay up for anyone to find us at
    all, and it was being taken down to no purpose. Blockchain connectivity was
    already reported informationally for exactly this reason; the database is now
    treated the same way.
    """
    crm_ready, blockchain_ready, monitor_ready, wallet, backend = _dependency_state()
    return jsonify(
        status="ok" if crm_ready and blockchain_ready else "degraded",
        service="up",
        database={"backend": backend, "ready": crm_ready},
        blockchain={
            "ready": blockchain_ready,
            "network": wallet.get("network", "Base Mainnet"),
            "chain_id": wallet.get("chain_id"),
            "fee_receiver": wallet.get("fee_receiver"),
            # `ready` above answers "is the chain reachable". This answers "did the
            # dedicated payment monitor start", which is a different question about
            # one redundant component. Both are reported so the split cannot hide a
            # monitor failure — see _dependency_state for why they were separated.
            "monitor_ready": monitor_ready,
            # The other scanner's proof of life, and how far it has read. If
            # monitor_ready is false and this is recent, the chain is demonstrably
            # fine and the alarm is about the monitor, not about Base.
            #
            # These report the FRESHEST evidence from either place the fact can live
            # — this process's memory or the shared store the worker writes — because
            # in the split deployment only the latter is ever populated here.
            "sales_scan_ok_at": (wallet.get("shared_sales_scan_heartbeat_at")
                                 or wallet.get("sales_scan_ok_at")),
            "sales_scan_block": wallet.get("sales_scan_block") or 0,
            # WHY the monitor is not ready. Redacted at write time (redact_rpc):
            # a paid endpoint carries its api key in the path. Publishing it here
            # is the difference between an alarm and an alarm with a cause.
            "rpc_error": wallet.get("rpc_error"),
            "monitor_heartbeat_at": (wallet.get("shared_monitor_heartbeat_at")
                                     or wallet.get("last_check_time")),
            # Where the payment monitor has scanned up to, and when it last
            # looked. Added because there was no way to see this from outside at
            # all: the figure lives in the paid /api/stats wallet block, so nobody
            # - including us - could tell whether the thing that detects incoming
            # payments was keeping up or had silently stopped.
            #
            # Read from this process's memory plus one bounded shared-store read
            # (the same kind crm_store.is_healthy() above already does). Deliberately
            # NOT an RPC call: /health is what the platform restarts us on.
            "monitor": {
                "last_block_checked": (wallet.get("last_block_checked")
                                       or int(wallet.get("shared_monitor_heartbeat_block") or 0)),
                "last_check_time": (wallet.get("last_check_time")
                                    or wallet.get("shared_monitor_heartbeat_at")),
            },
        },
    ), 200


@discovery_bp.route("/ready")
def ready():
    """Readiness (free, no paywall): 200 only when both dependencies are usable.

    This is the honest half of the pair that /health used to conflate. 503 here
    means "do not send me traffic" and is the correct answer while the database or
    the chain connection is unusable; it is separate from liveness precisely so a
    database blip cannot trigger a restart that cannot fix it.

    Kept separate rather than deleted because something should still be able to ask
    the question, and because a monitor that wants to alert on readiness now has a
    status code to read instead of parsing prose.

    Do NOT point the platform health check at this route. Its 503 is addressed to a
    load balancer deciding whether to send traffic, and a restart cannot repair a
    database or a rate-limited public RPC any more than it could before - pointing a
    restarter here would recreate F-10 under a new name. /health is the route for
    that, and it is liveness only on purpose.
    """
    crm_ready, blockchain_ready, monitor_ready, wallet, backend = _dependency_state()
    ready_now = bool(crm_ready and blockchain_ready)
    return jsonify(
        ready=ready_now,
        status="ready" if ready_now else "not_ready",
        service="up",
        database={"backend": backend, "ready": crm_ready},
        blockchain={"ready": blockchain_ready, "chain_id": wallet.get("chain_id"),
                    "monitor_ready": monitor_ready},
    ), 200 if ready_now else 503


@discovery_bp.route("/validation")
def validation():
    """Public validation page (free, no paywall): checkable facts only.

    HTML by default; JSON when the client sends Accept: application/json.
    Every figure is either derived from the live route table (the price range)
    or an externally linked record (third-party audit) — the page states facts
    and points at sources, nothing promotional.
    """
    from main import REAL_X402_ROUTES

    # The page used to publish a single "price_usd_per_call" taken from
    # KRISTO_SIGNAL_PRICE, so it advertised $0.003 while four of the six routes
    # charge $0.005 — a buyer who read the trust page and then called /api/stats
    # was billed 67% more than the page promised. It also called those prices
    # "unchanged since launch", which was never true: /api/sales was $0.05 on
    # 2026-08-29. A trust page does not get to round its own price down.
    _prices = sorted(float(route["price_usdc"]) for route in REAL_X402_ROUTES)
    price_floor, price_ceiling = (_prices[0], _prices[-1]) if _prices else (0.0, 0.0)

    # health() returns (response, code) — unwrap before reading the payload.
    hv = health()
    h = (hv[0] if isinstance(hv, tuple) else hv).get_json() or {}
    status = h.get("status") or "unknown"
    audit = {
        "date": "2026-10-18",
        "source": "Reddit",
        "transfers": 20,
        "total_usdc": 0.225,
        "result": "exact match with our ledger",
        "report": ("https://x402.nsgoods.org/proof/"
                   "payability-report-2026-10-18.json"),
    }
    facts = {
        "status": "operational" if status == "ok" else status,
        "uptime": {"days_green": UPTIME_DAYS_GREEN,
                   "days_total": UPTIME_DAYS_TOTAL,
                   "measured_to": UPTIME_MEASURED_TO},
        "price_usd_per_call_min": price_floor,
        "price_usd_per_call_max": price_ceiling,
        "price_note": ("six routes across two tiers; the exact atomic amount is "
                       "stated in every 402 challenge and per route in "
                       "endpoints[] below"),
        "third_party_audit": audit,
        "links": {
            "documentation": "/openapi.json",
            "quickstart": "/api/v1/quickstart",
            "payment_history": "/dashboard",
        },
        # x402 Trust — live values read from https://x402-trust.com/trust/search
        # on LAST_CHECKED (grades/scores/ids are their measurements, not ours).
        "x402_trust": {
            "profile": "https://x402-trust.com/endpoint/139372",
            "search": "https://x402-trust.com/trust/search?q=kristo",
            "badge": (
                '<a href="https://x402-trust.com/endpoint/139372">'
                '<img src="https://x402-trust.com/badge.svg?resource='
                'https%3A%2F%2Fkristo-intelligence-api.onrender.com%2Fapi'
                '%2Fstats" alt="x402 Trust — independent reliability grade, '
                'see the linked profile for the current value">'
                "</a>"
            ),
            "claim": "4/4 complete (Claim, Email confirmed, Domain file "
                     "seen, verified)",
            "scoring_note": (
                "Weighted scoring across technical fit, transparency, "
                "ecosystem presence and operational confidence; letter "
                "grades per endpoint, listed with the score each carries "
                "below. Current weights: see the leaderboard. Free snapshots "
                "refresh at least every 24 h, so the linked pages — not this "
                "dated copy — are authoritative."
            ),
            "leaderboard": "https://x402-trust.com/trust/leaderboard",
            "last_checked": "2026-11-04",
            "paid_endpoints": [
                {"path": "/api/v1/signal", "grade": "A", "score": 82.2,
                 "page": "https://x402-trust.com/endpoint/122932"},
                {"path": "/api/v1/whaleflow", "grade": "A", "score": 81.0,
                 "page": "https://x402-trust.com/endpoint/139367"},
                {"path": "/api/stats", "grade": "A", "score": 81.0,
                 "page": "https://x402-trust.com/endpoint/139372"},
                {"path": "/api/arb/opportunities", "grade": "A",
                 "score": 81.0,
                 "page": "https://x402-trust.com/endpoint/139339"},
                {"path": "/api/sales", "grade": "A", "score": 81.0,
                 "page": "https://x402-trust.com/endpoint/139342"},
                {"path": "/api/bot-status", "grade": "A", "score": 80.9,
                 "page": "https://x402-trust.com/endpoint/139366"},
            ],
        },
    }

    # ---- Нови секции за validation страницата (локални данни, без payment пипане) ----
    from datetime import datetime, timezone
    from main import _real_routes_payload
    _trust_by_path = {e["path"]: e for e in facts["x402_trust"]["paid_endpoints"]}
    _probe_checked = facts["x402_trust"]["last_checked"]
    _endpoints = []
    for _r in _real_routes_payload():
        _ep = _r.get("endpoint")
        _t = _trust_by_path.get(_ep, {})
        _endpoints.append({
            "path": _ep,
            "name": _r.get("name", ""),
            "method": _r.get("method", "GET"),
            "price_usdc": float(_r.get("price_usdc", 0)),
            "probe_status": _t.get("grade", "—"),
            "probe_score": _t.get("score"),
            "probe_last": _probe_checked,
            "probe_source": "x402-trust",
            "probe_page": _t.get("page", ""),
        })
    facts["endpoints"] = _endpoints
    facts["wellknown_links"] = {
        "trust_file": "/.well-known/x402-trust.txt",
        "x402_discovery": "/.well-known/x402.json",
    }
    facts["test_suite"] = {
        "passed": SUITE_TESTS_PASSED, "total": SUITE_TESTS_PASSED,
        "framework": "pytest",
        "last_run": SUITE_LAST_RUN,
        "note": "%d/%d tests green; adversarial audit 23/23 (mystery-agent "
                "simulation)" % (SUITE_TESTS_PASSED, SUITE_TESTS_PASSED),
    }
    # Последните реални settled трансакции (on-chain USDC -> payTo, Base;
    # източник: eth_getLogs, 30.10.2026) — външни платеци, без нашия demo портфейл.
    facts["recent_payments"] = [
        {"settled_at": "2026-10-30T07:59Z", "amount_usdc": 0.005,
         "payer": "0x54e163e9b8edda194d83f46add921bfa5fc5f4e0",
         "label": "nohumans.directory · nohumans-scout",
         "tx": "0xfcfea4afd8c1fd3793a334c7c96ad194f83949d77728206da6ff5d218eea34ef"},
        {"settled_at": "2026-10-30T08:02Z", "amount_usdc": 0.005,
         "payer": "0x54e163e9b8edda194d83f46add921bfa5fc5f4e0",
         "label": "nohumans.directory · nohumans-scout",
         "tx": "0xeb209e4d84c8d3c96e00367812da7c6256bc5166d069f03deb2494fea745716b"},
        {"settled_at": "2026-10-30T08:02Z", "amount_usdc": 0.005,
         "payer": "0x54e163e9b8edda194d83f46add921bfa5fc5f4e0",
         "label": "nohumans.directory · nohumans-scout",
         "tx": "0x276c983e68d6c9391d6b58a44d3daa867f8dddb35ea93859d644980968148b96"},
        {"settled_at": "2026-10-30T11:20Z", "amount_usdc": 0.003,
         "payer": "0xa1d1c0cf717402ff3651aa4873ccf96410b01978",
         "label": "organic buyer",
         "tx": "0x7f8bcea72e6c3b2dfeb1912c48cb74daa8cf8bbbf7df9ccd1021236c6fb4102c"},
    ]
    # "Recent" is a claim, so let a reader check it. On 2026-11-03 the newest row
    # here was already 4.7 days old, and a settlement list that has stopped moving
    # is read — fairly — as a dead product. The dates were always in the rows;
    # what was missing was one field saying where the list ends, so nobody has to
    # infer it. The page does not get to imply activity it cannot show.
    facts["payments_as_of"] = max(
        (p["settled_at"] for p in facts["recent_payments"]), default=None)
    facts["payments_count"] = len(facts["recent_payments"])
    facts["last_updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _ep_rows = "\n".join(
        f"<tr><td><code>{e['path']}</code><br>"
        f"<span style=\"color:var(--muted);font-size:12px\">{e['name']}</span></td>"
        f"<td>${e['price_usdc']:.3f}</td>"
        f"<td class=\"ok\">grade {e['probe_status']} ({e['probe_score']})</td>"
        f"<td>{e['probe_last']} · <a href=\"{e['probe_page']}\">trust page</a></td></tr>"
        for e in _endpoints)
    # The x402 Trust list was hardcoded in the HTML and disagreed with the JSON
    # facts: the HTML said 81.2 / grade B for /api/v1/signal, the JSON said 82.2
    # / grade A. Two versions of one page must not contradict each other, so the
    # HTML renders the same list the JSON publishes.
    _trust_rows = "\n".join(
        f"            <li><code>{e['path']}</code> — grade {e['grade']} "
        f"({e['score']}) · <a href=\"{e['page']}\">page</a></li>"
        for e in facts["x402_trust"]["paid_endpoints"])

    wants_json = request.accept_mimetypes.best_match(
        ["text/html", "application/json"]) == "application/json"
    if wants_json:
        return jsonify(facts)

    ok_cls = "ok" if facts["status"] == "operational" else "warn"
    # Absolute URLs for the crawler-facing tags. Built from the live host so the
    # page stays correct on Render, on a custom domain and in local tests alike.
    _site_root = request.host_url.rstrip("/")
    _canonical = _site_root + "/validation"
    _og_image = _site_root + "/static/og/kristo-og.png"
    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Validation — Kristo Intelligence</title>
<meta name="description" content="Checkable facts about the Kristo Intelligence x402 API: live status, uptime, on-chain payment history and third-party trust profiles. Free to read, no signup.">
<link rel="canonical" href="{_canonical}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Kristo Intelligence">
<meta property="og:title" content="Validation — Kristo Intelligence">
<meta property="og:description" content="Checkable facts about the Kristo Intelligence x402 API: live status, uptime, on-chain payment history and third-party trust profiles.">
<meta property="og:url" content="{_canonical}">
<meta property="og:image" content="{_og_image}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="Validation — Kristo Intelligence">
<meta name="twitter:description" content="Checkable facts about the Kristo Intelligence x402 API, free to read.">
<meta name="twitter:image" content="{_og_image}">
<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@type": "WebPage",
  "name": "Validation — Kristo Intelligence",
  "url": "{_canonical}",
  "isPartOf": {{ "@type": "WebSite", "name": "Kristo Intelligence",
                 "url": "{_site_root}/" }}
}}
</script>
<style>
  :root {{ --bg:#0a0e14; --panel:#11161f; --border:#232c3b; --text:#d7dde6;
           --muted:#8b96a5; --accent:#38bdf8; --green:#34d399; --amber:#fbbf24; }}
  body {{ background:var(--bg); color:var(--text); margin:0; padding:40px 20px;
          font-family:'Segoe UI',system-ui,sans-serif; font-size:15px;
          line-height:1.55; }}
  main {{ max-width:720px; margin:0 auto; }}
  h1 {{ font-size:19px; font-weight:600; letter-spacing:.3px; }}
  h1 span {{ color:var(--accent); }}
  .panel {{ background:var(--panel); border:1px solid var(--border);
            border-radius:12px; padding:20px 24px; margin:16px 0; }}
  dl {{ margin:0; }}
  dt {{ color:var(--muted); font-size:11px; text-transform:uppercase;
        letter-spacing:1px; margin-top:16px; }}
  dt:first-child {{ margin-top:0; }}
  dd {{ margin:5px 0 0; }}
  .ok {{ color:var(--green); font-weight:600; }}
  .warn {{ color:var(--amber); font-weight:600; }}
  a {{ color:var(--accent); }}
  code {{ font-family:ui-monospace,Consolas,monospace; font-size:13px;
          background:#0f172a; border:1px solid var(--border);
          border-radius:6px; padding:1px 6px; }}
  table {{ border-collapse:collapse; width:100%; margin-top:8px; font-size:13px; }}
  th, td {{ border:1px solid var(--border); padding:6px 8px; text-align:left; }}
  th {{ color:var(--muted); font-size:11px; text-transform:uppercase; letter-spacing:1px; }}
  footer {{ color:var(--muted); font-size:12px; margin-top:22px; }}
</style>
</head>
<body>
<main>
  <h1>KRISTO <span>INTELLIGENCE</span> — validation</h1>
  <div class="panel">
    <dl>
      <dt>Service status</dt>
      <dd class="{ok_cls}">{facts["status"]}</dd>
      <dt>Uptime</dt>
      <dd>{facts["uptime"]["days_green"]} of {facts["uptime"]["days_total"]} days
        green, to {facts["uptime"]["measured_to"]}</dd>
      <dt>Price</dt>
      <dd>${price_floor:.3f}–${price_ceiling:.3f} per call, depending on the
        route — the 402 challenge states the exact amount before you pay
        (<a href="/llms.txt">per-route prices</a>)</dd>
      <dt>Third-party audit — Reddit, {audit["date"]}</dt>
      <dd>{audit["transfers"]} transfers, {audit["total_usdc"]} USDC —
        {audit["result"]}.
        Report: <a href="{audit["report"]}">payability-report-{audit["date"]}.json</a></dd>
      <dt>Documentation</dt>
      <dd><a href="/openapi.json">OpenAPI</a> ·
          <a href="/api/v1/quickstart">quickstart</a></dd>
      <dt>Payment history</dt>
      <dd><a href="/dashboard">on-chain payments (dashboard)</a></dd>
    </dl>
  </div>
  <div class="panel">
    <dl>
      <dt>x402 Trust — provider profile</dt>
      <dd><a href="https://x402-trust.com/endpoint/139372">endpoint 139372
            (profile)</a> · <a
            href="https://x402-trust.com/trust/search?q=kristo">search
            "kristo"</a></dd>
      <dt>Badge (auto-updates with their score)</dt>
      <dd><a href="https://x402-trust.com/endpoint/139372"><img
            src="https://x402-trust.com/badge.svg?resource=https%3A%2F%2Fkristo-intelligence-api.onrender.com%2Fapi%2Fstats"
            alt="x402 Trust: grade B, recommendation proceed"
            height="20"></a></dd>
      <dt>Claim status</dt>
      <dd class="ok">4/4 complete — Claim ✓ · Email confirmed ✓ ·
          Domain file seen ✓ · verified ✓</dd>
      <dt>What x402 Trust measures</dt>
      <dd>Independent probes scored with a weighted mix of technical fit,
          transparency, ecosystem presence and operational confidence; each
          endpoint gets a letter grade (ours currently <b>A–B</b>). The
          current weighting lives on their
          <a href="https://x402-trust.com/trust/leaderboard">leaderboard</a>.
          Free snapshots refresh at least every 24 hours.</dd>
      <dt>Paid endpoints on x402 Trust</dt>
      <dd><ul style="margin:6px 0 0; padding-left:18px;">
{_trust_rows}
          </ul></dd>
      <dt>Last checked</dt>
      <dd>{facts['x402_trust']['last_checked']} (grades/scores read live from x402 Trust that day)</dd>
    </dl>
  </div>
  <div class="panel">
    <dl>
      <dt>Paid endpoints &amp; prices — 7 live x402 routes</dt>
      <dd><table>
        <tr><th>Endpoint</th><th>Price</th><th>Probe status</th><th>Last probe</th></tr>
        {_ep_rows}
      </table>
      Discovery files: <a href="/.well-known/x402-trust.txt">/.well-known/x402-trust.txt</a>
      ∙ <a href="/.well-known/x402.json">/.well-known/x402.json</a>
      (probe status = x402-trust per-endpoint grade, checked {_probe_checked})</dd>
    </dl>
  </div>
  <div class="panel">
    <dl>
      <dt>Test suite</dt>
      <dd class="ok">{SUITE_TESTS_PASSED}/{SUITE_TESTS_PASSED} tests green (pytest) — last run {SUITE_LAST_RUN}</dd>
      <dd>Adversarial audit: 23/23 (mystery-agent simulation)</dd>
    </dl>
  </div>
  <div class="panel">
    <dl>
      <dt>Recent settled payments (on-chain USDC → payTo, Base)</dt>
      <dd><table>
        <tr><th>Settled (UTC)</th><th>Amount</th><th>Payer</th><th>Label</th><th>Transaction</th></tr>
        <tr><td>2026-10-30 07:59</td><td>0.005 USDC</td><td><code>0x54e163e9…5f4e0</code></td><td>nohumans.directory · nohumans-scout</td><td><a href="https://basescan.org/tx/0xfcfea4afd8c1fd3793a334c7c96ad194f83949d77728206da6ff5d218eea34ef">0xfcfea4af…a34ef</a></td></tr>
        <tr><td>2026-10-30 08:02</td><td>0.005 USDC</td><td><code>0x54e163e9…5f4e0</code></td><td>nohumans.directory · nohumans-scout</td><td><a href="https://basescan.org/tx/0xeb209e4d84c8d3c96e00367812da7c6256bc5166d069f03deb2494fea745716b">0xeb209e4d…5716b</a></td></tr>
        <tr><td>2026-10-30 08:02</td><td>0.005 USDC</td><td><code>0x54e163e9…5f4e0</code></td><td>nohumans.directory · nohumans-scout</td><td><a href="https://basescan.org/tx/0x276c983e68d6c9391d6b58a44d3daa867f8dddb35ea93859d644980968148b96">0x276c983e…48b96</a></td></tr>
        <tr><td>2026-10-30 11:20</td><td>0.003 USDC</td><td><code>0xa1d1c0cf…01978</code></td><td>organic buyer</td><td><a href="https://basescan.org/tx/0x7f8bcea72e6c3b2dfeb1912c48cb74daa8cf8bbbf7df9ccd1021236c6fb4102c">0x7f8bcea7…4102c</a></td></tr>
      </table></dd>
    </dl>
  </div>
  <footer>Last updated: <b>{facts["last_updated"]}</b> (UTC) · Each figure above links
    to its source; the JSON view is at <code>Accept: application/json</code> on this URL.</footer>
</main>
</body>
</html>
"""
    return page


# Shared styling for the human-facing pages below. A plain string, so the CSS
# braces stay literal inside the f-strings that interpolate it.
_PAGE_CSS = """
  :root { --bg:#0a0e14; --panel:#11161f; --border:#232c3b; --text:#d7dde6;
           --muted:#8b96a5; --accent:#38bdf8; --green:#34d399; --amber:#fbbf24; }
  body { background:var(--bg); color:var(--text); margin:0; padding:40px 20px;
          font-family:'Segoe UI',system-ui,sans-serif; font-size:15px;
          line-height:1.55; }
  main { max-width:760px; margin:0 auto; }
  h1 { font-size:19px; font-weight:600; letter-spacing:.3px; }
  h1 span { color:var(--accent); }
  h2 { font-size:12px; text-transform:uppercase; letter-spacing:1px;
        color:var(--muted); margin:0 0 12px; font-weight:600; }
  .panel { background:var(--panel); border:1px solid var(--border);
            border-radius:12px; padding:20px 24px; margin:16px 0; }
  table { width:100%; border-collapse:collapse; font-size:14px; }
  th, td { text-align:left; padding:7px 10px 7px 0;
            border-bottom:1px solid var(--border); vertical-align:top; }
  th { color:var(--muted); font-size:11px; text-transform:uppercase;
        letter-spacing:.6px; font-weight:600; }
  code { background:#0d1117; border:1px solid var(--border); border-radius:5px;
          padding:1px 5px; font-size:13px; }
  a { color:var(--accent); text-decoration:none; }
  a:hover { text-decoration:underline; }
  .price { white-space:nowrap; font-weight:600; }
  .ok { color:var(--green); }
  ul { padding-left:18px; margin:8px 0 0; }
  li { margin:4px 0; }
  footer { color:var(--muted); font-size:12px; margin-top:26px;
            border-top:1px solid var(--border); padding-top:14px; }
"""

_CONTACT_EMAIL = "hristovdimitri2@gmail.com"


def _human_page_head(title: str, description: str, path: str,
                     site_root: str) -> str:
    """The crawler-facing head shared by the human pages, so the tags cannot drift."""
    canonical = site_root + path
    og_image = site_root + "/static/og/kristo-og.png"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<meta name="description" content="{description}">
<link rel="canonical" href="{canonical}">
<meta property="og:type" content="website">
<meta property="og:site_name" content="Kristo Intelligence">
<meta property="og:title" content="{title}">
<meta property="og:description" content="{description}">
<meta property="og:url" content="{canonical}">
<meta property="og:image" content="{og_image}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="twitter:title" content="{title}">
<meta name="twitter:description" content="{description}">
<meta name="twitter:image" content="{og_image}">
<script type="application/ld+json">
{{
  "@context": "https://schema.org",
  "@type": "WebPage",
  "name": "{title}",
  "url": "{canonical}",
  "isPartOf": {{ "@type": "WebSite", "name": "Kristo Intelligence",
                 "url": "{site_root}/" }}
}}
</script>
<style>{_PAGE_CSS}</style>
</head>
<body>
<main>
"""


@discovery_bp.route("/pricing")
def pricing():
    """The pricing page directories check for, built from the live route table.

    x402-list.com lists a reachable pricing page among its site-and-docs signals.
    This path answered 404, which cost a signal and left an agent with only
    llms.txt to read. Every figure below comes from REAL_X402_ROUTES — the same
    table the 402 challenges are built from — so this page cannot advertise a
    price the service will not charge.
    """
    from main import (FREE_TIER_LIMIT, REAL_X402_ROUTES, VIP_MONTHLY_USDC,
                      VIP_THRESHOLD_USDC)

    site_root = request.host_url.rstrip("/")
    ordered = sorted(REAL_X402_ROUTES,
                     key=lambda r: (float(r["price_usdc"]), r["endpoint"]))
    rows = "".join(
        f"<tr><td><code>{html.escape(r['endpoint'])}</code></td>"
        f"<td class='price'>${float(r['price_usdc']):.3f}</td>"
        f"<td>{html.escape(r.get('description') or r.get('name') or '')}</td>"
        f"<td><a href=\"{html.escape(r['endpoint'])}/sample\">free sample</a></td>"
        f"</tr>"
        for r in ordered)
    cheapest = float(ordered[0]["price_usdc"])
    dearest = float(ordered[-1]["price_usdc"])

    if FREE_TIER_LIMIT:
        free_line = (f"{FREE_TIER_LIMIT} free call per client; after that every "
                     "unpaid call returns HTTP 402.")
    else:
        free_line = ("No free calls. Every unpaid call to a paid route returns "
                     "HTTP 402 with the terms — a quote, not a charge.")

    page = _human_page_head(
        "Pricing — Kristo Intelligence",
        f"Six x402 routes on Base, ${cheapest:.3f} to ${dearest:.3f} USDC per "
        "call. Pay per call, no API key, no signup, no subscription. Free "
        "samples and machine-readable specs included.",
        "/pricing", site_root)
    page += f"""
<h1>Pricing <span>— pay per call, nothing else</span></h1>
<div class="panel">
  <h2>Paid routes — USDC on Base, x402</h2>
  <table>
    <tr><th>Endpoint</th><th>Price</th><th>Returns</th><th>Try it</th></tr>
    {rows}
  </table>
  <p>{free_line} No API key, no account, no subscription: the price of a call is
     stated in its own HTTP 402 challenge before you pay anything, and the same
     figure appears here, in <a href="/llms.txt">llms.txt</a> and in
     <a href="/openapi.json">openapi.json</a>.</p>
  <p>Range: <b>${cheapest:.3f}–${dearest:.3f} USDC</b> per call. Payment settles
     on Base; nothing is billed later.</p>
</div>
<div class="panel">
  <h2>How you pay — two rails</h2>
  <ul>
    <li><b>Preferred: <code>PAYMENT-SIGNATURE</code></b> (x402 v2). Sign an
        EIP-3009 <code>transferWithAuthorization</code> and retry; a facilitator
        verifies and settles it. No gas, and nothing waits on a block.
        <code>X-PAYMENT</code> is accepted as the v1 name.</li>
    <li><b>Alternative: <code>X-Payment-Proof</code></b>. Send USDC yourself and
        supply the proof. Self-describing, but it waits <b>3 confirmations,
        about 6 seconds</b> before the data is released.</li>
  </ul>
  <p>Status codes: <code>402</code> no credential · <code>401</code> credential
     unusable · <code>425</code> settlement in flight, retry · <code>200</code>
     paid and delivered.</p>
</div>
<div class="panel">
  <h2>Free — no payment, no key</h2>
  <ul>
    <li>The six <code>/sample</code> routes: one real payload shape per paid
        route, with a marker making clear it is an example.</li>
    <li><a href="/health">/health</a> · <a href="/validation">/validation</a>
        (live status, uptime, on-chain payment history) ·
        <a href="/llms.txt">/llms.txt</a> ·
        <a href="/openapi.json">/openapi.json</a> ·
        <a href="/agents.json">/agents.json</a> ·
        <a href="/mcp.json">/mcp.json</a> ·
        <a href="/.well-known/x402.json">/.well-known/x402.json</a></li>
  </ul>
</div>
<div class="panel">
  <h2>Human products — separate, bought with a card</h2>
  <ul>
    <li>Research plans and the monthly VIP are sold through Stripe on the
        <a href="/launch">launch page</a>. They are Telegram products.</li>
    <li><b>The monthly VIP (${int(VIP_MONTHLY_USDC)}) does not unlock the
        API.</b> API access is per call, in USDC on Base, at the prices above.</li>
    <li>A <b>single</b> USDC transfer of at least ${VIP_THRESHOLD_USDC} to the
        receiver generates a Telegram VIP invite code. No API route costs
        anything near that, so ordinary per-call usage will not reach it —
        that threshold is for large one-off transfers.</li>
  </ul>
</div>
<footer>Prices are generated from the same table the payment challenges are
  built from. Machine-readable: <a href="/llms.txt">llms.txt</a> ·
  <a href="/openapi.json">openapi.json</a> ·
  <a href="/.well-known/x402.json">.well-known/x402.json</a> ·
  <a href="/validation">validation</a> · <a href="/terms">terms</a></footer>
</main>
</body>
</html>
"""
    return page


@discovery_bp.route("/terms")
def terms():
    """The terms page directories check for, and the honest fine print.

    Also 404 before. Kept deliberately plain: what we license, what the data is
    not, what a payment does and does not buy.
    """
    site_root = request.host_url.rstrip("/")
    page = _human_page_head(
        "Terms — Kristo Intelligence",
        "Terms for the Kristo Intelligence x402 API: MIT-licensed code, data "
        "provided as is, not financial advice, pay-per-call in USDC on Base.",
        "/terms", site_root)
    page += f"""
<h1>Terms <span>— short, and meant to be read</span></h1>
<div class="panel">
  <h2>The software</h2>
  <p>This repository is released under the <b>MIT licence</b> — see
     <a href="https://github.com/hristovdimitri2-hub/kristo-intelligence-6/blob/main/LICENSE">LICENSE</a>.
     You may use, copy, modify and redistribute it, including commercially,
     provided the copyright notice and permission notice are kept.</p>
</div>
<div class="panel">
  <h2>The data and the API</h2>
  <p>Every response is provided <b>as is</b>, without warranty of any kind,
     express or implied, including merchantability or fitness for a particular
     purpose. Figures are derived from third-party sources — market feeds, RPC
     providers and public chain data — and can be delayed, incomplete or wrong.
     Each response states when it was produced and, where relevant, the block it
     was read at; check those fields rather than assuming freshness.</p>
</div>
<div class="panel">
  <h2>Not financial advice</h2>
  <p>Nothing served here is investment, legal or tax advice, or a
     recommendation to buy or sell anything. Signals and flow data are
     <b>inputs to your own judgement</b>, not instructions. You are solely
     responsible for any decision you take and for complying with the laws that
     apply to you.</p>
</div>
<div class="panel">
  <h2>Paying</h2>
  <ul>
    <li>Calls are paid per call in <b>USDC on Base</b> over x402. There is no
        account, no key and no recurring charge.</li>
    <li>An HTTP <code>402</code> is a <b>quote, not a charge</b>. Nothing is
        taken until you authorise a payment.</li>
    <li>A settled payment is delivered once. Replaying the same credential is
        rejected by design rather than served twice.</li>
    <li>Settled on-chain transfers cannot be reversed by us, and we cannot
        recover funds sent to a wrong address. Check the address in the 402
        challenge against <a href="/validation">/validation</a> before paying.</li>
  </ul>
</div>
<div class="panel">
  <h2>Card purchases (Stripe)</h2>
  <p>Research plans and the monthly VIP are sold through Stripe and are
     <b>Telegram products</b>; they do not unlock the API. Refund requests go to
     <a href="mailto:{_CONTACT_EMAIL}">{_CONTACT_EMAIL}</a> and are handled case
     by case. The monthly VIP is a subscription and can be cancelled.</p>
</div>
<div class="panel">
  <h2>Privacy and acceptable use</h2>
  <ul>
    <li>The API sets no accounts and no tracking cookies. Requests are logged
        for rate limiting, abuse prevention and the counters published on
        <a href="/validation">/validation</a>.</li>
    <li>Payments are on a public chain. Payer addresses and amounts are public
        and are not private data.</li>
    <li>Do not use the service unlawfully, attempt to bypass payment, or resell
        it in a way that misrepresents what it is.</li>
    <li>We may change prices, routes or availability. The price of a call is
        always the one in its own 402 challenge at the moment you call.</li>
  </ul>
</div>
<footer>Questions: <a href="mailto:{_CONTACT_EMAIL}">{_CONTACT_EMAIL}</a> ·
  <a href="/pricing">pricing</a> · <a href="/llms.txt">llms.txt</a> ·
  <a href="/validation">validation</a> · <a href="/">home</a></footer>
</main>
</body>
</html>
"""
    return page


@discovery_bp.route("/api/v1/signal/sample")
def signal_sample():
    """Free sample: input schema + representative output (no payment).

    Отговаря на nohumans warning `no_sample_query` (01.11.2026): агентите
    виждат реалната форма на отговора ПРЕДИ да платят. Static example —
    NOT live data; live values require a paid call ($0.003, x402 on Base).
    """
    return jsonify({
        "input": {
            "type": "http",
            "method": "GET",
            "queryParams": {},
            "note": ("No parameters — GET /api/v1/signal takes no query "
                     "params (empty queryParams schema)."),
        },
        "output_example": {
            "generated_at": "2026-11-01T10:00:00+00:00",
            "signals": [
                {"token": "ETH", "action": "monitor", "confidence": 0.62,
                 "price_usd": 2387.78,
                 "reasoning": "Range-bound; volume flat vs 24h average.",
                 "note": ""},
                {"token": "ONDO", "action": "hold", "confidence": 0.55,
                 "price_usd": 0.87,
                 "reasoning": "No fresh catalyst; uptrend intact.", "note": ""},
                {"token": "KAITO", "action": "monitor", "confidence": 0.50,
                 "price_usd": 1.42,
                 "reasoning": "Sideways; waiting for breakout volume.",
                 "note": ""},
                {"token": "DEGEN", "action": "monitor", "confidence": 0.48,
                 "price_usd": 0.0042,
                 "reasoning": "Low-liquidity drift; no entry signal.",
                 "note": ""},
            ],
        },
        "paid_route": "/api/v1/signal",
        "disclaimer": _sample_disclaimer("/api/v1/signal"),
    }), 200


@discovery_bp.route("/api/stats/sample")
def stats_sample():
    """Free static sample of GET /api/stats (no payment)."""
    return jsonify({
        "input": {"method": "GET", "parameters": [],
                  "parameters_note": "No parameters — call as-is.",
                  "example_url": request.host_url.rstrip("/") + "/api/stats"},
        "output_example": {
            "date": "2026-11-01",
            "requests_today": 120, "requests_total": 5400,
            "sales_today": 3, "sales_total_usdc": 0.011,
            "top_paths": [{"path": "/api/v1/signal", "count": 70},
                          {"path": "/api/stats", "count": 30}],
            "market": {"eth_usd": 2387.78, "fear_greed": 61},
        },
        "paid_route": "/api/stats",
        "disclaimer": _sample_disclaimer("/api/stats"),
    }), 200


@discovery_bp.route("/api/v1/whaleflow/sample")
def whaleflow_sample():
    """Free static sample of GET /api/v1/whaleflow (no payment)."""
    return jsonify({
        "input": {"method": "GET", "parameters": [],
                  "parameters_note": "No parameters — call as-is.",
                  "example_url": request.host_url.rstrip("/") + "/api/v1/whaleflow"},
        "output_example": {
            "chain": "base",
            "min_amount_usd": 5000000,
            "transfers": [
                {"amount_usd": 12500000, "token": "USDC",
                 "from": "0x1111111111111111111111111111111111111111",
                 "to": "0x2222222222222222222222222222222222222222",
                 "counterparty_label": "exchange-hot-wallet",
                 "tx": "0x…64-hex", "block": 43200000},
            ],
        },
        "paid_route": "/api/v1/whaleflow",
        "disclaimer": _sample_disclaimer("/api/v1/whaleflow"),
    }), 200


@discovery_bp.route("/api/sales/sample")
def sales_sample():
    """Free static sample of GET /api/sales (no payment)."""
    return jsonify({
        "input": {"method": "GET", "parameters": [],
                  "parameters_note": "No parameters — call as-is.",
                  "example_url": request.host_url.rstrip("/") + "/api/sales"},
        "output_example": {
            "note": "on-chain USDC settlements to the receiver (Base)",
            "sales": [
                {"settled_at": "2026-10-30T08:02:00+00:00",
                 "amount_usdc": 0.005,
                 "payer": "0x54e163e9b8edda194d83f46add921bfa5fc5f4e0",
                 "tx": "0xeb209e4d…5716b"},
            ],
        },
        "paid_route": "/api/sales",
        "disclaimer": _sample_disclaimer("/api/sales"),
    }), 200


@discovery_bp.route("/api/v1/seller-audit")
def seller_audit():
    """Free, honest on-chain audit of THIS service's own receiver.

    WHAT IT IS FOR. Measured demand, from a directory that logs what agents
    search for, puts seller trust at the very top: `seller conformance`,
    `settlement ledger` and `funded sellers`, each asked by ~50 independent
    client addresses over eight consecutive days. Their own summary of the gap:
    a search with no good answer is a service nobody is selling yet. This
    publishes the report those queries are asking for — about ourselves, in the
    exact shape any seller would receive.

    WHY IT ONLY AUDITS OUR OWN RECEIVER. The engine in services/seller_audit.py
    reads any receiver's incoming USDC on Base; that broader form is a paid
    product. This route is its free proof, and deliberately cannot be aimed at a
    thousand addresses by one caller.

    WHY IT READS THE SHARED STORE AND NOT THE CHAIN. The rows come from the
    monitor's continuous chain scan, which both processes share through Postgres.
    A chain sweep here would put a multi-second eth_getLogs walk inside an HTTP
    request path, and worse, it would repeat the split fixed in dc39a61: the
    worker would warm its own memory and this process would read an empty one.

    "COULD NOT LOOK" IS NEVER PUBLISHED AS "FOUND NOTHING". Whether the window
    was read end to end is a question about the MONITOR's health, not about this
    table, so coverage comes from the SHARED heartbeat. No heartbeat and no rows
    is `partial`, never a zero — and an unreadable store is `failed`, with its
    reason, rather than an exception on a page meant to be read by a stranger.
    """
    from services.seller_audit import build_audit, MAX_AUDIT_DAYS, MIN_AUDIT_DAYS

    import sys as _sys

    _entry = _sys.modules.get("__main__")
    _is_main = (str(getattr(_entry, "__file__", "") or "")
                .replace("\\", "/").rsplit("/", 1)[-1] == "main.py")
    if _is_main:
        dashboard_db = getattr(_entry, "dashboard_db", None)
        receiver = getattr(_entry, "X402_RECEIVER_ADDRESS", "") or ""
        heartbeat_key = getattr(_entry, "SALES_SCAN_HEARTBEAT_KEY",
                                "sales_scan_heartbeat_at")
    else:
        from main import dashboard_db, X402_RECEIVER_ADDRESS
        from main import SALES_SCAN_HEARTBEAT_KEY
        receiver = X402_RECEIVER_ADDRESS or ""
        heartbeat_key = SALES_SCAN_HEARTBEAT_KEY

    try:
        days = int(request.args.get("days") or 7)
    except (TypeError, ValueError):
        days = 7
    days = max(MIN_AUDIT_DAYS, min(MAX_AUDIT_DAYS, days))

    cutoff = (datetime.now(timezone.utc)
              - timedelta(days=days)).isoformat()

    rows: list = []
    store_error = ""
    try:
        if dashboard_db is None:
            store_error = "no_shared_store_configured"
        else:
            summary = dashboard_db.sales_summary(history_limit=1000)
            rows = list((summary or {}).get("history") or [])
    except Exception as exc:
        store_error = f"store_unreadable: {type(exc).__name__}"

    # Was the window actually read? That is the monitor's answer, published to the
    # shared store, not something this table can assert about itself.
    scanned_recently = False
    try:
        if dashboard_db is not None:
            scanned_recently = _fresh_stamp(dashboard_db.get_meta(heartbeat_key))
    except Exception:
        scanned_recently = False

    transfers = []
    for row in rows:
        try:
            ts = str(row.get("ts") or "")
            if cutoff and ts and ts < cutoff:
                continue
            transfers.append({
                "tx_hash": row.get("tx_hash") or "",
                "payer": row.get("sender") or "",
                "amount_usdc": float(row.get("amount_usdc") or 0.0),
                "block_number": row.get("block_number") or 0,
            })
        except (TypeError, ValueError):
            continue

    coverage = {"complete": bool(scanned_recently and not store_error)}
    # The old expression was `store_error or ("" if scanned_recently else "")`:
    # both branches returned "", so the reason for incomplete coverage was never
    # passed. Keep the honest split: a store that cannot be read is `failed`
    # (the table is not evidence at all), while a store that is fine but has no
    # fresh monitor heartbeat is `partial` (the window was not read end to end).
    # The heartbeat reason rides in `coverage.reason`, so it is stated without
    # turning a readable-but-unread window into a failed read.
    failed = store_error
    if not scanned_recently and not store_error:
        coverage["reason"] = "no_recent_scan"
    report = build_audit(transfers, coverage, receiver=receiver, days=days,
                         failed_reason=failed)
    report["source"] = ("this service's own monitor records, written to the shared "
                        "store as the chain was scanned")
    report["scope_note"] = ("Free and fixed to this service's own receiver. The same "
                            "engine reads any receiver on request.")
    return jsonify(report), 200


@discovery_bp.route("/api/v1/verify-seller")
def verify_seller():
    """PAID: the same honest audit, for any receiver the caller names.

    This is the broader form the free route above points at. It reads the chain
    directly rather than the shared store, because the receiver is not ours and
    no monitor of ours is already sweeping it.

    WHY IT COSTS WHAT IT COSTS. A 7-day window is thousands of adaptive
    eth_getLogs chunks, so this is the only route we sell that does real RPC work
    per call instead of serving a snapshot. The price and the census behind it
    live at KRISTO_VERIFY_SELLER_PRICE in config.py; what matters here is that
    the amount is read from the same single price source as every other route, so
    the challenge cannot quote a number of its own.

    THE GUARDS ARE THE PRODUCT'S HONESTY, not decoration:
      - the address must parse, or we would read a padded topic for a typo and
        report a clean zero for an address that does not exist
      - `days` is clamped to the engine's own bounds, never trusted
      - the window actually walked is reported back in `coverage.lookback_days`,
        so a report can be checked against the scan instead of believed
      - a chain failure is `read: "failed"` with its reason. It is never an
        exception, an empty report, or a zero: a buyer who paid $1 and got
        "\"distinct payers\": 0" because the RPC blinked has been told a lie, and
        the one thing this product cannot do is tell that particular lie.

    The free sibling exists on purpose. An agent should be able to see the exact
    report shape, including how coverage is stated, before paying a hundred times
    what our other routes cost.
    """
    from services.seller_audit import (
        audit_receiver, cached_audit, store_audit,
        DEFAULT_AUDIT_DAYS, MAX_AUDIT_DAYS, MIN_AUDIT_DAYS,
    )

    raw = (request.args.get("receiver") or "").strip()
    if not raw:
        return jsonify({
            "ok": False,
            "error": "receiver_required",
            "message": ("Name the Base address to audit, e.g. "
                        "?receiver=0xd4cdA900839c0feD4374EE37EA0dbe8E4C6fd08f"),
            "free_sample": request.host_url.rstrip("/") + "/api/v1/verify-seller/sample",
        }), 400

    # Validate before anything else. Reading logs for a malformed address would
    # return an empty set, which this engine would honestly label a clean read —
    # a truthful statement about an address that is not one.
    receiver = raw
    try:
        from web3 import Web3
        if not Web3.is_address(raw):
            raise ValueError("not an address")
        receiver = Web3.to_checksum_address(raw)
    except Exception:
        return jsonify({
            "ok": False,
            "error": "invalid_receiver",
            "message": ("`receiver` must be a 40-hex-character EVM address, "
                        "with or without the 0x prefix."),
            "received": raw[:64],
        }), 400

    try:
        days = int(request.args.get("days") or DEFAULT_AUDIT_DAYS)
    except (TypeError, ValueError):
        days = DEFAULT_AUDIT_DAYS
    days = max(MIN_AUDIT_DAYS, min(MAX_AUDIT_DAYS, days))

    # A cached report is served as-is and says so: the age is in the payload, and
    # a 15-minute-old on-chain read of a slow-moving address is not a stale fact,
    # it is the same fact.
    hit = cached_audit(receiver, days)
    if hit is not None:
        hit["served_from_cache"] = True
        return jsonify(hit), 200

    report = audit_receiver(receiver, days)
    report["served_from_cache"] = False
    report["source"] = ("the chain, read on demand for the address you named "
                        "(eth_getLogs on USDC transfers to that exact address)")
    report["scope_note"] = ("Reads any receiver on request. The free route "
                            "/api/v1/seller-audit is the same engine fixed to "
                            "this service's own address.")
    report["buyer_note"] = (
        "A distinct paying address is not a distinct customer, and a clean read "
        "is not an endorsement: this reports who paid, never whether the seller "
        "is honest. Read `coverage` before the headline — if `complete` is false, "
        "the window was not read end to end and the figures are a floor."
    )
    store_audit(receiver, days, report)
    return jsonify(report), 200


@discovery_bp.route("/api/v1/verify-seller/sample")
def verify_seller_sample():
    """Free sample of the $1.00 seller-verification report.

    Static, like every other sample here. It shows the shape AND the honesty
    rules — `coverage.complete` false with a `partial` read — because a buyer
    needs to see that an incomplete read is published as incomplete before
    trusting a complete one.
    """
    from services.seller_audit import MAX_AUDIT_DAYS, MIN_AUDIT_DAYS

    return jsonify({
        "input": {
            "type": "http",
            "method": "GET",
            "queryParams": {
                "receiver": "Base address to audit (0x + 40 hex). Required.",
                "days": f"window in days, {MIN_AUDIT_DAYS}-{MAX_AUDIT_DAYS}, "
                        "default 7. Optional.",
            },
            "example_url": (request.host_url.rstrip("/")
                            + "/api/v1/verify-seller?receiver="
                              "0xd4cdA900839c0feD4374EE37EA0dbe8E4C6fd08f&days=7"),
        },
        "output_example": {
            "ok": True,
            "receiver": "0xd4cdA900839c0feD4374EE37EA0dbe8E4C6fd08f",
            "window_days": 7,
            "read": "clean",
            "coverage": {
                "complete": True,
                "lookback_days": 7,
                "scanned_blocks": 201600,
                "failed_ranges": 0,
                "split_retries": 4,
            },
            "payer_analysis": {
                "total_txs": 6,
                "total_usdc": 0.018,
                "unique_payers": 3,
                "external_unique_payers": 2,
                "known_verification_txs": 3,
                "repeat_payers": 1,
                "avg_check_usdc": 0.003,
                "noise": {"large_txs": 0, "large_tx_count": 0},
            },
            "verdict": ("Read cleanly: 2 distinct paying address(es), 1 of them "
                        "paid more than once."),
            "notes": [
                "Only incoming USDC transfers on Base to this exact address are read.",
                "Transfers at or above the large-transfer threshold are counted as "
                "treasury/exchange flows, not as per-call payments.",
                "Known reviewer/verification addresses are counted separately so they "
                "cannot inflate the customer count.",
                "A distinct paying address is not a distinct customer: one operator "
                "can pay from several wallets, and several agents can share one.",
            ],
            "served_from_cache": False,
        },
        "paid_route": "/api/v1/verify-seller",
        # The disclaimer is generated from the price map, like every other
        # sample's: a typed price here is how the free sample for
        # /api/v1/whaleflow once overquoted its own product by 67%. The
        # `partial` case below is extra honesty this route needs and the others
        # do not, so it is carried alongside the generated sentence rather than
        # replacing it.
        "disclaimer": (_sample_disclaimer("/api/v1/verify-seller")
                       + " The `partial` case looks like this: read \"partial\", "
                         "coverage.complete false, and a verdict saying the "
                         "figures are a floor rather than a zero."),
    }), 200


@discovery_bp.route("/api/bot-status/sample")
def bot_status_sample():
    """Free static sample of GET /api/bot-status (no payment)."""
    return jsonify({
        "input": {"method": "GET", "parameters": [],
                  "parameters_note": "No parameters — call as-is.",
                  "example_url": request.host_url.rstrip("/") + "/api/bot-status"},
        "output_example": {
            "status": "ok",
            "heartbeat_at": "2026-11-01T10:00:00+00:00",
            "subscribers": 12,
            "commands_processed": 48,
            "service_wallet": {"state": "active"},
        },
        "paid_route": "/api/bot-status",
        "disclaimer": _sample_disclaimer("/api/bot-status"),
    }), 200


@discovery_bp.route("/api/arb/opportunities/sample")
def arb_sample():
    """Free static sample of GET /api/arb/opportunities (no payment)."""
    return jsonify({
        "input": {"method": "GET", "parameters": [],
                  "parameters_note": "No parameters — call as-is.",
                  "example_url": request.host_url.rstrip("/") + "/api/arb/opportunities"},
        "output_example": {
            "refresh_seconds": 60,
            "opportunities": [
                {"pair": "WETH/USDC", "buy_dex": "Uniswap V3",
                 "sell_dex": "Aerodrome", "spread_pct": 0.42,
                 "gross_profit_pct": 0.38,
                 "refreshed_at": "2026-11-01T10:00:00+00:00"},
            ],
        },
        "paid_route": "/api/arb/opportunities",
        "disclaimer": _sample_disclaimer("/api/arb/opportunities"),
    }), 200


# ── A2A (Agent2Agent) surface ───────────────────────────────────────────────
# An Agent Card at the standard path, plus a JSON-RPC endpoint that does one
# real, useful, honest thing: it answers a request for one of our data products
# with that product's FREE SAMPLE and the exact terms to buy the live one.
#
# WHY IT DOES NOT DELIVER THE PAID DATA ITSELF. These products are sold per call
# through the x402 paywall on the HTTP routes. An A2A endpoint that handed the
# live payload over for free would give the product away; one that claimed to
# sell it with no payment rail would be lying. So the skill really is "show me
# the shape and the price" — which is exactly what the free /sample routes
# already answer — and the paid path stays where it is and is pointed to
# explicitly. Nothing here invents data and nothing here undercuts the paywall.
#
# THE CARD MUST NOT DESCRIBE MORE THAN THIS. `streaming` and `pushNotifications`
# are declared FALSE, and no security scheme is advertised, because neither is
# implemented and this endpoint needs no credential. A card that advertises a
# method answering -32601 is precisely the "card pointing at a non-working
# endpoint" failure the card exists to avoid.
A2A_PROTOCOL_VERSION = "0.3.0"
A2A_AGENT_VERSION = "1.0.0"

#: Tasks live in memory and expire. This surface is a discovery convenience, not
#: a system of record, and a task that outlives its process is gone — saying so
#: is better than a lookup that appears to succeed and silently invents one.
A2A_TASK_TTL_SECONDS = 3600
A2A_MAX_TASKS = 500
_a2a_tasks: dict = {}
_a2a_task_lock = threading.Lock()


def _a2a_sample_builders() -> dict:
    """Paid route -> the view function that builds its free sample.

    Looked up rather than listed twice: a route with no sample is dropped from
    the catalogue below instead of being advertised and then 404ing.
    """
    return {
        "/api/v1/signal": signal_sample,
        "/api/stats": stats_sample,
        "/api/v1/whaleflow": whaleflow_sample,
        "/api/sales": sales_sample,
        "/api/bot-status": bot_status_sample,
        "/api/arb/opportunities": arb_sample,
        "/api/v1/verify-seller": verify_seller_sample,
    }


def _a2a_products(base_url: str) -> list:
    """The catalogue: the single public vitrine, joined to the paywall's prices.

    Prices come from `_route_price` — the same map the 402 reads — for the reason
    recorded there: a discovery surface that quotes an alias can advertise a
    number no caller is ever charged.
    """
    from main import REAL_X402_ROUTES

    builders = _a2a_sample_builders()
    out = []
    for route in REAL_X402_ROUTES:
        endpoint = route["endpoint"]
        if endpoint not in builders:
            continue
        out.append({
            "id": route["id"],
            "name": route.get("name", ""),
            "description": (route.get("description") or "").strip(),
            "endpoint": endpoint,
            "method": route.get("method", "GET"),
            "price_usdc": _route_price(endpoint),
            "sample": "%s/sample" % endpoint,
            "live_url": base_url + endpoint,
        })
    return out


def _a2a_tokens(product: dict) -> set:
    """The words that should select this product from a plain-language request."""
    last = product["endpoint"].rstrip("/").rsplit("/", 1)[-1]
    words = {product["id"].lower(), last.lower()}
    words.update(part.lower() for part in product["id"].split("-"))
    words.update(word.lower().strip(",.") for word in product["name"].split())
    return {word for word in words if len(word) >= 3}


def _a2a_pick(text: str, products: list):
    """The product a request asks for, or None when it is not clear.

    Scored by the total length of the matching tokens, so a longer, more
    specific word beats an incidental short one. Returning None for an unclear
    request is deliberate: answering with the wrong product would be a
    fabricated answer wearing the costume of a helpful one, and the caller can
    read the full catalogue instead.
    """
    low = (text or "").lower()
    best, best_score = None, 0
    for product in products:
        score = sum(len(tok) for tok in _a2a_tokens(product) if tok in low)
        if score > best_score:
            best, best_score = product, score
    return best


def _a2a_sample_payload(endpoint: str):
    """The free sample for one route, or None if it cannot be produced.

    The sample views already own the shape and the price disclaimer, so they are
    CALLED rather than re-described. Re-typing the schema here is how the two
    copies drift, and a sample that disagrees with the live response is worse
    than no sample.
    """
    builder = _a2a_sample_builders().get(endpoint)
    if builder is None:
        return None
    try:
        built = builder()
        response = built[0] if isinstance(built, tuple) else built
        return response.get_json()
    except Exception as exc:                      # noqa: BLE001
        return {"unavailable": type(exc).__name__}


def _a2a_how_to_pay(base_url: str) -> dict:
    """Machine-readable purchase terms — the same facts the 402 carries."""
    from main import (X402_CHAIN_ID, X402_RECEIVER_ADDRESS, X402_USDC_CONTRACT)

    return {
        "protocol": "x402",
        "version": "2",
        "network": "eip155:%d" % X402_CHAIN_ID,
        "chain": "base",
        "chain_id": X402_CHAIN_ID,
        "asset": "USDC",
        "token_contract": X402_USDC_CONTRACT,
        "pay_to": X402_RECEIVER_ADDRESS,
        "price_per_call_usdc": _cheapest_route_price(),
        "price_max_usdc": _dearest_route_price(),
        "flow": [
            "GET the live URL with no credential; it answers 402",
            "read PAYMENT-REQUIRED (or the JSON body): accepts[0].amount is "
            "ATOMIC USDC (6 decimals) — 3000 means $0.003, not $3000",
            "sign an EIP-3009 transferWithAuthorization for accepts[0].amount "
            "to accepts[0].payTo",
            "retry the same URL with the PAYMENT-SIGNATURE header",
        ],
        "terms": "%s/.well-known/x402" % base_url,
        "discovery": {
            "openapi": "%s/openapi.json" % base_url,
            "agents_json": "%s/agents.json" % base_url,
            "mcp_manifest": "%s/api/mcp/manifest" % base_url,
            "llms_txt": "%s/llms.txt" % base_url,
        },
    }


def _a2a_catalogue_text(products: list) -> str:
    lines = ["Kristo Intelligence — pay-per-call data API for AI agents on Base.",
             "Live data is bought at the HTTP routes below; this A2A surface "
             "answers with the free sample for a product and its exact terms.",
             ""]
    for product in products:
        lines.append("%-20s %s USDC/call  live: %s  sample: %s"
                     % (product["id"], ("%.3f" % product["price_usdc"]),
                        product["live_url"], product["sample"]))
    return "\n".join(lines)


def _a2a_task(text: str, base_url: str, message: dict) -> dict:
    """Build the completed task for one request. Never invents a value."""
    products = _a2a_products(base_url)
    chosen = _a2a_pick(text, products)
    task_id = "task-" + secrets.token_hex(12)
    now = datetime.now(timezone.utc).isoformat()

    if chosen is None:
        answer = ("I could not tell which product you are asking for, so here is "
                  "the whole catalogue rather than a guess.\n\n"
                  + _a2a_catalogue_text(products))
        data = {"matched": None, "catalogue": products,
                "how_to_pay": _a2a_how_to_pay(base_url)}
    else:
        sample = _a2a_sample_payload(chosen["endpoint"])
        answer = (
            "Product: %s (%s)\n"
            "Live data: %s — %.3f USDC per call over x402 on Base.\n"
            "This A2A endpoint does NOT return the live payload; it returns the "
            "free sample and the terms, so that nothing is given away and "
            "nothing is promised that is not sold.\n"
            "Free sample: %s"
            % (chosen["name"], chosen["id"], chosen["live_url"],
               chosen["price_usdc"], chosen["sample"]))
        data = {"matched": chosen["id"], "product": chosen,
                "free_sample": sample, "how_to_pay": _a2a_how_to_pay(base_url)}

    return {
        "kind": "task",
        "id": task_id,
        "contextId": "ctx-" + secrets.token_hex(8),
        "status": {"state": "completed", "timestamp": now},
        "history": [message] if message else [],
        "artifacts": [{
            "artifactId": "artifact-" + secrets.token_hex(8),
            "name": (chosen["id"] if chosen else "catalogue"),
            "description": ("Free sample and exact paid terms for one product."
                            if chosen else
                            "The full product catalogue with prices."),
            "parts": [
                {"kind": "text", "text": answer},
                {"kind": "data", "data": data},
            ],
        }],
    }


def _a2a_remember(task: dict) -> None:
    """Store a task, evicting the expired and then the oldest."""
    now = time.time()
    with _a2a_task_lock:
        for key in [k for k, v in _a2a_tasks.items()
                    if now - v.get("_stored_at", 0) > A2A_TASK_TTL_SECONDS]:
            _a2a_tasks.pop(key, None)
        while len(_a2a_tasks) >= A2A_MAX_TASKS:
            _a2a_tasks.pop(min(_a2a_tasks,
                               key=lambda k: _a2a_tasks[k].get("_stored_at", 0)),
                           None)
        _a2a_tasks[task["id"]] = dict(task, _stored_at=now)


def _a2a_public(task: dict) -> dict:
    """The task as served: the internal bookkeeping key is not part of the spec."""
    return {k: v for k, v in task.items() if not k.startswith("_")}


def _a2a_message_text(message) -> str:
    """Flatten an A2A message's parts into text. Both v0.2 and v0.3 part keys."""
    if not isinstance(message, dict):
        return ""
    chunks = []
    for part in message.get("parts") or []:
        if not isinstance(part, dict):
            continue
        if isinstance(part.get("text"), str):
            chunks.append(part["text"])
        elif isinstance(part.get("data"), dict):
            chunks.append(json.dumps(part["data"]))
    return "\n".join(chunks)


def _a2a_rpc_error(req_id, code: int, message: str, data=None):
    error = {"code": code, "message": message}
    if data is not None:
        error["data"] = data
    return jsonify({"jsonrpc": "2.0", "id": req_id, "error": error}), 200


@discovery_bp.route("/.well-known/agent-card.json")
def agent_card():
    """The A2A Agent Card (protocol 0.3.0), at the standard discovery path.

    Every field here is one a caller can check against a live response: the
    skills are the paid routes, each naming the free sample that documents
    it and the price the 402 actually charges.
    """
    base_url = request.host_url.rstrip("/")
    products = _a2a_products(base_url)
    # The A2A card and the x402 challenge must advertise the SAME icon in the
    # SAME format. They were two hand-written "/static/icons/kristo.svg" strings,
    # and the Bazaar accepts JPG/JPEG/PNG/WebP/GIF but not SVG — so the shared
    # constant is what stops one surface being fixed and the other left stale.
    from main import X402_ICON_PATH
    return jsonify({
        "protocolVersion": A2A_PROTOCOL_VERSION,
        "name": "Kristo Intelligence",
        "description": (
            "Pay-per-call data API for AI agents on Base: live DeFi trading "
            "signals, whale flow (USDC transfers of $5M or more), cross-DEX "
            "arbitrage radar, on-chain sales history and market stats. Six "
            "routes, each bought per call with USDC over x402 — no subscription "
            "and no API key. This A2A endpoint answers a request for a product "
            "with that product's free sample and its exact terms; the live data "
            "itself is bought at the HTTP route, because that is what the "
            "paywall sells."
        ),
        "url": "%s/a2a" % base_url,
        "version": A2A_AGENT_VERSION,
        "preferredTransport": "JSONRPC",
        "provider": {"organization": "Kristo Intelligence", "url": base_url},
        "documentationUrl": "%s/llms.txt" % base_url,
        "iconUrl": "%s%s" % (base_url, X402_ICON_PATH),
        # Declared false because they are NOT implemented. See the note above.
        "capabilities": {
            "streaming": False,
            "pushNotifications": False,
            "stateTransitionHistory": False,
        },
        "defaultInputModes": ["text/plain", "application/json"],
        "defaultOutputModes": ["text/plain", "application/json"],
        "skills": [
            {
                "id": product["id"],
                "name": product["name"],
                "description": (
                    "%s Free sample (no payment, no key): %s. Live data: %s at "
                    "%.3f USDC per call over x402 on Base."
                    % (product["description"], base_url + product["sample"],
                       product["live_url"], product["price_usdc"])),
                "tags": ["x402", "base", "usdc", product["id"]],
                "examples": [
                    "Show me the %s sample and what it costs" % product["name"],
                    "What are the terms for %s?" % product["endpoint"],
                ],
                "inputModes": ["text/plain"],
                "outputModes": ["application/json"],
            }
            for product in products
        ],
        # A non-standard block, and honest about being one: it is the same
        # payment facts the 402 and agents.json already publish, repeated where
        # an A2A client will look for them.
        "x402": _a2a_how_to_pay(base_url),
    }), 200


@discovery_bp.route("/a2a", methods=["GET", "POST"])
def a2a_endpoint():
    """Minimal A2A JSON-RPC: `message/send` and `tasks/get`, honestly.

    A GET is answered with a short description rather than a 405, because a
    directory (and a person) checking whether the card's URL is alive should get
    something readable instead of a protocol error about the wrong verb.
    """
    if request.method == "GET":
        base_url = request.host_url.rstrip("/")
        return jsonify({
            "protocol": "A2A",
            "protocolVersion": A2A_PROTOCOL_VERSION,
            "transport": "JSONRPC",
            "card": "%s/.well-known/agent-card.json" % base_url,
            "methods": ["message/send", "tasks/get"],
            "note": ("POST a JSON-RPC 2.0 request with method message/send. "
                     "This surface answers with a product's free sample and its "
                     "exact paid terms; the live data is bought at the HTTP "
                     "route over x402."),
        }), 200

    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return _a2a_rpc_error(None, -32700, "Parse error: body is not a JSON object")

    req_id = body.get("id")
    method = body.get("method")
    params = body.get("params")
    if not isinstance(params, dict):
        params = {}

    if body.get("jsonrpc") != "2.0" or not isinstance(method, str):
        return _a2a_rpc_error(req_id, -32600,
                              "Invalid Request: jsonrpc must be \"2.0\" and "
                              "method must be a string")

    base_url = request.host_url.rstrip("/")

    if method == "message/send":
        message = params.get("message")
        if not isinstance(message, dict):
            return _a2a_rpc_error(req_id, -32602,
                                  "Invalid params: message must be an object")
        text = _a2a_message_text(message)
        try:
            task = _a2a_task(text, base_url, message)
        except Exception as exc:                  # noqa: BLE001
            return _a2a_rpc_error(req_id, -32603,
                                  "Internal error building the task",
                                  {"type": type(exc).__name__})
        _a2a_remember(task)
        return jsonify({"jsonrpc": "2.0", "id": req_id,
                        "result": _a2a_public(task)}), 200

    if method == "tasks/get":
        task_id = params.get("id")
        if not isinstance(task_id, str) or not task_id:
            return _a2a_rpc_error(req_id, -32602,
                                  "Invalid params: id must be a task id string")
        with _a2a_task_lock:
            task = _a2a_tasks.get(task_id)
        if task is None:
            # A2A's TaskNotFound. Not a fabricated empty task: tasks are held in
            # memory only, so one from before a restart really is gone.
            return _a2a_rpc_error(
                req_id, -32001, "Task not found: %s" % task_id,
                {"note": "Tasks are kept in memory and expire after %d seconds."
                         % A2A_TASK_TTL_SECONDS})
        return jsonify({"jsonrpc": "2.0", "id": req_id,
                        "result": _a2a_public(task)}), 200

    return _a2a_rpc_error(
        req_id, -32601, "Method not found: %s" % method,
        {"supported": ["message/send", "tasks/get"],
         "note": ("message/stream and the push-notification methods are not "
                  "implemented, which is why the agent card declares streaming "
                  "and pushNotifications as false.")})


def _mcp_tools(base_url):
    """Shared MCP tool definitions — served identically by the SSE endpoint
    (/mcp/sse) and the Streamable HTTP endpoint (POST /mcp). Each tool
    advertises its x402 price so the agent can pay before calling; paid
    calls still flow through the regular 402 paywall.

    Every paid route is exposed. This list used to carry only three of the six,
    so an MCP client could not buy /api/v1/signal (the flagship product),
    /api/v1/whaleflow or /api/arb/opportunities at all — while agents.json
    described all six and the tools' own descriptions pointed only at each
    other. The names match agents_json() so one product is not two names.

    Prices are read from X402_PRICE_MAP, which is the paywall's own source of
    truth, instead of the flat X402_FEE_USDC alias they used before: every route
    price is environment-overridable, so a hardcoded value here would silently
    advertise a price the paywall does not charge.
    """
    from main import (
        X402_CHAIN_ID,
        X402_FEE_USDC,
        X402_PRICE_MAP,
        X402_RECEIVER_ADDRESS,
        X402_USDC_CONTRACT,
    )

    def _price(route):
        return float(X402_PRICE_MAP.get(route, X402_FEE_USDC))

    def _tool(name, route, description, input_schema=None):
        """One MCP tool. `input_schema` is omitted by every route that takes no
        input; /api/v1/verify-seller requires a `receiver`, and an MCP tool that
        declares an empty schema while its route demands a query parameter tells
        the agent the call is complete when it is not.
        """
        return {
            "name": name,
            "description": description,
            "inputSchema": (input_schema if input_schema is not None
                            else {"type": "object", "properties": {},
                                  "additionalProperties": False}),
            # MACHINE-READABLE "THIS ONLY READS", and it is not cosmetic.
            #
            # Every tool here is a pure read: a chain scan, a market snapshot, a
            # status read. The DESCRIPTIONS have always said so in prose — "Read-
            # only operation, no side effects" — but the protocol carries that
            # fact in `annotations`, and a client that reads the annotation
            # instead of the sentence saw nothing at all. Two directories said so
            # in public, and a buyer sees it before paying:
            #
            #   mcptry, per tool: "This tool isn't marked read-only, so it MAY
            #   CHANGE SOMETHING on the server or in an account you connected.
            #   [I understand, run it anyway]"
            #
            #   Glama's TDQS, per tool: "WITH NO ANNOTATIONS SUPPLIED, the
            #   description carries the full burden" — and scored the behavior
            #   dimension 4/5 for exactly that reason, across all seven.
            #
            # That warning sat in front of a paid call that only reads. Friction
            # there is expensive and it is also simply untrue, and an agent
            # deciding whether to spend is the audience this file exists for.
            #
            # `openWorldHint` is TRUE on purpose and is not a hedge: the answers
            # genuinely depend on the outside world — Base, CoinGecko,
            # DEXScreener — so a client should expect them to change between
            # calls. Claiming otherwise would be the dishonesty in the other
            # direction.
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": True,
            },
            "x402": {"price_usdc": _price(route), "chain_id": X402_CHAIN_ID,
                     "receiver": X402_RECEIVER_ADDRESS,
                     "token_contract": X402_USDC_CONTRACT,
                     "endpoint": f"{base_url}{route}"},
        }

    # The payment facts live in each tool's structured `x402` block (price,
    # receiver, chain, token) and once in the registry artifact's pricing.note.
    # They used to be repeated as a prose sentence at the end of EVERY tool
    # description, and seven copies of it pushed the publisher extension past
    # the registry's 4096-byte limit — publishing failed with a 400 that
    # `mcp-publisher validate` called valid.
    return [
        _tool(
            "get_market_stats", "/api/stats",
            "Read-only operation — no side effects, no parameters. Returns "
            "the live Base market snapshot: aggregated activity, daily "
            "request/sales counters, the official agent catalog, and "
            "real-time market data (CoinGecko, DEXScreener, Fear & Greed). "
            "Use it for market context and price/indicator lookups; use "
            "get_onchain_sales for paid-call revenue and get_bot_status for "
            "integration health. ",
        ),
        _tool(
            "get_onchain_sales", "/api/sales",
            "Read-only operation — no side effects, no parameters. Returns "
            "the real on-chain payment history to this service's fee "
            "receiver on Base: total_volume_usd, total_sales, by_token, up "
            "to 100 history rows (tx hash, payer, amount, block, "
            "timestamp), source=\"real_blockchain\", plus the wallet state "
            "and a market snapshot. Use it when you need provable revenue "
            "or settlement evidence; use get_market_stats for prices and "
            "get_bot_status for integration health. ",
        ),
        _tool(
            "get_bot_status", "/api/bot-status",
            "Read-only operation — no side effects, no parameters. Returns "
            "the service's Telegram integration status as JSON: "
            "telegram_bot_running, telegram_token_configured, "
            "last_heartbeat, uptime_started, messages_sent, active_users, "
            "commands_processed, vip_invites_sent, plus the wallet state. "
            "Use it to confirm this service's own monitoring is alive (and "
            "its heartbeat recent) before trusting other outputs; use "
            "get_market_stats for market data or get_onchain_sales for "
            "provable revenue. ",
        ),
        _tool(
            "get_trading_signal", "/api/v1/signal",
            "Read-only operation — no side effects, no parameters. Returns "
            "this service's flagship trading-agent signals for ETH, ONDO, "
            "KAITO and DEGEN: action, confidence, price_usd and the model's "
            "reasoning. Use it when you need a directional call rather than "
            "raw market data; use get_whale_flow for large-transfer flow and "
            "get_arbitrage_opportunities for cross-DEX spreads. ",
        ),
        _tool(
            "get_whale_flow", "/api/v1/whaleflow",
            "Read-only operation — no side effects, no parameters. Returns "
            "network-wide USDC whale flow on Base: transfers of $5M or more, "
            "refreshed every 60 seconds, with labelled counterparties. Use it "
            "to see where size is moving; use get_trading_signal for "
            "directional calls or get_market_stats for broad context. ",
        ),
        _tool(
            "get_arbitrage_opportunities", "/api/arb/opportunities",
            "Read-only operation — no side effects, no parameters. Returns "
            "live cross-DEX arbitrage spreads on Base, refreshed every 60 "
            "seconds. Use it for executable price gaps between venues; use "
            "get_market_stats for aggregate prices or get_trading_signal for "
            "directional calls. ",
        ),
        # The only tool that requires input. It is also the only one that
        # answers a question ABOUT another seller rather than about this
        # service, which is why it is the one agents ask for by name when they
        # are deciding whether to pay somebody else.
        _tool(
            "verify_seller_receiver", "/api/v1/verify-seller",
            # Kept short on purpose: `tools` is the bulk of the publisher
            # extension, and the registry rejects anything over 4096 bytes
            # measured as compact JSON. The long form of this sentence lives in
            # the OpenAPI description and llms.txt, where nothing is billed by
            # the byte.
            "Read-only; REQUIRES `receiver`. Audits ANY receiver's incoming "
            "USDC on Base: distinct payers, repeat payers, concentration, "
            "probes vs customers. Decides whether a seller is safe to pay. "
            "Reports partial/failed, never a zero it did not measure.",
            input_schema={
                "type": "object",
                "properties": {
                    "receiver": {
                        "type": "string",
                        "description": "USDC receiver address to audit. A "
                                       "bare 40-hex address is accepted and "
                                       "checksummed.",
                    },
                    "days": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 30,
                        "default": 7,
                        "description": "Lookback window in days.",
                    },
                },
                "required": ["receiver"],
                "additionalProperties": False,
            },
        ),
    ]


_MCP_FALLBACK_PROTOCOL = "2025-11-25"


def _example_arguments(input_schema: dict) -> dict:
    """The smallest argument object an agent could plausibly send.

    Used as the Bazaar `example`. For a PAID tool it does not need to succeed —
    it needs to reach the payment check and provoke a 402, which any call to a
    priced tool does. It still has to be VALID against the schema, because the
    catalog validates `info.input` against `schema.properties.input` and a
    rejected declaration is a missing listing.

    Required properties get a typed placeholder — an EVM address, a small
    integer, a short string — so a tool that takes a `receiver` is described by
    something an agent could actually copy.
    """
    if not isinstance(input_schema, dict):
        return {}
    required = input_schema.get("required") or []
    props = input_schema.get("properties") or {}
    if not required:
        return {}
    out: dict = {}
    for key in required:
        spec = props.get(key) or {}
        kind = spec.get("type")
        lowered = key.lower()
        if any(word in lowered for word in ("receiver", "address", "wallet",
                                            "payer", "account")):
            # Named like an address, so describe it with one. USDC's own
            # contract is public, belongs to nobody, and satisfies any 0x
            # pattern — an agent copying the example gets something usable
            # rather than the literal string "example".
            out[key] = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
        elif kind == "integer" or kind == "number":
            out[key] = spec.get("default", 7)
        elif kind == "boolean":
            out[key] = False
        elif kind == "array":
            out[key] = []
        elif kind == "object":
            out[key] = {}
        elif isinstance(spec.get("pattern"), str) and "0x" in spec["pattern"]:
            out[key] = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
        else:
            out[key] = "example"
    return out


def _retype_bazaar_for_mcp(extensions, tool, name: str,
                           transport: str = "streamable-http") -> None:
    """Rewrite `extensions.bazaar` from the HTTP shape into the MCP shape.

    IN PLACE AND BEST-EFFORT. The caller has already built a valid challenge, and
    a discovery nicety must never be able to break the paid call it describes —
    so an unexpected shape leaves the extension exactly as it was.

    WHY IT IS NEEDED AT ALL. `_x402_challenge_core` is shared with the HTTP path
    deliberately, so it emits `info.input = {type: "http", method: "GET",
    queryParams: {}}`. Measured live: the CDP catalog carries 515 resources with
    `type: "mcp"`, and our seven MCP tools were none of them — an MCP tool that
    advertises `type: "http"` is not an MCP resource, so it cannot be found by an
    agent searching the MCP half of the catalog.

    The `example` is the part Coinbase singles out: it is passed as the tool's
    `arguments`, and "if the example is missing or the tool returns success
    instead of a payment challenge, Bazaar cannot index the tool".
    """
    if not isinstance(extensions, dict):
        return
    bazaar = extensions.get("bazaar")
    if not isinstance(bazaar, dict):
        return
    info = bazaar.get("info")
    if not isinstance(info, dict):
        return
    if not isinstance(tool, dict):
        return

    schema = tool.get("inputSchema") or {"type": "object", "properties": {}}
    example = _example_arguments(schema)

    info["input"] = {
        "type": "mcp",
        "toolName": tool.get("name") or name,
        "transport": transport,
        "description": tool.get("description") or "",
        "example": example,
        "inputSchema": schema,
    }
    # The declaration is validated against `schema.properties.input`, so the
    # schema has to describe what was just declared — a mismatch is a rejection,
    # which is a missing listing rather than a visible error.
    bazaar["schema"] = {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "type": "object",
        "properties": {
            "input": {
                "type": "object",
                "properties": {
                    "type": {"type": "string", "const": "mcp"},
                    "toolName": {"type": "string"},
                    "transport": {"type": "string"},
                    "description": {"type": "string"},
                    "example": {"type": "object"},
                    "inputSchema": {"type": "object"},
                },
                "required": ["type", "toolName"],
            },
            "output": {
                "type": "object",
                "properties": {"type": {"type": "string"}},
                "required": ["type"],
            },
        },
    }


def _mcp_forward_arguments(tool, arguments):
    """A tool's arguments as the route's query string. Returns (query, problem).

    WHY THIS EXISTS AT ALL, and it is not a nicety: the forward below used to call
    the route with NO query string, so a tool that takes input lost it. Measured
    on the live service, 09.11 19:26:49 — `verify_seller_receiver` was called with
    a valid `receiver`, the rail settled $0.10 (tx
    0x697923104b312862fc333fd6464e542a77a7253a635a2070125ccbff9d7413f0, status
    0x1), the forwarded GET arrived with no `receiver`, the route answered the
    honest 400 `receiver_required` — and the buyer was handed the challenge back
    with the money gone and the nonce already spent. Every tool without input
    worked, which is why six payments in a row hid it.

    The rules are the tool's OWN `inputSchema`, so the declaration, the challenge
    and the call cannot drift: required keys must be present, types must match,
    and unknown keys are refused because every schema here declares
    `additionalProperties: false`. A `receiver` is normalized to lowercase hex —
    the route checksums it, and a mixed-case typo would otherwise fail there
    instead of here, after the money had moved.
    """
    schema = tool.get("inputSchema") or {}
    props = schema.get("properties") or {}
    args = arguments if isinstance(arguments, dict) else {}
    name = tool.get("name") or "?"

    unknown = sorted(set(args) - set(props))
    if unknown:
        return {}, ("Unknown argument(s) for tool '%s': %s. This tool accepts "
                    "%s." % (name, ", ".join(unknown),
                             ", ".join(sorted(props)) or "no arguments"))

    query = {}
    for key in schema.get("required") or []:
        if key not in args or args[key] in ("", None):
            return {}, ("Missing required argument '%s' for tool '%s'. It is "
                        "required by the tool's own inputSchema; nothing was "
                        "charged." % (key, name))
    for key, value in args.items():
        spec = props.get(key) or {}
        kind = spec.get("type")
        if kind == "string":
            if not isinstance(value, str) or not value.strip():
                return {}, ("Argument '%s' for tool '%s' must be a non-empty "
                            "string." % (key, name))
            query[key] = value.strip()
        elif kind == "integer":
            try:
                query[key] = int(value)
            except (TypeError, ValueError):
                return {}, ("Argument '%s' for tool '%s' must be an integer."
                            % (key, name))
        elif kind == "boolean":
            if not isinstance(value, bool):
                return {}, ("Argument '%s' for tool '%s' must be a boolean."
                            % (key, name))
            query[key] = value
        else:
            query[key] = value

    receiver = query.get("receiver")
    if receiver is not None:
        body = receiver[2:] if receiver.lower().startswith("0x") else receiver
        if len(body) != 40 or any(c not in "0123456789abcdefABCDEF" for c in body):
            return {}, ("Argument 'receiver' for tool '%s' must be a "
                        "40-hex-character EVM address, with or without the 0x "
                        "prefix; got %r. Nothing was charged." % (name, receiver))
        query["receiver"] = "0x" + body.lower()
    return query, None


def _serve_paid_mcp_tool(path: str, price: float, payment_header: str,
                         arguments: dict | None = None):
    """Settle through the HTTP rail, then return the route's own answer.

    WHY A FORWARD RATHER THAN A SECOND IMPLEMENTATION. The rail already verifies,
    settles through the CDP-first facilitator chain, records the sale and enforces
    the replay lock — and it does all of that on the HTTP route. Re-deriving any
    of it here would create a second payment path that can disagree with the first,
    which is the defect this file spends most of its comments preventing.

    So the caller's own payment header is handed to the route it paid for, and the
    route's response is what the tool returns. One price, one receiver, one
    settlement, one sale.

    Returns the parsed body on success, or None — and None means "still not
    paid", so the caller falls back to returning the challenge. A forward that
    fails must never look like a purchase that succeeded.
    """
    if not path:
        return None
    try:
        from main import app as _app

        with _app.test_client() as client:
            # The tool's arguments ARE the route's query string. Dropping them
            # (which this did until 09.11 19:26, at a cost of $0.10 and a spent
            # nonce) makes a paid call to an input-taking tool unservable: the
            # route answers 400 `receiver_required` and the buyer gets nothing.
            resp = client.get(path, query_string=arguments or {},
                              headers={"PAYMENT-SIGNATURE": payment_header})

        # A 200 IS NOT PROOF OF PAYMENT, and the first version of this shipped
        # that defect. The forward arrives from 127.0.0.1 — loopback — and the
        # free tier grants on IP, so `PAYMENT-SIGNATURE: FAKE` returned the data
        # for nothing. Measured: "Free tier access: ip=127.0.0.1, used=1/1".
        #
        # So the test is not "did it answer" but "DID A SETTLEMENT HAPPEN". The
        # HTTP rail emits a PAYMENT-RESPONSE header only when a real tx settled
        # and `g.x402_delivered_tx` was stamped, which is the same evidence the
        # paying caller gets. No settlement, no sale, no data — and the caller
        # receives the challenge, which is the honest answer.
        if resp.status_code != 200:
            return None
        settled = any(k.lower() == "payment-response" and (v or "").strip()
                      for k, v in resp.headers.items())
        if not settled:
            logging.getLogger(__name__).warning(
                "MCP paid forward to %s answered %s WITHOUT a settlement — "
                "refusing to serve it as a purchase",
                path, resp.status_code)
            return None
        body = resp.get_json(silent=True)
        return body if isinstance(body, dict) else None
    except Exception as exc:  # noqa: BLE001 - a discovery nicety, never fatal
        logging.getLogger(__name__).debug(
            "MCP paid forward to %s failed: %s", path, exc)
        return None


def _mcp_dispatch(body):
    """Shared JSON-RPC dispatcher for BOTH transports (POST /mcp and the SSE
    message POST). Returns (kind, payload):

        "invalid"      -> payload is the JSON-RPC -32600 error object
        "notification" -> payload is None (there is nothing to answer)
        "response"     -> payload is the result OR a JSON-RPC error envelope

    Audit #6 BREAK 1: the two transports used to drift — SSE pushed canned
    initialize/tools answers with protocolVersion 2024-11-05 while streamable
    echoed the client. ONE dispatcher guarantees protocolVersion, tools and
    the x402 payload stay identical.
    """
    if not isinstance(body, dict) or "method" not in body:
        return "invalid", {"jsonrpc": "2.0", "id": None,
                           "error": {"code": -32600,
                                     "message": "Invalid Request"}}
    method = body.get("method", "")
    msg_id = body.get("id")
    # Notifications carry no id and expect no response body.
    if method.startswith("notifications/"):
        return "notification", None

    base_url = request.host_url.rstrip("/")
    tools = _mcp_tools(base_url)

    if method == "initialize":
        params = body.get("params") or {}
        result = {
            "protocolVersion": (params.get("protocolVersion")
                                or _MCP_FALLBACK_PROTOCOL),
            "capabilities": {"tools": {}},
            "serverInfo": {
                "name": "kristo-intelligence",
                # Was hardcoded "1.0.0" while server.json published 6.2.0 — an
                # MCP client comparing the two concluded we were ancient.
                "version": SERVICE_VERSION,
                "title": "Kristo Intelligence — DeFi signals (x402/USDC on Base)",
            },
            # SAME REASON AS THE TOOL TEXT BELOW: this string is discovery
            # metadata the Bazaar screens, and the previous wording was an
            # instruction ("pay the exact USDC amount to the listed receiver and
            # retry the target endpoint with the payment header"). It now states
            # the same facts as a description of the service.
            "instructions": (
                "Kristo Intelligence — paid DeFi signals on Base, billed per "
                "call in USDC via x402. Each tool's x402 metadata states its "
                "price, network, receiver and asset; an unpaid call returns the "
                "payment requirements this server accepts."
            ),
        }
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": tools}
    elif method == "tools/call":
        params = body.get("params") or {}
        name = params.get("name", "")
        tool = next((t for t in tools if t.get("name") == name), None)
        if tool is None:
            # tool errors stay inside a JSON-RPC error envelope
            return "response", {"jsonrpc": "2.0", "id": msg_id,
                                "error": {"code": -32602,
                                          "message": f"Unknown tool: {name}"}}
        x = tool.get("x402", {})
        # A priced tool result is where an MCP agent decides whether it CAN pay,
        # and this one answered in prose plus a private `{"x402": ...}` shape. An
        # independent prober read that as `payment_terms_unreadable` (checked
        # 07.11): "says payment is required, but without x402 terms we can read: a
        # listing cannot verify yet" — and its own note is blunter: an agent
        # "cannot pay it in-session". The tool named a URL to go and pay somewhere
        # else, which an agent inside an MCP session will not do.
        #
        # The fix is NOT to invent terms here. It is to publish the SAME canonical
        # challenge the HTTP 402 already carries, built by the same
        # `_x402_challenge_core` call the HTTP path uses, so the two cannot drift:
        # one price, one receiver, one CAIP-2 network, one atomic amount.
        #
        # Best-effort on purpose. If anything here fails, the previous shape stands
        # and the tool still answers — a discovery nicety must never take the
        # endpoint down.
        payment_required = None
        paid_response = None
        try:
            from urllib.parse import urlsplit

            from main import _x402_challenge_core, CHALLENGE_DESCRIPTIONS

            # `x["endpoint"]` is absolute (base_url + route) because that is what
            # an agent must call; the canonical builder joins it to the request
            # host and CHALLENGE_DESCRIPTIONS keys on the path, so both need the
            # PATH. Passing the absolute URL through would have produced
            # "http://host/https://host/api/..." as the resource url and an empty
            # description — a worse lie than the prose it replaced.
            raw_endpoint = x.get("endpoint") or ""
            path = urlsplit(raw_endpoint).path if "//" in raw_endpoint else raw_endpoint

            # ── CAN THEY ACTUALLY BUY? ────────────────────────────────────────
            #
            # Until now: NO. This handler built the challenge and returned it,
            # every time, with no code that could accept a payment — so an agent
            # inside an MCP session could read our terms and never complete a
            # purchase. The tool text even said "then call <endpoint> with the
            # payment header", i.e. go and pay somewhere else, which is exactly
            # the behaviour an MCP client will not perform.
            #
            # That is the shape of `api.aiskills402.com`, measured in the same
            # session: 175 listings, discovery-only MCP ("Buying is over HTTP in
            # this release"), and the FEWEST payers in the market census — 7,
            # against 13 and 12 for the two hosts whose MCP can pay.
            #
            # The remedy is not a second payment implementation. It is to hand
            # the caller's own payment header to the HTTP rail we already trust,
            # let it settle, and then serve the route it protects. One price, one
            # receiver, one settlement path — the same reason the challenge is
            # built by `_x402_challenge_core` in the first place.
            payment_header = (
                (request.headers.get("PAYMENT-SIGNATURE") or "").strip()
                or (request.headers.get("X-PAYMENT") or "").strip()
            )
            if payment_header:
                # VALIDATE BEFORE THE RAIL IS TOUCHED. Settling is what spends
                # the buyer's money, and the rail settles before the route
                # handler runs — so an argument the route will refuse has to be
                # refused HERE, where no nonce is spent and the caller can fix
                # the call and reuse the same signature. An unpaid call is left
                # exactly as it was: it still gets the challenge, because an
                # agent reading the terms has not been charged and must be able
                # to see them.
                query, problem = _mcp_forward_arguments(tool, params.get("arguments"))
                if problem:
                    return "response", {"jsonrpc": "2.0", "id": msg_id,
                                        "error": {"code": -32602,
                                                  "message": problem}}
                paid_response = _serve_paid_mcp_tool(
                    path, float(x.get("price_usdc") or 0), payment_header, query)

            accepts, resource, extensions = _x402_challenge_core(
                path, float(x.get("price_usdc") or 0),
                description=CHALLENGE_DESCRIPTIONS.get(path, ""))

            # ── THE RESOURCE MUST NAME THE TOOL, NOT THE ROUTE ───────────────
            #
            # Measured, AFTER a real MCP payment settled through CDP: the catalog
            # still showed zero MCP entries for us. The payment payload carried
            # `resource.url = .../api/v1/whaleflow`, because
            # `_x402_challenge_core` builds it from the HTTP path — and CDP
            # indexes a resource by that url, so it filed the settlement under the
            # HTTP route we already had and never under the tool.
            #
            # The catalog's own MCP entries say what the identity must be:
            #
            #     https://mcp.xrpl-utilities.io/mcp#xrpl_pulse_recent_events
            #
            # `<mcp endpoint>#<toolName>`. That is what makes 515 MCP resources
            # addressable as TOOLS rather than as endpoints, and it is the piece
            # our declaration was missing.
            tool_name = tool.get("name") or name
            if isinstance(resource, dict) and tool_name:
                parsed = urlsplit(resource.get("url") or "")
                if parsed.scheme and parsed.netloc:
                    resource = dict(resource)
                    # The HOST, never the route. An earlier version split on
                    # "/mcp" and appended, which produced
                    # "http://localhost/api/v1/whaleflow/mcp#get_whale_flow" —
                    # a url with a url glued into it. The existing test
                    # `test_the_resource_url_is_the_route_not_a_url_glued_to_a_url`
                    # caught it, which is what that test is for.
                    resource["url"] = "%s://%s/mcp#%s" % (
                        parsed.scheme, parsed.netloc, tool_name)
            # RETYPE THE BAZAAR EXTENSION FOR MCP, and this is the whole reason
            # our seven tools were invisible to half the catalog.
            #
            # `_x402_challenge_core` is shared with the HTTP path on purpose — one
            # price, one receiver, one network — but it therefore emits the HTTP
            # shape:
            #
            #     "input": {"type": "http", "method": "GET", "queryParams": {}}
            #
            # Measured against the live catalog: 515 resources carry `type: "mcp"`
            # and ours were none of them, because an MCP tool advertising itself
            # as `type: "http"` is not an MCP resource. The shape the catalog
            # actually stores is:
            #
            #     "input": {"type": "mcp", "toolName": ..., "transport": ...,
            #               "description": ..., "example": {...},
            #               "inputSchema": {...}}
            #
            # and Coinbase's own guidance names the `example` as the thing that
            # decides it: "Provide an example that causes the tool to return an
            # x402 payment-required response. If the example is missing or the
            # tool returns success instead of a payment challenge, Bazaar cannot
            # index the tool."
            _retype_bazaar_for_mcp(extensions, tool, name, transport="streamable-http")
            payment_required = {
                "x402Version": 2,
                "error": "payment_required",
                "accepts": accepts,
                "resource": resource,
                "extensions": extensions,
            }
        except Exception as exc:      # pragma: no cover - defensive
            # Match this module's style: it has no module-level `log`, and a
            # bare `log.debug` here would raise NameError INSIDE the handler and
            # take down the very call it was meant to protect.
            logging.getLogger(__name__).debug(
                "MCP %s: could not build x402 terms: %s", name, exc)

        # DESCRIBES, DOES NOT INSTRUCT — load-bearing, not politeness.
        #
        # This is the text the Bazaar's crawler reads when it calls the tool with
        # the declared `example`, and the metadata content policy refuses text
        # that "could instruct an agent instead of describing the endpoint" — with
        # no error anywhere, just a resource that never appears. Measured 10.11:
        # CDP ACCEPTED our declaration (`bazaar: processing`), their crawler hit
        # this endpoint six times, and 24 minutes later the catalog still held 0
        # of our rows. The old wording was the shape that policy screens for:
        #
        #     "is pay-per-call via x402: send 0.005 USDC on 8453 to 0xd4cd…, then
        #      call https://…/api/stats with the payment header."
        #
        # an amount, a receiver and a URL delivered as orders to the reader.
        # Nothing is LOST by rewording: the price, receiver, chain, asset and
        # endpoint stay machine-readable in `x402` and in the `accepts` block
        # below, and the full challenge is still repeated as text for clients that
        # read only content[].
        # THE SPEC SHAPE, and this is the fix for the missing listing.
        #
        # specs/transports-v2/mcp.md, "Payment Required Signaling", is a MUST:
        #
        #   "When a tool requires payment, servers MUST return a tool result with
        #    `isError: true` containing the PaymentRequired data."
        #   "Servers MUST provide the PaymentRequired in both formats:
        #     1. structuredContent (REQUIRED): Direct PaymentRequired object
        #     2. content[0].text (REQUIRED): JSON-encoded string of the same
        #        PaymentRequired object"
        #
        # We satisfied neither. Measured live before this change: the result had
        # only ['content', 'structuredContent'] — NO isError — and content[0].text
        # was a human sentence with the challenge relegated to content[1]. To
        # anything checking the documented signal, an unpaid call looked like a
        # SUCCESSFUL tool call, and Coinbase says plainly what that costs: "if the
        # tool returns success instead of a payment challenge, Bazaar cannot index
        # the tool". That matches every measurement we have — CDP accepted the
        # declaration (`bazaar: processing`), its crawler hit /mcp six times, and
        # the catalog still gained nothing.
        tool_text = (
            f"Payment required. Tool '{name}' is billed per call in USDC on "
            f"chain {x.get('chain_id')} via x402, at the price stated in this "
            "response's payment requirements. The accepted payment terms are "
            "carried in the structured content below."
        )
        content = [{"type": "text", "text": tool_text}]
        structured = {"x402": x}
        if paid_response is not None:
            # PAID AND SERVED. The tool answers with the route's own payload —
            # the same bytes a paying HTTP caller receives, because it IS that
            # caller, forwarded. Nothing is re-derived and nothing can drift.
            return "response", {
                "jsonrpc": "2.0", "id": msg_id,
                "result": {
                    "content": [{"type": "text",
                                 "text": json.dumps(paid_response)}],
                    "structuredContent": paid_response,
                },
            }
        if payment_required is not None:
            # `x402` above is kept for clients already reading it; the canonical
            # object is added alongside. content[0] is the JSON, as the spec
            # requires, and the sentence moves to second place — a client that
            # reads only content[] still finds the challenge, and now at the index
            # it is specified to look at.
            structured.update(payment_required)
            content = [{"type": "text", "text": json.dumps(payment_required)},
                       {"type": "text", "text": tool_text}]
            result = {"content": content, "structuredContent": structured,
                      "isError": True}
        else:
            result = {"content": content, "structuredContent": structured}
    else:
        return "response", {"jsonrpc": "2.0", "id": msg_id,
                            "error": {"code": -32601,
                                      "message": f"Method not found: {method}"}}
    return "response", {"jsonrpc": "2.0", "id": msg_id, "result": result}


_SSE_SESSIONS: "dict[str, queue.Queue]" = {}
_SSE_SESSIONS_LOCK = threading.Lock()
_SSE_IDLE_CLOSE_SECONDS = 15   # stray/probe GETs never pin a worker thread

#: How many SSE sessions may be open at once.
#:
#: The comment above was wrong, and this is the fix. A stray or probe GET does pin
#: a worker thread — for the whole idle window — and this is the OLD HTTP+SSE
#: transport, open to anyone, unauthenticated and unclassified: it was in neither
#: X402_FREE_ENDPOINTS nor X402_PAID_ENDPOINTS, so nothing rate-limited it either.
#: Procfile runs one worker with eight threads, so eight concurrent SSE clients left
#: none for anything else, /health included, for fifteen seconds at a time — and a
#: repeated curl loop is a total outage. Eight requests. F-21 in
#: docs/PERFORMANCE_AND_ARCHITECTURE_AUDIT.md describes exactly this and was never
#: fixed; it also compounds F-10, because a service that stops answering /health
#: gets restarted into a cold start and cannot serve the health check either.
#:
#: Capping concurrency is the right lever rather than a rate limit: the resource
#: being exhausted is threads, not request rate, and a rate limit would still let
#: eight connections through if they arrived spaced apart. Four leaves half the
#: pool for everything else. Over the cap the answer is 503 with Retry-After, which
#: is honest and retryable — and, because this transport is free, no paying customer
#: can ever be refused by it. The streamable POST /mcp transport has no such limit
#: and is the one modern clients use.
_SSE_MAX_SESSIONS = 4


@discovery_bp.route("/mcp/sse")
def mcp_sse():
    """MCP HTTP+SSE transport (the legacy transport the official python
    ``sse_client`` still speaks).

    Audit #6 BREAK 1 — what was wrong and what this now does:
      * the endpoint event advertised THIS GET-only route, so the client's
        POSTs got 405 -> now it advertises ``POST /mcp/message?sessionId=..``;
      * answers were canned initialize/tools pushes that never matched a
        client request -> every client message now goes through the SAME
        ``_mcp_dispatch`` the streamable route uses and its response is
        queued back onto this stream as ``event: message``;
      * protocolVersion drifted (canned 2024-11-05 vs streamable's echo)
        -> both transports share one dispatcher: identical by construction.
    """
    session_id = secrets.token_urlsafe(18)
    inbox: queue.Queue = queue.Queue()
    with _SSE_SESSIONS_LOCK:
        # Counted and claimed under the same lock: two clients arriving together
        # must not both see room for the last slot.
        if len(_SSE_SESSIONS) >= _SSE_MAX_SESSIONS:
            resp = jsonify({
                "jsonrpc": "2.0",
                "id": None,
                "error": {
                    "code": -32000,
                    "message": (
                        "Too many concurrent SSE sessions (%d). This transport "
                        "holds one worker thread per open stream, so the number "
                        "is capped. Retry, or use POST /mcp — the streamable "
                        "transport, which has no such limit and is what modern "
                        "MCP clients speak." % _SSE_MAX_SESSIONS),
                },
            })
            resp.status_code = 503
            resp.headers["Retry-After"] = "5"
            return resp
        _SSE_SESSIONS[session_id] = inbox
    base_url = request.host_url.rstrip("/")
    post_url = f"{base_url}/mcp/message?sessionId={session_id}"

    def generate():
        last_activity = time.monotonic()
        try:
            yield "event: endpoint\n"
            yield f"data: {post_url}\n\n"
            while True:
                try:
                    payload = inbox.get(timeout=5)
                except queue.Empty:
                    # keep-alive comment; close after a full idle window so
                    # buffered/probe readers never hang a worker.
                    if time.monotonic() - last_activity >= _SSE_IDLE_CLOSE_SECONDS:
                        return
                    yield ": keepalive\n\n"
                    continue
                last_activity = time.monotonic()
                yield "event: message\n"
                yield "data: " + json.dumps(payload) + "\n\n"
        finally:
            with _SSE_SESSIONS_LOCK:
                _SSE_SESSIONS.pop(session_id, None)

    resp = Response(generate(), mimetype="text/event-stream")
    resp.headers["Cache-Control"] = "no-cache"
    resp.headers["X-Accel-Buffering"] = "no"
    return resp


@discovery_bp.route("/mcp/message", methods=["POST"])
def mcp_sse_message():
    """POST half of the HTTP+SSE transport: receives ONE JSON-RPC message
    and answers it on the session's SSE stream.

    Returns 202 for everything — the official client calls raise_for_status()
    on the POST and reads answers from the stream; a JSON-RPC error still
    reaches it as ``event: message``.
    """
    session_id = (request.args.get("sessionId") or "").strip()
    with _SSE_SESSIONS_LOCK:
        inbox = _SSE_SESSIONS.get(session_id)
    if inbox is None:
        return jsonify({"jsonrpc": "2.0", "id": None,
                        "error": {"code": -32001,
                                  "message": "unknown sessionId"}}), 404
    _kind, payload = _mcp_dispatch(request.get_json(silent=True))
    if payload is not None:
        inbox.put(payload)
    return "", 202


@discovery_bp.route("/mcp", methods=["POST", "DELETE"])
def mcp_streamable_http():
    """MCP Streamable HTTP transport (JSON-RPC over POST) — ADDITIVE.

    Catalog scanners (Smithery etc.) require POST-based Streamable HTTP.
    The SSE endpoint (/mcp/sse) remains untouched and continues to work;
    the payment layer and the payTo invariant are not affected — tools
    advertise their x402 price, and paid calls still flow through the
    regular 402 paywall. Stateless: no session id is issued.
    """
    if request.method == "DELETE":
        # Session termination; we are stateless, so nothing to clean up.
        return "", 204

    # ONE dispatcher for both transports (see _mcp_dispatch): identical
    # protocolVersion / tools / x402 answers by construction.
    kind, payload = _mcp_dispatch(request.get_json(silent=True))
    if kind == "invalid":
        return jsonify(payload), 400
    if kind == "notification":
        return "", 202
    return jsonify(payload), 200


@discovery_bp.route("/mcp")
def mcp_info():
    """Human/machine summary of the MCP endpoints we expose."""
    base_url = request.host_url.rstrip("/")
    return jsonify({
        "mcp": {
            "transport": "sse",
            "sse_endpoint": f"{base_url}/mcp/sse",
            "manifest": f"{base_url}/api/mcp/manifest",
        },
        "clients": ["Claude Desktop", "Cursor", "Continue", "LangChain",
                    "any MCP-compatible agent"],
        "payment": "x402 (USDC on Base) — tools are paid endpoints",
    })


def _repo_json_file(filename: str):
    """Serve a JSON file from the repo root VERBATIM (no re-serialisation).

    Verbatim on purpose: a claim file is compared as-is by third-party probes,
    and jsonify() would re-order keys and re-escape the document.
    """
    import logging
    import os as _os

    repo_root = _os.path.dirname(_os.path.dirname(_os.path.dirname(
        _os.path.abspath(__file__))))
    path = _os.path.join(repo_root, filename)
    try:
        with open(path, "rb") as handle:
            return Response(handle.read(), mimetype="application/json")
    except Exception as exc:                      # missing or unreadable
        logging.getLogger(__name__).warning(
            "%s could not be served from %s: %s", filename, path, exc)
        return jsonify({"ok": False, "error": "claim_file_unavailable",
                        "file": filename}), 503


@discovery_bp.route("/glama.json")
def glama_json():
    """Glama's SERVER ownership file (their listing probe looks here too).

    Glama's OWN schema (`https://glama.ai/mcp/schemas/server.json`) defines exactly
    one required key — `maintainers`, "GitHub usernames that have permission to
    maintain the server". That is ownership, not product metadata, so this route
    serves that file VERBATIM from the repository root (one source of truth: the
    same file GitHub and their repo probe read) instead of restating it here.

    The tools, prices and endpoint URL are deliberately NOT invented into this
    file: the schema does not define them, and Glama reads them from the live MCP
    endpoint it health-checks (`{base}/mcp`), which is generated from our single
    price source.
    """
    return _repo_json_file("glama.json")


@discovery_bp.route("/.well-known/glama.json")
def glama_connector_claim():
    """Glama's CONNECTOR HTTP challenge (step 2 of their claim window).

    A different document from the server-ownership file above, and a different
    schema (`.../schemas/connector.json`): it is the one-time `claim` token their
    window shows, bound to the owner's Glama account, served so their
    "Check HTTP challenge" button can read it back. Static by design — no
    addresses, prices or endpoints — so it can never disturb the payment layer.
    """
    return _repo_json_file("glama-connector-claim.json")


@discovery_bp.route("/api/mcp/manifest")
def api_mcp_manifest():
    """MCP (Model Context Protocol) manifest for AI agent M2M payments."""
    from main import (
        _record_request,
        VIP_MONTHLY_USDC,
        VIP_THRESHOLD_USDC,
    )
    from config import (get_base_fee_receiver, KRISTO_SIGNAL_PRICE,
                        KRISTO_ARB_PRICE, KRISTO_WHALEFLOW_PRICE)

    _record_request("api_mcp_manifest", True)
    fee_receiver = get_base_fee_receiver()
    base_url = request.host_url.rstrip("/")

    manifest = {
        "protocol": "x402",
        "version": "1.0",
        "service": "Kristo Intelligence API",
        "description": "AI-powered DeFi trading signals and crypto market intelligence",
        "payment": {
            "chain": "base",
            "chain_id": 8453,
            "currency": "USDC",
            "token_contract": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
            "receiver_address": fee_receiver,
            "tiers": [
                {
                    "id": "micro_request",
                    "name": "Micro Request",
                    # This tier used to carry TWO different numbers in one
                    # object: price_usdc: MICRO_FEE_USDC (the dearest route,
                    # 0.005) while its own description said "from
                    # KRISTO_SIGNAL_PRICE" (0.003). An agent reading the field
                    # budgeted for the wrong one. Both now derive from the live
                    # price map, and the single-price field quotes the cheapest
                    # route so it can never overstate.
                    "price_usdc": _cheapest_route_price(),
                    "price_max_usdc": _dearest_route_price(),
                    "description": (
                        "Pay-per-call: from %s USDC per API request, up to %s "
                        "(per-endpoint pricing in 'endpoints.available')"
                        % (_cheapest_route_price(), _dearest_route_price())),
                    "access": "single API call",
                    "endpoints": ["/api/stats", "/api/sales", "/api/bot-status",
                                  "/api/arb/opportunities", "/api/v1/signal",
                                  "/api/v1/whaleflow"],
                },
                {
                    # $29 is a HUMAN product, not a machine tier. Paying it
                    # issues a Telegram VIP invite code (see "vip_threshold" in
                    # instructions below) and does NOT unlock API calls: no route
                    # consults the subscriber list — main.py reads it only to
                    # classify the payment and to de-duplicate the invite code.
                    # The previous wording ("unlimited for 30 days", endpoints
                    # ["ALL"]) told an autonomous agent that one $29 payment buys
                    # unlimited access, which the code cannot honour.
                    "id": "vip_monthly",
                    "name": "Monthly VIP (human product)",
                    "price_usdc": VIP_MONTHLY_USDC,
                    "description": "Telegram VIP group invite code, sold to humans through Stripe",
                    "access": "Telegram channel only",
                    "endpoints": [],
                    "api_access_granted": False,
                    "unlimited_api_access": False,
                    "machine_purchasable": False,
                    "bonus": "Telegram VIP group invite code",
                },
            ],
        },
        "endpoints": {
            "base_url": base_url,
            "available": [
                # Every one of these reads the paywall's own map. Three used the
                # flat MICRO_FEE_USDC alias and three the per-product constants;
                # both are overridable separately from the map the paywall
                # actually charges from, so any of them could advertise a number
                # we do not charge.
                {"path": "/api/stats", "method": "GET",
                 "cost_usdc": _route_price("/api/stats"),
                 "description": "Market activity and daily stats"},
                {"path": "/api/sales", "method": "GET",
                 "cost_usdc": _route_price("/api/sales"),
                 "description": "Real on-chain sales history"},
                {"path": "/api/bot-status", "method": "GET",
                 "cost_usdc": _route_price("/api/bot-status"),
                 "description": "Telegram bot status"},
                {"path": "/api/arb/opportunities", "method": "GET",
                 "cost_usdc": _route_price("/api/arb/opportunities"),
                 "description": "Live cross-DEX arbitrage spreads on Base (60s refresh)"},
                {"path": "/api/v1/signal", "method": "GET",
                 "cost_usdc": _route_price("/api/v1/signal"),
                 "description": "Trading-agent signals (action, confidence, price_usd, reasoning) for Ethereum (ETH)/ONDO/KAITO/DEGEN"},
                {"path": "/api/v1/whaleflow", "method": "GET",
                 "cost_usdc": _route_price("/api/v1/whaleflow"),
                 "description": "Network-wide whale flow: USDC transfers >= $5M on Base with labeled counterparties (60s refresh)"},
                {"path": "/api/v1/verify-seller", "method": "GET",
                 "cost_usdc": _route_price("/api/v1/verify-seller"),
                 "description": "Audit any USDC receiver on Base before paying it (requires ?receiver=0x…)"},
                {"path": "/api/mcp/manifest", "method": "GET", "cost_usdc": 0.0,
                 "description": "This manifest (free)"},
                {"path": "/dashboard", "method": "GET", "cost_usdc": 0.0,
                 "description": "HTML dashboard (free)"},
            ],
        },
        "instructions": {
            "payment": f"Send USDC to {fee_receiver} on Base network",
            "verification": "Payments are verified on-chain via Transfer event logs",
            # This used to read "Payments >= $0.1 USDC ...", which reads as a
            # cumulative total. The code tests a single transfer
            # (main.py:884, `amount_usd >= VIP_THRESHOLD_USDC`), and when this
            # was written no API route cost anywhere near $0.1 — the dearest was
            # $0.005 — so the promise could not be reached by any ordinary
            # customer. Same family as the volume discount that could never
            # trigger. /api/v1/verify-seller above the old ceiling changed the premise: a
            # single audit now clears the threshold on its own, so the note says
            # which of the two cases holds instead of repeating a claim that is
            # no longer true. The dearest price is generated, never typed.
            "vip_threshold": (
                f"A single payment of at least ${VIP_THRESHOLD_USDC} USDC "
                "generates a Telegram VIP invite code. This is one transfer, "
                "not a running total. The dearest route costs "
                f"${_dearest_route_price():.3f}, so "
                + ("one call to that route earns the invite by itself; the "
                   "cheaper routes will not reach the threshold from per-call "
                   "usage."
                   if _dearest_route_price() >= VIP_THRESHOLD_USDC else
                   "ordinary per-call usage will not reach it.")),
        },
    }
    return jsonify(manifest)


@discovery_bp.route("/.well-known/x402.json")
def well_known_x402():
    """Serve current 8-agent x402 discovery metadata from the catalog store."""
    from main import _build_x402_discovery, _safe_jsonify

    return _safe_jsonify(_build_x402_discovery(request.host_url.rstrip("/")))


@discovery_bp.route("/.well-known/x402")
def well_known_x402_scan():
    """x402scan-compatible discovery file (no .json extension).

    Returns the fan-out format expected by x402scan:
        {
          "version": 1,
          "resources": [{"url": "https://host/api/stats",
                         "name": "…", "description": "…"}, …],
          "ownershipProofs": ["0x..."]
        }

    Each resource is an OBJECT with url/name/description — the exact shape
    x402 Doctor's well-known-names check reads ("Serve the resources as
    {"url": …, "name": …, "description": …} objects"): directories such as
    the XRPL AI Hub list resources BY name+description, and 6 bare URL
    strings would show up unnamed ("6 of 6 resources … have no name and
    description"). Same 6 URLs, same order as before; only the wrapping
    changed.

    This is the discovery endpoint that https://www.x402scan.com/resources/register
    probes when a user submits the server URL. See:
    https://github.com/Merit-Systems/x402scan/blob/main/docs/DISCOVERY.md
    """
    from main import (X402_RECEIVER_ADDRESS, X402_FEE_USDC, FREE_TIER_LIMIT,
                      X402_PRICE_MAP)

    base_url = request.host_url.rstrip("/")
    # The price note is DERIVED, never typed: it must describe the same numbers
    # the 402 challenges will ask for.
    _prices = sorted({round(float(p), 6) for p in X402_PRICE_MAP.values()})
    _cheapest = _prices[0]
    price_range_note = (
        "$%.3f per call on every route" % _prices[0] if len(_prices) == 1
        else "prices per route: %s" % ", ".join("$%.3f" % p for p in _prices)
    )
    tier_note = (
        f"after the free tier ({FREE_TIER_LIMIT} call{'s' if FREE_TIER_LIMIT != 1 else ''} per IP) is exhausted"
        if FREE_TIER_LIMIT > 0
        else "for each request (no free tier: every unpaid call returns HTTP 402)"
    )
    return jsonify({
        "version": 1,
        # Objects, not bare strings (x402 Doctor well-known-names): each
        # entry names the resource so directories can list it as
        # "Kristo — …" instead of a generic label. Order and URLs are the
        # exact 6 paid routes, unchanged.
        "resources": [
            {
                "url": f"{base_url}/api/stats",
                "name": "Kristo — Market Stats",
                "description": ("Real-time market activity and daily "
                                "aggregated stats for Base DeFi."),
            },
            {
                "url": f"{base_url}/api/sales",
                "name": "Kristo — On-Chain Sales",
                "description": ("Verified on-chain sales history from the "
                                "Base ecosystem with amounts and timestamps."),
            },
            {
                "url": f"{base_url}/api/bot-status",
                "name": "Kristo — Bot Status",
                "description": ("Telegram sales bot status: heartbeat, "
                                "subscribers and processed commands."),
            },
            {
                "url": f"{base_url}/api/arb/opportunities",
                "name": "Kristo — Arbitrage Radar",
                "description": ("Live cross-DEX arbitrage spreads on Base, "
                                "refreshed every 60 seconds."),
            },
            {
                "url": f"{base_url}/api/v1/signal",
                "name": "Kristo — Trading Signal",
                "description": ("Live DeFi trading signal: action, "
                                "confidence and reasoning for "
                                "Ethereum (ETH)/ONDO/KAITO/DEGEN."),
            },
            {
                "url": f"{base_url}/api/v1/whaleflow",
                "name": "Kristo — Whale Flow",
                "description": ("USDC whale transfers >= $5M on Base with "
                                "labeled counterparties."),
            },
            {
                "url": f"{base_url}/api/v1/verify-seller",
                "name": "Kristo — Seller Verification",
                "description": ("Audit any USDC receiver on Base before paying "
                                "it: distinct payers, repeat payers, "
                                "concentration, probes vs customers."),
            },
        ],
        "ownershipProofs": [X402_RECEIVER_ADDRESS],
        # The price line is GENERATED from the price map (see the top of this
        # module) and states a per-route range: an external agent (Circadian,
        # issue #1 on 06.09) correctly reported that an earlier wording implied
        # ONE price for all resources while four of them cost more. The 402 body
        # is the authority — this text must never contradict it.
        "instructions": (
            "Every unpaid call returns HTTP 402 with a canonical x402 v2 "
            f"challenge: send the EXACT USDC amount from that response's "
            f"`accepts[0].amount` ({price_range_note}, USDC on Base, chain 8453) "
            "to " + X402_RECEIVER_ADDRESS + f" {tier_note}. "
            "Retry with the standard X-PAYMENT header (x402 v2, settled via the "
            "Coinbase x402 facilitator) or X-Payment-Proof: base64url(JSON("
            "{payer, transaction_hash, amount_usdc}))."
        ),
    })


@discovery_bp.route("/mcp.json")
def mcp_json():
    """MCP (Model Context Protocol) discovery file for AI agent indexing."""
    from main import (
        X402_CHAIN,
        X402_CHAIN_ID,
        X402_FEE_USDC,
        X402_RECEIVER_ADDRESS,
        X402_USDC_CONTRACT,
        FREE_TIER_LIMIT,
    )
    # KRISTO_WHALEFLOW_PRICE was NOT in this import while the tool list below
    # uses it -> NameError -> live 500 on /mcp.json. That is the exact failure
    # "Audit #6 BREAK 2" recorded one route over, and it survived for the same
    # reason: no test called this route. Both are fixed together.
    from config import (KRISTO_SIGNAL_PRICE, KRISTO_ARB_PRICE,
                        KRISTO_WHALEFLOW_PRICE)

    # Cheapest real route price — the same derived-floor rule as the OpenAPI
    # security blurb: never quote one flat amount for routes that differ.
    _cheapest = min(float(KRISTO_SIGNAL_PRICE), float(KRISTO_ARB_PRICE))

    base_url = request.host_url.rstrip("/")

    # Route -> tool name, taken from the same list POST /mcp answers tools/list
    # with, so this document cannot name a tool the protocol does not serve.
    # Deliberately a plain dict with no .get default: if a paid route ever gains
    # no tool, this raises here rather than quietly publishing a name that an
    # agent will then fail to call.
    _mcp_names = {}
    for _tool_entry in _mcp_tools(base_url):
        _mcp_names[_tool_entry["x402"]["endpoint"][len(base_url):]] = (
            _tool_entry["name"])

    def _mcp_name(route):
        return _mcp_names[route]

    return jsonify({
        "schema_version": "1.0",
        "name": "Kristo Intelligence API",
        "description": "AI-powered DeFi trading signals and crypto market intelligence on Base",
        "base_url": base_url,
        "protocol": "x402",
        "payment": {
            "chain": X402_CHAIN,
            "chain_id": X402_CHAIN_ID,
            "currency": "USDC",
            "token_contract": X402_USDC_CONTRACT,
            "receiver_address": X402_RECEIVER_ADDRESS,
            # One flat "per call" number cannot be true for six routes at two
            # prices. The single-price field quotes the CHEAPEST so it can never
            # overstate (see _cheapest_route_price), the range bounds it, and the
            # 402 always states the exact amount.
            "price_per_call_usdc": _cheapest_route_price(),
            "price_max_usdc": _dearest_route_price(),
            "free_tier_limit": FREE_TIER_LIMIT,
            # No "monthly_vip_usdc" field: $29 is a human product sold through
            # Stripe. It issues a Telegram invite code and does NOT unlock API
            # calls — same reasoning as the note in agents_json() below.
            "unlocks_api_calls_on_extra_payment": False,
        },
        # All six paid routes. The list used to carry only three of them, so an
        # agent reading this file could not discover /api/v1/signal,
        # /api/v1/whaleflow or /api/arb/opportunities at all.
        # "free_tier_eligible" is computed from the live limit instead of being
        # hardcoded True: production runs with FREE_TIER_LIMIT=0, so promising a
        # free call here was simply untrue.
        #
        # The NAMES now come from _mcp_tools, which is the list POST /mcp answers
        # tools/list with. They had drifted: this file said "get_sales_history"
        # while the protocol, agents.json and server.json all said
        # "get_onchain_sales", so an agent that trusted this document called a
        # tool that does not exist and never found the one that does. _mcp_tools
        # already carried the rule in its docstring — "the names match
        # agents_json() so one product is not two names" — and this copy broke it.
        #
        # The three free entries that used to sit in "tools" are plain HTTP GETs,
        # not MCP tools, and tools/call on them fails. They are still advertised,
        # under "free_endpoints" below, where nothing tries to call them as tools.
        "tools": [
            {
                "name": _mcp_name("/api/stats"),
                "description": "Get market activity, daily stats, the official eight-agent catalog, and real-time market data (CoinGecko, DEXScreener, Fear & Greed)",
                "endpoint": f"{base_url}/api/stats",
                "method": "GET",
                "cost_usdc": _route_price("/api/stats"),
                "free_sample": f"{base_url}/api/stats/sample",
                "free_tier_eligible": bool(FREE_TIER_LIMIT),
            },
            {
                "name": _mcp_name("/api/sales"),
                "description": "Get real on-chain sales history (USDC transfers) and live market snapshot",
                "endpoint": f"{base_url}/api/sales",
                "method": "GET",
                "cost_usdc": _route_price("/api/sales"),
                "free_sample": f"{base_url}/api/sales/sample",
                "free_tier_eligible": bool(FREE_TIER_LIMIT),
            },
            {
                "name": _mcp_name("/api/bot-status"),
                "description": "Get Telegram bot integration status and wallet info",
                "endpoint": f"{base_url}/api/bot-status",
                "method": "GET",
                "cost_usdc": _route_price("/api/bot-status"),
                "free_sample": f"{base_url}/api/bot-status/sample",
                "free_tier_eligible": bool(FREE_TIER_LIMIT),
            },
            {
                "name": _mcp_name("/api/arb/opportunities"),
                "description": "Live cross-DEX arbitrage spreads on Base, refreshed every 60 seconds",
                "endpoint": f"{base_url}/api/arb/opportunities",
                "method": "GET",
                "cost_usdc": _route_price("/api/arb/opportunities"),
                "free_sample": f"{base_url}/api/arb/opportunities/sample",
                "free_tier_eligible": bool(FREE_TIER_LIMIT),
            },
            {
                "name": _mcp_name("/api/v1/signal"),
                "description": "Trading-agent signals (action, confidence, price_usd, reasoning) for Ethereum (ETH)/ONDO/KAITO/DEGEN",
                "endpoint": f"{base_url}/api/v1/signal",
                "method": "GET",
                "cost_usdc": _route_price("/api/v1/signal"),
                "free_sample": f"{base_url}/api/v1/signal/sample",
                "free_tier_eligible": bool(FREE_TIER_LIMIT),
            },
            {
                "name": _mcp_name("/api/v1/whaleflow"),
                "description": "Large USDC transfers on Base with labeled counterparties",
                "endpoint": f"{base_url}/api/v1/whaleflow",
                "method": "GET",
                "cost_usdc": _route_price("/api/v1/whaleflow"),
                "free_sample": f"{base_url}/api/v1/whaleflow/sample",
                "free_tier_eligible": bool(FREE_TIER_LIMIT),
            },
            {
                "name": _mcp_name("/api/v1/verify-seller"),
                "description": ("Audit any USDC receiver on Base before paying it: "
                                "distinct payers, repeat payers, concentration, "
                                "probes vs customers. Requires a receiver address."),
                "endpoint": f"{base_url}/api/v1/verify-seller",
                "method": "GET",
                "cost_usdc": _route_price("/api/v1/verify-seller"),
                "free_sample": f"{base_url}/api/v1/verify-seller/sample",
                "free_tier_eligible": bool(FREE_TIER_LIMIT),
                # The only advertised tool that takes input, so the document
                # names it rather than leaving an agent to guess.
                "parameters": [
                    {"name": "receiver", "in": "query", "required": True},
                    {"name": "days", "in": "query", "required": False,
                     "default": 7},
                ],
            },
        ],
        "free_endpoints": [
            {
                "name": "mcp_manifest",
                "description": "The full MCP/x402 payment manifest (free)",
                "endpoint": f"{base_url}/api/mcp/manifest",
                "method": "GET",
            },
            {
                "name": "x402_discovery",
                "description": "x402 payment discovery metadata (free)",
                "endpoint": f"{base_url}/.well-known/x402.json",
                "method": "GET",
            },
            {
                "name": "openapi_spec",
                "description": "OpenAPI 3.0 specification (free)",
                "endpoint": f"{base_url}/openapi.json",
                "method": "GET",
            },
        ],
        "data_sources": {
            "coingecko": "https://api.coingecko.com/api/v3/simple/price",
            "dexscreener": "https://api.dexscreener.com",
            "fear_greed_index": "https://api.alternative.me/fng/",
        },
        "cache_ttl_minutes": 15,
        "instructions": {
            "payment": f"Send the EXACT USDC amount stated by the endpoint's 402 "
                       f"challenge (from ${_cheapest:.3f}) on Base to "
                       f"{X402_RECEIVER_ADDRESS}",
            "verification": "Payments verified on-chain via ERC-20 Transfer event logs",
            "retry": "After payment confirmation, retry the endpoint to access data",
        },
    })


@discovery_bp.route("/openapi.json")
def openapi_spec():
    """OpenAPI 3.0 specification for AI agent discovery (x402scan-compatible).

    Includes:
    - x-discovery.ownershipProofs (top-level, x402scan preferred location)
    - x-payment-info per paid operation (x402scan required)
    - NO security scheme on paid ops: paid = x-payment-info + 402 only
      (an apiKey scheme misclassified routes as "apiKey+paid"; see #1270)
    - 402 response declared on every paid operation
    """
    from main import (
        X402_CHAIN,
        X402_CHAIN_ID,
        X402_FEE_USDC,
        X402_RECEIVER_ADDRESS,
        X402_USDC_CONTRACT,
        FREE_TIER_LIMIT,
    )
    # Per-endpoint x402 prices (single source of truth: config.py). The newer
    # routes carry a different headline price than the flat X402_FEE_USDC used
    # by the original three operations.
    from config import (
        KRISTO_ARB_PRICE,
        KRISTO_SIGNAL_PRICE,
        KRISTO_WHALEFLOW_PRICE,
    )

    # The security-scheme blurb used to state one flat amount ("send 0.005 USDC")
    # while the routes cost 0.003-0.005 — a buyer could overpay or misread the
    # product. It now points at the only authoritative number, the route's own 402
    # challenge, and quotes the cheapest route as a floor (derived, never typed).
    # It used to average only THREE of the six routes by naming their constants;
    # it now reads the paywall's own map, so a route added or repriced later
    # cannot leave this number behind.
    _cheapest = _cheapest_route_price()
    _dearest = _dearest_route_price()

    def _fmt_amount(value):
        """Exactly the decimals the value needs, never fewer than three.

        `str()` was used here and it is truthful but inconsistent: str(0.005)
        is "0.005" while str(1.0) is "1.0", so /api/v1/verify-seller published
        its $1.00 as "1.0" while every other route published three places. The
        convention is three, but three places would LIE about a finer price —
        an environment-overridable 0.0005 would be advertised as 0.001 — so
        trailing zeros are trimmed only down to the third decimal.
        """
        text = ("%.6f" % float(value)).rstrip("0")
        if text.endswith("."):
            text += "000"
        while len(text.split(".")[1]) < 3:
            text += "0"
        return text

    base_url = request.host_url.rstrip("/")
    # x-payment-info shared block for all paid operations.
    # x402scan expects `protocols` to be an ARRAY OF PROTOCOL OBJECTS and a
    # single pricing mode object with a currency — see its integration spec:
    # "Set x-payment-info.protocols (array of protocol objects) and one pricing
    # mode (fixed or dynamic) with currency."
    # A plain ["x402"] array of strings is not parsed, which is why every paid
    # route was indexed without a usable price.
    # Receiver / chain / chain_id / token_contract remain available at the
    # document level in info.x402, and the runtime 402 challenge stays the
    # authoritative source of payment details.
    payment_info = {
        "price": {
            "mode": "fixed",
            "currency": "USD",
            # `mode: fixed` is kept for schema compatibility, but the amount must
            # not overstate: it is the CHEAPEST paid route. Every operation below
            # carries its own exact price, and the 402 is authoritative.
            "amount": _fmt_amount(_cheapest),
            "amount_max": _fmt_amount(_dearest),
        },
        "protocols": [{"x402": {}}],
    }
    # Standard 402 response with required payment headers
    response_402 = {
        "description": "Payment Required — x402 challenge with exact USDC amount and receiver",
        "headers": {
            "X-Payment-Required": {"schema": {"type": "string"}},
            "X-Payment-Address": {"schema": {"type": "string"}},
            "X-Payment-Amount-USDC": {"schema": {"type": "string"}},
        },
    }

    def _paid_op(summary, description, cost_usdc=None, parameters=None):
        """Paid operation entry.

        `cost_usdc` overrides the per-call price advertised in
        x-payment-info/x402. Omitting it falls back to the shared block, which
        states the CHEAPEST route — the old fallback was the flat
        X402_FEE_USDC, the dearest one, so an operation that forgot to declare
        its own price advertised more than the paywall charges.
        """
        cost = _cheapest if cost_usdc is None else cost_usdc
        if cost == _cheapest:
            op_payment_info = payment_info
        else:
            op_payment_info = dict(payment_info)
            op_payment_info["price"] = {
                **payment_info["price"],
                "amount": _fmt_amount(cost),
            }
        # x402 Doctor "openapi-input-schema" (21.10): x402scan does not
        # register a paid operation without an input declaration. The original
        # routes are plain GET handlers with NO query parameters (no
        # request.args in any of them), so for those the honest declaration is
        # an explicit empty parameters list plus a "no parameters" note in the
        # description — a paid operation that stays silent about its input
        # reads as "may need input we can't see". A route that DOES take input
        # passes `parameters` and gets neither the empty list nor the note, so
        # the sentence never describes a route that takes a query string.
        if parameters is None:
            description = (description
                           + " Takes no parameters (plain GET, no query "
                           "string).")
        return {
            "summary": summary,
            "description": description,
            "parameters": [] if parameters is None else parameters,
            "x-payment-info": op_payment_info,
            "x402": {"cost_usdc": cost, "free_tier_eligible": True},
            # NO security/securitySchemes for x402 (maintainer review, x402scan
            # #1270): an apiKey scheme here made agentcash classify every paid
            # route as "apiKey+paid" and keyless agents bailed out BEFORE
            # paying. Paid = x-payment-info + a 402 response, nothing else.
            "responses": {
                # x402scan: an operation without an input/output schema is
                # reported as "Input/Output Schema Missing", so every paid route
                # declares a minimal JSON response schema.
                "200": {
                    "description": "Successful response",
                    "content": {
                        "application/json": {
                            "schema": {"type": "object"}
                        }
                    },
                },
                "402": response_402,
            },
        }

    def _free_op(summary, description):
        return {
            "summary": summary,
            "description": description,
            # Explicitly public: excludes these routes from x402 402-probing
            # (x402scan/agentcash: routes without an auth mode declaration
            # get probed for a 402 challenge and show up as errors).
            "security": [],
            "responses": {"200": {"description": "Successful response"}},
        }

    spec = {
        "openapi": "3.0.3",
        "info": {
            "title": "Kristo Intelligence API",
            # Was "6.0.0" while server.json published 6.2.0: the API document and
            # the registry artifact disagreed about which release this is.
            "version": SERVICE_VERSION,
            "description": "AI-powered DeFi trading signals and crypto market "
                           "intelligence — pay-per-call USDC on Base (x402 v2, "
                           "no API keys). Example: curl -i "
                           "https://kristo-intelligence-api.onrender.com/api/v1/signal "
                           "→ 402 → pay accepts[0].amount → retry with "
                           "X-PAYMENT → 200.",
            # x402scan lists info.x-guidance among the required top-level fields;
            # it is the agent-facing "how do I call this" hint.
            "x-guidance": "GET-only paid JSON routes. Every unpaid call returns HTTP 402 "
                          "with a self-describing x402 v2 challenge (exact USDC amount, "
                          "receiver, chain); pay on Base and retry.",
            "x402": {
                "protocol": "x402",
                "receiver_address": X402_RECEIVER_ADDRESS,
                "currency": "USDC",
                "chain": X402_CHAIN,
                "chain_id": X402_CHAIN_ID,
                "token_contract": X402_USDC_CONTRACT,
                "price_per_call_usdc": _cheapest,
                "price_max_usdc": _dearest,
                "free_tier_limit": FREE_TIER_LIMIT,
            },
            # Ownership verification + contact channel for agents/operators
            # (x402scan: "Add info.contact.email to your openapi.json")
            "contact": {"email": "hristovdimitri2@gmail.com"},
        },
        "x-discovery": {
            "ownershipProofs": [X402_RECEIVER_ADDRESS],
        },
        "servers": [{"url": base_url}],
        "paths": {
            "/api/stats": {"get": _paid_op(
                "Market activity and daily stats",
                "Returns real-time market activity, daily stats, and aggregated metrics for the Base DeFi ecosystem.",
                _route_price("/api/stats"),
            )},
            "/api/sales": {"get": _paid_op(
                "Real on-chain sales history",
                "Returns verified on-chain sales transactions from the Base ecosystem, including amounts, token pairs, and timestamps.",
                _route_price("/api/sales"),
            )},
            "/api/bot-status": {"get": _paid_op(
                "Telegram bot integration status",
                "Returns the current status of the Telegram sales bot, including last bulletin time, subscriber count, and operational metrics.",
                _route_price("/api/bot-status"),
            )},
            "/api/arb/opportunities": {"get": _paid_op(
                "Cross-DEX arbitrage radar",
                "Live cross-DEX arbitrage spreads on Base (DEXScreener), refreshed every 60 seconds.",
                _route_price("/api/arb/opportunities"),
            )},
            "/api/v1/signal": {"get": _paid_op(
                "Live DeFi trading signal",
                "Live DeFi trading signal: action, confidence and one-line reasoning for Ethereum (ETH)/ONDO/KAITO/DEGEN — refreshed under 5 minutes from live market data.",
                _route_price("/api/v1/signal"),
            )},
            "/api/v1/whaleflow": {"get": _paid_op(
                "Live whale flow",
                "Live whale flow: USDC transfers >= $5M on Base with labeled counterparties — scanned continuously (freshness follows the RPC provider's limits; the response always states the block scanned to).",
                _route_price("/api/v1/whaleflow"),
            )},
            # The only paid operation that takes input, so it is also the only
            # one that declares `parameters` instead of the shared "takes no
            # parameters" note. `receiver` is required; `days` is optional and
            # the route clamps it to its own bounds, which is why it is declared
            # with the same defaults a caller would get by omitting it.
            "/api/v1/verify-seller": {"get": _paid_op(
                "Seller verification — audit any USDC receiver on Base",
                "Reads the incoming USDC transfers of ANY receiver address on Base and reports what a payer would want to know before paying it: distinct paying addresses, repeat payers, how concentrated the revenue is, treasury-sized flows, and which addresses look like verification probes rather than customers. Answers 'is this seller safe to pay' and 'verify an x402 endpoint before paying' with chain data instead of a reputation score. Reports its own coverage and says `partial` or `failed` when it could not read the whole window, because a zero it did not measure is indistinguishable from a zero that is real.",
                _route_price("/api/v1/verify-seller"),
                parameters=[
                    {
                        "name": "receiver",
                        "in": "query",
                        "required": True,
                        "description": "The USDC receiver address to audit. "
                                       "EVM address; a bare 40-hex address is "
                                       "accepted and checksummed.",
                        "schema": {"type": "string"},
                    },
                    {
                        "name": "days",
                        "in": "query",
                        "required": False,
                        "description": "Lookback window in days. Clamped to "
                                       "the engine's bounds; the window "
                                       "actually walked is published as "
                                       "coverage.lookback_days.",
                        "schema": {"type": "integer", "minimum": 1,
                                   "maximum": 30, "default": 7},
                    },
                ],
            )},
            "/api/v1/agents": {"get": _free_op(
                "Agent catalog (free)",
                "Returns the 8-agent catalog with descriptions, categories, and pricing for each agent SKU.",
            )},
            "/api/mcp/manifest": {"get": _free_op(
                "MCP/x402 payment manifest (free)",
                "Machine-readable MCP/x402 manifest for AI agent discovery.",
            )},
            "/.well-known/x402": {"get": _free_op(
                "x402 discovery file (x402scan-compatible, free)",
                "Returns {version: 1, resources: [...], ownershipProofs: [...]} format expected by x402scan.",
            )},
            "/.well-known/x402.json": {"get": _free_op(
                "x402 payment metadata (legacy, free)",
                "Legacy x402 payment discovery metadata with receiver address, pricing tiers, and endpoint list.",
            )},
            "/openapi.json": {"get": _free_op(
                "This OpenAPI specification (free)",
                "OpenAPI 3.0 specification with x-payment-info per operation.",
            )},
            "/llms.txt": {"get": _free_op(
                "LLM-friendly API description (free)",
                "Plain-text API description for LLMs.",
            )},
            "/health": {"get": _free_op(
                "Health check (free)",
                "Service health status.",
            )},
            "/dashboard": {"get": _free_op(
                "HTML dashboard (free)",
                "HTML dashboard page with charts and metrics.",
            )},
        },
        # components.securitySchemes.x402 REMOVED (x402scan #1270): the apiKey
        # scheme made agentcash classify paid routes as "apiKey+paid" (keyless
        # agents quit before paying) and its description advertised a wrong
        # manual flow ("retry with X-Payment-Address …"). The real flow is the
        # 402 challenge + X-PAYMENT / PAYMENT-SIGNATURE header — documented in
        # x-payment-info and the 402 response, both kept above.
    }
    return jsonify(spec)


@discovery_bp.route("/favicon.ico")
@discovery_bp.route("/favicon.svg")
def favicon():
    """Minimal SVG favicon (x402scan/agentcash check /favicon.ico|png|svg)."""
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
        '<rect width="32" height="32" rx="6" fill="#1a1a2e"/>'
        '<text x="16" y="22" font-family="monospace" font-size="16" '
        'font-weight="bold" fill="#00ff88" text-anchor="middle">K</text>'
        "</svg>"
    )
    resp = Response(svg, mimetype="image/svg+xml")
    resp.headers["Cache-Control"] = "public, max-age=86400"
    return resp


@discovery_bp.route("/robots.txt")
def robots_txt():
    """Allow all crawlers; point them at the key discovery endpoints."""
    content = f"""User-agent: *
Allow: /
Disallow: /api/admin/

# Machine-readable discovery endpoints for AI agents and crawlers
Sitemap: {request.host_url.rstrip('/')}/sitemap.xml
"""
    return Response(content, mimetype="text/plain")


@discovery_bp.route("/sitemap.xml")
def sitemap_xml():
    """Dynamic sitemap for SEO — always reflects the current host."""
    base_url = request.host_url.rstrip("/")
    # Only genuinely indexable pages belong in a sitemap. /dashboard, /nexus and
    # /agents all serve the SAME noindex dashboard HTML (verified live: identical
    # 45,971-byte response), so listing them asked crawlers to index three
    # duplicate pages that each answer "do not index me" - a direct contradiction
    # that costs trust. Meanwhile /validation - a real content page - was missing
    # from the sitemap entirely. The machine-readable endpoints stay: they are
    # not HTML, but crawlers and agent registries do use sitemaps to find them.
    pages = [
        ("/", "1.0", "daily"),
        ("/validation", "0.8", "weekly"),
        ("/pricing", "0.8", "weekly"),
        ("/launch", "0.7", "weekly"),
        ("/terms", "0.4", "monthly"),
        ("/llms.txt", "0.6", "weekly"),
        ("/openapi.json", "0.6", "weekly"),
        ("/.well-known/x402.json", "0.6", "weekly"),
        ("/.well-known/ai-plugin.json", "0.6", "weekly"),
        ("/agents.json", "0.6", "weekly"),
        ("/api/mcp/manifest", "0.6", "weekly"),
    ]
    urls = "\n".join(
        f"  <url><loc>{base_url}{path}</loc>"
        f"<changefreq>{freq}</changefreq><priority>{prio}</priority></url>"
        for path, prio, freq in pages
    )
    xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{urls}
</urlset>"""
    return Response(xml, mimetype="application/xml")


#: IndexNow key (32 hex characters).
#:
#: IndexNow lets a site tell Bing, Yandex and Seznam IMMEDIATELY that a URL was
#: added or changed, instead of waiting to be re-crawled. Ownership is proven
#: simply by hosting this exact key at https://<host>/<key>.txt — no account, no
#: login, no verification meta tag. That makes this the one indexing channel we
#: can open without waiting on anyone, which matters because being absent from
#: public search is our single biggest visibility gap.
INDEXNOW_KEY = "2c90228c28c14958f379d6fd487411d3"


@discovery_bp.route("/" + INDEXNOW_KEY + ".txt")
def indexnow_key_file():
    """Serve the IndexNow ownership proof at the exact path it must live at.

    The rule uses the literal key rather than a `<key>` converter on purpose: a
    converter would match ANY root-level .txt path and could shadow a future
    file. /robots.txt and /sitemap.xml are unaffected.
    """
    return Response(INDEXNOW_KEY + "\n", mimetype="text/plain")


#: Google Search Console ownership proof.
#:
#: GSC is where search queries, impressions and crawl errors become visible, and it
#: is the one search surface we cannot reach any other way. It verifies ownership by
#: fetching this exact file from the site root.
#:
#: This is a URL-prefix property, never a Domain property, and that is forced rather
#: than chosen: our host is an onrender.com subdomain, so the DNS TXT record a Domain
#: property requires is one we can never publish. The URL-prefix method asks only for
#: a file we can serve.
#:
#: The rule is the literal filename rather than a converter, for the same reason the
#: IndexNow route above is: /google<string>.html would match any future root-level
#: google*.html file and quietly shadow it.
GOOGLE_SITE_VERIFICATION_TOKEN = "18e5c8e044f8ea37"
GOOGLE_SITE_VERIFICATION_FILE = "google%s.html" % GOOGLE_SITE_VERIFICATION_TOKEN

#: The exact bytes Google issued, with no trailing newline. Their downloaded file is
#: 53 bytes and ends at the "l" of ".html". A newline would very likely still verify,
#: but there is no reason to serve something other than what they handed us.
GOOGLE_SITE_VERIFICATION_BODY = (
    "google-site-verification: " + GOOGLE_SITE_VERIFICATION_FILE)


@discovery_bp.route("/" + GOOGLE_SITE_VERIFICATION_FILE)
def google_site_verification_file():
    """Serve the Google Search Console ownership proof at its exact path.

    Google re-fetches this file to keep the property verified, so removing it later
    would eventually un-verify the site. It is not a secret: it grants nothing beyond
    the ability to see this site's own search statistics.
    """
    return Response(GOOGLE_SITE_VERIFICATION_BODY, mimetype="text/html")


#: One-time ownership token issued by x402-list.com on 2026-11-03 for the listing
#: update that corrects the header name in our description. It is published in
#: the source because the directory has to read it back from this exact path, it
#: stops being accepted on 2026-11-06T16:45Z, and it is not a secret. The
#: environment variable overrides it, so a future review can be published without
#: touching the source again.
X402LIST_OWNERSHIP_TOKEN = (
    "x402list-verify-w2MY9CZlPMUZGlduF-eSweszp2bytYkrxafDFnvVLPA")
X402LIST_OWNERSHIP_TOKEN_EXPIRES = datetime(2026, 11, 6, 16, 45, 52,
                                            tzinfo=timezone.utc)


@discovery_bp.route("/.well-known/x402list.txt")
def x402list_verification():
    """Ownership proof for a listing update on x402-list.com.

    x402-list.com proves an operator owns a listing by issuing a one-time token
    and asking them to publish it at this exact path, which it then reads back
    before a human reviews the change. The token arrives only after the update
    form is submitted and expires in 72 hours.

    The environment variable wins over the bundled token, and the bundled token
    stops being served once it expires — so this path only ever answers with a
    proof that is still current. With nothing valid to serve it answers 404
    rather than an empty 200, because a token left over from a finished review
    would otherwise sit here as an ownership claim we can no longer support. The
    token is not a secret: the directory requires it to be public.
    """
    token = (os.environ.get("X402LIST_VERIFICATION_TOKEN")
             or X402LIST_OWNERSHIP_TOKEN).strip()
    if not token:
        return Response("not configured\n", status=404, mimetype="text/plain")
    if (token == X402LIST_OWNERSHIP_TOKEN
            and datetime.now(timezone.utc) >= X402LIST_OWNERSHIP_TOKEN_EXPIRES):
        return Response("expired\n", status=404, mimetype="text/plain")
    return Response(token + "\n", mimetype="text/plain")


@discovery_bp.route("/agents.json")
def agents_json():
    """agents.json — emerging standard for AI-agent service discovery.

    Describes the service, its x402 payment scheme, and the endpoints an
    autonomous agent can call — so agents can find, price and pay for this
    API without any human interaction.
    """
    from main import (
        X402_CHAIN_ID,
        X402_FEE_USDC,
        X402_RECEIVER_ADDRESS,
        X402_USDC_CONTRACT,
        FREE_TIER_LIMIT,
        # The single public vitrine. The endpoint list below is GENERATED from
        # this instead of being typed out again: the hand-typed version had
        # drifted to 5 of the 6 real routes, quietly hiding /api/v1/whaleflow
        # from every agent that reads this file. (Audit #6 BREAK 2 was the same
        # class of failure one level down — an untested route served a live 500.)
        REAL_X402_ROUTES,
    )

    base_url = request.host_url.rstrip("/")
    return jsonify({
        "spec_version": "1.0",
        "name": "Kristo Intelligence",
        "description": (
            "AI-powered DeFi trading signals and crypto market intelligence "
            "on Base. Autonomous agents pay per call with USDC via x402."
        ),
        "url": base_url,
        "payment": {
            "protocol": "x402",
            "chain": "base",
            "chain_id": X402_CHAIN_ID,
            "currency": "USDC",
            "token_contract": X402_USDC_CONTRACT,
            "receiver_address": X402_RECEIVER_ADDRESS,
            # Never one flat number for routes at two prices: the single-price
            # field quotes the cheapest so it cannot overstate, and the range
            # bounds it (see _cheapest_route_price).
            "price_per_call_usdc": _cheapest_route_price(),
            "price_max_usdc": _dearest_route_price(),
            "free_tier_limit": FREE_TIER_LIMIT,
            # There is deliberately NO "monthly_vip_usdc" field here any more.
            # $29 is a HUMAN product sold through Stripe: paying it issues a
            # Telegram invite code and does NOT unlock API calls. No route
            # consults the subscriber list — main.py only reads it to classify
            # the payment and to avoid issuing a second invite code to the same
            # wallet. Leaving the field here told an autonomous agent it could
            # spend $29 on unlimited access it cannot receive.
            "unlocks_api_calls_on_extra_payment": False,
        },
        # Generated from the single public vitrine (main.REAL_X402_ROUTES) — the
        # same list llms.txt, the landing pages and the tests read.
        "endpoints": [
            {
                "path": route["endpoint"],
                "method": "GET",
                "name": route.get("name", ""),
                "description": (route.get("description") or "").strip(),
                "cost_usdc": float(route["price_usdc"]),
                "free_sample": "%s/sample" % route["endpoint"],
                "free_tier_eligible": False,
            }
            for route in REAL_X402_ROUTES
        ],
        "docs": {
            "llms_txt": f"{base_url}/llms.txt",
            "openapi": f"{base_url}/openapi.json",
            "x402_discovery": f"{base_url}/.well-known/x402.json",
            "mcp_manifest": f"{base_url}/api/mcp/manifest",
            # A2A (protocol 0.3.0). Published here and in llms.txt because the
            # card otherwise existed only at its conventional path: an agent
            # reading this manifest — which is exactly the agent that buys —
            # learned our six HTTP routes and nothing about the A2A surface.
            # The card answers the same six products with their free sample and
            # their terms; it does not hand out the paid payload, and its own
            # capabilities block says so.
            "a2a_agent_card": f"{base_url}/.well-known/agent-card.json",
            "a2a_endpoint": f"{base_url}/a2a",
        },
        "payment_verification": "On-chain ERC-20 Transfer event monitoring",
    })


@discovery_bp.route("/.well-known/ai-plugin.json")
def ai_plugin_json():
    """OpenAI ai-plugin.json manifest — the classic ChatGPT-plugin discovery
    format that many agent scanners still crawl for."""
    from main import (
        X402_CHAIN_ID,
        X402_FEE_USDC,
        X402_RECEIVER_ADDRESS,
        X402_USDC_CONTRACT,
        FREE_TIER_LIMIT,
        REAL_X402_ROUTES,
    )

    # Same derived-floor rule as the other manifests: never quote one flat amount
    # for routes that differ. This blurb used to state X402_FEE_USDC alone, which
    # is the most expensive route, so two of the six real routes were advertised
    # above their actual price.
    _floor = min(float(route["price_usdc"]) for route in REAL_X402_ROUTES)
    _ceiling = max(float(route["price_usdc"]) for route in REAL_X402_ROUTES)

    base_url = request.host_url.rstrip("/")
    return jsonify({
        "schema_version": "v1",
        "name_for_human": "Kristo Intelligence",
        "name_for_model": "kristo_intelligence",
        "description_for_human": (
            "AI-powered DeFi trading signals and crypto market intelligence on "
            "Base. Pay per request with USDC via the x402 protocol — no API keys."
        ),
        # This string used to end with "One free call per client." Production
        # runs with FREE_TIER_LIMIT=0, so that was a promise the paywall could
        # not keep, and it named only the X-Payment-Proof rail. Both are
        # derived/generated now: the count comes from the live limit and the
        # price range from the vitrine.
        "description_for_model": (
            "Fetch DeFi market stats, real on-chain USDC sales history, whale "
            "flow, arbitrage spreads, trading signals and bot integration "
            "status. Every paid route costs between "
            f"{_floor} and {_ceiling} USDC per call via x402 (HTTP 402); the "
            "exact amount is always stated in the 402 response. Pay with the "
            "standard x402 header PAYMENT-SIGNATURE (EIP-3009, settled through "
            "the facilitator); clients on x402 v1 may send X-PAYMENT instead, "
            "and a manual on-chain transfer is also accepted via the "
            "X-Payment-Proof header after 3 confirmations. This deployment "
            f"grants {FREE_TIER_LIMIT} free calls per client, so treat every "
            "call as paid. A free sample of every paid route is served at "
            "<endpoint>/sample and needs no payment."
        ),
        "auth": {"type": "none"},
        "api": {
            "type": "openapi",
            "url": f"{base_url}/openapi.json",
            "has_user_authentication": False,
        },
        "logo_url": f"{base_url}/favicon.ico",
        "contact_email": "hristovdimitri2@gmail.com",
        "legal_info_url": f"{base_url}/llms.txt",
        "x402_payment": {
            "protocol": "x402",
            "network": "base",
            "chain_id": X402_CHAIN_ID,
            "token_contract": X402_USDC_CONTRACT,
            "receiver_address": X402_RECEIVER_ADDRESS,
            # Not one flat fee — the routes differ. The 402 always states the
            # exact amount; these two bound it.
            "price_min_usdc": _floor,
            "price_max_usdc": _ceiling,
            # This one contradicted the two fields directly above it: the prose
            # in this same response says "between _floor and _ceiling", while
            # this field still quoted the flat X402_FEE_USDC — the dearest route.
            # An agent reading the machine field overpaid for four of six routes.
            "price_per_call_usdc": _floor,
            "free_tier_limit": FREE_TIER_LIMIT,
            # Standard rail first. This block used to advertise only the
            # proof header, so a spec client reading it was pointed at the
            # slower path. The proof header is still named — it is the only
            # path for smart wallets and exchange withdrawals — but the
            # standard rail stays first.
            "challenge_header": "PAYMENT-REQUIRED",
            "preferred_header": "PAYMENT-SIGNATURE",
            "alternative_headers": ["X-PAYMENT", "X-Payment-Proof"],
            "proof_header": "X-Payment-Proof",
            # Published on npm, so the field names the package and stops there.
            # It used to pin "@1.1.0 (from the repository; the npm release is still
            # 1.0.0, proof rail only, ~24s per call)" - true while the registry
            # served 1.0.0, and a lie the moment 1.1.0 was published, which it now
            # is. A version string in a manifest is a claim with an expiry date. The
            # machines that read this field install whatever `latest` is, and that
            # is now the release we want them to have.
            "client_package": "kristo-x402-client",
        },
        # What an agent scanner reading this file can actually buy. It used to
        # name no route at all.
        "x402_endpoints": [
            {
                "path": route["endpoint"],
                "method": "GET",
                "name": route.get("name", ""),
                "cost_usdc": float(route["price_usdc"]),
                "free_sample": "%s/sample" % route["endpoint"],
            }
            for route in REAL_X402_ROUTES
        ],
    })


@discovery_bp.route("/llms.txt")
def llms_txt():
    """LLM-friendly plain-text description of the API for AI agent discovery.

    PRICES ARE GENERATED, NEVER TYPED. This document used to carry a single flat
    "$0.005 per API call" (wrong for /api/v1/signal and /api/v1/whaleflow) and a
    "Monthly VIP $29 USDC" line (a HUMAN product sold through Stripe — it has no
    place in a machine-paid API description). It also listed only 3 of the 6 paid
    routes. Everything below is read from the single price source and from
    REAL_X402_ROUTES, so it cannot drift again.
    """
    from main import (
        X402_CHAIN_ID,
        X402_RECEIVER_ADDRESS,
        X402_USDC_CONTRACT,
        FREE_TIER_LIMIT,
        REAL_X402_ROUTES,
    )

    base_url = request.host_url.rstrip("/")
    paid = [(r["endpoint"], r["name"], float(r["price_usdc"]),
             (r.get("description") or "").strip())
            for r in REAL_X402_ROUTES]
    cheapest = min(price for _e, _n, price, _d in paid)
    free_tier_line = (
        f"- Free tier: {FREE_TIER_LIMIT} free call(s) per client, then payment "
        f"required"
        if FREE_TIER_LIMIT
        else "- Free tier: none — every unpaid call returns HTTP 402 (no free "
             "calls, no signup)"
    )
    paid_lines = "\n".join(
        "- GET %s — %s ($%.3f USDC per call)%s"
        % (endpoint, name, price, ("\n  " + description) if description else "")
        for endpoint, name, price, description in paid
    )
    # Every paid route has a free /sample twin (all six are in
    # X402_FREE_ENDPOINTS), so this list is DERIVED from REAL_X402_ROUTES and can
    # never drift out of sync with the paid list above it. They were previously
    # advertised nowhere at all: an agent had no way to see our response shape
    # without paying first, which is the hardest possible way to be discovered.
    sample_lines = "\n".join(
        "- GET %s/sample — free sample response for %s (no payment, no signup)"
        % (endpoint, name)
        for endpoint, name, _price, _description in paid
    )

    content = f"""# Kristo Intelligence API

> AI-powered DeFi trading signals and crypto market intelligence.
> Uses the x402 payment protocol — pay with USDC on Base.

## Payment (x402 Protocol)

- Chain: Base (chain_id: {X402_CHAIN_ID})
- Currency: USDC
- Token contract: {X402_USDC_CONTRACT}
- Receiver address: {X402_RECEIVER_ADDRESS}
- Price per API call: from ${cheapest:.3f} USDC — see the per-route list below
  (the HTTP 402 challenge of each route always states the exact amount)
{free_tier_line}

## How to Pay

Two rails are accepted. Rail 1 is the standard x402 flow — prefer it, because
it is what the x402 ecosystem (x402-fetch, x402scan, facilitators) speaks.
Rail 2 is for smart wallets and exchange withdrawals: Coinbase Smart Wallet,
Binance Web3, passkey signers, and payouts that arrive as a plain USDC
transfer. Those cannot sign EIP-3009, so they pay with a plain transfer and
prove it with a header. That is the normal path for such a wallet, not a
last resort.

### Units — get this right before you move money

The protocol fields are in **atomic units** (USDC has 6 decimals), the way an
ERC-20 contract wants them:

| Field | Example | Unit |
|---|---|---|
| `accepts[0].amount` | `"5000"` | **atomic** — pass `5000` straight to `transfer()` |
| `x402_amount` | `"5000"` | **atomic** |
| `payment.amount_usdc` | `5000` | **atomic**, despite the name |
| `X-Payment-Amount-USDC` header | `0.005` | **decimal USDC** |

So `5000` means **0.005 USDC**, not 5000 USDC. If your wallet API takes a
decimal amount, divide by `1e6`; if it takes the raw ERC-20 value, use the
number as-is. Paying 5000 USDC for a 0.005 USDC call is accepted by our
on-chain check (`amount >= price`) and the excess is NOT refunded.

### Rail 1 — standard x402 (preferred)

1. Call the endpoint you want. It answers HTTP 402 with the canonical
   `PAYMENT-REQUIRED` response header (base64 of the PaymentRequired JSON) and a
   JSON body whose `accepts[0]` states the exact `amount` (atomic USDC units),
   `payTo`, `asset` and `network` for THAT route — the amount differs per route.
2. Sign an EIP-3009 `transferWithAuthorization` for exactly that amount (scheme
   "exact") and repeat the SAME request with the signed payload in the
   `PAYMENT-SIGNATURE` header. Clients still on x402 v1 send the same payload in
   `X-PAYMENT`; both are accepted and `PAYMENT-SIGNATURE` wins if both are sent.
3. Settlement runs through the x402 facilitator automatically. A signed payload
   is single-use — replaying it is rejected.
4. If the call answers HTTP 425 (`settlement_in_flight`), your payment DID settle
   on-chain but our node has not reached the confirming block yet. Wait a few
   seconds and retry the exact same request. Do NOT pay again.

### Rail 2 — smart wallets and exchange withdrawals

**Who this is for:** Coinbase Smart Wallet, Binance Web3, passkey signers, and
payouts that arrive as a plain USDC transfer. These cannot sign an EIP-3009
authorization, so Rail 1 is closed to them. This is their normal path, not a
last resort.

1. Send `accepts[0].amount` — remembering it is in ATOMIC units, so `"5000"` is
   0.005 USDC — on Base to `accepts[0].payTo`.
2. Wait for 3 confirmations (~6 seconds on Base) — this rail requires them.
3. Repeat the request with the `X-Payment-Proof` header:
   `base64url(JSON({{"payer": "<your wallet>", "transaction_hash": "<tx hash>", "amount_usdc": <the ATOMIC amount you sent, e.g. 5000>}}))`.
   ATOMIC, exactly like `accepts[0].amount` — and it is the same field the 402
   body already fills in for you (`"amount_usdc": 5000` for a $0.005 call), so
   use that value verbatim rather than the decimal price.
   We do not read this field when verifying: the real amount is decoded from the
   transaction's Transfer event, so it cannot be used to underpay. The wrong unit
   therefore costs you nothing on-chain — it just makes your own logs claim you
   paid a 5000th of what you did.
4. The server verifies the transfer on-chain and grants access. Each proof is
   single-use.

## Endpoints

### Paid (x402 — one payment unlocks one call)

{paid_lines}

### Free (always accessible)

- GET /.well-known/x402.json — x402 payment discovery metadata
- GET /openapi.json — OpenAPI 3.0 specification
- GET /llms.txt — This file (LLM-friendly API description)
- GET /api/mcp/manifest — MCP/x402 machine-readable manifest
- GET /agents.json — agent and service discovery manifest
- GET /.well-known/agent-card.json — A2A Agent Card (protocol 0.3.0)
- POST /a2a — A2A JSON-RPC (message/send, tasks/get): name a product and it
  answers with that product's free sample and its exact terms. Free.
- GET /api/v1/agents — the same six paid routes as a compact, PRICED catalogue
  (id, category, endpoint, price, description) — the fastest way for an agent to
  decide which route to buy. Free, no payment, no key.
- GET /api/v1/quickstart — step-by-step first-call walkthrough
- GET /validation — checkable facts: status, uptime, on-chain payment history
- GET /api/v1/settlement-classes — every USDC settlement into our receiver,
  split by what the payer actually IS: us, crawl infrastructure, a verifier, or
  a customer. Includes the method and the unflattering half — most of our
  settled volume is our own money, and the number says so. The classifier reads
  on-chain behaviour, not a self-report, so a payer cannot relabel itself by
  changing its User-Agent. Free.
- GET /.well-known/paycheck.json — the payout wallet, declared as
  {{"payTo": ["0x…"]}}, so a deliberate rotation is recognised by monitors that
  watch it instead of reading as a hijack. Free.
- GET /pricing — every paid route and its exact price, and both payment rails
- GET /terms — licence, what the data is not, how paying works
- GET /health — Service health check
- GET /dashboard — HTML dashboard

#### Free samples of every paid route

Each one returns the real response shape with example data, and costs nothing.
Use them to build and test a client before spending anything.

{sample_lines}

#### Free: an honest on-chain audit of our own receiver

- GET /api/v1/seller-audit — free, no payment, no signup

Incoming USDC transfers on Base to our receiver address, with a payer analysis
built for the question an agent asks before it pays a seller:

- distinct paying addresses, and which of them paid more than once
- treasury-sized flows separated out, because they are not per-call payments
- known reviewer and verification addresses counted separately, so they can never
  inflate the customer count
- repeat-payer concentration, so one operator paying from several wallets is
  visible rather than averaged away
- the read's own coverage: a window that was not read end to end is published as
  `partial`, with its verdict saying the figures are a floor — never as a zero

We publish this about ourselves, in the shape any seller would receive, because
the alternative is asking to be trusted. It is fixed to our own receiver on
purpose: the same engine reads any receiver on request, and that broader form is
a paid product rather than something one caller can aim at a thousand addresses.

## Agent-to-Agent (A2A)

We speak A2A, protocol 0.3.0. The card is at
{base_url}/.well-known/agent-card.json and the endpoint is {base_url}/a2a.

- `message/send` — name a product in plain text; it answers with that product's
  free sample and its exact paid terms.
- `tasks/get` — fetch a task you sent earlier and we are still holding.

Be clear about what this buys you: the A2A surface returns the SAMPLE and the
TERMS. It does not return the live payload. That is what the HTTP route's
paywall sells, and asking here differently will not change it — this is a
discovery and negotiation surface, not a way round the 402. We set it up that
way on purpose: an A2A endpoint that handed out the paid data would be selling
the same product twice at two prices.

The card advertises no capability we do not have: no streaming, no push
notifications, no state-transition history.

## Base URL

{base_url}

## HTTP 402 Response

When payment is required, the API returns HTTP 402 with:
- the `PAYMENT-REQUIRED` response header — canonical standard base64 (not
  base64url) of `{{x402Version, error, accepts, resource, extensions}}`
- a JSON body mirroring those same fields, plus self-contained `x402_*` mirrors
  so a model holding ONLY this JSON can still pay: `x402_network` (CAIP-2),
  `x402_amount` (atomic units), `x402_recipient`, `x402_token_contract`
- legacy convenience headers: `X-Payment-Required`, `X-Payment-Address`,
  `X-Payment-Amount-USDC`, `X-Payment-Chain`, `X-Payment-Token-Contract` and
  `WWW-Authenticate`

## Status Codes

- 200 — paid call delivered
- 402 — payment required (no credential was presented at all)
- 401 — a credential WAS presented but is unusable: bad signature, wrong amount
  or receiver, expired authorization window, or an unknown / already-used
  transaction
- 425 — the payment already settled on-chain but our node has not caught up yet;
  retry the same request shortly, and do not pay again

## Discovery Files

- x402: {base_url}/.well-known/x402.json
- OpenAPI: {base_url}/openapi.json
- LLMs: {base_url}/llms.txt
- MCP Manifest: {base_url}/api/mcp/manifest
- A2A Agent Card: {base_url}/.well-known/agent-card.json
- A2A endpoint: {base_url}/a2a
"""
    return Response(content, mimetype="text/plain")
