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
import os
import queue
import secrets
import threading
import time
from datetime import datetime, timezone

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
SUITE_TESTS_PASSED = 727
SUITE_LAST_RUN = "2026-11-05"

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


def _dependency_state():
    """Read the two dependencies of this service, and say how they are.

    Returns (crm_ready, blockchain_ready, wallet, backend). The `__main__` dance is
    here so /health and /ready cannot drift apart in how they find the live state —
    the lazy `import main` copy keeps its defaults because the env guard skips its
    threads, and reading it reports a false "degraded".

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
    else:
        from main import _lock, _wallet_state, crm_store
    from config import BASE_CHAIN_ID

    try:
        crm_ready = bool(crm_store.is_healthy())
    except Exception:
        # An unreachable store answers "not ready", it does not take /health down.
        crm_ready = False
    with _lock:
        wallet = dict(_wallet_state)
    blockchain_ready = bool(
        wallet.get("rpc_connected")
        and wallet.get("chain_id") == BASE_CHAIN_ID
        and wallet.get("receiver_valid")
    )
    return crm_ready, blockchain_ready, wallet, getattr(crm_store, "backend", "unknown")


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
    crm_ready, blockchain_ready, wallet, backend = _dependency_state()
    return jsonify(
        status="ok" if crm_ready and blockchain_ready else "degraded",
        service="up",
        database={"backend": backend, "ready": crm_ready},
        blockchain={
            "ready": blockchain_ready,
            "network": wallet.get("network", "Base Mainnet"),
            "chain_id": wallet.get("chain_id"),
            "fee_receiver": wallet.get("fee_receiver"),
            # Where the payment monitor has scanned up to, and when it last
            # looked. Added because there was no way to see this from outside at
            # all: the figure lives in the paid /api/stats wallet block, so nobody
            # - including us - could tell whether the thing that detects incoming
            # payments was keeping up or had silently stopped.
            #
            # This is read from memory, deliberately: /health is what the platform
            # restarts us on, so it must not gain an RPC call. last_check_time is
            # what makes the block number interpretable without one.
            "monitor": {
                "last_block_checked": wallet.get("last_block_checked") or 0,
                "last_check_time": wallet.get("last_check_time"),
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
    crm_ready, blockchain_ready, wallet, backend = _dependency_state()
    ready_now = bool(crm_ready and blockchain_ready)
    return jsonify(
        ready=ready_now,
        status="ready" if ready_now else "not_ready",
        service="up",
        database={"backend": backend, "ready": crm_ready},
        blockchain={"ready": blockchain_ready, "chain_id": wallet.get("chain_id")},
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
            <li><code>/api/v1/signal</code> — grade A (81.2) ·
              <a href="https://x402-trust.com/endpoint/122932">page</a></li>
            <li><code>/api/v1/whaleflow</code> — grade B (79.9) ·
              <a href="https://x402-trust.com/endpoint/139367">page</a></li>
            <li><code>/api/stats</code> — grade B (79.9) ·
              <a href="https://x402-trust.com/endpoint/139372">page</a></li>
            <li><code>/api/arb/opportunities</code> — grade B (79.9) ·
              <a href="https://x402-trust.com/endpoint/139339">page</a></li>
            <li><code>/api/sales</code> — grade B (79.9) ·
              <a href="https://x402-trust.com/endpoint/139342">page</a></li>
            <li><code>/api/bot-status</code> — grade B (79.9) ·
              <a href="https://x402-trust.com/endpoint/139366">page</a></li>
          </ul></dd>
      <dt>Last checked</dt>
      <dd>2026-10-19 (grades/scores read live from x402 Trust that day)</dd>
    </dl>
  </div>
  <div class="panel">
    <dl>
      <dt>Paid endpoints &amp; prices — 6 live x402 routes</dt>
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
        supply the proof. Self-describing, but it waits <b>12 confirmations,
        about 24 seconds</b> before the data is released.</li>
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

    def _tool(name, route, description):
        return {
            "name": name,
            "description": description,
            "inputSchema": {"type": "object", "properties": {},
                            "additionalProperties": False},
            "x402": {"price_usdc": _price(route), "chain_id": X402_CHAIN_ID,
                     "receiver": X402_RECEIVER_ADDRESS,
                     "token_contract": X402_USDC_CONTRACT,
                     "endpoint": f"{base_url}{route}"},
        }

    _paid = ("Paid via x402 (HTTP 402 challenge with the exact USDC amount and "
             "receiver on Base).")
    return [
        _tool(
            "get_market_stats", "/api/stats",
            "Read-only operation — no side effects, no parameters. Returns "
            "the live Base market snapshot: aggregated activity, daily "
            "request/sales counters, the official agent catalog, and "
            "real-time market data (CoinGecko, DEXScreener, Fear & Greed). "
            "Use it for market context and price/indicator lookups; use "
            "get_onchain_sales for paid-call revenue and get_bot_status for "
            "integration health. " + _paid,
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
            "get_bot_status for integration health. " + _paid,
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
            "provable revenue. " + _paid,
        ),
        _tool(
            "get_trading_signal", "/api/v1/signal",
            "Read-only operation — no side effects, no parameters. Returns "
            "this service's flagship trading-agent signals for ETH, ONDO, "
            "KAITO and DEGEN: action, confidence, price_usd and the model's "
            "reasoning. Use it when you need a directional call rather than "
            "raw market data; use get_whale_flow for large-transfer flow and "
            "get_arbitrage_opportunities for cross-DEX spreads. " + _paid,
        ),
        _tool(
            "get_whale_flow", "/api/v1/whaleflow",
            "Read-only operation — no side effects, no parameters. Returns "
            "network-wide USDC whale flow on Base: transfers of $5M or more, "
            "refreshed every 60 seconds, with labelled counterparties. Use it "
            "to see where size is moving; use get_trading_signal for "
            "directional calls or get_market_stats for broad context. " + _paid,
        ),
        _tool(
            "get_arbitrage_opportunities", "/api/arb/opportunities",
            "Read-only operation — no side effects, no parameters. Returns "
            "live cross-DEX arbitrage spreads on Base, refreshed every 60 "
            "seconds. Use it for executable price gaps between venues; use "
            "get_market_stats for aggregate prices or get_trading_signal for "
            "directional calls. " + _paid,
        ),
    ]


_MCP_FALLBACK_PROTOCOL = "2025-11-25"


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
            "instructions": (
                "Kristo Intelligence — paid DeFi signals on Base. Tools "
                "advertise their x402 price; pay the exact USDC amount to "
                "the listed receiver and retry the target endpoint with "
                "the payment header."
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
        result = {
            "content": [{
                "type": "text",
                "text": (
                    f"Tool '{name}' is pay-per-call via x402: send "
                    f"{x.get('price_usdc')} USDC on {x.get('chain_id')} "
                    f"to {x.get('receiver')}, then call "
                    f"{x.get('endpoint')} with the payment header. "
                    "The 402 challenge at that endpoint is self-describing."
                ),
            }],
            "structuredContent": {"x402": x},
        }
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
                 "description": "Trading-agent signals (action, confidence, price_usd, reasoning) for ETH/ONDO/KAITO/DEGEN"},
                {"path": "/api/v1/whaleflow", "method": "GET",
                 "cost_usdc": _route_price("/api/v1/whaleflow"),
                 "description": "Network-wide whale flow: USDC transfers >= $5M on Base with labeled counterparties (60s refresh)"},
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
            # (main.py:884, `amount_usd >= VIP_THRESHOLD_USDC`), and no API route
            # costs anywhere near $0.1 — the dearest is $0.005 — so as worded the
            # promise could not be reached by any ordinary customer. Same family
            # as the volume discount that could never trigger.
            "vip_threshold": (
                f"A single payment of at least ${VIP_THRESHOLD_USDC} USDC "
                "generates a Telegram VIP invite code. This is for large one-off "
                "transfers, not accumulated API calls: the dearest route costs "
                f"${_dearest_route_price():.3f}, so ordinary per-call usage will "
                "not reach it."),
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
                                "ETH/ONDO/KAITO/DEGEN."),
            },
            {
                "url": f"{base_url}/api/v1/whaleflow",
                "name": "Kristo — Whale Flow",
                "description": ("USDC whale transfers >= $5M on Base with "
                                "labeled counterparties."),
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
                "description": "Trading-agent signals (action, confidence, price_usd, reasoning) for ETH/ONDO/KAITO/DEGEN",
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
            "amount": str(_cheapest),
            "amount_max": str(_dearest),
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

    def _paid_op(summary, description, cost_usdc=None):
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
                "amount": str(cost),
            }
        # x402 Doctor "openapi-input-schema" (21.10): x402scan does not
        # register a paid operation without an input declaration. All six
        # routes are plain GET handlers with NO query parameters (no
        # request.args in any of them), so the honest declaration is an
        # explicit empty parameters list plus a "no parameters" note in the
        # description — a paid operation that stays silent about its input
        # reads as "may need input we can't see".
        return {
            "summary": summary,
            "description": (description
                            + " Takes no parameters (plain GET, no query "
                            "string)."),
            "parameters": [],
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
                "Live DeFi trading signal: action, confidence and one-line reasoning for ETH/ONDO/KAITO/DEGEN — refreshed under 5 minutes from live market data.",
                _route_price("/api/v1/signal"),
            )},
            "/api/v1/whaleflow": {"get": _paid_op(
                "Live whale flow",
                "Live whale flow: USDC transfers >= $5M on Base with labeled counterparties — scanned continuously (freshness follows the RPC provider's limits; the response always states the block scanned to).",
                _route_price("/api/v1/whaleflow"),
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
        # not keep, and it named only the legacy X-Payment-Proof rail. Both are
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
            "X-Payment-Proof header after 12 confirmations. This deployment "
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
            # Standard rail first. This block advertised only the legacy proof
            # header, so a spec client reading it was pointed at the slow path.
            "challenge_header": "PAYMENT-REQUIRED",
            "preferred_header": "PAYMENT-SIGNATURE",
            "legacy_headers": ["X-PAYMENT", "X-Payment-Proof"],
            "proof_header": "X-Payment-Proof",
            # Published on npm, so the field names the package and stops there.
            # It used to pin "@1.1.0 (from the repository; the npm release is still
            # 1.0.0, legacy rail only, ~24s per call)" - true while the registry
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
Rail 2 is a legacy self-describing proof that we still honour.

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

### Rail 2 — legacy self-describing proof (fallback)

1. Send `accepts[0].amount` — remembering it is in ATOMIC units, so `"5000"` is
   0.005 USDC — on Base to `accepts[0].payTo`.
2. Wait for 12 confirmations (~24 seconds on Base) — this rail requires them.
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
- GET /api/v1/agents — the same six paid routes as a compact, PRICED catalogue
  (id, category, endpoint, price, description) — the fastest way for an agent to
  decide which route to buy. Free, no payment, no key.
- GET /api/v1/quickstart — step-by-step first-call walkthrough
- GET /validation — checkable facts: status, uptime, on-chain payment history
- GET /pricing — every paid route and its exact price, and both payment rails
- GET /terms — licence, what the data is not, how paying works
- GET /health — Service health check
- GET /dashboard — HTML dashboard

#### Free samples of every paid route

Each one returns the real response shape with example data, and costs nothing.
Use them to build and test a client before spending anything.

{sample_lines}

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
"""
    return Response(content, mimetype="text/plain")
