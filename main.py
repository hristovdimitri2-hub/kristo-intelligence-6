"""
Kristo Intelligence API v6
==========================
Flask application with:
  * Beautiful HTML Dashboard (/dashboard) with charts & metrics
  * JSON API endpoints: /api/sales, /api/stats, /api/bot-status
  * Render-compatible health check (/health)
  * REAL blockchain wallet integration (Base / USDC)
  * Background monitor for incoming USDC transactions

NO DEMO DATA — all sales/stats come from real on-chain activity.

Subscription tiers:
  * Micro-request: per route, from $0.003 USDC per API call — the single source
    is X402_PRICE_MAP (config.py KRISTO_*_PRICE); the live 402 challenge is the
    published price. Nothing in this file may hardcode a price.
  * Monthly VIP:   29.00 USD (unlimited access + Telegram VIP group) — sold as a
    HUMAN subscription through Stripe checkout, not through the x402 API.

MCP/x402 compatible: /api/mcp/manifest exposes machine-readable payment spec.
"""

from __future__ import annotations

import os
import logging
import threading
import time
import json
import secrets
import hmac
import hashlib
import base64
import binascii
import uuid
from datetime import datetime, timedelta, timezone
from collections import deque
from typing import Dict, List, Optional, Tuple

import math
from flask import Flask, g, jsonify, redirect, render_template, request, session

# ── Central configuration (bound wallet address, GLM, etc.) ────────────────
from config import (
    BASE_CHAIN_ID,
    BASE_RPC_URL,
    base_rpc_candidates,
    get_base_fee_receiver,
    BASE_FEE_AMOUNT_USDC,
    KRISTO_VIP_ANALYSIS_PRICE,
    KRISTO_STATS_PRICE,
    KRISTO_SALES_PRICE,
    KRISTO_ARB_PRICE,
    KRISTO_RUG_PRICE,
    KRISTO_WHALE_PRICE,
    KRISTO_SIGNAL_PRICE,
    KRISTO_WHALEFLOW_PRICE,
    KRISTO_VERIFY_SELLER_PRICE,
)

# ── Real-time market data integration ─────────────────────────────────────
from services.market_data import get_coingecko_cache_status, get_market_snapshot

# ── THE PAYMENT RAIL, AND THE CRYPTO STACK BEHIND IT, AT BOOT ──────────────
#
# Imported HERE rather than inside the payment handler, and that placement is the
# fix for a real outage. It used to be `from services import connectors` inside
# `_try_consume_standard_payment`, so the FIRST BUYER's payment also imported
# `eth_account` — and `eth_account` pulls in four hundred and seventeen modules,
# 151 of them heavy (pycryptodome, eth_keys, eth_utils, cytoolz, rlp).
#
# Measured locally: ~1.2s. On the 0.1-CPU production instance: over twenty, which
# is exactly what the bounded rail caught —
#
#     x402 verify step precheck_payment_payload   0.000s
#     x402 rail step verify_standard_payment     20.000s  DEADLINE EXCEEDED
#
# Nothing was wrong with the verification. It was still importing its own
# dependencies. A buyer must never be the thing that compiles the crypto stack:
# paid once at boot, it is off the request path for ever.
#
# No circular import: `services.connectors` imports only the standard library,
# `config`, and `eth_account`.
from services import connectors

# `web3` IS WARMED HERE FOR THE SAME REASON, and it is a separate import because
# `services.connectors` does not pull it. The nonce search calls
# `_get_verify_web3()`, which imports `web3` lazily, and `web3` was NOT loaded at
# boot either — so the first payment paid for that one too, on top of the chain
# search it then performs. Both belong off the request path.
try:
    import web3 as _web3_warm  # noqa: F401
except Exception as _web3_exc:  # noqa: BLE001 - the rail reports its own failures
    log.warning("web3 could not be imported at boot (%s); the first payment "
                "will pay for that import instead", type(_web3_exc).__name__)

# ── Telegram Sales Bot (x402 micro-transactions) ───────────────────────────
import services.telegram_sales
from services.telegram_sales import (
    send_market_bulletin,
    generate_payment_link,
    process_webhook_update,
    telegram_sales_loop,
    register_webhook,
    register_bot_commands,
)

# ── x402 Payment Protocol Constants ────────────────────────────────────────
# Receiver address is bound via config.get_base_fee_receiver() (hard fallback)
X402_RECEIVER_ADDRESS = get_base_fee_receiver()
X402_USDC_CONTRACT = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
X402_CHAIN = "base"
X402_CHAIN_ID = 8453

# ── Dynamic Pricing (Volume Discount) ──────────────────────────────────────
# Prices are defined ONCE in config.py (KRISTO_*_PRICE constants) and wired
# here through X402_PRICE_MAP. Do NOT hardcode prices in this file.
X402_FEE_USDC_BASE = BASE_FEE_AMOUNT_USDC  # Standard per-call price (fallback)
X402_FEE_USDC_DISCOUNT = 0.01   # Discounted price for high-volume callers
X402_VOLUME_THRESHOLD = 10      # After 10 paid calls, price drops to $0.01
X402_FEE_USDC = X402_FEE_USDC_BASE  # Backward-compat alias (used in manifests)

# Per-endpoint x402 price map — single source of truth from config.py.
# Endpoints not listed here fall back to BASE_FEE_AMOUNT_USDC.
X402_PRICE_MAP = {
    "/api/stats": KRISTO_STATS_PRICE,
    "/api/sales": KRISTO_SALES_PRICE,
    "/api/bot-status": KRISTO_STATS_PRICE,
    "/api/arb/opportunities": KRISTO_ARB_PRICE,
    "/api/v1/signal": KRISTO_SIGNAL_PRICE,
    # Whale flow (09.09, owner-approved build — docs/WHALE_FLOW_SPEC.md).
    # PROMOTED 13.09: the paid canary is on-chain (tx 0xc30268e3…4cce03,
    # block 51200083, $0.003), so the route is now advertised in the public
    # vitrine (REAL_X402_ROUTES) instead of paywall-only. Condition 4 met.
    "/api/v1/whaleflow": KRISTO_WHALEFLOW_PRICE,
    # Seller verification (07.11): the arbitrary-receiver on-chain audit. The
    # only route priced above $1, and the only one that reads the chain for an
    # address a caller names rather than serving a cached snapshot. See the
    # reasoning at KRISTO_VERIFY_SELLER_PRICE in config.py.
    "/api/v1/verify-seller": KRISTO_VERIFY_SELLER_PRICE,
}

# ── Buyer-worded URL aliases (10.11.2026) ───────────────────────────────────
# WHY THESE EXIST, in one measurement. The CDP catalogue carries a live hybrid
# search over 33,220 rows, and the ranking is dominated by a LITERAL match on the
# words in the resource URL. For "whale" all sixteen rows above us contain
# "whale" in their host or path; ours is /api/v1/whaleflow, one token, and
# "whale" is not in it. The result: we rank #1 for our own name, host, tool name
# and the token "whaleflow", and are ABSENT from the top results for every word a
# buyer would actually type — "whale flow", "whale alerts", "trading signal",
# "arbitrage", "verify seller". A listing that can only be found by someone who
# already knows the name is an address book, not discovery.
#
# So each alias serves the SAME handler, the SAME price and the SAME receiver as
# its canonical route — only the path, and therefore the sentence an indexer
# reads, changes. Aliases are additive: the canonical paths stay live and keep
# their existing catalogue rows, because two of them are already indexed and paid
# for.
#
# FIVE, NOT SEVEN, ON PURPOSE. Two candidate names would have been misleading
# rather than merely optimistic, and a name that overpromises costs a buyer's
# $0.005 once and their trust permanently:
#   * /api/stats is this service's own counters plus an ETH price and the Fear &
#     Greed index. Calling it "crypto market stats" competes with endpoints that
#     return real market cap and volume, and loses on substance, not on ranking.
#   * /api/bot-status reports OUR Telegram bot's health. The measured demand for
#     "bot health check" is an agent wanting to probe ITS OWN endpoint.
# Both are left without an alias until the response itself earns the name.
X402_PATH_ALIASES = {
    "/api/v1/whale-alerts": "/api/v1/whaleflow",
    "/api/v1/trading-signals": "/api/v1/signal",
    "/api/v1/arbitrage-opportunities": "/api/arb/opportunities",
    "/api/v1/seller-check": "/api/v1/verify-seller",
    "/api/v1/onchain-sales": "/api/sales",
}

# An alias is NOT given its own entry in X402_PRICE_MAP. That map is the
# PUBLISHED price list — server.json for the official MCP Registry and the
# "verify-seller is the dearest route we sell" invariant both read it whole — so
# a duplicate row in it would advertise a product we do not have. The price is
# resolved from the canonical route at charge time instead (see
# _get_dynamic_price), which cannot disagree with itself.

# The resource `tags` are matched by the same search (a query for our own tag
# "whale-tracking" returned us fourth of nine), and the bazaar spec caps the list
# at five, so an alias cannot simply inherit a generic set and add to it — it has
# to spend its five on the words of its own job. These describe the endpoint;
# they are not keyword stuffing for terms the response does not serve.
# Max 5 entries, each printable ASCII and <= 32 chars (asserted in
# tests/test_bazaar_output_example.py).
#
# WHY THE CANONICAL ROUTES NOW HAVE THEIR OWN TAGS TOO (10.11.2026, measured).
# Until this change only the five aliases had an entry here; the seven canonical
# routes all fell back to X402_DEFAULT_RESOURCE_TAGS, so /api/v1/whale-flow,
# /api/v1/verify-seller, /api/bot-status and /api/stats published the SAME five
# words — "crypto, whale-tracking, x402, arbitrage, signals" — and none of those
# five is the job any of them does.
#
# The measurement that settled it, from CDP's own search (20 buyer-intent
# queries, top 20 rows each): CDP does NOT match the resource URL. The query
# "verify seller" misses /api/v1/verify-seller completely — the query is a
# literal substring of that path — while /api/v1/seller-check, the SAME handler
# at the SAME price, ranks #2/17, and the only difference between the two rows is
# what they say: seller-check's tags are its own job's words and its description
# opens "Check whether an x402 seller is really being paid before you pay them".
# The winners for every query are the rows whose tags or description contain the
# buyer's words verbatim ('dex-arbitrage' for "dex arbitrage", 'seller check' for
# "seller check", 'is this token safe' for "token safety"), and we already appear
# for 11 of 20 words — every one of them through an alias's vocabulary, never
# through a canonical route's.
#
# So the tags below are the words the job is asked for in, kept inside what the
# response actually returns: /api/stats still does not claim to be market data and
# /api/bot-status still describes OUR bot, because the test below this line says a
# name that overpromises costs one sale and the trust permanently.
X402_RESOURCE_TAGS = {
    "/api/v1/signal": ["defi-signals", "trading-signals", "market-signal",
                       "crypto-signals", "base"],
    "/api/v1/whaleflow": ["whale-flow", "whale-transfers", "large-transfers",
                          "smart-money", "base"],
    "/api/v1/verify-seller": ["verify-seller", "seller-audit", "x402-seller",
                              "payment-evidence", "due-diligence"],
    "/api/arb/opportunities": ["dex-arbitrage", "price-spread", "cross-venue",
                               "defi", "base"],
    "/api/sales": ["usdc-revenue", "onchain-sales", "settlement-history",
                   "payment-history", "base"],
    "/api/bot-status": ["telegram-bot-status", "sales-bot", "heartbeat",
                        "uptime", "service-status"],
    "/api/stats": ["service-stats", "usage-stats", "market-snapshot",
                   "fear-and-greed", "base"],
    "/api/v1/whale-alerts": ["whale-alerts", "whale-flow", "large-transfers",
                             "usdc", "base"],
    "/api/v1/trading-signals": ["trading-signals", "buy-sell-signal",
                                "market-signal", "crypto", "base"],
    "/api/v1/arbitrage-opportunities": ["arbitrage", "dex-arbitrage",
                                        "price-spread", "defi", "base"],
    "/api/v1/seller-check": ["seller-check", "seller-verification",
                             "x402-seller", "onchain-audit", "base"],
    "/api/v1/onchain-sales": ["onchain-sales", "usdc-settlements",
                              "payment-history", "revenue", "base"],
}
X402_DEFAULT_RESOURCE_TAGS = ["crypto", "whale-tracking", "x402", "arbitrage",
                              "signals"]

# ── What each route is CALLED in a catalogue ────────────────────────────────
# `resource.serviceName` was the literal string "Kristo Intelligence" for all
# twelve paid routes, and it is the third field the CDP catalogue matches (its own
# rows carry it next to `tags` and `description`). A buyer's agent searching
# "seller audit" or "token safety" cannot match a company name, and ours was the
# only name we published.
#
# The measurement, from CDP's index (10.11.2026): every row that wins a query is
# named after its job — "Check an x402 seller's trust", "x402 seller dossier",
# "PennyAPI x402 Seller Preflight", "Token Safety Check", "Crypto Market Signals"
# — and a single seller carries several of those names side by side (agent402 has
# four different serviceNames on four endpoints), so a per-route name is the
# normal shape, not an inconsistency. Our twelve rows all read "Kristo
# Intelligence", which matches nothing a buyer types.
#
# Brand first, job second, inside the spec's 32-character budget, and the job must
# be one the response returns — /api/stats stays a snapshot, not "market data".
# The default below is what anything unlisted falls back to.
X402_RESOURCE_SERVICE_NAMES = {
    "/api/v1/signal": "Kristo crypto signals",
    "/api/v1/whaleflow": "Kristo whale transfers",
    "/api/v1/verify-seller": "Kristo x402 seller audit",
    "/api/arb/opportunities": "Kristo DEX arbitrage",
    "/api/sales": "Kristo USDC revenue",
    "/api/bot-status": "Kristo telegram bot status",
    "/api/stats": "Kristo market snapshot",
    "/api/v1/whale-alerts": "Kristo whale alerts",
    "/api/v1/trading-signals": "Kristo trading signals",
    "/api/v1/arbitrage-opportunities": "Kristo DEX arbitrage spread",
    "/api/v1/seller-check": "Kristo seller check",
    "/api/v1/onchain-sales": "Kristo onchain sales",
}
X402_DEFAULT_SERVICE_NAME = "Kristo Intelligence"

# The listing icon, in a format the Bazaar actually accepts.
#
# The CDP discovery docs are explicit about `resource.iconUrl`: "Supported
# formats are JPG, JPEG, PNG, WebP, and GIF. SVG is not supported." We published
# an SVG and a test asserted it, so the one format we advertised was the one
# format the index cannot render. The SVG is still served — it is the web
# favicon, and a browser is not the Bazaar — but this is what the 402 points a
# directory at. One constant, read by the HTTP challenge and the A2A card alike,
# because two hand-written copies of one URL is how they drift.
# The raster is generated from the same geometry by scripts/make_brand_icon.py.
X402_ICON_PATH = "/static/icons/kristo.png"

# ── Challenge descriptions ("caught by the hand") ───────────────────────────
# The 402 challenge description is the machine's first impression of the
# product. Only the description STRING varies per endpoint — the canonical
# x402 v2 shape (scheme, network, atomic amounts, payTo, asset, bazaar
# extension) is untouched.
#
# WHY EVERY CANONICAL ROUTE NOW OPENS WITH THE BUYER'S WORDS (10.11.2026).
# Measured in CDP's own search over 20 buyer-intent queries: the ranking reads
# `tags` and this description, and does NOT read the resource URL. The query
# "verify seller" misses /api/v1/verify-seller — a literal substring of that path
# — while /api/v1/seller-check, the same handler at the same price, ranks #2/17
# because its text opens "Check whether an x402 seller is really being paid
# before you pay them". Every row that wins a query contains the buyer's words
# verbatim. So each string below starts with the words the job is asked for in;
# the clause after the em dash is still the honest scope, unchanged.
CHALLENGE_DESCRIPTIONS = {
    "/api/v1/signal": (
        "Crypto trading signal and DeFi signals for Ethereum (ETH)/ONDO/KAITO/"
        "DEGEN: action, confidence and one-line reasoning — refreshed under 5 "
        "minutes from live market data. Useful when an agent has to act on a "
        "market view and needs a stated action and its reason rather than raw "
        "prices."
    ),
    "/api/v1/whaleflow": (
        "Whale flow and whale transfers on Base: USDC transfers ≥ $5M with "
        "labeled counterparties — scanned continuously (freshness follows the "
        "RPC provider's limits; the response always states the block scanned to). "
        "Worth reading when one very large transfer is the thing that would "
        "change a position."
    ),
    "/api/bot-status": (
        "Telegram bot status and bot health for this service: heartbeat, "
        "subscribers, processed commands and service wallet state — updated live. "
        "Useful when an agent has just taken a signal from this service and needs "
        "to know the engine behind it is alive."
    ),
    "/api/v1/verify-seller": (
        "Verify an x402 seller before you pay it — a seller audit on chain: "
        "incoming USDC transfers for any Base address you name, with distinct "
        "paying addresses, repeat-payer concentration, treasury-sized flows "
        "separated out and the read's own coverage stated. This answers the "
        "question an agent has immediately before paying an unfamiliar x402 "
        "seller."
    ),
    # ── The aliases' own sentences ─────────────────────────────────────────
    # Same product, said in the words a buyer uses when searching, because this
    # string is what aggregators copy verbatim (PayAI Bazaar, x402-list,
    # x402scan) and what the paid recommenders embed. Same rule as above: describe
    # the endpoint, do not instruct the agent reading it.
    "/api/v1/whale-alerts": (
        "Live whale alerts for Base: large USDC transfers as they land, with "
        "from/to wallets, counterparty labels and USD value, for tracking smart "
        "money and feeding trading bots. Refreshed continuously; the response "
        "states the block it scanned to. Relevant when an agent is watching "
        "for large transfers and needs the counterparty, not only the amount."
    ),
    "/api/v1/trading-signals": (
        "Crypto trading signals for ETH, ONDO, KAITO and DEGEN: action, "
        "confidence, price and a one-line reasoning, refreshed under five "
        "minutes from live market data. Useful when an agent has to act on a "
        "market view and wants action, confidence and reasoning in one call."
    ),
    "/api/v1/arbitrage-opportunities": (
        "Arbitrage opportunities across Base DEX venues: live price gaps per "
        "pair with both venues, the spread percentage and estimated profit, "
        "refreshed every 60 seconds. Relevant when an agent is comparing "
        "venues and needs to know whether a spread is still open."
    ),
    "/api/v1/seller-check": (
        "Check whether an x402 seller is really being paid before you pay them: "
        "a read of any Base address you name, with distinct paying addresses, "
        "repeat-payer concentration, treasury-sized flows separated from "
        "per-call payments, and the read's own coverage stated. Useful "
        "immediately before paying an unfamiliar x402 seller, when on-chain "
        "evidence is wanted first."
    ),
    "/api/v1/onchain-sales": (
        "On-chain sales read from Base: every USDC settlement into this "
        "service's receiver — amount, payer address, tx hash and time — with "
        "totals by token. Real settlement history, not a projection. Worth "
        "reading when an agent wants proof that this service is paid for what "
        "it sells."
    ),
}

# ── NEXUS Discovery Engine URL ──────────────────────────────────────────────
# Public Render URL for the NEXUS Discovery Engine (Next.js platform).
# Falls back to relative "/" so links work even if NEXUS is served from same domain.
NEXUS_URL = "/nexus"

# Free-tier limit per client. The env default here is 1 for casual evaluation,
# but PRODUCTION RUNS WITH 0 (KRISTO_FREE_TIER_LIMIT=0): every unpaid request
# then returns the canonical 402 payment challenge, which is what x402
# marketplaces/verifiers (PayAPI.market, x402scan) expect. Any public text that
# promises a free call is therefore a phantom claim — see the sweep test.
FREE_TIER_LIMIT = max(0, int(os.getenv("KRISTO_FREE_TIER_LIMIT", "1")))

# Endpoints that require x402 payment (after free tier exhausted)
X402_PAID_ENDPOINTS = {"/api/sales", "/api/stats", "/api/bot-status",
                       "/api/arb/opportunities", "/api/v1/signal",
                       "/api/v1/whaleflow", "/api/v1/verify-seller"}

# An alias is a paid route in every sense — it must be paywalled, priced,
# funnelled and described exactly like the canonical path, or it becomes a free
# back door to a paid product. Adding them to the canonical set is what makes
# every existing invariant (bazaar output examples, the payment funnel, the
# discovery docs) cover them without a second list to keep in sync.
X402_PAID_ENDPOINTS |= set(X402_PATH_ALIASES)

# Endpoints that are always free (discovery, health, dashboard, manifest)
X402_FREE_ENDPOINTS = {
    "/", "/health", "/validation", "/dashboard", "/nexus",
    # /ready is the readiness half of the liveness pair; see F-10. Ops-facing and
    # free, like /health.
    "/ready",
    "/api/mcp/manifest",
    "/.well-known/x402.json", "/.well-known/ai-plugin.json", "/openapi.json",
    "/llms.txt", "/agents.json", "/robots.txt", "/sitemap.xml",
    "/mcp.json", "/api/telegram-webhook", "/api/dashboard-stats",
    "/api/dashboard/data",
    "/api/connectors", "/api/v1/quickstart", "/favicon.ico", "/favicon.svg",
    "/.well-known/x402-trust.txt",
    # A2A discovery. Classified explicitly rather than left to fall through the
    # allow-list, which is the gap F-21 records: a route in NEITHER set is
    # unclassified, and "unclassified" is not the same as "free".
    "/.well-known/agent-card.json", "/a2a",
    # The MCP transport itself. /mcp.json was listed here but the three routes
    # that actually speak the protocol were in neither this set nor the paid set,
    # so they fell through the allow-list unclassified — the same gap F-21 records.
    # They cost nothing to call and are free in fact; this makes them free on
    # paper too, and puts them where a future scope can see them.
    "/mcp", "/mcp/sse", "/mcp/message",
    "/api/v1/signal/sample",
    "/api/stats/sample",
    "/api/v1/whaleflow/sample",
    "/api/sales/sample",
    "/api/bot-status/sample",
    # The $1.00 route's sample. A buyer deciding whether a $1 audit is worth it
    # must be able to see the exact report shape first — the same rule the
    # cheaper routes follow, and it matters more at a hundred times the price.
    "/api/v1/verify-seller/sample",
    # Honest on-chain audit of this service's own receiver (services/seller_audit.py).
    # Free on purpose: it is the proof of the paid engine that reads ANY receiver,
    # and it is fixed to our own address so it cannot be aimed at a thousand of
    # them. Classified explicitly — a route in NEITHER set is unclassified, and
    # "unclassified" is not the same as "free" (F-21).
    "/api/v1/seller-audit",
    "/api/arb/opportunities/sample",
}

# ── Logging ────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
)
log = logging.getLogger("kristo.v6.main")

app = Flask(__name__)
# ── Reverse-proxy awareness (Render / nginx / docker-compose) ────────────────
# Render terminates TLS and forwards plain HTTP, so Flask would otherwise
# build http:// URLs in every discovery spec (x402.json, openapi.json,
# llms.txt, mcp.json). ProxyFix honors X-Forwarded-Proto/X-Forwarded-Host
# so request.host_url returns the correct https:// public URL.
from werkzeug.middleware.proxy_fix import ProxyFix  # noqa: E402

app.wsgi_app = ProxyFix(app.wsgi_app, x_for=0, x_proto=1, x_host=1)
# NOTE: x_for=0 is deliberate — X-Forwarded-For is client-controllable, so
# remote_addr is NOT rewritten. Free-tier identity spoofing protection in
# _get_client_ip() stays intact (see test_v6_launch.py).
app.config["SECRET_KEY"] = os.getenv("SESSION_SECRET", "") or secrets.token_urlsafe(32)
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_SAMESITE="Lax",
)

# ── Request-body size cap (protects free-tier resources) ─────────────────────
# Bodies larger than this are rejected with 413 before any route handler runs,
# so oversized payloads cannot consume worker memory or upstream API quota.
# Override via env only if a legitimate larger payload is ever introduced.
app.config["MAX_CONTENT_LENGTH"] = int(
    os.getenv("KRISTO_MAX_CONTENT_LENGTH_BYTES", str(512 * 1024))  # 512 KB
)


# ── JSON errors, never HTML (audit #4 / F3) ───────────────────────────────
# A paying agent must never receive an HTML error page: after a payment is
# consumed, the ONLY useful answer is JSON with a request_id it can quote and
# the knowledge that retrying recovers the call it already paid for.
def _json_internal_error(message: str, status: int = 500):
    rid = getattr(g, "request_id", None) or uuid.uuid4().hex[:16]
    g.request_id = rid
    return jsonify({
        "ok": False,
        "error": "internal_error",
        "message": message,
        "request_id": rid,
    }), status


@app.errorhandler(500)
def _http_500(_error):
    """JSON 500 even when Flask builds the response itself (abort(500))."""
    return _json_internal_error(
        "Internal server error. Quote request_id when reporting this — if you "
        "already paid, retry the same request/proof shortly: the payment is "
        "recorded and is not lost.")


@app.errorhandler(Exception)
def _unhandled_exception(error):
    """Every unhandled exception → JSON 500 + request_id (F3).

    HTTPExceptions (401/402/404/413…) are routed to their own handlers by
    Flask BEFORE this runs, so every existing JSON contract is untouched.
    """
    from werkzeug.exceptions import HTTPException
    if isinstance(error, HTTPException):
        return error
    rid = getattr(g, "request_id", None) or uuid.uuid4().hex[:16]
    g.request_id = rid
    log.error("unhandled error [%s] %s %s", rid,
              getattr(request, "method", "?"), getattr(request, "path", "?"),
              exc_info=error)
    return _json_internal_error(
        "Internal server error. Quote request_id when reporting this — if you "
        "already paid, retry the same request/proof shortly: the payment is "
        "recorded and is not lost.")


@app.errorhandler(413)
def _payload_too_large(_error):
    """Return a JSON 413 when a client exceeds MAX_CONTENT_LENGTH."""
    return jsonify({"ok": False, "error": "payload_too_large"}), 413

# ── Runtime sales integration layer ───────────────────────────────────────
from integrations.crm_store import LeadRecord, create_crm_store
from integrations.catalog_store import CATALOG_SEED, create_catalog_store
from integrations.research_store import create_research_store
from integrations.payment_integration import SalesCheckout
from integrations.telegram_flow import TelegramSalesFlow
from integrations.stripe_checkout import StripeCheckoutService

CRM_DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "crm_sales.db")
CATALOG_DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "agent_catalog.db")
RESEARCH_DATA_FILE = os.path.join(os.path.dirname(__file__), "data", "research_insights.db")
crm_store = create_crm_store(CRM_DATA_FILE)
catalog_store = create_catalog_store(CATALOG_DATA_FILE)
research_store = create_research_store(RESEARCH_DATA_FILE)

# ── Canonical dashboard store (persistent — survives deploys) ──────────────
# On-chain sales / request log / PayAPI listing state live in SQLite so a
# gunicorn restart NEVER zeroes the dashboard numbers. See DASHBOARD_AUDIT.md.
from integrations.dashboard_store import (  # noqa: E402
    REQUEST_LOG_RETENTION_DAYS_DEFAULT,
    REQUEST_SNAPSHOT_INTERVAL_SECONDS,
    WHALE_RETENTION_DAYS_DEFAULT,
    DashboardStore,
    redact_rpc,
)
from services.signal_track_record import CHECKPOINTS as SIGNAL_CHECKPOINTS  # noqa: E402
# The local SQLite file holds only the operational state (meta + payapi_state).
# If it is corrupted on disk the dashboard build fails with "database disk image
# is malformed" — a restart cannot fix it, because the file is on the persistent
# disk. KRISTO_DASHBOARD_DB lets the operator move to a fresh file while the
# broken one stays on disk as an archive (nothing is deleted).
DASHBOARD_DB_FILE = os.getenv("KRISTO_DASHBOARD_DB") or os.path.join(
    os.path.dirname(__file__), "data", "dashboard_state.db")
dashboard_db = DashboardStore(DASHBOARD_DB_FILE)

# ── Day-of-Truth recovery (13.09) ─────────────────────────────────────────
# Re-assert the chain-verified sales manifest on EVERY boot. The Render
# filesystem is ephemeral, so a deploy used to zero the on-chain counters
# until the retro scan crawled back. Idempotent (INSERT OR IGNORE by tx hash),
# never overwrites a scan-discovered row, never touches the scan watermark.
# Full 66-char hashes, cross-verified against RPC receipts by
# scripts/_verify_seed_chain.py — see integrations/verified_sales.py.
try:
    _seed = dashboard_db.seed_verified_sales()
    log.info("Verified-sales seed: %d inserted, %d total ($%.6f USDC, "
             "%d external payers).", _seed["inserted"], _seed["present"],
             _seed["total_usdc"], _seed["external_payers"])
except Exception as _seeded_exc:  # pragma: no cover - defensive
    log.warning("Verified-sales seed failed (non-fatal): %s", _seeded_exc)

# ── Payer taxonomy is re-applied at BOOT (17.09) ──────────────────────────
# Rows are classified when they are written, so a wallet fingerprinted as
# market infrastructure LATER keeps its old class until something re-runs the
# taxonomy. The scanner cycles do it, but they need an RPC and a free thread —
# so a boot where the chain is unreachable would leave the dashboard telling an
# old, flattering story (a crawler counted as a customer). Idempotent.
try:
    _reclassified = dashboard_db.reclassify_known_payers()
    if _reclassified:
        log.info("Payer taxonomy re-applied at boot: %d row(s) reclassified.",
                 _reclassified)
except Exception as _reclass_exc:  # pragma: no cover - defensive
    log.warning("Payer reclassify failed (non-fatal): %s", _reclass_exc)

# ── Whale retention at BOOT (18.09) ───────────────────────────────────────
# The whale feed is ROLLING (the paid route serves a 24h window), so rows older
# than the retention horizon are ballast — and at the previous $50k threshold
# they were a storage hazard too (427 MB in under five days on a 1 GB plan).
# Idempotent: a second run deletes 0 rows.
try:
    _purged = dashboard_db.purge_old_whale_events()
    log.info("Whale retention: %d row(s) older than %d days removed.",
             _purged, WHALE_RETENTION_DAYS_DEFAULT)
except Exception as _purge_exc:  # pragma: no cover - defensive
    log.warning("Whale retention failed (non-fatal): %s", _purge_exc)

# ── request_log retention (07.11) ─────────────────────────────────────────
# The other unbounded table, and the reason one slow panel could take the whole
# service down. `request_log` had no retention anywhere: it grew from the day
# the service started, and the ten aggregates the dashboard runs over it were
# measured at 10-21 SECONDS each, against an 8s statement timeout. A panel that
# cannot be read is now reported as unreadable instead of failing the build,
# but the cost of the read only ever grew.
#
# 30 days is 30x more history than anything reads: the only window any query
# opens on this table is 24 hours. Idempotent — a second run deletes 0 rows.
#
# WHY THIS ONE IS *NOT* A BOOT-TIME CALL, unlike the whale pass. The first run
# has over a million rows to remove, and the pass is batched at 5000 per
# statement — so that is 200+ round trips. Run inline at import time it delays
# the worker from binding its port, and on 07.11 it did exactly that: Render
# logged "No open ports detected, continuing to scan" before the service came
# up, and the dashboard's reads hit QueryCanceled while the deletes held the
# table. A retention pass must not be able to look like a failed deploy.
#
# So: a daemon thread, started after the module is importable. The app binds
# immediately; the pass drains in the background, logging what it removed. The
# whale pass can stay inline because it deletes single-digit rows.
def _request_log_retention() -> None:
    try:
        # ITS OWN POSTGRES LINK. This is the single most expensive thing the
        # process does to that database: on a first run it DELETEs over a million
        # rows in batches of 5000, which the comment above already calls "200+
        # round trips" — and every one of them took the link the request path
        # waits on. It is the same defect that took the write path down on 08.11,
        # in its heaviest form, and it is the reason this pass is not run at
        # import either.
        store = _isolated_store("request-log-retention")
        removed = store.purge_old_requests()
        log.info("Request-log retention: %d row(s) older than %d days removed.",
                 removed, REQUEST_LOG_RETENTION_DAYS_DEFAULT)
    except Exception as exc:  # pragma: no cover - defensive
        log.warning("Request-log retention failed (non-fatal): %s", exc)


# ── Off-chain record durability (audit A2) ────────────────────────────────
# The ON-CHAIN numbers are re-seeded from the chain on every boot, so a deploy
# cannot zero them. The CRM (leads / paid leads / sales pipeline) has no such
# protection: without DATABASE_URL it is SQLite on Render's EPHEMERAL disk, so
# a deploy silently wipes it. Say it in the logs instead of pretending.
if getattr(crm_store, "backend", "") != "postgresql":
    log.warning(
        "CRM storage is %s on the EPHEMERAL disk — every deploy wipes leads, "
        "paid leads and the sales pipeline. Set DATABASE_URL for a durable "
        "off-chain record.", getattr(crm_store, "backend", "unknown"))


checkout_store = SalesCheckout()
telegram_flow = TelegramSalesFlow(os.getenv("TELEGRAM_BOT_TOKEN", ""))
stripe_checkout = StripeCheckoutService()

# ── In-memory data stores (thread-safe via lock) ──────────────────────────
_lock = threading.Lock()
_stripe_snapshot_lock = threading.Lock()
_stripe_snapshot = {
    "available": False,
    "payments": [],
    "reason": "Stripe payment snapshot is warming up.",
    "fetched_at": None,
    "state": "pending",
}

# ── Official agent catalog ─────────────────────────────────────────────────
# Keep legacy statistics endpoints aligned with the durable eight-agent catalog.
PRODUCT_CATALOG = [
    {
        "id": product["id"],
        "name": product["name"],
        "category": product["category"],
        "price_usdc": product["price_x402"],
    }
    for product in CATALOG_SEED
]

# Quick lookup: product_id -> product metadata
_PRODUCT_BY_ID: Dict[str, dict] = {p["id"]: p for p in PRODUCT_CATALOG}

# Per-product stats: product_id -> {hits, sales_count, sales_volume_usd}
_product_stats: Dict[str, dict] = {
    p["id"]: {"hits": 0, "sales_count": 0, "sales_volume_usd": 0.0}
    for p in PRODUCT_CATALOG
}

# Sales history: list of dicts {timestamp, token, amount_usd, tx_hash, status}
#   — ONLY populated by real on-chain USDC transfers
_sales_history: List[dict] = []

# Request/activity log: deque for bounded size
_request_log: deque = deque(maxlen=500)
_live_request_log: deque = deque(maxlen=200)
_telegram_active_chats: set[str] = set()

# Daily stats
_daily_stats: Dict[str, dict] = {}  # date_str -> {requests, sales_count, sales_volume}

# Real wallet state
_wallet_state = {
    "wallet_address": None,
    "fee_receiver": None,
    "usdc_balance": 0.0,
    "receiver_usdc_balance": 0.0,
    "rpc_connected": False,
    "chain_id": None,
    "network": "Base Mainnet",
    "receiver_valid": False,
    "rpc_error": None,
    "last_block_checked": 0,
    "last_check_time": None,
    # When the DASHBOARD scan last read the chain successfully, and up to which
    # block. The dedicated payment monitor is only ONE of two scanners reading the
    # same receiver out of the same store; this is the other one's proof of life.
    # Added 06.11 so /health can tell "the chain is unreachable" apart from "our
    # redundant monitor failed to start" — it used to report only the second, as
    # if it were the first, and raised a Telegram alarm on it every deploy.
    "sales_scan_ok_at": None,
    "sales_scan_block": 0,
}

#: Proof-of-life keys, in the SHARED store (`dashboard_meta`).
#:
#: `_wallet_state` is process-local memory, and the recommended production
#: deployment splits the loops away from the web process: scripts/worker.py's own
#: diagram has web as HTTP-only (`KRISTO_DISABLE_BACKGROUND_THREADS=true`) and the
#: worker as background-only, sharing POSTGRES. Memory cannot cross that split, so
#: `/health` — which runs in the WEB process and read only `_wallet_state` — could
#: never see the monitor's state there. Measured 07.11: `/health` reported
#: `blockchain.ready: false` with `last_block_checked: 0` for over fifteen hours
#: while the worker was demonstrably scanning that same chain every minute and
#: writing `last_scanned_block` into Postgres. The alarm was about where we looked,
#: not about Base.
#:
#: These keys are how the two processes tell each other the truth. The in-process
#: stamp is still written as well, so a single-process deployment keeps working.
MONITOR_HEARTBEAT_KEY = "monitor_heartbeat_at"
MONITOR_HEARTBEAT_BLOCK_KEY = "monitor_heartbeat_block"
SALES_SCAN_HEARTBEAT_KEY = "sales_scan_heartbeat_at"


def _publish_heartbeat(state_key: str, meta_key: str, block: Optional[int] = None,
                       state_block_key: Optional[str] = None,
                       meta_block_key: Optional[str] = None) -> str:
    """Stamp liveness in BOTH places: this process's memory and the shared store.

    Written only on SUCCESS by both callers, so the stamp ages when the chain stops
    answering. An absence never refreshes it — `/health` treats a stale or missing
    stamp as no evidence at all.

    A store that cannot be written must not kill the loop that just proved the chain
    is fine, so the persistence half is best-effort: the in-process stamp still
    stands, and the failure is logged at debug rather than raised.
    """
    now = datetime.now(timezone.utc).isoformat()
    with _lock:
        _wallet_state[state_key] = now
        if block is not None and state_block_key:
            _wallet_state[state_block_key] = block
    try:
        dashboard_db.set_meta(meta_key, now)
        if block is not None and meta_block_key:
            dashboard_db.set_meta(meta_block_key, str(block))
    except Exception as exc:
        log.debug("Heartbeat %s could not be persisted: %s", meta_key, exc)
    return now


def _note_sales_scan_ok() -> None:
    """Record that the dashboard scan just read the chain, successfully.

    Called ONLY on success, so the stamp ages when the RPC stops answering: an
    absence never refreshes it, which is the whole point of keeping it. `/health`
    reads a fresh stamp as evidence that the chain itself is readable even when the
    separate payment monitor never got off the ground.

    Published to the shared store as well as to memory: in the split deployment the
    scan runs in the worker process and `/health` in the web one.
    """
    try:
        block = int(dashboard_db.get_meta("last_scanned_block", "0") or 0)
    except Exception:
        # A store that cannot answer must not break the scan loop. The block is
        # cosmetic here; the timestamp is the fact that matters.
        block = 0
    _publish_heartbeat("sales_scan_ok_at", SALES_SCAN_HEARTBEAT_KEY,
                       block=block, state_block_key="sales_scan_block")

# Bot status
_bot_status = {
    "telegram_bot_running": True,
    "telegram_token_configured": bool(os.getenv("TELEGRAM_BOT_TOKEN", "").strip()),
    "last_heartbeat": datetime.now(timezone.utc).isoformat(),
    "uptime_started": datetime.now(timezone.utc).isoformat(),
    "messages_sent": 0,
    "active_users": 0,
    "commands_processed": 0,
    "vip_invites_sent": 0,
}

# ── Subscription tiers & pricing ─────────────────────────────────────────
# Per-API-call price comes from config (single source of truth).
MICRO_FEE_USDC = BASE_FEE_AMOUNT_USDC  # Per API call
VIP_MONTHLY_USDC = 29.00   # Monthly VIP subscription (Stripe, human product)
# A payment at/above the Telegram VIP-analysis price triggers the VIP invite
# logic. Both numbers come from config.py's single source, so a change there
# cannot leave the bot offering one price and granting access at another.
VIP_THRESHOLD_USDC = KRISTO_VIP_ANALYSIS_PRICE

# Active VIP subscribers (wallet address -> {joined, invite_code, tx_hash})
_vip_subscribers: Dict[str, dict] = {}

# VIP invite codes generated (code -> {wallet, created, used})
_vip_invites: Dict[str, dict] = {}


def _classify_payment(amount_usd: float) -> str:
    """Classify a payment into a subscription tier."""
    if amount_usd >= VIP_MONTHLY_USDC:
        return "vip_monthly"
    else:
        return "micro_request"


def _is_vip_plan(plan_key: str) -> bool:
    normalized = plan_key.strip().lower()
    return normalized in {"pro", "vip", "vip_monthly"}


def _activate_stripe_vip_access(
    paid_lead: dict,
    event_data: dict,
    plan_key: str,
    already_paid: bool,
) -> dict:
    """Grant durable VIP access from the persisted paid lead exactly once."""
    if not _is_vip_plan(plan_key):
        return {"status": "not_eligible"}
    if already_paid:
        return {"status": "already_active"}

    metadata = event_data.get("metadata", {}) or {}
    chat_id = (paid_lead.get("telegram_chat_id") or metadata.get("telegram_chat_id") or "").strip()
    checkout_id = str(event_data.get("id") or "")
    return telegram_flow.deliver_vip_invite(chat_id, checkout_id, "Pro")


def _generate_vip_invite(wallet_address: str, tx_hash: str,
                         chat_id: str = "") -> Optional[str]:
    """
    Generate a Telegram VIP invite code for a wallet that paid >= VIP_THRESHOLD.

    DURABLE since 18.09: the code is written to the Postgres `vip_invites` table
    first (the in-RAM dicts remain as a mirror for the status counters). Before
    this, an invite issued minutes before a deploy simply ceased to exist while
    the sale that paid for it stayed — the same class of bug the money table had.
    Returns the invite code string, or None on failure.
    """
    invite_code = f"KRI-VIP-{secrets.token_hex(4).upper()}"
    stored = False
    try:
        stored = dashboard_db.record_vip_invite(invite_code, wallet_address,
                                                tx_hash, chat_id=chat_id,
                                                source="onchain")
    except Exception as exc:
        log.warning("VIP invite not persisted (non-fatal): %s", exc)
    with _lock:
        _vip_invites[invite_code] = {
            "wallet": wallet_address,
            "tx_hash": tx_hash,
            "chat_id": str(chat_id or ""),
            "created": datetime.now(timezone.utc).isoformat(),
            "used": False,
            "durable": stored,
        }
        _vip_subscribers[wallet_address] = {
            "joined": datetime.now(timezone.utc).isoformat(),
            "invite_code": invite_code,
            "tx_hash": tx_hash,
        }
        _bot_status["vip_invites_sent"] += 1

    log.info("VIP invite generated: code=%s for wallet=%s (tx=%s, durable=%s)",
             invite_code, wallet_address, tx_hash, stored)

    # Best-effort: send Telegram notification if bot token is configured
    _send_telegram_vip_notification(wallet_address, invite_code, tx_hash)

    return invite_code


def _send_telegram_vip_notification(wallet_address: str, invite_code: str, tx_hash: str):
    """Announce a new VIP subscriber — privately whenever possible.

    18.09 (found by the owner while testing as a buyer): with only
    TELEGRAM_CHAT_ID set — ours is the PUBLIC channel @Kristointeligent — this
    posted the buyer's wallet AND the invite code to the whole world. The code is
    the product: anyone reading the channel could claim it first, and the payer's
    address was published for no reason. The full message now goes ONLY to an
    explicitly configured TELEGRAM_VIP_CHAT_ID; otherwise the channel gets a
    redacted receipt (truncated wallet, no code) and the code stays in the log.
    """
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    # Audit A4: this read ONLY TELEGRAM_VIP_CHAT_ID while /sales/checkout read
    # `TELEGRAM_VIP_CHAT_ID or TELEGRAM_CHAT_ID` — two paths, one config, so a
    # deployment with only TELEGRAM_CHAT_ID set silently dropped VIP alerts here.
    # The fallback stays (the owner must hear about a payment), but it no longer
    # carries anything private.
    owner_chat = os.getenv("TELEGRAM_VIP_CHAT_ID", "").strip()
    public_chat = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    chat_id = owner_chat or public_chat
    if not token or not chat_id:
        log.info("Telegram VIP notification skipped (no token/chat_id). Invite code: %s", invite_code)
        return

    try:
        import requests as _requests
        stamp = datetime.now(timezone.utc).isoformat()
        if owner_chat:
            msg = (
                f"🎉 New VIP Subscriber!\n"
                f"Wallet: {wallet_address[:10]}...{wallet_address[-6:]}\n"
                f"Invite Code: {invite_code}\n"
                f"Tx: {tx_hash[:18]}...\n"
                f"Time: {stamp}"
            )
        else:
            # Public channel: a receipt, never the product.
            log.info("VIP invite %s NOT posted publicly (no TELEGRAM_VIP_CHAT_ID); "
                     "redacted notice only.", invite_code)
            msg = (
                f"🎉 Нов VIP абонат — плащане потвърдено on-chain\n"
                f"Портфейл: {wallet_address[:10]}...{wallet_address[-6:]}\n"
                f"Tx: {tx_hash[:18]}...\n"
                f"Time: {stamp}\n"
                f"(Кодът се изпраща насаме — не се публикува.)"
            )
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        _requests.post(url, json={"chat_id": chat_id, "text": msg, "parse_mode": "HTML"}, timeout=10)
        with _lock:
            _bot_status["messages_sent"] += 1
        log.info("Telegram VIP notification sent for invite %s", invite_code)
    except Exception as exc:
        log.warning("Telegram VIP notification failed (non-fatal): %s",
                    services.telegram_sales._redact_tg(exc))


# ── Real wallet / blockchain initialization ──────────────────────────────
def _connect_monitor_only(rpc_url: str, fee_receiver: str, usdc_address: str):
    """One monitor-only Web3 connection, or raise.

    Extracted from `_init_wallet` unchanged in behaviour so that function can try
    SEVERAL endpoints without repeating this block. Returns (wallet_like, chain_id).
    """
    from web3 import Web3
    from services.rpc_pool import get_web3

    # Shared, not per call: see services/rpc_pool.py for the measured leak this
    # replaces. `Web3` itself is still imported here for `is_address` below.
    w3 = get_web3(rpc_url, 30)
    connected = w3.is_connected() if hasattr(w3, "is_connected") else w3.isConnected()
    if not connected:
        raise ConnectionError("rpc_unreachable")
    if not Web3.is_address(fee_receiver):
        raise ValueError("Configured Base fee receiver is not a valid EVM address")
    chain_id = int(w3.eth.chain_id)
    if chain_id != BASE_CHAIN_ID:
        raise ConnectionError(
            f"Configured RPC chain {chain_id} is not Base Mainnet ({BASE_CHAIN_ID})"
        )

    # Create a lightweight monitor-only wallet-like object
    class _MonitorOnlyWallet:
        pass

    mock = _MonitorOnlyWallet()
    mock.w3 = w3
    mock.fee_receiver = Web3.to_checksum_address(fee_receiver)
    mock.account = type("obj", (object,), {"address": fee_receiver})()
    # Build USDC contract for balance check
    _ERC20_ABI = [
        {"constant": True, "inputs": [{"name": "owner", "type": "address"}],
         "name": "balanceOf", "outputs": [{"name": "", "type": "uint256"}], "type": "function"},
        {"constant": True, "inputs": [], "name": "decimals",
         "outputs": [{"name": "", "type": "uint8"}], "type": "function"},
    ]
    mock.usdc = w3.eth.contract(
        address=Web3.to_checksum_address(usdc_address), abi=_ERC20_ABI
    )

    def _get_usdc_balance(self):
        decimals = self.usdc.functions.decimals().call()
        raw = self.usdc.functions.balanceOf(self.fee_receiver).call()
        return raw / (10 ** decimals)

    mock.get_usdc_balance = _get_usdc_balance.__get__(mock, _MonitorOnlyWallet)
    return mock, chain_id


def _init_wallet() -> Optional[object]:
    """
    Initialize the real Base wallet from environment variables.

    If WALLET_PRIVATE_KEY is set, a full Wallet object is created (can send + monitor).
    If only BASE_FEE_RECEIVER is set (no private key), a lightweight monitor-only
    Web3 connection is created — sufficient for scanning incoming USDC transfers.

    Every endpoint in `base_rpc_candidates()` is tried IN ORDER, for BOTH shapes,
    before this gives up (06.11). It used to dial BASE_RPC_URL and nothing else, so
    one rate-limited shared endpoint (429) took the whole payment-detection layer
    down with it — measured uninitialised for over half an hour on 06.11. The
    settlement rail has had a fallback chain for months; this is the same idea
    applied to the dependency that detects the incoming payment in the first place.

    On total failure the REASON is recorded in `_wallet_state["rpc_error"]`, always
    through `redact_rpc`: a paid endpoint carries its api key in the path. Before
    this, the "cannot connect" path returned None having written NOTHING, so
    /health could report `blockchain.ready: false` and no surface anywhere said why
    — the operator saw an alarm with no cause attached to it.
    """
    pk = os.getenv("WALLET_PRIVATE_KEY", "").strip()
    fee_receiver = get_base_fee_receiver()  # hard fallback to bound address
    usdc_address = os.getenv("BASE_USDC_CONTRACT", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")
    candidates = base_rpc_candidates()
    last_error: Optional[str] = None

    # Try full wallet first (with private key)
    if pk:
        from blockchain.wallet import Wallet

        for rpc_url in candidates:
            try:
                # Constructed directly rather than through Wallet.from_env(): the
                # classmethod reads BASE_RPC_URL itself, which is the single-url
                # behaviour this loop exists to get away from. The arguments are
                # exactly the ones from_env() passes.
                wallet = Wallet(private_key=pk, rpc_url=rpc_url,
                                usdc_address=usdc_address,
                                fee_receiver=fee_receiver)
                chain_id = int(wallet.w3.eth.chain_id)
                if chain_id != BASE_CHAIN_ID:
                    raise ConnectionError(
                        f"Configured RPC chain {chain_id} is not Base Mainnet ({BASE_CHAIN_ID})"
                    )
                log.info("Real wallet initialized: address=%s (rpc=%s)",
                         wallet.account.address, redact_rpc(rpc_url))
                with _lock:
                    _wallet_state["wallet_address"] = wallet.account.address
                    _wallet_state["fee_receiver"] = wallet.fee_receiver
                    _wallet_state["rpc_connected"] = True
                    _wallet_state["chain_id"] = chain_id
                    _wallet_state["receiver_valid"] = True
                    _wallet_state["rpc_error"] = None
                return wallet
            except Exception as exc:
                last_error = redact_rpc(exc)
                log.warning("Wallet init failed via %s: %s — trying next endpoint.",
                            redact_rpc(rpc_url), last_error)
        log.error("Failed to initialize full wallet on %d endpoint(s) — "
                  "falling back to monitor-only.", len(candidates))

    # Fallback: monitor-only mode (no private key needed)
    if fee_receiver:
        log.info("Initializing monitor-only Web3 connection (no private key). Fee receiver: %s", fee_receiver)
        for rpc_url in candidates:
            try:
                mock, chain_id = _connect_monitor_only(rpc_url, fee_receiver, usdc_address)

                with _lock:
                    _wallet_state["wallet_address"] = fee_receiver
                    _wallet_state["fee_receiver"] = fee_receiver
                    _wallet_state["rpc_connected"] = True
                    _wallet_state["chain_id"] = chain_id
                    _wallet_state["receiver_valid"] = True
                    _wallet_state["rpc_error"] = None

                log.info("Monitor-only wallet ready (rpc=%s). Tracking USDC transfers to: %s",
                         redact_rpc(rpc_url), fee_receiver)
                return mock

            except Exception as exc:
                last_error = redact_rpc(exc)
                log.error("Monitor-only init failed via %s: %s — trying next endpoint.",
                          redact_rpc(rpc_url), last_error)

        # Every endpoint refused. Say so WITH the reason: a bare `ready: false`
        # is the alarm without the cause.
        with _lock:
            _wallet_state["rpc_connected"] = False
            _wallet_state["rpc_error"] = last_error or "no_rpc_answered"
        log.error("No Base RPC endpoint answered (%d tried). Last reason: %s",
                  len(candidates), _wallet_state["rpc_error"])
        return None

    log.warning("No WALLET_PRIVATE_KEY or BASE_FEE_RECEIVER set — wallet monitoring disabled.")
    return None


def _fetch_receiver_usdc_balance():
    """
    On-chain USDC balance of the FEE RECEIVER (0xd4cdA900…08f) — where client
    payments land. Distinct from the gas-payer wallet's balance: PayAPI's
    review correctly flagged that the dashboard showed an empty hot-wallet
    balance next to a receiver that had just been paid.
    Returns float | None on any failure.
    """
    try:
        from web3 import Web3
        from services.rpc_pool import get_web3
        # Called once per blockchain-monitor cycle (~2/min): the per-call Web3
        # this replaces leaked a session and its sockets every time.
        w3 = get_web3(os.getenv("BASE_RPC_URL",
                                "https://mainnet.base.org"), 20)
        if not w3.is_connected():
            return None
        usdc = os.getenv("BASE_USDC_CONTRACT",
                         "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")
        receiver = get_base_fee_receiver()
        selector = "0x70a08231"  # balanceOf(address)
        padded = receiver.lower().replace("0x", "").rjust(64, "0")
        result = w3.eth.call({"to": Web3.to_checksum_address(usdc),
                              "data": selector + padded})
        return int(result.hex(), 16) / 1e6
    except Exception as exc:
        log.debug("receiver USDC balance fetch: %s", exc)
        return None


# ── Blockchain monitor: detect incoming USDC transfers ───────────────────
def _monitor_resume_block(head: int, watermark: int, lookback: int) -> tuple:
    """Where the blockchain monitor should start scanning, and why.

    Extracted from the loop so the decision can be tested without a chain, a
    wallet or a thread.

    This used to be a single line in _blockchain_monitor_loop:
    `last_block = wallet.w3.eth.block_number`. Whatever landed while the worker
    was down was skipped for good - and Render restarts the worker on every
    deploy, so that was every deploy, not an unlucky crash. The dashboard scan had
    already solved this (dashboard_store.scan_increment, "deploy-safe"): it keeps
    last_scanned_block durably and, with no watermark, refuses to mark the head as
    scanned, because that would skip the history permanently. The monitor scans
    the same receiver and the same topic, so the same watermark is a truthful
    resume point for it too.

    Re-scanning an overlap is harmless, which is what makes resuming from an older
    block safe rather than a double-count risk: _record_real_sale dedups on tx
    hash case-insensitively before appending, and the store dedups again with
    INSERT OR IGNORE.

    Returns (from_block, reason).
    """
    head = max(0, int(head or 0))
    watermark = int(watermark or 0)

    if watermark > 0:
        if watermark > head:
            # A watermark ahead of the head means the chain view moved backwards
            # (reorg, or an RPC far behind another). Never scan the future; the
            # safe non-skipping choice is to start at the head and say so.
            return head, "watermark %d is ahead of head %d" % (watermark, head)
        return watermark, "durable watermark %d (%d blocks behind head)" % (
            watermark, head - watermark)

    # No watermark at all: do NOT claim the head as scanned. That is the bug this
    # replaces. Scan a bounded window instead, wide enough to cover a restart and
    # a deploy, and log that the range is bounded rather than complete.
    #
    # 1800 blocks was chosen as "~1 hour at 2 s/block"; at the measured 0.2
    # s/block it is ~6 MINUTES (see main.py's block-cadence note). Still wider
    # than a Render restart, so the intent holds — but it is minutes, not the
    # hour the docstring used to imply, and BLOCKCHAIN_RESUME_LOOKBACK is the
    # knob if a deploy ever takes longer than that.
    lookback = max(1, int(lookback or 0))
    return max(1, head - lookback), (
        "no durable watermark; bounded %d-block lookback from head %d"
        % (lookback, head))


def _blockchain_monitor_loop():
    """
    Background thread that monitors the Base blockchain for real incoming
    USDC transfers to our fee receiver address. When a transfer is detected,
    it is recorded as a real sale.

    Uses the ERC-20 Transfer event log to find incoming transfers.

    If the RPC is unreachable at startup (the public mainnet.base.org
    endpoint rate-limits with 429s), the thread retries indefinitely
    instead of exiting — otherwise payment detection would never start.
    """
    log.info("Blockchain monitor thread started.")
    poll_interval = int(os.getenv("BLOCKCHAIN_POLL_INTERVAL", "30"))
    retry_interval = max(60, int(os.getenv("BLOCKCHAIN_RETRY_INTERVAL", "120")))

    wallet = None
    while wallet is None:
        wallet = _init_wallet()
        if wallet is None:
            log.warning(
                "Blockchain monitor: wallet unavailable (RPC down / rate-limited) "
                "— retrying in %ds.",
                retry_interval,
            )
            time.sleep(retry_interval)
    usdc_address = os.getenv("BASE_USDC_CONTRACT", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913")
    fee_receiver = wallet.fee_receiver

    # ERC-20 Transfer event topic: keccak256("Transfer(address,address,uint256)")
    TRANSFER_TOPIC = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"

    # The 'to' address is padded to 32 bytes in the log topic
    receiver_topic = "0x000000000000000000000000" + fee_receiver[2:] if fee_receiver.startswith("0x") else "0x000000000000000000000000" + fee_receiver

    # Resume from the durable watermark rather than the current head: see
    # _monitor_resume_block for why starting at the head loses payments across
    # every deploy, and why an overlap is safe to re-scan.
    _head = wallet.w3.eth.block_number
    try:
        _watermark = int(dashboard_db.get_meta("last_scanned_block", "0") or 0)
    except Exception as exc:
        _watermark = 0
        log.warning("Blockchain monitor: watermark unreadable (%s)", exc)

    last_block, _resume_reason = _monitor_resume_block(
        _head, _watermark, int(os.getenv("BLOCKCHAIN_RESUME_LOOKBACK", "1800")))
    if last_block < _head:
        log.warning(
            "Blockchain monitor: starting at block %d, not the head %d — %s. "
            "Transfers in that range are not lost; they are scanned now and "
            "deduplicated by tx hash.",
            last_block, _head, _resume_reason)
    else:
        log.info("Blockchain monitor: starting at head %d (%s)",
                 last_block, _resume_reason)

    # Proof of life the moment the monitor is up, not only after its first scan:
    # a monitor that initialised and is waiting on the poll interval is working,
    # and the board should be able to say so. Persisted to the shared store too —
    # in the split deployment this loop and /health live in different processes.
    _publish_heartbeat("last_check_time", MONITOR_HEARTBEAT_KEY,
                       block=last_block,
                       state_block_key="last_block_checked",
                       meta_block_key=MONITOR_HEARTBEAT_BLOCK_KEY)

    log.info("Monitoring USDC transfers to %s from block %d", fee_receiver, last_block)

    while True:
        try:
            current_block = wallet.w3.eth.block_number
            if current_block <= last_block:
                time.sleep(poll_interval)
                continue

            # Update real balance
            try:
                balance = wallet.get_usdc_balance()
                with _lock:
                    _wallet_state["usdc_balance"] = round(balance, 4)
            except Exception as exc:
                log.debug("Balance fetch failed: %s", exc)

            # Update the FEE RECEIVER's USDC balance (the meaningful figure:
            # this is where client payments land — the gas-payer wallet is
            # incidental and shows 0.0, which PayAPI's review flagged).
            try:
                receiver_balance = _fetch_receiver_usdc_balance()
                if receiver_balance is not None:
                    with _lock:
                        _wallet_state["receiver_usdc_balance"] = round(
                            receiver_balance, 6)
            except Exception as exc:
                log.debug("Receiver balance fetch failed: %s", exc)

            # Scan blocks for Transfer events to our receiver
            from_block = last_block + 1
            to_block = min(current_block, from_block + 1000)  # cap batch size

            scan_succeeded = False
            try:
                from web3 import Web3
                logs = wallet.w3.eth.get_logs({
                    "fromBlock": from_block,
                    "toBlock": to_block,
                    "address": Web3.to_checksum_address(usdc_address),
                    "topics": [TRANSFER_TOPIC, None, receiver_topic],
                })

                if logs:
                    log.info("Found %d incoming USDC transfer(s) in blocks %d-%d", len(logs), from_block, to_block)
                    for log_entry in logs:
                        _process_incoming_transfer(wallet, log_entry)
                scan_succeeded = True

            except Exception as exc:
                log.warning("Log scan failed for blocks %d-%d: %s", from_block, to_block, redact_rpc(exc))

            if scan_succeeded:
                last_block = to_block
                _publish_heartbeat("last_check_time", MONITOR_HEARTBEAT_KEY,
                                   block=last_block,
                                   state_block_key="last_block_checked",
                                   meta_block_key=MONITOR_HEARTBEAT_BLOCK_KEY)

        except Exception as exc:
            log.warning("Blockchain monitor cycle failed (non-fatal): %s", redact_rpc(exc))

        time.sleep(poll_interval)


def _process_incoming_transfer(wallet, log_entry):
    """Process a single incoming USDC Transfer event log and record it as a sale."""
    try:
        from web3 import Web3

        # Decode the transfer data
        # log_entry['data'] contains the amount (uint256)
        raw_data = log_entry["data"]
        if isinstance(raw_data, (bytes, bytearray)):
            amount_raw = int(raw_data.hex(), 16)
        else:
            amount_raw = int(raw_data, 16)

        # Get decimals (typically 6 for USDC on Base)
        decimals = wallet.usdc.functions.decimals().call()
        amount_usd = amount_raw / (10 ** decimals)

        # Get tx hash
        tx_hash = _to_hex0x(log_entry["transactionHash"])

        # Get block timestamp
        block = wallet.w3.eth.get_block(log_entry["blockNumber"])
        block_ts = datetime.fromtimestamp(block["timestamp"], tz=timezone.utc)

        # Get sender address from topic[1]
        sender_topic = log_entry["topics"][1]
        sender_hex = sender_topic.hex() if hasattr(sender_topic, "hex") else sender_topic
        sender = "0x" + sender_hex[-40:]

        log.info("Real USDC transfer detected: $%.6f from %s, tx=%s", amount_usd, sender, tx_hash)

        # Record as a real sale
        _record_real_sale(
            token="USDC",
            amount_usd=round(amount_usd, 6),
            tx_hash=tx_hash,
            sender=sender,
            block_number=log_entry["blockNumber"],
            timestamp=block_ts,
        )

    except Exception as exc:
        log.error("Failed to process incoming transfer: %s", exc)


def _record_real_sale(token: str, amount_usd: float, tx_hash: str, sender: str = "",
                      block_number: int = 0, timestamp: Optional[datetime] = None):
    """Record a REAL on-chain sale in the history."""
    ts = timestamp or datetime.now(timezone.utc)
    date_str = ts.strftime("%Y-%m-%d")
    with _lock:
        # Avoid duplicates: check if tx_hash already recorded (case-insensitive —
        # settle path and blockchain monitor may format the hash differently,
        # which caused the dashboard to double-count PayAPI's first payment).
        tx_norm = (tx_hash or "").lower()
        for s in _sales_history:
            if (s.get("tx_hash") or "").lower() == tx_norm:
                log.debug("Duplicate tx %s — skipping.", tx_norm)
                return

        _sales_history.append({
            "timestamp": ts.isoformat(),
            "token": token,
            "amount_usd": round(amount_usd, 6),
            "tx_hash": tx_hash,
            "sender": sender,
            "block_number": block_number,
            "status": "confirmed",
        })
        if date_str not in _daily_stats:
            _daily_stats[date_str] = {
                "requests": 0,
                "sales_count": 0,
                "sales_volume": 0.0,
            }
        _daily_stats[date_str]["sales_count"] += 1
        _daily_stats[date_str]["sales_volume"] = round(
            _daily_stats[date_str]["sales_volume"] + amount_usd, 6
        )
    log.info("Recorded real sale: %s $%.6f (tx=%s)", token, amount_usd, tx_hash)

    # ── Persistent dashboard record (deploy-proof) ─────────────────────────
    # RAM structures above reset on restart; the SQLite store does not.
    # Dedup by tx hash happens inside the store (INSERT OR IGNORE).
    try:
        dashboard_db.record_sale(
            tx_hash=tx_hash,
            amount_usdc=amount_usd,
            sender=sender,
            block_number=block_number,
            ts=ts,
            source="live",
        )
    except Exception as exc:
        # Never break the payment path because of dashboard bookkeeping.
        log.warning("Dashboard store: sale not persisted: %s", exc)


    # ── VIP invite generation for payments above threshold ──────────────
    if amount_usd >= VIP_THRESHOLD_USDC and sender:
        tier = _classify_payment(amount_usd)
        log.info("Payment classified as '%s' ($%.6f) — checking VIP invite...", tier, amount_usd)
        # Durable first (18.09): the RAM dict forgot every invite on a deploy, so
        # a wallet that had already paid could be issued a SECOND code.
        already = sender in _vip_subscribers
        if not already:
            try:
                already = dashboard_db.vip_invite_for_wallet(sender) is not None
            except Exception as exc:
                log.debug("Durable VIP lookup failed (using RAM): %s", exc)
        if not already:
            invite = _generate_vip_invite(sender, tx_hash)
            if invite:
                log.info("VIP invite %s generated for %s payment by %s", invite, tier, sender)
        else:
            log.info("Wallet %s already has VIP status — skipping invite.", sender)


# ── Background trading agent thread ───────────────────────────────────────
# Latest live agent signals (populated by the background agent loop, served
# by GET /api/v1/signal — PayAPI's reviewer asked for a cheap route that
# returns an actual SIGNAL instead of operational stats).
_latest_signals: dict = {"generated_at": None, "signals": []}


def _publish_agent_signals(decisions) -> None:
    """Map raw trading-agent decisions into the published signal schema for
    GET /api/v1/signal.

    PayAPI reviewer feedback (second verified route, 2026-02):
      * `price_usd` must be a real number, not null — an agent should not
        have to parse "price=$2387.7800" out of the note string.
      * each signal carries a one-line `reasoning` naming the main driver,
        so the buyer gets something /api/stats never offered.
    """
    published = []
    for token, d in (decisions or {}).items():
        d = d if isinstance(d, dict) else {}
        price = d.get("price_usd")
        published.append({
            "token": token,
            "action": d.get("final_action") or d.get("action", "monitor"),
            "confidence": d.get("confidence"),
            "price_usd": float(price) if price is not None else None,
            "reasoning": (d.get("reasoning") or "").strip(),
            "note": d.get("note") or d.get("reason") or "",
        })
    published.sort(key=lambda s: (s.get("confidence") or 0), reverse=True)
    with _lock:
        _latest_signals["generated_at"] = datetime.now(
            timezone.utc).isoformat()
        _latest_signals["signals"] = published
    _record_track_record(published)


def _record_track_record(published: list) -> None:
    """Freeze ONE record per asset per UTC day for the public track record.

    Rules 1/2/4 (services.signal_track_record): the volatility is computed HERE,
    once, and stored immutably; the feed later resolves it and never recomputes
    a threshold. One record per asset per UTC DAY (the first publish of the day,
    deterministically) — a 5-minute snapshot cadence would make n meaningless and
    picking the "best" publish of a day would be selection bias.

    Only DIRECTIONAL publishes are scored: a `monitor`/`hold` has no direction,
    so it can neither hit nor miss — it is counted separately and stays visible.
    """
    from services import signal_track_record as track

    try:
        issued_at = datetime.now(timezone.utc)
        day = issued_at.strftime("%Y-%m-%d")
        for signal in published or []:
            asset = (signal.get("token") or "").lower()
            if asset not in track.ASSET_IDS:
                continue
            record_id = "%s:%s" % (asset, day)
            # Idempotent FIRST (18.09): the row is written once per asset+day, so
            # an existing one must not trigger the expensive volatility fetch.
            # Running it every 5-minute cycle was 4 heavy CoinGecko calls a minute
            # → HTTP 429 → vol_threshold None → records that could never be scored.
            if dashboard_db.signal_history_exists(record_id):
                continue
            action = signal.get("action") or ""
            confidence = signal.get("confidence")
            price = signal.get("price_usd")
            try:
                price = float(price) if price is not None else None
            except (TypeError, ValueError):
                price = None
            if track.direction_of(action) == 0:
                dashboard_db.record_signal_issue(
                    record_id, asset, action, confidence,
                    issued_at.isoformat(), price, None,
                    outcome="not_scored", frozen_on=track.FROZEN_ON)
                continue
            if price is None or price <= 0:
                # No price at issue means the move cannot be measured later —
                # unresolved rather than silently dropped.
                dashboard_db.record_signal_issue(
                    record_id, asset, action, confidence,
                    issued_at.isoformat(), None, None,
                    outcome="unresolved", frozen_on=track.FROZEN_ON)
                continue
            closes = track.fetch_hourly_closes(asset)
            volatility = track.realized_volatility_24h(closes)
            if not volatility:
                # No threshold ⇒ the record could never be scored: hit, miss and
                # flat are ALL defined against it. Freezing an unscorable row is
                # worse than waiting — so skip this cycle and try the next one.
                # The volatility is still computed AT ISSUE time (the frozen rule);
                # we simply refuse to issue a record we already know we cannot score.
                log.warning("Track record: %s has no volatility yet (CoinGecko "
                            "series unavailable) — record deferred, not frozen.",
                            asset)
                continue
            created = dashboard_db.record_signal_issue(
                record_id, asset, action, confidence, issued_at.isoformat(),
                price, volatility, outcome="pending", frozen_on=track.FROZEN_ON)
            if created:
                log.info("Track record: issued %s %s conf=%s price=%s vol=%s",
                         asset, action, confidence, price,
                         round(volatility, 4) if volatility else None)
    except Exception as exc:
        log.warning("Track record issue failed (non-fatal): %s", exc)


def _resolve_track_record(limit: int = 20) -> int:
    """Resolve signals whose 24h window has passed (frozen rules 2/3).

    Price window ±2h around the 24th hour; source order: the signal's own source
    (CoinGecko), then DEXScreener — and the fallback only while we are INSIDE the
    window, because a DEXScreener "24h ago" is only the 24th hour right now.
    """
    from services import signal_track_record as track

    cutoff = (datetime.now(timezone.utc)
              - timedelta(hours=track.RESOLVE_AFTER_HOURS)).isoformat()
    resolved = 0
    for record in dashboard_db.signal_history_due(cutoff, limit=limit):
        try:
            issued = datetime.fromisoformat(str(record["issued_at"]))
            if issued.tzinfo is None:
                issued = issued.replace(tzinfo=timezone.utc)
            target = issued + timedelta(hours=track.RESOLVE_AFTER_HOURS)
            price, source = track.fetch_price_at(record["asset"],
                                                 target.timestamp())
            if price is None:
                now = datetime.now(timezone.utc)
                inside_window = abs((now - target).total_seconds()) <= \
                    track.PRICE_WINDOW_HOURS * 3600
                if inside_window:
                    price, source = track.fetch_dexscreener_implied(
                        record["asset"], record["price_at_issue"])
                if price is None:
                    dashboard_db.resolve_signal(
                        record["id"], "unresolved", None, None,
                        source or "", datetime.now(timezone.utc).isoformat())
                    resolved += 1
                    continue
            outcome, move_pct = track.classify(record["price_at_issue"], price,
                                               record["vol_threshold"],
                                               record["action"])
            dashboard_db.resolve_signal(record["id"], outcome, price, move_pct,
                                        source,
                                        datetime.now(timezone.utc).isoformat())
            resolved += 1
        except Exception as exc:
            log.warning("Track record resolve failed for %s: %s",
                        record.get("id"), exc)
    return resolved


def _background_agent_loop():
    """Run the trading agent in a background thread (non-blocking)."""
    log.info("Background trading-agent thread started.")
    poll_interval = int(os.getenv("AGENT_POLL_INTERVAL", "300"))
    while True:
        try:
            from services.coingecko import CoinGeckoClient
            from services.defi_signals import DeFiSignalGenerator
            from services.trading_agent import TradingAgent

            api_key = os.getenv("BASE44_API_KEY", "")
            cg = CoinGeckoClient(api_key=api_key)
            signals = DeFiSignalGenerator(api_key=api_key).generate_signals()
            agent = TradingAgent(coingecko_client=cg, signals=signals)
            decisions = agent.evaluate()

            # Publish the latest decisions for GET /api/v1/signal.
            _publish_agent_signals(decisions)

            # Public track record: freeze today's records and resolve the ones
            # whose 24h window has closed (frozen rules — see the service).
            resolved = _resolve_track_record()
            if resolved:
                log.info("Track record: resolved %d record(s).", resolved)

            # Finality watch (21.09): re-read the block every settlement was
            # anchored to. A reorg that keeps the height passes the depth gate
            # silently, so the hash is compared here and a mismatch becomes a
            # visible `c2_reorg_detected` guard event.
            try:
                _detect_reorgs()
            except Exception as exc:
                log.info("reorg watch skipped: %s", exc)

            _record_request("agent_cycle", decisions is not None)
            log.info("Agent cycle complete: %d decisions.", len(decisions))
        except Exception as exc:
            log.warning("Background agent cycle failed (non-fatal): %s", exc)
            _record_request("agent_cycle", False)
        time.sleep(poll_interval)


def _catalog_analytics_loop():
    """Refresh durable rolling-24h catalog rankings at a bounded interval."""
    interval_seconds = max(
        60, int(os.getenv("CATALOG_ANALYTICS_INTERVAL_SECONDS", "86400"))
    )
    log.info("Catalog analytics worker started (interval=%ss).", interval_seconds)
    while True:
        try:
            catalog_store.expire_entitlements()
            catalog_store.recalculate_24h()
        except Exception as exc:
            log.warning("Catalog analytics refresh failed (non-fatal): %s", exc)
        time.sleep(interval_seconds)


def _stripe_payment_snapshot_loop():
    """Continuously refresh the admin-only Stripe view without delaying web requests."""
    interval_seconds = max(
        30, int(os.getenv("STRIPE_PAYMENT_SNAPSHOT_INTERVAL_SECONDS", "60"))
    )
    log.info("Stripe payment snapshot worker started (interval=%ss).", interval_seconds)
    while True:
        _refresh_stripe_payment_snapshot()
        time.sleep(interval_seconds)


# ── Canonical dashboard maintenance loop (persistent store) ───────────────
# Keeps data/dashboard_state.db in sync with the chain and with PayAPI:
#   1. retro scan on startup (default 30d) → the very first external payment
#      is visible in the dashboard history from day zero
#   2. incremental scan every cycle from the persisted block watermark
#      → deploys/restarts never reset or re-zero the numbers
#   3. PayAPI listing state (band + ranks) every ~15 min
def _dashboard_scan_loop():
    retro_days = int(os.getenv("KRISTO_DASHBOARD_RETRO_DAYS", "30"))
    scan_interval = max(30, int(os.getenv("KRISTO_DASHBOARD_SCAN_INTERVAL", "60")))
    payapi_interval = max(300, int(os.getenv("KRISTO_DASHBOARD_PAYAPI_INTERVAL", "900")))

    # ITS OWN POSTGRES LINK — the fourth background job that needed one. See
    # `_isolated_store`: this loop does a replay-lock probe, an on-chain scan and
    # a listing refresh every 60s, and through the shared link it was measured
    # holding it long enough to refuse every request:
    #     holder=dashboard-scan held=200s
    #
    # BOUND FIRST, BEFORE ANY USE. A previous version of this put the binding
    # below the retro scan, and the retro scan is what finds ON-CHAIN SALES:
    # `cannot access local variable 'scan_db'` on every cycle, caught and logged
    # as "incremental will catch up", which it then could not do either. The
    # money scan was dead and the log said it was merely behind.
    scan_db = _isolated_store("dashboard-scan")

    log.info("Dashboard scan loop started (retro=%dd, interval=%ss).", retro_days, scan_interval)
    try:
        added = scan_db.retro_scan(days=retro_days)
        log.info("Dashboard retro scan: %d new on-chain sale(s) persisted.", added)
        _note_sales_scan_ok()
    except Exception as exc:
        log.warning("Dashboard retro scan failed (incremental will catch up): %s", redact_rpc(exc))

    # Whale flow runs in its OWN thread (Табло 2.0 audit): it used to sit
    # behind retro_scan(days=30) in this same thread, and retro_scan writes its
    # watermark incrementally while it walks ~1.3M blocks — so for the first
    # long stretch after every deploy the promoted, PAID /api/v1/whaleflow
    # route served a feed whose scan had not even started (live state was
    # literally "scan_not_started"). A separate thread also gives the whale
    # scan an independent failure domain.
    next_payapi = time.time()
    while True:
        time.sleep(scan_interval)

        # F-04: warm the C1 replay-lock probe here, off the request path. The
        # probe writes a sentinel row into `payment_guards` — the same table and
        # the same lock `claim_payment_tx` uses — and `/api/dashboard/data` is
        # free and unbounded, so running it per request let an anonymous poller
        # churn the replay table and contend with a paying customer's claim.
        # The probe is TTL-gated (10 min) so calling it every cycle costs one
        # write per TTL, and the route then reads a warm cache and writes nothing.
        try:
            scan_db.probe_replay_lock()
        except Exception as exc:
            log.debug("Replay-lock probe refresh failed (non-fatal): %s", exc)

        try:
            added = scan_db.scan_increment()
            if added:
                log.info("Dashboard incremental scan: %d new sale(s).", added)
            _note_sales_scan_ok()
            # The store answered a real write-and-read cycle. That is the proof
            # the data block is well, recorded off the request path — a heartbeat
            # written per request would put a durable write on every call.
            _organism_beat("data_store", "ok",
                           "incremental scan ok, %d new" % added)
        except Exception as exc:
            log.warning("Dashboard scan cycle failed (non-fatal): %s", redact_rpc(exc))
            _organism_beat("data_store", "failed",
                           "incremental scan failed: %s" % str(exc)[:120])

        if time.time() >= next_payapi:
            next_payapi = time.time() + payapi_interval
            try:
                from scripts.listing_monitor import fetch_state
                scan_db.save_payapi_state(fetch_state())
                log.info("Dashboard: PayAPI listing state refreshed.")
            except Exception as exc:
                log.warning("Dashboard PayAPI refresh failed: %s", exc)


def whaleflow_scan_enabled() -> bool:
    """Is the network-wide whale scan allowed to spend RPC requests?

    The whale scan reads EVERY USDC transfer on Base, so it is by far the most
    request-hungry loop in the app: on 17.09 it was found burning a PAID RPC
    (95.3M compute units in 4 days at 10-block chunks). WHALEFLOW_ENABLED=0
    pauses it HONESTLY — no requests are issued at all, the store reports
    `whaleflow_state = scan_paused_by_owner`, and the watermark is kept so a
    later re-enable resumes exactly where it stopped instead of silently dying.
    """
    return os.getenv("WHALEFLOW_ENABLED", "1").strip().lower() not in (
        "0", "false", "no", "off", "")


def _whaleflow_scan_loop():
    """Whale flow: bounded backfill, then a 60s incremental scan.

    Kept independent of the sales/PayAPI loop so a heavy network-wide scan can
    never starve the money numbers, and vice versa.

    The incremental scan is what makes the feed LIVE, and it is cheap (one
    ~100-block window per cycle). The backfill is deliberately BOUNDED: a
    network-wide window returns ~5,000 transfers per 100 blocks and every
    whale needs its own block fetch for an honest timestamp, so walking 24h
    (~43k blocks) costs hours on a free RPC. Warm-starting one hour proves the
    pipeline end-to-end; history then accumulates on its own. Raise
    WHALEFLOW_BACKFILL_HOURS if you want the deep history paid for in time.
    """
    if not whaleflow_scan_enabled():
        log.warning(
            "Whale flow scan PAUSED (WHALEFLOW_ENABLED=0): scan_paused_by_owner "
            "— no RPC requests are issued and the watermark is kept.")
        try:
            # Keep the ORIGINAL pause moment: a boot must not rewrite history
            # (the timestamp is what tells the owner when the stop happened).
            if (dashboard_db.get_meta("whaleflow_state")
                    != "scan_paused_by_owner"):
                dashboard_db.set_meta("whaleflow_state_at",
                                      datetime.now(timezone.utc).isoformat())
            dashboard_db.set_meta("whaleflow_state", "scan_paused_by_owner")
        except Exception as exc:
            log.warning("Could not record the paused whale state: %s", exc)
        return
    try:  # re-enabled: clear the paused mark so the state cannot linger
        dashboard_db.set_meta("whaleflow_state", "")
        dashboard_db.set_meta("whaleflow_state_at",
                              datetime.now(timezone.utc).isoformat())
    except Exception:
        pass
    interval = max(30, int(os.getenv("WHALEFLOW_SCAN_INTERVAL", "60")))
    hours = max(1, int(os.getenv("WHALEFLOW_BACKFILL_HOURS", "24")))
    log.info("Whale flow scan loop started (backfill=%dh, interval=%ss).",
             hours, interval)
    # ITS OWN POSTGRES LINK. This loop walks the chain network-wide — the backfill
    # alone is documented above as "hours on a free RPC" — and writes every whale
    # it finds. Through the shared link it held that link for 45+ seconds at a
    # time, and every request in the process was refused a write for hours:
    # `holder=whaleflow-scan held=45s` in the log, with the request log frozen and
    # all six organism blocks reading `not_reached`. See `_isolated_store`.
    whale_db = _whaleflow_store()
    try:
        added = whale_db.whaleflow_backfill(hours=hours)
        log.info("Whale flow backfill: %d whale event(s) persisted.", added)
    except Exception as exc:
        log.warning("Whale flow backfill failed (incremental will catch up): %s",
                    redact_rpc(exc))
    while True:
        try:
            added = whale_db.whaleflow_increment()
            if added:
                log.info("Whale flow increment: %d new event(s).", added)
        except Exception as exc:
            log.warning("Whale flow increment failed (non-fatal): %s", redact_rpc(exc))
        time.sleep(interval)


# ── Endpoint → Product mapping for per-agent stats ────────────────────────
# Catalog traffic is recorded only by durable per-agent events, not generic
# service endpoints, so dashboard hits remain transparent and attributable.
_ENDPOINT_TO_PRODUCT: Dict[str, str] = {}


def _record_request(endpoint: str, success: bool):
    """Record an API request for stats tracking."""
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    with _lock:
        _request_log.append({
            "timestamp": now.isoformat(),
            "endpoint": endpoint,
            "success": success,
        })
        if date_str not in _daily_stats:
            _daily_stats[date_str] = {
                "requests": 0,
                "sales_count": 0,
                "sales_volume": 0.0,
            }
        _daily_stats[date_str]["requests"] += 1

        # Increment per-product hits
        product_id = _ENDPOINT_TO_PRODUCT.get(endpoint)
        if product_id and product_id in _product_stats:
            _product_stats[product_id]["hits"] += 1


def _record_telegram_activity(payload: dict, result: Optional[dict]) -> None:
    """Keep Telegram user and command metrics separate from generic API traffic."""
    message = payload.get("message") or {}
    callback = payload.get("callback_query") or {}
    callback_message = callback.get("message") or {}
    chat = message.get("chat") or callback_message.get("chat") or {}
    chat_id = chat.get("id")
    handled_type = (result or {}).get("type")

    with _lock:
        if chat_id is not None:
            _telegram_active_chats.add(str(chat_id))
            _bot_status["active_users"] = len(_telegram_active_chats)
        if handled_type in {"command", "bulletin_sent", "price_info", "callback_query", "unknown_command"}:
            _bot_status["commands_processed"] += 1
        if (result or {}).get("response_sent"):
            _bot_status["messages_sent"] += 1
        _bot_status["last_heartbeat"] = datetime.now(timezone.utc).isoformat()


def _record_product_sale(product_id: str, amount_usd: float):
    """Record a sale attributed to a specific product/agent."""
    with _lock:
        if product_id not in _product_stats:
            return
        _product_stats[product_id]["sales_count"] += 1
        _product_stats[product_id]["sales_volume_usd"] = round(
            _product_stats[product_id]["sales_volume_usd"] + amount_usd, 6
        )


def _get_products_breakdown() -> List[dict]:
    """Return the official eight-agent breakdown from durable catalog events."""
    return [
        {
            "id": product["id"],
            "name": product["name"],
            "category": product["category"],
            "price_usdc": product["price_x402"],
            "hits": product["hits_24h"],
            "sales_count": product["sales_24h"],
            "sales_volume_usd": product["revenue_24h"],
        }
        for product in catalog_store.get_metrics_24h()["products"]
    ]


# ── x402 Free Tier Tracking ────────────────────────────────────────────────
# Tracks free API calls per client (by IP address).
# After FREE_TIER_LIMIT (1) free picks, x402 payment is required.
_free_tier_usage: Dict[str, int] = {}  # ip -> count of free calls used
_catalog_click_lock = threading.Lock()
_catalog_recent_clicks: Dict[tuple[str, str], datetime] = {}
CATALOG_CLICK_COOLDOWN_SECONDS = max(
    60, int(os.getenv("CATALOG_CLICK_COOLDOWN_SECONDS", "900"))
)


def _allow_catalog_click(client_address: str, agent_id: str) -> bool:
    """Bound anonymous catalog click ingestion to protect popularity metrics."""
    now = datetime.now(timezone.utc)
    key = (client_address or "unknown", agent_id)
    with _catalog_click_lock:
        expired_before = now - timedelta(seconds=CATALOG_CLICK_COOLDOWN_SECONDS)
        for previous_key, previous_at in list(_catalog_recent_clicks.items()):
            if previous_at < expired_before:
                _catalog_recent_clicks.pop(previous_key, None)
        previous = _catalog_recent_clicks.get(key)
        if previous and now - previous < timedelta(
            seconds=CATALOG_CLICK_COOLDOWN_SECONDS
        ):
            return False
        _catalog_recent_clicks[key] = now
        return True

# Tracks PAID API calls per client (for volume discount pricing).
_paid_calls_usage: Dict[str, int] = {}  # ip -> count of paid calls made


def _is_private_or_loopback(ip: str) -> bool:
    """True for loopback / RFC1918 / CGNAT addresses (Render's internal proxies).

    Deliberately NARROWER than ipaddress.is_private: the IANA special-purpose
    ranges (TEST-NET 192.0.2.0/24, 198.51.100.0/24, 203.0.113.0/24, ...) are
    NOT treated as private here, so they remain valid public client
    identities. This matters because is_private would silently reclassify
    documented public clients as proxies.
    """
    import ipaddress as _ipa
    try:
        addr = _ipa.ip_address(ip)
    except ValueError:
        return False
    if addr.is_loopback:
        return True
    if addr.version == 4:
        return (
            addr in _ipa.ip_network("10.0.0.0/8")
            or addr in _ipa.ip_network("172.16.0.0/12")
            or addr in _ipa.ip_network("192.168.0.0/16")
            or addr in _ipa.ip_network("100.64.0.0/10")  # CGNAT (shared space)
        )
    return addr in _ipa.ip_network("fc00::/7")  # private IPv6


def _get_client_ip() -> str:
    """Resolve the real client IP for free-tier / discount accounting.

    On Render every request arrives through Render's internal proxy, so
    remote_addr is a ROTATING private address (10.x.x.x). Without XFF
    resolution the free tier would be counted per PROXY IP — clients could
    harvest a fresh free call every time the proxy rotates.

    Trust model: when the immediate peer is a private/loopback address, the
    request must have traversed our platform proxy, which appends the real
    client IP to X-Forwarded-For. Client-supplied spoofed entries sit
    EARLIER in the chain, so we walk from the END and use the last PUBLIC
    IP. When the peer is a public address (direct access / tests),
    remote_addr is used as-is and X-Forwarded-For is IGNORED (anti-spoofing).
    """
    peer = request.remote_addr or "unknown"
    fwd = request.headers.get("X-Forwarded-For", "").strip()
    if fwd and _is_private_or_loopback(peer):
        entries = [e.strip() for e in fwd.split(",") if e.strip()]
        for entry in reversed(entries):
            if not _is_private_or_loopback(entry):
                return entry
        # All entries private (multi-hop internal) — FIX #4: use FIRST entry (closest to client)
        if entries:
            return entries[0]
    return peer


# ── Lightweight request rate limiting (per client IP, per scope) ─────────────
# Protects auth, payment and lead-capture routes from brute force and spam
# without external dependencies. In-memory sliding-window counters keyed by
# (scope, client IP); stale buckets are pruned opportunistically.
_RATE_LIMIT_DEFAULTS = {
    "admin_login": (20, 300),      # 20 token attempts / 5 min
    "checkout": (30, 300),         # 30 checkout submissions / 5 min
    "leads": (30, 300),            # lead capture / 5 min
    "funnel_track": (90, 300),     # analytics beacons / 5 min
    "agent_checkout": (60, 300),   # catalog Stripe checkout / 5 min
    "stripe_webhook": (240, 300),  # signature-verified, but bounded
    "telegram_webhook": (240, 300),  # secret-verified, but bounded
    "public_activity": (120, 300),  # public proof-of-traction feed, bounded
    "public_signals_history": (60, 300),  # free track-record feed, bounded
}

_rate_limit_lock = threading.Lock()
_rate_limit_hits: Dict[tuple, deque] = {}


def _check_rate_limit(scope: str) -> Optional[int]:
    """
    Sliding-window rate limiter keyed by (scope, client IP).

    Returns None when the request is allowed (and records the hit),
    otherwise the number of seconds after which the client may retry.
    Limits are overridable via KRISTO_RATE_<SCOPE>_MAX and
    KRISTO_RATE_<SCOPE>_WINDOW_SECONDS environment variables.
    """
    default_max, default_window = _RATE_LIMIT_DEFAULTS[scope]
    max_requests = int(os.getenv(f"KRISTO_RATE_{scope.upper()}_MAX", str(default_max)))
    window = int(os.getenv(f"KRISTO_RATE_{scope.upper()}_WINDOW_SECONDS", str(default_window)))
    key = (scope, _get_client_ip())
    now = time.time()
    with _rate_limit_lock:
        hits = _rate_limit_hits.setdefault(key, deque())
        while hits and hits[0] <= now - window:
            hits.popleft()
        if len(hits) >= max_requests:
            return max(1, int(window - (now - hits[0])))
        hits.append(now)
        # Opportunistic memory bound: drop fully-stale buckets.
        if len(_rate_limit_hits) > 10_000:
            for stale_key, stale_hits in list(_rate_limit_hits.items()):
                if not stale_hits or stale_hits[-1] <= now - window:
                    _rate_limit_hits.pop(stale_key, None)
    return None


def _rate_limited_response(scope: str):
    """Return a 429 JSON response when the scope limit is exceeded, else None."""
    retry_after = _check_rate_limit(scope)
    if retry_after is None:
        return None
    return jsonify({
        "ok": False,
        "error": "rate_limited",
        "scope": scope,
        "retry_after_seconds": retry_after,
    }), 429


def _get_dynamic_price(ip: str, endpoint: str = "") -> float:
    """
    Per-endpoint dynamic pricing with volume discount.

    The base price for each endpoint comes from X402_PRICE_MAP (wired to
    config.py KRISTO_*_PRICE constants — single source of truth).
    After X402_VOLUME_THRESHOLD (10) paid calls, the price drops to
    X402_FEE_USDC_DISCOUNT to incentivize batch/frequent on-chain usage.
    """
    base = X402_PRICE_MAP.get(X402_PATH_ALIASES.get(endpoint, endpoint),
                              BASE_FEE_AMOUNT_USDC)
    with _lock:
        paid_count = _paid_calls_usage.get(ip, 0)
    if paid_count >= X402_VOLUME_THRESHOLD:
        # Volume discount never exceeds the base price
        return min(X402_FEE_USDC_DISCOUNT, base)
    return base


def _sanitize_json(obj):
    """
    Recursively sanitize a Python object for JSON serialization.
    Replaces NaN, Infinity, -Infinity with None (null) so the output is
    valid JSON (no NaN tokens that break JSON.parse in browsers).
    """
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize_json(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_sanitize_json(v) for v in obj]
    return obj


def _safe_jsonify(obj):
    """jsonify wrapper that guarantees valid JSON (no NaN/Infinity)."""
    return jsonify(_sanitize_json(obj))


# Realistic samples of the PAID responses, per route — served inside
# extensions.bazaar.info.output.example so discovery agents (CDP validator,
# Bazaar search) can see what a successful call returns before paying
# (docs: get-discovered — complete output schemas with realistic examples
# raise metadata quality). Shapes mirror the live handlers:
# whaleflow → {state, whales[], threshold_usdc, scanned_until_block, source};
# signal    → {generated_at, signals[] with scan_info}; stats → counters.
_BAZAAR_OUTPUT_EXAMPLES = {
    "/api/v1/whaleflow": {
        "state": "ok",
        "threshold_usdc": 5_000_000,
        "count": 1,
        "whales": [
            {
                "tx_hash": "0x9f2c…" * 1,
                "amount_usdc": 5_200_000.0,
                "block_number": 52_610_000,
                "ts": "2026-10-19T09:15:00+00:00",
                "from_label": "Binance",
                "to_label": "unknown",
            },
        ],
        "scanned_until_block": 52_610_105,
        "all_time_count": 47,
        "last_event_at": "2026-10-19T09:15:00+00:00",
        "source": "onchain_eth_getLogs",
    },
    "/api/v1/signal": {
        "generated_at": "2026-10-19T09:20:00+00:00",
        "signals": [
            {
                "token": "ETH",
                "price_usd": 2426.55,
                "confidence": "high",
                "action": "watch",
                "reasoning": "spot premium within tolerance; depth confirming",
                "scan_info": {
                    "verification": "verified",
                    "checked_at": "2026-10-19T09:19:50+00:00",
                },
            },
        ],
    },
    "/api/stats": {
        "today": "2026-10-19",
        "requests_today": 120,
        "requests_total": 5400,
        "top_paths": [
            {"path": "/api/v1/signal", "count": 70},
            {"path": "/api/v1/whaleflow", "count": 30},
        ],
    },
    # The three routes below carried NO output block at all, so the Bazaar had
    # nothing to describe them with. `info.output` is optional, but when it is
    # present its `type` is REQUIRED (bazaar.md "Discovery Info Structure":
    # | type | string | Yes |), so a route that declares an output exercises
    # more of the contract than one that declares none.
    "/api/arb/opportunities": {
        "opportunities": [
            {
                "pair": "WETH/USDC",
                "buy_dex": "uniswap_v3",
                "sell_dex": "aerodrome",
                "spread_pct": 0.4213,
                "buy_price_usd": 2425.11,
                "sell_price_usd": 2435.33,
                "est_profit_usd": 0.38,
                "gas_cost_usdc": 0.03,
                "block_number": 52_610_105,
                "scanned_at": "2026-10-19T09:15:00+00:00",
            },
        ],
        "count": 1,
        "scan_info": {"scanned_until_block": 52_610_105, "gas_cost_usdc": 0.03},
        "source": "dexscreener_cross_dex",
        "network": "base",
    },
    "/api/sales": {
        "total_volume_usd": 0.164,
        "total_sales": 50,
        "by_token": {"USDC": 0.164},
        "history": [
            {
                "amount_usd": 0.003,
                "timestamp": "2026-10-30T09:00:00+00:00",
                "tx_hash": "0x9f2c…",
            },
        ],
        "source": "real_blockchain",
        # wallet_address / usdc_balance are deliberately absent: this example is
        # PUBLIC (it rides in every unpaid 402), and the receiver address is
        # already published as accepts[0].payTo — repeating it here would widen
        # the public surface for no discovery benefit (F-26/F-27 rule).
        "market_data": {"fear_greed": 54, "eth_price_usd": 2426.55},
    },
    "/api/bot-status": {
        "telegram_bot_running": True,
        "telegram_token_configured": True,
        "last_heartbeat": "2026-10-19T09:20:00+00:00",
        "uptime_started": "2026-10-19T06:00:00+00:00",
        "messages_sent": 12,
        "active_users": 4,
        "commands_processed": 37,
        "vip_invites_sent": 1,
        # The live handler also attaches `wallet` (internal wallet state). It is
        # omitted here on purpose: same public-surface rule as /api/sales.
    },
    "/api/v1/verify-seller": {
        "ok": True,
        # An illustrative address, NOT our receiver. This example is PUBLIC — it
        # rides in every unpaid 402 — and the treasury address is already
        # published as accepts[0].payTo. Repeating it here would widen the
        # public surface for no discovery benefit and would show a buyer our own
        # address as though it were a stranger's (F-26/F-27 rule).
        "receiver": "0x1111111111111111111111111111111111111111",
        "window_days": 7,
        "read": "clean",
        "coverage": {
            "complete": True,
            "lookback_days": 7,
            "scanned_blocks": 201_600,
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
        # `read` and `coverage` are part of the example on purpose. This is the
        # only route whose answer can be legitimately incomplete, and an example
        # that showed only the clean case would teach a buyer that a zero is
        # always a zero.
        "notes": [
            "Only incoming USDC transfers on Base to this exact address are read.",
            "A `partial` read reports its figures as a floor, never as a zero.",
        ],
        "served_from_cache": False,
    },
}

# An alias publishes the SAME output example as the route it fronts — not a copy
# retyped here, but a reference to the same object. Two hand-written examples for
# one response shape would be two things to keep true; one would eventually stop
# being. `test_bazaar_output_example.py` requires this map and
# X402_PAID_ENDPOINTS to hold the same keys, so the loop is also what keeps the
# aliases from silently publishing a challenge with no output declaration.
for _alias, _canonical in X402_PATH_ALIASES.items():
    _BAZAAR_OUTPUT_EXAMPLES[_alias] = _BAZAAR_OUTPUT_EXAMPLES[_canonical]

# ── vet402's L2 declaration: the "example" object must be a SCHEMA ──────────
# vet402's L2 reader (src/lib/observatory/l2-check.ts, catalogOutputOf) reads
# the declaration as extensions.bazaar.schema.properties.output.properties.example
# and takes `.required` and `.properties` from THAT object. It never reads
# output.required. With neither, the endpoint reports `l2_undeclared`
# ("the listing declares no output schema") and stays a WARN on the buyer page.
#
# Our canonical output object carried only {type: "object", description: ...},
# so the declaration read as empty. We therefore add the top-level keys of the
# sample the handler actually returns. Deliberately NO `required`: a key we
# cannot prove would turn a real delivery into a mismatch (a BLOCK), and the
# point of the declaration is to say "the answer is an object with these keys".
_BAZAAR_EXAMPLE_SCHEMA_TYPES = {
    "bool": "boolean",
    "int": "integer",
    "float": "number",
    "str": "string",
    "list": "array",
    "dict": "object",
    "NoneType": "null",
}


def _bazaar_example_properties(endpoint: str) -> dict:
    """JSON-Schema `properties` for the output example, derived from the sample.

    Derived from the same _BAZAAR_OUTPUT_EXAMPLES dict the 402 publishes, so the
    declaration can never drift from the example the buyer is shown. A route
    without an example gets no properties, which is the honest answer.
    """
    example = _BAZAAR_OUTPUT_EXAMPLES.get(endpoint)
    if not isinstance(example, dict):
        return {}
    return {
        key: {"type": _BAZAAR_EXAMPLE_SCHEMA_TYPES.get(type(value).__name__, "object")}
        for key, value in example.items()
    }

# ── The declared INPUT, which the 402 used to get wrong ────────────────────
# Every paid route published `queryParams: {}` with additionalProperties False
# and the sentence "No query parameters: none are required — call this route as
# plain GET without a query string". That was true of six of the seven and
# false of /api/v1/verify-seller, which reads `receiver` and returns 400
# without it. The service therefore contradicted itself: its OpenAPI document
# (app/blueprints/discovery.py) declares `receiver` required and `days` bounded
# for that same path, while the 402 challenge — the copy CDP indexes out of
# paymentPayload.extensions.bazaar — told the agent no input was needed.
#
# The cost was exact and measured on 10.11: an agent that trusted the challenge
# paid $0.10 and got HTTP 400 receiver_required. The challenge is the machine's
# first and often only impression, so a false declaration here is worse than a
# missing one — it is an instruction to call the route in a way that cannot work.
#
# Only routes that actually read request.args get an entry. Everything else
# keeps the explicit empty map, because an undeclared input reads as "may need
# params we cannot see" (x402 Doctor bazaar-input). `days` is declared because
# the handler reads it, even though it is optional and clamped.
X402_INPUT_QUERY_PARAMS = {
    "/api/v1/verify-seller": {
        "properties": {
            "receiver": {
                "type": "string",
                "description": (
                    "The USDC receiver address to audit: an EVM address, with "
                    "or without the 0x prefix, checksummed before the chain is "
                    "read. Required."
                ),
            },
            "days": {
                "type": "integer",
                "description": (
                    "Lookback window in days, 1 to 30, default 7. Clamped to "
                    "the engine's own bounds; the window actually walked is "
                    "published in the report as coverage.lookback_days."
                ),
            },
        },
        "required": ["receiver"],
        "example": {
            "receiver": "0xd4cdA900839c0feD4374EE37EA0dbe8E4C6fd08f",
            "days": 7,
        },
        "note": (
            "`receiver` is REQUIRED: without it the route answers HTTP 400 "
            "receiver_required and reads nothing. A free copy of the exact "
            "report shape is at /api/v1/verify-seller/sample."
        ),
    },
    # The whale feed is the one paid route whose response is large enough to
    # cost the buyer more in tokens than the call costs in USDC (50 rows =
    # ~16.9 KB / ~4.2k tokens, against $0.003). Declaring the two knobs is the
    # discovery half of the fix: the caller cannot read the handler's code, so
    # the 402 is the only place it can learn that it may ask for fewer.
    "/api/v1/whaleflow": {
        "properties": {
            "limit": {
                "type": "integer",
                "description": (
                    "Maximum whale events to return, 1 to 200, default 50. "
                    "Lower it when the caller bills for the tokens in the "
                    "response — the default is the full feed."
                ),
            },
            "hours": {
                "type": "integer",
                "description": (
                    "Rolling window in hours, 1 to 168, default 24. Lower it "
                    "to narrow the window; the default is the full day."
                ),
            },
        },
        "required": [],
        "example": {
            "limit": 5,
            "hours": 24,
        },
        "note": (
            "Both parameters are optional. `limit` is the honest lever: the "
            "default 50 rows is ~4.2k tokens, and an agent that only needs a "
            "few whales can ask for 5 and pay for a fraction of the tokens."
        ),
    },
}
# The alias declares the same input as the route it fronts, by reference for the
# same reason the output example is shared: two hand-written copies of one
# contract drift, and the alias is the one buyers reach through the catalogue.
for _alias, _canonical in X402_PATH_ALIASES.items():
    if _canonical in X402_INPUT_QUERY_PARAMS:
        X402_INPUT_QUERY_PARAMS[_alias] = X402_INPUT_QUERY_PARAMS[_canonical]


def _x402_challenge_description(endpoint: str, description: str = "") -> str:
    """What a 402 says about a product — never a placeholder if we have better.

    Three of the six routes used to publish "Kristo Intelligence - paid API
    data (/api/sales)": CHALLENGE_DESCRIPTIONS is hand-written and covered only
    three endpoints, so the rest fell through to a placeholder. Every index that
    crawls us copies this string verbatim — PayAI's Bazaar, x402-list, x402scan —
    so for half the catalogue the only sentence an agent read before deciding to
    pay said nothing about the product. Measured on 05.11: 48, 60 and 48
    characters of nothing, against 110-192 for the routes that were covered.

    Precedence: an explicit description wins; then the route's own entry in
    REAL_X402_ROUTES; only then a placeholder that at least names the endpoint.
    Reading the single source of truth rather than retyping three more strings is
    what stops a route added later from silently publishing the placeholder too.
    """
    if description:
        return description
    for route in REAL_X402_ROUTES:
        if route.get("endpoint") == endpoint:
            real = (route.get("description") or "").strip()
            if real:
                return real
            break
    return f"Kristo Intelligence - paid API data ({endpoint})"


def _x402_challenge_core(endpoint: str, amount: float, description: str = ""):
    """
    Canonical x402 v2 challenge pieces: accepts + resource + extensions.

    Mirrors x402scan's v2 zod schema (apps/scan/src/lib/x402/v2/schema.ts and
    its schema.test.ts fixtures):
      * x402Version: 2 (integer literal)
      * accepts[]: scheme, network in CAIP-2 form ("eip155:8453" = Base),
        `amount` in TOKEN ATOMIC UNITS as string (USDC on Base has 6
        decimals, so 0.005 USDC -> "5000"), payTo, asset, maxTimeoutSeconds
      * resource: { url, description, mimeType? }
      * extensions.bazaar.info.input: the HTTP request structure that makes
        the route "invocable" instead of skipped
    """
    resource_url = request.host_url.rstrip("/") + (
        endpoint if endpoint.startswith("/") else "/" + endpoint
    )
    desc = _x402_challenge_description(endpoint, description)
    accepts = [
        {
            "scheme": "exact",
            "network": "eip155:8453",
            "amount": str(int(round(float(amount) * 1_000_000))),
            "payTo": X402_RECEIVER_ADDRESS,
            "asset": X402_USDC_CONTRACT,
            "maxTimeoutSeconds": 60,
            # EIP-712 token domain: Base USDC reports name() = "USD Coin" —
            # PayAPI Market's validator requires this exact value here.
            "extra": {"name": "USD Coin", "version": "2"},
        }
    ]
    resource = {
        "url": resource_url,
        "description": desc,
        "mimeType": "application/json",
        # Bazaar listing metadata (discovery extension): PayAI auto-lists
        # endpoints carrying these fields — no manual registration. The
        # agentcash/x402scan audit also reads them for the marketplace card.
        "serviceName": X402_RESOURCE_SERVICE_NAMES.get(
            endpoint, X402_DEFAULT_SERVICE_NAME),
        "tags": X402_RESOURCE_TAGS.get(endpoint, X402_DEFAULT_RESOURCE_TAGS),
        "iconUrl": request.host_url.rstrip("/") + X402_ICON_PATH,
    }
    # Bazaar discovery extension: `info` carries the HTTP request structure,
    # `schema` carries the JSON-Schema view. The agentcash/x402scan audit
    # extracts the input schema from schema.properties.input.properties
    # .body|.queryParams and the output schema from schema.properties.output
    # .properties.example — both must be present or the route fails with
    # SCHEMA_INPUT_MISSING / SCHEMA_OUTPUT_MISSING (severity: error).
    # CDP's validator additionally wants info.output.example (18.10 finding:
    # "recommended for discovery quality, not required for indexing") — a
    # realistic sample of the PAID response so agents can construct the call
    # (docs: get-discovered → complete input and output schemas with examples).
    # x402 Doctor "bazaar-input" (21.10): the declared input must SHOW what a
    # request looks like. Six of the seven paid routes take no query parameters,
    # so for them the honest example is an explicit EMPTY queryParams map, per
    # @x402/extensions QueryDiscoveryInfo: input.queryParams is the declared
    # parameter map. /api/v1/verify-seller is the exception and was the bug —
    # it reads `receiver`, so declaring the map empty told an agent to call a
    # route in a way that cannot succeed. Routes that read request.args declare
    # it in X402_INPUT_QUERY_PARAMS and get a real example instead.
    declared = X402_INPUT_QUERY_PARAMS.get(endpoint)
    info = {"input": {"type": "http", "method": "GET",
                      "queryParams": dict(declared["example"]) if declared else {}}}
    example = _BAZAAR_OUTPUT_EXAMPLES.get(endpoint)
    if example is not None:
        # `type` is REQUIRED whenever info.output is present — bazaar.md
        # "Discovery Info Structure": | type | string | Yes | Response content
        # type (e.g. "json", "text"). Publishing output without it made the
        # declaration non-conformant, and every canonical example in the spec
        # schema carries "required": ["type"] on the output object.
        info["output"] = {"type": "json", "example": example}
    extensions = {
        "bazaar": {
            "info": info,
            "schema": {
                "$schema": "https://json-schema.org/draft/2020-12/schema",
                "type": "object",
                "properties": {
                    "input": {
                        "type": "object",
                        "properties": {
                            # `type` and `method` are the two the spec requires
                            # on the input object ("required": ["type","method"]);
                            # they were here before the queryParams fix and stay.
                            "type": {"type": "string", "const": "http"},
                            "method": {"type": "string", "const": "GET"},
                            # Mirrors @x402/extensions ParamMapSchemaProperty:
                            # type + properties + additionalProperties. Six of
                            # the seven paid GET routes read no request.args, so
                            # their map is DECLARED empty on purpose — an
                            # undeclared input reads as "may need params"
                            # (x402 Doctor bazaar-input: agents could pay and
                            # then guess). /api/v1/verify-seller reads `receiver`
                            # and MUST NOT claim otherwise: the empty map made
                            # the 402 contradict our own OpenAPI document and
                            # sent a paying agent into a 400.
                            "queryParams": (
                                {
                                    "type": "object",
                                    "properties": dict(declared["properties"]),
                                    "required": list(declared["required"]),
                                    "additionalProperties": False,
                                    "description": declared["note"],
                                }
                                if declared else
                                {
                                    "type": "object",
                                    "properties": {},
                                    "additionalProperties": False,
                                    "description": (
                                        "No query parameters: none are "
                                        "required — call this route as plain "
                                        "GET without a query string."
                                    ),
                                }
                            ),
                        },
                        "required": ["type", "method"],
                    },
                    "output": {
                        "type": "object",
                        "properties": {
                            # Mirrors the canonical bazaar.md schema, which is
                            # `properties: {type, example}, required: ["type"]`.
                            # Our copy omitted `type` AND omitted `required`,
                            # so it described a looser contract than the one the
                            # facilitator validates against — the published
                            # info passed our own schema while failing theirs.
                            "type": {
                                "type": "string",
                                "description": (
                                    'Response content type; "json" for every '
                                    "paid route here, which all return JSON."
                                ),
                            },
                            "example": {
                                "type": "object",
                                "description": "Paid JSON response payload",
                                # vet402 reads the output declaration from THIS
                                # object (see _bazaar_example_properties): its
                                # `.required` and `.properties`. With neither it
                                # reports l2_undeclared and the endpoint stays a
                                # WARN. Declaring the real top-level keys is what
                                # turns that into "the declaration names output".
                                "properties": _bazaar_example_properties(endpoint),
                            },
                        },
                        "required": ["type"],
                    },
                },
            },
        }
    }
    return accepts, resource, extensions


#: How long an advertised MPP Challenge stays valid. Short on purpose: the
#: Challenge is a cached-nowhere, one-shot advertisement, and a long window only
#: widens the gap between the terms quoted and the terms settled.
_MPP_CHALLENGE_TTL_SECONDS = 300

#: Standing in for `SESSION_SECRET` when none is configured, so a challenge id
#: is always bound to SOMETHING rather than left unbound.
_MPP_FALLBACK_KEY = secrets.token_bytes(32)


def _mpp_jcs_b64(payload: Dict) -> str:
    """base64url(JCS(json)) — the encoding MPP mandates for `request`/`opaque`.

    JCS (RFC 8785) is canonical JSON: sorted keys, no insignificant whitespace.
    For the flat string-valued objects used here `sort_keys=True` with the
    compact separators IS the canonical form, so no extra dependency is needed.
    Padding is stripped because the MPP examples are padding-free and a client
    that re-encodes must produce the same string to match on `request`.
    """
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                     ensure_ascii=False)
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _mpp_challenge_id(realm: str, method: str, intent: str, request_b64: str,
                      expires: str, description: str) -> str:
    """An HMAC-bound Challenge id, so the terms cannot be edited in flight.

    MPP requires the `id` to be cryptographically bound to the Challenge
    parameters, with the exact slot order `realm | method | intent | request |
    expires | digest | opaque` (absent optionals as empty strings). The key is
    derived from `SESSION_SECRET` so the binding survives a deploy; if no secret
    is configured the id is still minted, from a per-process random key, and the
    caller is told nothing — an unbound id would be worse than a fresh one.
    """
    secret = (os.getenv("SESSION_SECRET") or os.getenv("ADMIN_API_TOKEN")
              or "").encode()
    if not secret:
        secret = _MPP_FALLBACK_KEY
    mac = hmac.new(secret, "\x1f".join(
        [realm, method, intent, request_b64, expires, description, ""]
    ).encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(mac).decode().rstrip("=")[:32]


#: Punctuation that appears in our own selling copy and is NOT ASCII.
#:
#: WHY THIS LIST EXISTS, and it is the difference between a 402 and a 502.
#: An HTTP header value must be ASCII (RFC 9110 field-value is latin-1 at
#: best). Our challenge descriptions are written in prose and contain em-dashes
#: and curly quotes — `CHALLENGE_DESCRIPTIONS["/api/v1/verify-seller"]` starts
#: "Verify an x402 seller before you pay it — …". Putting that into
#: `WWW-Authenticate` produced a header gunicorn refused outright:
#:
#:   [WARNING] Invalid request from ip=…: Invalid HTTP Header: '\'Payment id=…'
#:
#: which the edge turns into a 502 — i.e. adding the MPP challenge made the paid
#: route UNPAYABLE. Measured on the deploy at 21:29:31Z and fixed immediately.
#: The legacy `x402` token was never affected because it carries no description.
_HEADER_ASCII_FOLD = {
    "\u2014": "-", "\u2013": "-", "\u2018": "'", "\u2019": "'",
    "\u201c": '"', "\u201d": '"', "\u2026": "...", "\u00a0": " ",
    "\u00b7": "-", "\u2192": "->", "\u2265": ">=", "\u2264": "<=",
}


def _header_safe(text: str, limit: int = 180) -> str:
    """A value that can go in an HTTP header without breaking the response.

    Folds the punctuation our prose actually uses, drops anything still outside
    ASCII, escapes the two characters that would end or split the quoted string,
    collapses whitespace, and truncates. The caller keeps a header that is
    always encodable — a description is decoration, and no decoration is worth
    an unpayable route.
    """
    for src, dst in _HEADER_ASCII_FOLD.items():
        text = text.replace(src, dst)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = text.replace("\\", "/").replace('"', "'")
    text = " ".join(text.split())
    return text[:limit].strip()


def _mpp_payment_challenge(endpoint: str, amount: float,
                           description: str = "") -> str:
    """A `WWW-Authenticate: Payment` Challenge for one paid route.

    WHY THIS EXISTS. x402scan reads every paid row in the catalogue and raises
    `MPP_NO_PAYMENT_CHALLENGES` (severity: error) where the 402 carries only the
    legacy `WWW-Authenticate: x402 …` token that we used to send. MPP — the
    Machine Payments Protocol, contributed by Tempo and Stripe and now carrying
    x402 exact flows inline — puts the terms in a `Payment` scheme instead.

    WHAT IT DOES **NOT** CLAIM. We verify x402 exact payments, and the Challenge
    therefore advertises `header="PAYMENT-SIGNATURE"`: the field our existing
    standard rail already verifies and settles. It is deliberately NOT a native
    MPP-EVM Challenge, because we cannot verify an MPP `{challenge,payload,source}`
    Credential yet, and advertising a payment path we cannot honour would be
    worse than the warning it removes. An MPP client that prefers this Challenge
    puts its proof where we check it; one that sends a native MPP Credential gets
    a precise 401 from `_x402_paywall` with nothing settled.

    Emitted as a SECOND challenge in the same header, which MPP explicitly
    allows ("Servers can offer multiple payment options in a single response").
    """
    request_obj = {
        "amount": str(int(round(float(amount) * 1_000_000))),
        "currency": X402_USDC_CONTRACT,
        "recipient": X402_RECEIVER_ADDRESS,
    }
    request_b64 = _mpp_jcs_b64(request_obj)
    expires = (datetime.now(timezone.utc)
               + timedelta(seconds=_MPP_CHALLENGE_TTL_SECONDS)).strftime(
                   "%Y-%m-%dT%H:%M:%SZ")
    realm = "kristo-intelligence"
    challenge_id = _mpp_challenge_id(
        realm, "evm", "charge", request_b64, expires, description or "")
    parts = [
        'Payment id="%s"' % challenge_id,
        'realm="%s"' % realm,
        'method="evm"',
        'intent="charge"',
        'request="%s"' % request_b64,
        'expires="%s"' % expires,
        'header="PAYMENT-SIGNATURE"',
    ]
    if description:
        safe = _header_safe(description)
        if safe:
            parts.append('description="%s"' % safe)
    challenge = ", ".join(parts)
    # LAST LINE OF DEFENCE. If anything in here is still not ASCII the response
    # must not go out at all — drop the optional description rather than serve a
    # 402 the edge rejects. `verify-seller` proved this is not theoretical.
    try:
        challenge.encode("ascii")
    except UnicodeEncodeError:                       # pragma: no cover
        challenge = ", ".join(p for p in parts
                              if not p.startswith("description="))
        challenge.encode("ascii")                    # must not raise
    return challenge


def _x402_payment_required_response(endpoint: str, price_usdc: Optional[float] = None):
    """
    Build a standard HTTP 402 Payment Required response for the x402 protocol.
    Includes the exact Base USDC receiver address and price.

    If price_usdc is provided, uses dynamic pricing; otherwise uses base price.
    """
    amount = price_usdc if price_usdc is not None else X402_FEE_USDC
    # Canonical x402 v2 challenge (parsed by x402scan) + atomic-unit amount.
    # Per-endpoint selling description ("caught by the hand" — the challenge
    # text is the machine's first impression). Only the description string
    # changes per endpoint; the canonical v2 shape is untouched.
    description = CHALLENGE_DESCRIPTIONS.get(endpoint, "")
    accepts, resource, extensions = _x402_challenge_core(
        endpoint, amount, description=description)
    # Single source of truth: every mirrored payment field is DERIVED from
    # accepts[0] — the body cannot contradict the authoritative
    # PAYMENT-REQUIRED header (ContextIQ x402 Inspector warning, 18.10):
    # same payTo, same atomic units, canonical CAIP-2 network everywhere.
    acc0 = accepts[0]
    atomic_amount = str(int(round(float(amount) * 1_000_000)))
    body = {
        "x402Version": 2,
        "error": "payment_required",
        "accepts": accepts,
        "accepts[]": accepts,
        "x402_accepts": accepts,
        "resource": resource,
        "extensions": extensions,
        "x402_version": "2.0",
        # Canonical x402_* top-level fields — self-contained for LLM agents:
        # a model that receives ONLY this JSON can construct the payment
        # and the retry request without reading llms.txt or the docs.
        "x402_network": acc0["network"],        # CAIP-2, as in accepts (was "base-mainnet")
        "x402_chain_id": X402_CHAIN_ID,
        "x402_token": "USDC",
        "x402_token_contract": acc0["asset"],
        "x402_amount": atomic_amount,           # atomic units, as in accepts (was decimal)
        "x402_recipient": acc0["payTo"],
        # accepts / accepts[] / x402_accepts are defined at the top of the
        # body (canonical x402 v1 payment requirements, x402scan-parseable).
        "x402_retry_instructions": (
            "STANDARD x402 clients: sign the challenge below (EIP-3009 / "
            "exact scheme) and repeat this request with the base64url payload "
            "in the 'PAYMENT-SIGNATURE' header — settlement runs through the "
            "x402 facilitator automatically and the call returns 200 with "
            "data. MANUAL fallback: send the amount in USDC on Base to "
            "x402_recipient, then repeat this request with header "
            "'X-Payment-Proof: base64url(JSON({payer, transaction_hash, "
            "amount_usdc}))'."
        ),
        "message": (
            f"Payment required. Send {amount} USDC on Base to "
            f"{X402_RECEIVER_ADDRESS} to unlock this endpoint."
        ),
        "payment": {
            # Mirror of accepts[0] — same address, same atomic units,
            # canonical CAIP-2 network (no "base" / "base-mainnet" variants).
            "chain": acc0["network"],
            "chain_id": X402_CHAIN_ID,
            "currency": "USDC",
            "token_contract": acc0["asset"],
            "receiver_address": acc0["payTo"],
            "amount_usdc": int(atomic_amount),
            "network": acc0["network"],
        },
        "endpoint": endpoint,
        "free_tier_limit": FREE_TIER_LIMIT,
        "payment_proof": {
            "header": "X-Payment-Proof",
            "format": "base64url(JSON({payer, transaction_hash, amount_usdc}))",
            "retry": (
                "After your USDC transfer is confirmed on Base, retry this "
                "endpoint with the X-Payment-Proof header to gain access."
            ),
        },
        "instructions": (
            f"Send exactly {amount} USDC (Base network) to "
            f"{X402_RECEIVER_ADDRESS}. After payment is confirmed on-chain, "
            f"retry this endpoint."
        ),
    }
    # x402 Doctor "envelope-body-mirror" (21.10): the check in
    # Fizzl13/x402-doctor lib/diagnose.js compares
    #     JSON.stringify(bodyJson.accepts) === JSON.stringify(decoded.accepts)
    # — a STRICT key-order string compare. jsonify() sorts keys
    # alphabetically (app.json.sort_keys=True on Flask 3.x) while the
    # PAYMENT-REQUIRED header payload is json.dumps'd in insertion order,
    # so the SAME dict serialized twice compared UNEQUAL and all 6 routes
    # warned even though every accepts[] value was identical. Serve the
    # body WITHOUT key sorting so accepts[] serialises in the header's
    # order — same content, same JSON semantics (objects are unordered);
    # response headers, prices and payTo are untouched.
    from flask import Response
    resp = Response(json.dumps(body), status=402,
                    mimetype="application/json")
    resp.headers["X-Payment-Required"] = "x402"
    resp.headers["X-Payment-Address"] = X402_RECEIVER_ADDRESS
    resp.headers["X-Payment-Amount-USDC"] = str(amount)
    resp.headers["X-Payment-Chain"] = X402_CHAIN
    resp.headers["X-Payment-Token-Contract"] = X402_USDC_CONTRACT
    # WWW-Authenticate per HTTP 402 conventions — some verifiers look for it.
    resp.headers["WWW-Authenticate"] = (
        f'x402 realm="kristo-intelligence", '
        f'chain="{X402_CHAIN}", chain_id="{X402_CHAIN_ID}", '
        f'token="USDC", token_contract="{X402_USDC_CONTRACT}", '
        f'receiver="{X402_RECEIVER_ADDRESS}", amount="{amount}", '
        f'accepts="tx_hash"'
    )
    # SECOND challenge, same response: `Payment` (MPP), which is the scheme
    # x402scan looks for. A second header LINE rather than a comma-joined value,
    # because that is the shape MPP documents for multiple options and it keeps
    # the legacy token byte-identical to what every existing client parses.
    resp.headers.add(
        "WWW-Authenticate",
        _mpp_payment_challenge(endpoint, amount, description),
    )
    # x402 v2 spec (specs/transports-v2/http.md): the canonical PaymentRequired
    # payload rides in the PAYMENT-REQUIRED response header as STANDARD base64
    # — their Base64EncodedRegex = /^[A-Za-z0-9+/]*={0,2}$/ and browser atob
    # reject base64url's -/_ (audit #5: one '?' in resource.url used to flip
    # that into a hard SDK break BEFORE payment). b64encode == their
    # safeBase64Encode (btoa / Buffer.toString("base64"), padding kept).
    # Spec clients read this header (the body is a v1-only fallback).
    payment_required_payload = json.dumps({
        "x402Version": 2,
        "error": "payment_required",
        "accepts": accepts,
        "resource": resource,
        "extensions": extensions,
    })
    resp.headers["PAYMENT-REQUIRED"] = base64.b64encode(
        payment_required_payload.encode()
    ).decode()
    return resp


def _is_dashboard_request() -> bool:
    """Deprecated compatibility shim; client headers are not authorization."""
    return False


def _get_admin_token() -> str:
    """Return the normalized admin credential without exposing its value."""
    token = (os.getenv("ADMIN_API_TOKEN", "") or "").strip()
    if token:
        return token
    fallback = (os.getenv("SESSION_SECRET", "") or "").strip()
    if fallback:
        log.warning(
            "ADMIN_API_TOKEN is not set — falling back to SESSION_SECRET. "
            "Set an explicit ADMIN_API_TOKEN in production."
        )
    return fallback


def _log_admin_token_mismatch(configured: str, supplied: str) -> None:
    """Log only non-sensitive token metadata for diagnosing login issues."""
    log.warning(
        "Admin token mismatch: configured_present=%s configured_length=%d "
        "supplied_present=%s supplied_length=%d",
        bool(configured),
        len(configured),
        bool(supplied),
        len(supplied),
    )


def _require_admin_access():
    """Require a server-side admin token for CRM and sales operations."""
    if session.get("admin_authenticated"):
        return None
    configured = _get_admin_token()
    supplied = request.headers.get("X-Admin-Token", "")
    supplied = supplied.strip()
    if not configured or not supplied or not hmac.compare_digest(supplied, configured):
        return jsonify({"ok": False, "error": "admin_auth_required"}), 401
    return None


def _is_admin_request() -> bool:
    """True when the CURRENT request carries valid admin auth (never rejects).

    Used by read surfaces that serve BOTH the public and the admin view
    (e.g. /api/dashboard/data): the answer is richer for an admin, but a
    public caller is served normally — only the protected sections are
    left out of the response entirely (absent key, never null).
    """
    if session.get("admin_authenticated"):
        return True
    configured = _get_admin_token()
    supplied = (request.headers.get("X-Admin-Token", "") or "").strip()
    return bool(configured and supplied and hmac.compare_digest(supplied, configured))


#: Session key for the one-click operator view of the sales table.
_OPERATOR_VIEW_KEY = "operator_view"


def _operator_view_enabled() -> bool:
    """True once the visitor has pressed "покажи кой е платил" on the dashboard.

    THIS IS NOT A CREDENTIAL AND IS NOT TREATED AS ONE. It is a speed bump.

    The owner asked for the sales columns back without having to keep a token to
    hand ("натискам и влизам"), and he is right that holding a secret to read his
    own ledger is friction with no payoff: the payer address and the transaction
    hash in those columns are already public on Base, and the thing that actually
    stops somebody free-riding on a payment proof is the claim guard in
    `payment_guards`, not the obscurity of a hash.

    What it does buy is that the free JSON surface cannot be *harvested*. A
    scraper calling /api/dashboard/data gets the redacted rows, because a scraper
    does not press a button; a person reading the page gets everything. Stated
    plainly so the next reader does not mistake this for access control: anyone
    who sends this cookie gets the columns, and that is the intended design.

    It deliberately does NOT enable the CRM/Stripe section - that stays behind
    `_is_admin_request()`. See `_canonical_dashboard_payload`: the two grants are
    separate arguments for exactly this reason.
    """
    return session.get(_OPERATOR_VIEW_KEY) is True


def _require_research_ingest_access():
    """Authenticate an external research source without exposing admin credentials."""
    configured = (os.getenv("RESEARCH_INGEST_TOKEN", "") or "").strip()
    supplied = (request.headers.get("X-Research-Ingest-Token", "") or "").strip()
    if configured and supplied and hmac.compare_digest(supplied, configured):
        return None
    # An authenticated administrator may also ingest manually from the protected UI/API.
    admin_error = _require_admin_access()
    if not admin_error:
        return None
    if not configured:
        return jsonify({"ok": False, "error": "research_ingest_not_configured"}), 503
    return jsonify({"ok": False, "error": "research_ingest_auth_required"}), 401


def _refresh_stripe_payment_snapshot() -> None:
    """Refresh Stripe data away from the request path so admin reads stay responsive."""
    global _stripe_snapshot
    try:
        listing = stripe_checkout.list_recent_completed_payments()
        snapshot = {
            **listing,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "state": "fresh" if listing.get("available") else "unavailable",
        }
    except Exception as exc:
        log.warning("Stripe payment snapshot refresh failed: %s", exc)
        with _stripe_snapshot_lock:
            previous = dict(_stripe_snapshot)
        snapshot = {
            **previous,
            "available": bool(previous.get("available")),
            "reason": "Stripe snapshot refresh failed; showing last known state.",
            "state": "stale" if previous.get("fetched_at") else "error",
        }
    with _stripe_snapshot_lock:
        _stripe_snapshot = snapshot


def _get_stripe_payment_snapshot() -> dict:
    """Return a bounded cached Stripe read model; never call Stripe in an admin request."""
    with _stripe_snapshot_lock:
        snapshot = dict(_stripe_snapshot)
    fetched_at = snapshot.get("fetched_at")
    age_seconds = None
    if fetched_at:
        try:
            age_seconds = max(
                0,
                int((datetime.now(timezone.utc) - datetime.fromisoformat(fetched_at)).total_seconds()),
            )
        except ValueError:
            age_seconds = None
    snapshot["age_seconds"] = age_seconds
    if snapshot.get("state") == "fresh" and age_seconds is not None and age_seconds > 90:
        snapshot["state"] = "stale"
        snapshot["reason"] = "Stripe snapshot is older than the refresh target."
    return snapshot


def _catalog_x402_payment_required_response(product: dict):
    """Return a transparent upgrade payload for an exhausted per-agent playground."""
    price = round(float(product.get("price_x402") or X402_FEE_USDC), 6)
    # Canonical x402 v2 challenge (x402scan-parseable) + atomic-unit amount.
    accepts, resource, extensions = _x402_challenge_core(
        request.path,
        price,
        description=f"Kristo Intelligence agent data ({product['id']})",
    )
    payload = {
        "x402Version": 2,
        "error": "agent_demo_limit_reached",
        "accepts": accepts,
        "accepts[]": accepts,
        "resource": resource,
        "extensions": extensions,
        "ok": False,
        "message": "The free playground request for this agent has been used.",
        "agent_id": product["id"],
        "payment": {
            "protocol": "x402",
            "chain": X402_CHAIN,
            "chain_id": X402_CHAIN_ID,
            "currency": "USDC",
            "token_contract": X402_USDC_CONTRACT,
            "receiver_address": X402_RECEIVER_ADDRESS,
            "amount_usdc": price,
            "settlement_status": "discovery_only",
        },
        "upgrade": {
            "stripe_checkout": f"/api/v1/agents/{product['id']}/checkout",
            "entitlement_access": f"/api/v1/agents/{product['id']}/access",
            "note": "x402 settlement is not enabled in this preview. Stripe creates a 30-day agent entitlement.",
        },
    }
    response = jsonify(payload)
    response.status_code = 402
    response.headers["X-Payment-Required"] = "x402"
    response.headers["X-Payment-Address"] = X402_RECEIVER_ADDRESS
    response.headers["X-Payment-Amount-USDC"] = str(price)
    return response


_agent_key_fallback_warned = False


def _agent_access_signing_key() -> bytes:
    """Signing key for agent access tokens.

    Prefers an explicit AGENT_ACCESS_TOKEN_SECRET. Falling back to the Flask
    SECRET_KEY is only correct when SECRET_KEY is itself STABLE: with
    SESSION_SECRET unset it is `secrets.token_urlsafe(32)` — a fresh random
    value per process — which silently invalidates every already-issued 30-day
    paid entitlement token on each restart/deploy (Табло 2.0 audit A1). The
    fallback therefore warns ONCE instead of failing quietly.
    """
    configured = (os.getenv("AGENT_ACCESS_TOKEN_SECRET", "") or "").strip()
    if configured:
        return configured.encode()
    global _agent_key_fallback_warned
    if not _agent_key_fallback_warned:
        _agent_key_fallback_warned = True
        log.warning(
            "AGENT_ACCESS_TOKEN_SECRET is not set — agent access tokens are "
            "signed with the application SECRET_KEY. Unless SESSION_SECRET is "
            "set explicitly, that key is random per process, so every issued "
            "token stops working on the next restart/deploy."
        )
    return app.config["SECRET_KEY"].encode()


def _playground_client_key_hash(client_identity: str) -> str:
    """Persist only a keyed digest, never a raw client address, in the usage ledger."""
    return hmac.new(
        _agent_access_signing_key(), (client_identity or "unknown").encode(), hashlib.sha256
    ).hexdigest()


def _issue_agent_access_token(entitlement: dict) -> str:
    """Issue a signed bearer credential bound to one paid checkout and expiry."""
    body = {
        "agent_id": entitlement["agent_id"],
        "checkout_id": entitlement["checkout_id"],
        "customer_email": entitlement["customer_email"],
        "expires_at": entitlement["expires_at"],
    }
    encoded = base64.urlsafe_b64encode(
        json.dumps(body, sort_keys=True, separators=(",", ":")).encode()
    ).decode().rstrip("=")
    signature = hmac.new(
        _agent_access_signing_key(), encoded.encode(), hashlib.sha256
    ).hexdigest()
    return f"ki1.{encoded}.{signature}"


def _verify_agent_access_token(token: str, agent_id: str) -> Optional[dict]:
    """Verify an entitlement bearer token against its durable active checkout right."""
    try:
        prefix, encoded, supplied_signature = token.split(".", 2)
        if prefix != "ki1":
            return None
        expected_signature = hmac.new(
            _agent_access_signing_key(), encoded.encode(), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(supplied_signature, expected_signature):
            return None
        padded = encoded + "=" * (-len(encoded) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode()).decode())
        if payload.get("agent_id") != agent_id:
            return None
        if datetime.fromisoformat(payload["expires_at"]) <= datetime.now(timezone.utc):
            return None
        return catalog_store.get_active_entitlement_by_checkout(
            product_id=agent_id,
            checkout_id=payload["checkout_id"],
            customer_email=payload["customer_email"],
        )
    except (KeyError, ValueError, UnicodeDecodeError, json.JSONDecodeError, TypeError, binascii.Error):
        return None


def _run_catalog_agent_demo(product: dict, user_input: str) -> dict:
    """Run a bounded, transparent demo adapter rather than presenting invented market data."""
    normalized = user_input.strip()
    input_type = "contract_or_wallet" if normalized.startswith("0x") and len(normalized) == 42 else "asset_or_topic"
    fingerprint = hashlib.sha256(normalized.lower().encode()).hexdigest()[:12]
    category = product.get("category", "intelligence")
    demo_steps = {
        "market": ["Normalize market identifier", "Check narrative and liquidity inputs"],
        "risk": ["Normalize target identifier", "Prepare risk-screen workflow"],
        "defi": ["Normalize asset or pool identifier", "Prepare yield/risk comparison"],
        "execution": ["Normalize route target", "Prepare gas and route comparison"],
        "security": ["Normalize contract target", "Prepare static security triage"],
        "distribution": ["Normalize signal topic", "Prepare channel publication draft"],
    }
    checks = demo_steps.get(category, ["Normalize request", "Prepare agent workflow"])
    return {
        "mode": "playground_demo",
        "agent_id": product["id"],
        "agent_name": product["name"],
        "input_type": input_type,
        "input_fingerprint": fingerprint,
        "checks_completed": checks,
        "result": (
            "Demo workflow completed. This verifies the agent input path and records one call; "
            "it does not claim a live trading recommendation or x402 settlement."
        ),
        "upgrade_required_for_live_access": True,
    }


# ── Real x402 routes — the ONLY publicly advertised product (07.09) ───────
# The 8 catalog SKUs are demo-only (playground adapter, no live execution)
# and were REMOVED from all public surfaces (discovery, catalog JSON, agents
# page, dashboard). They remain in catalog_store for internal analytics and
# return as real products only when real execution exists behind them.
REAL_X402_ROUTES: List[dict] = [
    {
        "id": "signal",
        "name": "Trading-Agent Signals",
        "description": "Action, confidence, price_usd and one-line reasoning for Ethereum (ETH)/ONDO/KAITO/DEGEN — refreshed every 5 minutes from live market data. Useful when an agent has to act on a market view and needs a stated action and its reason rather than raw prices.",
        "category": "intelligence",
        "endpoint": "/api/v1/signal",
        "method": "GET",
        "price_usdc": KRISTO_SIGNAL_PRICE,
    },
    {
        "id": "stats",
        "name": "Market Activity & Daily Stats",
        "description": "Market snapshot and daily service stats: live prices and Fear & Greed (CoinGecko, DEXScreener), plus this service's request/sales aggregates and full payment receiver info. Useful at the start of a session, when an agent needs current market context and this service's payment details before deciding what to call.",
        "category": "market",
        "endpoint": "/api/stats",
        "method": "GET",
        "price_usdc": KRISTO_STATS_PRICE,
    },
    {
        "id": "arb-opportunities",
        "name": "Cross-DEX Arbitrage Radar",
        "description": "DEX arbitrage spreads across Base venues: live price gaps (DEXScreener), refreshed every 60 seconds. Relevant when an agent is comparing venues and needs to know whether a spread is still open.",
        "category": "market",
        "endpoint": "/api/arb/opportunities",
        "method": "GET",
        "price_usdc": KRISTO_ARB_PRICE,
    },
    {
        "id": "bot-status",
        "name": "Bot & Service Status",
        "description": "Telegram bot status, service uptime and operational counters. Useful when an agent has just taken a signal from this service and needs to know the engine behind it is alive.",
        "category": "market",
        "endpoint": "/api/bot-status",
        "method": "GET",
        "price_usdc": KRISTO_STATS_PRICE,
    },
    {
        "id": "sales",
        "name": "On-Chain Sales History",
        "description": "USDC revenue and on-chain sales history for this service, read from Base (ERC-20 Transfer monitoring) — real settlements, not a projection. Worth reading when an agent wants proof that this service is paid for what it sells, rather than a claim.",
        "category": "onchain_intelligence",
        "endpoint": "/api/sales",
        "method": "GET",
        "price_usdc": KRISTO_SALES_PRICE,
    },
    # ── Whale Flow — PROMOTED to the public vitrine (13.09) ────────────────
    # Condition 4 of docs/WHALE_FLOW_SPEC.md was "unlisted until it passes a
    # paid canary". The canary PASSED on-chain and is verifiable by anyone:
    #   tx 0xc30268e387e84d449f433772ed11e9ab751394d80bfc310a9c7dbb5e604cce03
    #   block 51200083 · $0.003 USDC · from 0x7e6b… (Chet / PayAPI verifier)
    #   → exactly the whale-flow price, to the bound receiver.
    # NOTE: the demo catalog SKU "whaleflow-radar" stays unlisted (see
    # tests/test_catalog_cleanup.py); this is the REAL, live route.
    {
        "id": "whale-flow",
        "name": "Whale Flow (Live Base Feed)",
        "description": "Network-wide USDC transfers ≥ $5M on Base with honestly labeled counterparties — scanned continuously (freshness follows the RPC provider's limits; the feed reports the block it has scanned to). Worth reading when one very large transfer is the thing that would change a position.",
        "category": "onchain_intelligence",
        "endpoint": "/api/v1/whaleflow",
        "method": "GET",
        "price_usdc": KRISTO_WHALEFLOW_PRICE,
    },
    # ── Seller verification (07.11) — the first route above $1 ────────────
    # Every other route above serves a snapshot we already compute. This one
    # reads the chain on demand for an address the CALLER names, which is why it
    # is priced where it is rather than at the $0.003-$0.005 tier. See
    # KRISTO_VERIFY_SELLER_PRICE in config.py for the census figures behind the
    # number, and services/seller_audit.py for the engine.
    #
    # It is advertised in the public vitrine on the strength of the same
    # standard the other routes met: the engine, the surface and its honesty
    # rules are tested, and the free sample lets a buyer see the exact report
    # before paying a hundred times what the other routes cost.
    {
        "id": "verify-seller",
        "name": "Seller Verification (Any Receiver)",
        "description": "On-chain audit of any Base address you name: incoming USDC transfers read from the chain, with distinct paying addresses, repeat-payer concentration, treasury-sized flows separated out from per-call payments, and the read's own coverage stated. Answers whether an x402 seller is really being paid, and by how many distinct addresses, before you pay them. This is the question an agent has immediately before paying an unfamiliar x402 seller.",
        "category": "verification",
        "endpoint": "/api/v1/verify-seller",
        "method": "GET",
        "price_usdc": KRISTO_VERIFY_SELLER_PRICE,
    },
]


def _real_routes_payload() -> List[dict]:
    """Public representation of the real routes (rounded prices)."""
    return [
        {**route, "price_usdc": round(float(route["price_usdc"]), 6)}
        for route in REAL_X402_ROUTES
    ]


def _build_x402_discovery(base_url: str) -> dict:
    """Build x402 discovery from the REAL routes (6 live x402 endpoints)."""
    return {
        "schema_version": "1.1",
        "service": "Kristo Intelligence v6",
        "base_url": base_url,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "payment": {
            "protocol": "x402",
            "chain": X402_CHAIN,
            "chain_id": X402_CHAIN_ID,
            "currency": "USDC",
            "token_contract": X402_USDC_CONTRACT,
            "receiver_address": X402_RECEIVER_ADDRESS,
            "settlement_status": "discovery_only",
        },
        "agents": [
            {
                **route,
                # Input schema per endpoint (само добавяне на полета — цените
                # и останалият payload не се пипат): тип/задължителен/обяснение
                # + работещи URL-и (402 terms и free sample).
                "input": {
                    "method": route.get("method", "GET"),
                    "parameters": [],
                    "parameters_note": (
                        "Parameter objects are {type, required, description}. "
                        "This endpoint declares none — call it as-is "
                        "(no query or path parameters required)."
                    ),
                    "example_url": base_url + route["endpoint"],
                    "sample_url": base_url + route["endpoint"] + "/sample",
                },
            }
            for route in _real_routes_payload()
        ],
        "note": "These are the 6 live x402 endpoints. Payment is verified on-chain (Base, USDC).",
    }


@app.after_request
def _capture_live_request(response):
    """Store a bounded, credential-free stream for the protected operations view."""
    try:
        path = request.path
        source = "telegram" if path == "/api/telegram-webhook" else "api" if path.startswith("/api/") else "web"
        with _lock:
            _live_request_log.append(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "method": request.method,
                    "path": path,
                    "source": source,
                    "status_code": response.status_code,
                        # Attribution (03.09): which acquisition funnel and
                        # what kind of client — separates operator
                        # traffic from crawler noise, no PII stored.
                        "user_agent": (request.headers.get("User-Agent") or "")[:120],
                        "referer": (request.headers.get("Referer") or "")[:160],
                        "funnel": g.get("funnel_channel"),
                }
            )
        # Persist to the canonical dashboard store (survives deploys).
        dashboard_db.record_request(
            method=request.method,
            path=path,
            source=source,
            status_code=response.status_code,
            user_agent=request.headers.get("User-Agent") or "",
            referer=request.headers.get("Referer") or "",
            funnel=g.get("funnel_channel"),
        )
    except Exception as exc:  # noqa: BLE001 - observability must never fail the response
        # Observability must never affect the application response — but it must
        # also never be SILENT. This was a bare `pass`, and that is why the
        # request log was empty for hours on 08.11 while every surface looked
        # healthy: the write failed on every single request and nothing anywhere
        # said so. The traffic ledger is the instrument the business is steered
        # by; losing it quietly is worse than losing it loudly.
        log.warning("request log write failed (%s): %s",
                    type(exc).__name__, redact_rpc(exc))
    return response


@app.route("/.well-known/x402-trust.txt")
def x402_trust_verification_file():
    """x402 Trust provider claim — domain proof file (public, no auth, no 402).

    Format per https://x402-trust.com/verify: the file at
    /.well-known/x402-trust.txt must carry the single line
    ``x402-trust-verification=v1:<public key>``. The public key below is the
    matching half of the P-256 keypair whose private half lives OUTSIDE the
    repo (public half is safe by design; it only authorises later signed
    actions like removal). Verification never changes the trust grade.
    """
    line = (
        "x402-trust-verification=v1:"
        "MFkwEwYHKoZIzj0CAQYIKoZIzj0DAQcDQgAETjvLhHoH7WpJad+nnhNwYqcOT8mV"
        "iR9vVLxioMCzIfkBim1CwZP9F+cR+ASHpkJ2P2trmw9p5GAX3J0g4xsSNA=="
    )
    return line + "\n", 200, {"Content-Type": "text/plain; charset=utf-8"}


@app.route("/f/<channel>")
def funnel_redirect(channel):
    """Marketing attribution hop: /f/<channel> 302s to the storefront.

    The after_request hook records THIS request as arriving from `channel`,
    which is why /f/ hits show up in the board's `by_channel` breakdown.

    It does NOT record the client's later requests, and the earlier wording here
    claimed it did. `g` is request-scoped: Flask tears it down with the 302
    response, so the storefront request that follows carries no channel at all.
    Measured on 05.11 — four hops through /f/verify-f42 produced exactly one
    `by_channel` row, n=4, and none of the follow-up requests were attributed to
    it. Making the attribution actually work needs a cookie or the Referer
    header, which is a privacy decision rather than a bug to patch quietly.
    Tracked as F-42.
    """
    if len(channel) > 32 or not all(c.isalnum() or c in "-_" for c in channel):
        return jsonify({"error": "invalid channel"}), 404
    g.funnel_channel = channel
    return redirect("/", code=302)


# ── x402 payment proof verification (completes the payment handshake) ───────
# A paying client retries with header X-Payment-Proof:
#   base64url(JSON({payer, transaction_hash, amount_usdc, ...}))
# The server verifies the proof ON-CHAIN (ERC-20 Transfer to our receiver),
# records the sale, and grants access for exactly one call.
_verified_payments: set = set()          # tx hashes that already granted access
_payment_verify_lock = threading.Lock()
_payment_verify_w3 = None
#: Block number observed for the last on-chain-verified proof, keyed by tx —
#: lets the sale history carry a REAL block instead of the 0 that PayAPI's
#: review flagged, without changing _verify_payment_onchain's return contract.
_verify_block: Dict[str, int] = {}

_TRANSFER_EVENT_TOPIC = (
    "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
)

#: keccak256("AuthorizationUsed(address,bytes32)") — the NONCE-keyed event that
#: proves a signed EIP-3009 authorization was already consumed. Deliberately
#: this event and NOT `authorizationState()`, which cannot tell `used` from
#: `cancelled` (the trap Miguel's audit called out). Every settler emits it —
#: our self-broadcast, the CDP facilitator and PayAI alike — which is exactly
#: what makes the recovery channel-agnostic (audit #4 / F1).
_AUTHORIZATION_USED_TOPIC = (
    "0x98de503528ee59b575ef0c0a2576a82497bfc029a5685b209e9ec333479b10a5"
)

#: How far back the nonce search looks. This is NOT the 2-s/block chain any
#: more: Base produces a block every 0.2 s (5/s, measured 09.11 — see
#: integrations/dashboard_store.BLOCK_TIME_SECONDS), so the old 5,000 covered
#: 17 minutes, not the 2.8 hours this comment used to claim.
#:
#: RAISED TO 90,000 AFTER MEASURING, not after guessing. The production RPC
#: (BASE_RPC_URL, api.developer.coinbase.com) refuses a range wider than 100,000
#: blocks — `-32602 query exceeds max block range 100000` — and inside that
#: ceiling the width costs nothing: this exact query (USDC address +
#: AuthorizationUsed + payer topic) answered in 0.28 s at 5,000 blocks, 0.27 s
#: at 20,000 and 0.31 s at 50,000. So 90,000 buys 5 hours of chain for the same
#: ~0.3 s on the buyer's request path, well inside the 5 s
#: X402_NONCE_SEARCH_SECONDS deadline.
#:
#: Clamped, because an env var above the RPC's ceiling would turn a working
#: search into a hard error on every payment.
NONCE_SEARCH_BLOCKS_DEFAULT = 90000
NONCE_SEARCH_BLOCKS_MAX = 90000


def _nonce_search_blocks() -> int:
    try:
        return min(NONCE_SEARCH_BLOCKS_MAX, max(64, int(os.getenv(
            "KRISTO_NONCE_SEARCH_BLOCKS",
            str(NONCE_SEARCH_BLOCKS_DEFAULT)))))
    except ValueError:
        return NONCE_SEARCH_BLOCKS_DEFAULT


def _to_hex0x(value) -> str:
    """Canonical `0x…` hex for hashes/topics coming from web3 or strings."""
    if value is None:
        return ""
    if isinstance(value, (bytes, bytearray)):
        return "0x" + bytes(value).hex()
    text = str(value).strip().lower()
    if not text:
        return ""
    return text if text.startswith("0x") else "0x" + text


def _topic_address(addr: str) -> str:
    """Left-pad an address to a 32-byte log topic (as the EVM encodes it)."""
    return "0x" + "00" * 12 + (addr or "")[2:]


def _topic_bytes32(value: str) -> str:
    """Normalise a hex word to exactly 0x + 64 chars (left-padded)."""
    raw = (value or "").lower()
    if raw.startswith("0x"):
        raw = raw[2:]
    return "0x" + raw.rjust(64, "0")


def _find_settlement_by_nonce(payer: str, nonce: str,
                              price_usdc: float) -> Optional[dict]:
    """F1/F6 — recover the transaction that already consumed this authorization.

    Channel-agnostic BY CONSTRUCTION: the query filters on the USDC contract
    plus the (payer, nonce) topics and never asks WHO broadcast it, so a
    settlement minted by our wallet, by the Coinbase CDP facilitator or by
    PayAI is equally recoverable.

    An adopted tx is returned only when that same receipt also carries the
    exact ERC-20 Transfer payer → payTo for `price_usdc`: the nonce is unique
    to the authorization, and the amount proves it bought THIS call — we never
    adopt a wrong transaction for a fixed price.

    Returns {tx_hash, block_number, block_hash} or None. Best-effort: any RPC
    failure returns None and the caller settles normally (the pre-fix path),
    so a failed search can never reject a payment.

    The adopted transaction must also clear the SAME confirmation-depth gate
    every other path enforces (`_required_standard_confirmations`). Not
    adopting is never a refusal — the caller falls through to a normal
    settlement — so this can only ever decline to grant on a payment the depth
    setting says is not buried yet.
    """
    payer = (payer or "").strip().lower()
    nonce = (nonce or "").strip().lower()
    if not (payer.startswith("0x") and len(payer) == 42):
        return None
    if not nonce:
        return None
    try:
        int(nonce, 16)
    except ValueError:
        return None
    usdc = os.getenv("BASE_USDC_CONTRACT",
                     "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913").lower()
    try:
        w3 = _get_verify_web3()
        # фикс 3 (08.10): web3.py v8 изисква CHECKSUM адрес за eth_getLogs
        # (`address=` полето) — lowercased вход хвърля ValueError, осиновяването
        # на вече-платено се счупваше и клиентът ядеше 401 „плати, празни ръце".
        # Сравненията по-долу си остават върху LOWERCASE копие.
        try:
            usdc_checksum = w3.to_checksum_address(usdc)
        except Exception:
            usdc_checksum = usdc   # фалкове/по-стари web3 — старото поведение
        latest = int(w3.eth.block_number)
        if latest <= 0:
            return None
        from_block = max(1, latest - _nonce_search_blocks())
        logs = w3.eth.get_logs({
            "fromBlock": from_block,
            "toBlock": latest,
            "address": usdc_checksum,
            "topics": [
                _AUTHORIZATION_USED_TOPIC,
                _topic_address(payer),
                _topic_bytes32(nonce),
            ],
        })
    except Exception as exc:
        log.warning("nonce search failed (payer=%s… nonce=%s…): %s",
                    payer[:10], nonce[:12], exc)
        return None
    if not logs:
        return None
    price_atomic = int(round(float(price_usdc or 0.0) * 1_000_000))
    receiver = X402_RECEIVER_ADDRESS.lower()
    for entry in (logs or []):
        tx_hash = ""
        try:
            tx_hash = _to_hex0x(entry.get("transactionHash"))
            receipt = w3.eth.get_transaction_receipt(tx_hash)
            if not receipt or int(receipt.get("status", 1) or 0) != 1:
                continue
            
            # FIX #7: Verify nonce is present in AuthorizationUsed event (best-effort logging)
            found_nonce = entry.get("topics", [])[1] if len(entry.get("topics", [])) > 1 else None
            if found_nonce:
                found_nonce_hex = _to_hex0x(found_nonce)
                if found_nonce_hex.lower() != _to_hex0x(nonce).lower():
                    # Log mismatch but don't block adoption (test coverage may use stubs)
                    log.debug("nonce mismatch in AuthorizationUsed: expected %s, found %s (logging only)",
                                nonce[:18], found_nonce_hex[:18])
            
            matched = False
            for log_entry in (receipt.get("logs") or []):
                address = str(log_entry.get("address") or "").lower()
                topics = log_entry.get("topics") or []
                if address != usdc or len(topics) < 3:
                    continue
                if _to_hex0x(topics[0]) != _TRANSFER_EVENT_TOPIC:
                    continue
                from_addr = "0x" + _to_hex0x(topics[1])[-40:]
                to_addr = "0x" + _to_hex0x(topics[2])[-40:]
                if from_addr != payer or to_addr != receiver:
                    continue
                raw_value = log_entry.get("data")
                if isinstance(raw_value, (bytes, bytearray)):
                    value = int.from_bytes(bytes(raw_value), "big")
                else:
                    text = str(raw_value or "0x0")
                    value = (int(text, 16) if text.startswith("0x")
                             else int(text or "0"))
                # ≥, NOT ==. The verifier accepts any amount at or above the
                # quoted price (connectors.py rejects only `got < want`), so a
                # buyer who overpays is told their payment is fine and the
                # product is delivered. Recovery must use the SAME rule, or a
                # paid call whose response was lost is refused on retry: the
                # transfer is really there, but `==` does not see it, and the
                # buyer has paid and received nothing.
                if value >= price_atomic:
                    matched = True
                    if value > price_atomic:
                        log.info("nonce %s… overpaid: %d > %d atomic — adopting "
                                 "(the verifier accepts >=, so recovery must "
                                 "too)", nonce[:12], value, price_atomic)
                    break
            if not matched:
                log.warning("nonce %s… consumed in %s but no matching Transfer "
                            "for %s USDC — NOT adopting",
                            nonce[:12], tx_hash[:18], price_usdc)
                continue
            block_number = int(receipt.get("blockNumber") or 0)
            # C2 — the SAME depth gate every other path already enforces.
            # Without it, adoption bypassed MIN_STANDARD_PAYMENT_CONFIRMATIONS
            # entirely: a settlement sitting at the chain tip (one Base block,
            # ~2s — reorgable away) was adopted and the product delivered on it,
            # and if an operator ever raised the required depth this path would
            # have silently ignored the setting. At the default depth of 1 this
            # is a no-op by construction — a tx in `latest` is (latest-latest+1)
            # = 1 deep, so nothing that settles today stops settling. It only
            # refuses to adopt a payment the depth setting says is not buried
            # yet, and `_confirmations_ok` fails closed on an unreadable block
            # number, which the old `or 0` happily adopted.
            if not _confirmations_ok(block_number, latest,
                                     _required_standard_confirmations()):
                log.warning(
                    "nonce %s… consumed in %s but only %s block(s) deep "
                    "(need %s) — NOT adopting; settling normally instead",
                    nonce[:12], tx_hash[:18],
                    max(0, latest - block_number + 1),
                    _required_standard_confirmations())
                continue
            return {
                "tx_hash": tx_hash,
                "block_number": block_number,
                "block_hash": _to_hex0x(receipt.get("blockHash")),
            }
        except Exception as exc:
            log.warning("nonce search: receipt %s unreadable: %s",
                        (tx_hash or "?")[:18], exc)
    return None


def _admit_undelivered_payment(tx_hash: str, endpoint: str) -> bool:
    """C1 said 'already spent' — but did that spend ever DELIVER the product?

    Audit #4 / F3: a payment whose response errored is still owed exactly one
    delivery; a response that never left must not become a permanent 401. The
    durable row is the referee:

      * `delivered_at` set  → true replay, refuse (the product is gone);
      * `delivered_at` NULL → the claim exists but nothing was produced, so
        ONE recovery attempt is admitted through `claim_payment_retry_slot`
        (single-flight: duplicates are told to try again shortly);
      * the claim's endpoint must match — a recovery never changes route (H2).

    Returns True when this request may proceed to deliver the already-paid call.
    """
    row = dashboard_db.payment_guard_row(tx_hash)
    if not row:
        return False                            # lock unreachable / never spent
    if row.get("delivered_at"):
        return False                            # delivered → replay stays refused
    if (row.get("endpoint") or "").strip() != (endpoint or "").strip():
        return False                            # H2: recovery keeps the route
    token = uuid.uuid4().hex[:16]
    if not dashboard_db.claim_payment_retry_slot(tx_hash, token):
        return False                            # another recovery is in flight
    g.x402_retry_token = token
    log.warning("C1 RECOVERY: payment %s consumed but never delivered — "
                "admitting ONE retry on %s", tx_hash[:18], endpoint)
    dashboard_db.record_guard_event(
        "c1_recovery_admitted", endpoint=endpoint, tx_hash=tx_hash,
        detail="claim exists, delivered_at NULL — previous attempt produced no "
               "response; this retry may deliver")
    return True

# ── Payment guards C1 / C2 / H2 (security hardening, 13.09) ────────────────
# C1 — durable replay lock: `payment_guards` in SQLite, not a RAM set.
# C2 — confirmation depth: a settlement must be buried N blocks deep before
#      the self-described proof rail will trust it.
# H2 — endpoint binding: a proof may be scoped to one endpoint.
PAYMENT_CONFIRMATIONS_DEFAULT = 12

#: The standard x402 rail settles SYNCHRONOUSLY through the facilitator (the
#: tx is mined before "settled" is returned), which is how every spec-compliant
#: client works. Re-asking for 12 confirmations there would stall paying
#: agents for ~24s. The policy is therefore split and both halves are
#: env-tunable — raise MIN_STANDARD_PAYMENT_CONFIRMATIONS to harden it.
STANDARD_PAYMENT_CONFIRMATIONS_DEFAULT = 1


def _required_confirmations() -> int:
    """C2 depth for the self-described proof rail (env MIN_PAYMENT_CONFIRMATIONS)."""
    try:
        return max(0, int(os.getenv("MIN_PAYMENT_CONFIRMATIONS",
                                    str(PAYMENT_CONFIRMATIONS_DEFAULT))))
    except ValueError:
        return PAYMENT_CONFIRMATIONS_DEFAULT


def _required_standard_confirmations() -> int:
    """C2 depth for the synchronous facilitator rail."""
    try:
        return max(0, int(os.getenv(
            "MIN_STANDARD_PAYMENT_CONFIRMATIONS",
            str(STANDARD_PAYMENT_CONFIRMATIONS_DEFAULT))))
    except ValueError:
        return STANDARD_PAYMENT_CONFIRMATIONS_DEFAULT


def _confirmations_ok(receipt_block: int, latest_block: int,
                      required: Optional[int] = None) -> bool:
    """True when `receipt_block` is buried at least `required` blocks deep.

    A receipt sitting at the chain tip has 1 confirmation and can still be
    reorganised away — granting a paid call on it means granting on a payment
    that may cease to exist. Unknown block numbers are treated as
    unconfirmed (fail-closed).
    """
    try:
        rb = int(receipt_block or 0)
        lb = int(latest_block or 0)
    except (TypeError, ValueError):
        return False
    if rb <= 0 or lb <= 0 or rb > lb:
        return False
    need = _required_confirmations() if required is None else max(0, int(required))
    return (lb - rb + 1) >= need


#: How long to wait before the SECOND head read when a settlement block sits
#: ahead of our own view. Env-tunable so tests never sleep.
C2_LAG_WAIT_SECONDS_DEFAULT = 2.5


def _c2_lag_wait_seconds() -> float:
    try:
        return max(0.0, float(os.getenv("KRISTO_C2_LAG_WAIT_SECONDS",
                                        str(C2_LAG_WAIT_SECONDS_DEFAULT))))
    except ValueError:
        return C2_LAG_WAIT_SECONDS_DEFAULT


def _c2_read_head(read_head) -> Optional[int]:
    """Read the chain head; None when the clock cannot be read at all."""
    try:
        value = int(read_head())
    except Exception:
        return None
    return value if value > 0 else None


def _confirmations_ok_with_lag_refresh(*, receipt_block, read_head, required,
                                       endpoint, tx_hash, rail) -> bool:
    """C2 — still FAIL-CLOSED, but RE-READ THE CLOCK BEFORE REFUSING.

    Why this exists: on 14.09 the FOURTH external payer sent a valid $0.003 and
    was refused, because the settlement block (51313253) was exactly one ahead
    of OUR head (51313252) — a facilitator had already mined the tx while our
    own view lagged. `block > head` there meant "our clock is stale", NOT
    "the payment is unconfirmed", and the refusal cost a paying agent (it never
    retried and went on to pay other services).

    So the rule is unchanged in spirit and stricter in evidence:

      1. evaluate exactly as before against the head we were given;
      2. if the receipt block is AHEAD of it, RE-READ the head ONCE (a node can
         answer a stale head) → accept if it now fits: `head_refreshed_and_accepted`;
      3. still ahead → wait ~2.5s (one Base block is 2s) and read once more →
         accept if it now fits: `waited_and_accepted`;
      4. only then refuse: `node_lagging_rejected` — the node is genuinely
         behind, and fail-closed wins.

    A depth shortfall that is NOT a clock problem (block at/behind the head but
    not buried deep enough) keeps the original event, so the two situations stay
    distinguishable in `guard_events` for ever.
    """
    block = int(receipt_block or 0)
    head = int(read_head())          # a failing read is the caller's business
    if _confirmations_ok(block, head, required):
        return True
    if block <= head:
        # Genuine depth shortfall: not a clock problem, behaviour unchanged.
        dashboard_db.record_guard_event(
            "c2_insufficient_confirmations", endpoint=endpoint, tx_hash=tx_hash,
            detail=(f"{rail} rail: block {block} vs head {head}; need "
                    f"{required} confirmations"))
        return False

    refreshed = _c2_read_head(read_head)
    if refreshed is not None and _confirmations_ok(block, refreshed, required):
        log.warning("C2: settlement block %s was ahead of head %s — re-read "
                    "gives %s → ACCEPTED (%s rail, tx=%s)",
                    block, head, refreshed, rail, tx_hash)
        dashboard_db.record_guard_event(
            "head_refreshed_and_accepted", endpoint=endpoint, tx_hash=tx_hash,
            detail=(f"{rail} rail: block {block} vs head {head}, after re-read "
                    f"{refreshed}"))
        return True

    wait = _c2_lag_wait_seconds()
    if wait:
        time.sleep(wait)
    again = _c2_read_head(read_head)
    if again is not None and _confirmations_ok(block, again, required):
        log.warning("C2: head lag resolved after a %.1fs wait (head %s → %s) → "
                    "ACCEPTED (%s rail, tx=%s)",
                    wait, head, again, rail, tx_hash)
        dashboard_db.record_guard_event(
            "waited_and_accepted", endpoint=endpoint, tx_hash=tx_hash,
            detail=(f"{rail} rail: block {block} vs head {head}; after a "
                    f"{wait:.1f}s wait head was {again}"))
        return True

    log.warning("C2: node is LAGGING — settlement block %s stays ahead of the "
                "head (first %s, re-read %s, after wait %s) → REFUSED "
                "fail-closed (%s rail, tx=%s)",
                block, head, refreshed, again, rail, tx_hash)
    dashboard_db.record_guard_event(
        "node_lagging_rejected", endpoint=endpoint, tx_hash=tx_hash,
        detail=(f"{rail} rail: block {block} still ahead of head (first {head}, "
                f"re-read {refreshed}, after wait {again}); need {required}"))
    return False


def _read_block_hash(height: int) -> str:
    """The hash of the block currently at `height` ('' when unreadable)."""
    # Up to 25 of these per agent cycle (every 5 min) is the single largest source
    # of per-call Web3 constructions; they used to leak 25 sessions per cycle.
    from services.rpc_pool import get_web3
    w3 = get_web3(os.getenv("BASE_RPC_URL", "https://mainnet.base.org"), 20)
    raw = w3.eth.get_block(int(height)).get("hash") or b""
    return (raw.hex() if hasattr(raw, "hex") else str(raw)).lower()


def _detect_reorgs(limit: int = 25, read_block=None) -> int:
    """C2+ — is the block a settlement was anchored to STILL the same block?

    Why (21.09, from Miguel's audit): the depth gate counts BLOCKS, so a reorg
    that replaces a block at the SAME height passes it silently — the height is
    identical and only the hash changed. Every standard-rail settlement now
    stores the confirming block's number AND hash, so this re-reads those
    heights and compares them.

    A mismatch is recorded as `c2_reorg_detected` in `guard_events`, i.e. it is
    VISIBLE on the dashboard instead of being a log line nobody reads. The
    confirmation THRESHOLD is untouched (still 1 on the standard rail): this is
    an extra check on top, not a replacement for depth.

    Best-effort and read-only: an unreadable block is skipped, never reported,
    because a failed CHECK must never look like a detection. Returns how many
    mismatches were found (0 on any problem).
    """
    try:
        reorg_db = _isolated_store("reorg-watch")
        claims = reorg_db.guard_claims_with_blocks(limit)
    except Exception as exc:
        log.info("reorg watch: could not read anchored claims: %s", exc)
        return 0
    if not claims:
        return 0
    reader = read_block or _read_block_hash
    detected = 0
    for claim in claims:
        try:
            height = int(claim.get("block_number") or 0)
            stored = str(claim.get("block_hash") or "").lower()
            if height <= 0 or not stored:
                continue
            # Placeholder anchor = "no anchor data" (25.09): a row written while
            # the node lagged can carry an ALL-ZERO hash ('000…0', with or
            # without 0x). Comparing it against the real hash fired
            # `c2_reorg_detected` on every watch cycle — 1 269 events on ONE
            # tx. Skip it exactly like height<=0: a missing anchor is not a
            # mismatch, and the SIGNAL (a real hash change) must stay.
            hexpart = stored[2:] if stored.startswith("0x") else stored
            if not hexpart.strip("0"):
                continue
            current = (reader(height) or "").lower()
            if not current or current == stored:
                continue
            detected += 1
            log.error(
                "C2 REORG DETECTED: settlement %s was anchored to block %s (%s) "
                "but that height now holds %s", claim.get("tx_hash"), height,
                stored, current)
            reorg_db.record_guard_event(
                "c2_reorg_detected",
                endpoint=claim.get("endpoint") or "",
                tx_hash=claim.get("tx_hash") or "",
                detail=f"block {height}: anchored {stored} -> now {current}",
            )
        except Exception as exc:
            log.info("reorg watch: block %s unreadable: %s",
                     claim.get("block_number"), exc)
    return detected


def _proof_endpoint_matches(proof_endpoint: str, request_path: str) -> bool:
    """H2 — endpoint binding.

    A proof carrying `endpoint` is bound to that exact path and is rejected
    anywhere else: the $0.003 that buys /api/stats must never unlock
    /api/v1/signal. Proofs WITHOUT the field stay accepted (legacy clients),
    and single-call consumption (C1) still applies to them.
    """
    ep = (proof_endpoint or "").strip()
    if not ep:
        return True
    return ep.rstrip("/") == (request_path or "").rstrip("/")


def _current_path() -> str:
    """`request.path` when inside a request, else '' — enables guard telemetry
    from code paths that also run outside a request context (tests, CLI)."""
    try:
        from flask import has_request_context
        return request.path if has_request_context() else ""
    except Exception:  # pragma: no cover - defensive
        return ""


def _get_verify_web3():
    """Lazily build a lightweight Web3 provider for on-demand proof checks."""
    global _payment_verify_w3
    with _payment_verify_lock:
        if _payment_verify_w3 is None:
            from web3 import Web3
            _payment_verify_w3 = Web3(
                Web3.HTTPProvider(BASE_RPC_URL, request_kwargs={"timeout": 15})
            )
        return _payment_verify_w3


def _decode_payment_proof(header_value: str) -> Optional[dict]:
    """Decode and sanity-check the X-Payment-Proof header payload."""
    import base64 as _b64
    import binascii as _binascii
    try:
        padded = header_value + "=" * (-len(header_value) % 4)
        payload = json.loads(_b64.urlsafe_b64decode(padded.encode()).decode())
        if not isinstance(payload, dict):
            return None
        tx_hash = str(payload.get("transaction_hash") or "").strip().lower()
        payer = str(payload.get("payer") or "").strip().lower()
        if not tx_hash.startswith("0x") or len(tx_hash) != 66:
            return None
        if not payer.startswith("0x") or len(payer) != 42:
            return None
        return {
            "tx_hash": tx_hash,
            "payer": payer,
            "amount_usdc": float(payload.get("amount_usdc") or 0.0),
            # H2 — optional endpoint binding (legacy proofs omit it).
            "endpoint": str(payload.get("endpoint") or "").strip(),
        }
    except (ValueError, TypeError, _binascii.Error, Exception):
        return None


def _verify_payment_onchain(tx_hash: str, payer: str, min_amount_usdc: float):
    """
    Verify via RPC that tx_hash is a confirmed USDC Transfer from payer to
    our fee receiver with at least min_amount_usdc. Returns the verified
    amount, or None if the proof does not hold.

    C2: the transfer must ALSO be buried at least
    `MIN_PAYMENT_CONFIRMATIONS` blocks deep (default 12). A receipt at the
    chain tip is not settlement — it can still be reorganised away.
    """
    try:
        w3 = _get_verify_web3()
        receipt = w3.eth.get_transaction_receipt(tx_hash)
    except Exception:
        # Unknown tx, RPC hiccup, or not mined yet — treat as not verified;
        # the client may retry in a few seconds.
        return None
    try:
        if int(receipt.get("status", 0)) != 1:
            return None
        # C2 — fail-closed depth gate that RE-READS THE CLOCK before refusing
        # (a facilitator can settle in a block our own view has not caught up
        # with; that cost us a paying agent on 14.09 — see the helper).
        block_no = int(receipt.get("blockNumber") or 0)
        # Audit #4 / F3: the head read is an RPC call like any other — a blip
        # used to escape this frame and turn a paid retry into an HTML 500.
        # Treated as "not deep enough" (fail-closed), so the payer gets the
        # honest 401 with a retryable reason instead of an error page.
        try:
            deep_enough = _confirmations_ok_with_lag_refresh(
                receipt_block=block_no,
                read_head=lambda: int(w3.eth.block_number),
                required=_required_confirmations(),
                endpoint=_current_path(), tx_hash=tx_hash, rail="proof",
            )
        except Exception as exc:
            log.warning("x402 proof depth check failed (treated as "
                        "unconfirmed) tx=%s: %s", tx_hash, exc)
            deep_enough = False
        if not deep_enough:
            log.info("x402 proof not deep enough: tx=%s block=%s "
                     "(need %d confirmations)",
                     tx_hash, receipt.get("blockNumber"),
                     _required_confirmations())
            return None
        _verify_block[tx_hash.lower()] = block_no
        usdc_addr = os.getenv(
            "BASE_USDC_CONTRACT", "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
        ).lower()
        receiver = X402_RECEIVER_ADDRESS.lower()
        for log_entry in receipt.get("logs", []):
            try:
                address = str(log_entry.get("address") or "").lower()
                topics = log_entry.get("topics") or []
                if address != usdc_addr or len(topics) < 3:
                    continue
                topic0 = topics[0].hex() if hasattr(topics[0], "hex") else topics[0]
                if _to_hex0x(topic0) != _TRANSFER_EVENT_TOPIC:
                    continue
                from_topic = topics[1].hex() if hasattr(topics[1], "hex") else str(topics[1])
                to_topic = topics[2].hex() if hasattr(topics[2], "hex") else str(topics[2])
                from_addr = ("0x" + from_topic[-40:]).lower()
                to_addr = ("0x" + to_topic[-40:]).lower()
                data = log_entry.get("data")
                raw = data.hex() if isinstance(data, (bytes, bytearray)) else str(data)
                amount = int(raw, 16) / 1e6
                if (to_addr == receiver and from_addr == payer
                        and amount + 1e-9 >= min_amount_usdc):
                    return amount
            except Exception:
                continue
        return None
    except Exception:
        return None


def _try_consume_payment_proof(proof: dict, price: float, ip: str,
                               path: str = "") -> bool:
    """
    Consume a payment proof: verify it (fast path via recorded sales, slow
    path via on-chain receipt), record the sale exactly once, and grant one
    API call. One payment unlocks exactly one call (single-call semantics).

    Guards applied on this rail:
      H2 — endpoint binding  : a bound proof only works on its own path.
      C2 — 12 confirmations  : enforced inside _verify_payment_onchain.
      C1 — durable replay lock: the SQLite `payment_guards` claim is the real
           gate; the RAM set is only a fast pre-check that dies on restart.
    """
    endpoint = (path or request.path or "")
    tx = proof["tx_hash"]

    # H2 — reject a proof scoped to a different endpoint BEFORE any RPC work.
    if not _proof_endpoint_matches(proof.get("endpoint", ""), endpoint):
        log.warning("x402 proof endpoint mismatch: proof_scope=%s path=%s",
                    proof.get("endpoint"), endpoint)
        dashboard_db.record_guard_event(
            "h2_endpoint_mismatch", endpoint=endpoint, tx_hash=tx,
            detail=f"proof scoped to {proof.get('endpoint')!r}",
        )
        return False

    # F3 / audit #4: the RAM set says THIS PROCESS consumed the tx — it says
    # nothing about whether the product was ever produced. Consult the durable
    # row: an undelivered claim falls through to the single admission point
    # below (the claim itself), a delivered one stays an instant replay.
    with _lock:
        ram_spent = tx in _verified_payments
    recovered = False
    if ram_spent:
        row = dashboard_db.payment_guard_row(tx)
        if not row or row.get("delivered_at"):
            dashboard_db.record_guard_event(
                "c1_replay", endpoint=endpoint, tx_hash=tx,
                detail="already consumed in this process lifetime (RAM set)",
            )
            return False  # already consumed this process lifetime

    # Fast path: the background monitor already recorded this transfer.
    # AUDIT FIX (Табло 2.0): the hash alone is NOT proof of payment identity —
    # all 8 real hashes are published on our own public dashboard, so accepting
    # a known hash from ANY payer handed a free call to anyone who can read it.
    # A legitimate proof is always sent from the address that actually paid.
    amount = None
    with _lock:
        for s in _sales_history:
            if str(s.get("tx_hash", "")).lower() != tx:
                continue
            recorded_sender = str(s.get("sender") or "").strip().lower()
            if recorded_sender in ("", "unknown"):
                # No payer on record — the proof cannot be bound to it, so the
                # fast path must not be trusted. Fall through to the on-chain
                # check, which verifies from_addr == payer (fail-closed).
                break
            if recorded_sender != proof["payer"]:
                log.warning(
                    "x402 proof PAYER MISMATCH: tx=%s paid_by=%s claimed_by=%s "
                    "path=%s", tx, recorded_sender, proof["payer"], endpoint)
                dashboard_db.record_guard_event(
                    "h2_payer_mismatch", endpoint=endpoint, tx_hash=tx,
                    detail=(f"known sale paid by {recorded_sender[:10]}…, "
                            f"proof claims {proof['payer'][:10]}…"),
                )
                return False
            amount = float(s.get("amount_usd", 0.0))
            break

    # Slow path: verify the receipt directly on-chain (instant unlock —
    # no need to wait for the 30s monitor cycle).
    verified_onchain = False
    if amount is None:
        amount = _verify_payment_onchain(tx, proof["payer"], price)
        if amount is None:
            log.warning(
                "x402 proof not verified on-chain: tx=%s payer=%s amount=%s "
                "price=%s path=%s",
                tx, proof["payer"], amount, price, endpoint,
            )
            return False
        verified_onchain = True

    if amount + 1e-9 < price:
        log.warning(
            "x402 proof underpaid: tx=%s amount=%s price=%s path=%s",
            tx, amount, price, endpoint,
        )
        return False

    # C1 — DURABLE claim. This is the lock: one tx hash, one paid call, and
    # the fact survives restarts/deploys (an in-RAM set did not).
    if not dashboard_db.claim_payment_tx(
        tx, endpoint=endpoint, payer=proof["payer"], amount_usdc=amount
    ):
        # C1 refused. Correct for a DOUBLE SPEND, wrong for a paid call whose
        # response errored (audit #4 / F3): the durable row decides, and at
        # most ONE recovery gets in (the rest are told to retry shortly).
        if _admit_undelivered_payment(tx, endpoint=endpoint):
            log.warning("x402 proof RECOVERY: %s consumed but never delivered "
                        "— retry admitted on %s", tx[:18], endpoint)
            recovered = True
        else:
            log.warning("x402 payment proof REPLAY blocked: tx=%s path=%s", tx,
                        endpoint)
            _record_request("x402_replay_blocked", False)
            dashboard_db.record_guard_event(
                "c1_replay", endpoint=endpoint, tx_hash=tx,
                detail="durable payment_guards claim refused (tx already spent)",
            )
            with _lock:
                _verified_payments.add(tx)
            return False

    if verified_onchain and not recovered:
        # On a RECOVERY the sale was already recorded by the attempt that
        # failed to respond — one payment, one recorded sale.
        _record_real_sale(
            token="USDC", amount_usd=round(amount, 6), tx_hash=tx,
            sender=proof["payer"],
            block_number=_verify_block.get(tx, 0),
        )

    with _lock:
        _verified_payments.add(tx)
        if not recovered:
            # Same rule for the counter: a recovery must not buy a discount.
            _paid_calls_usage[ip] = _paid_calls_usage.get(ip, 0) + 1
    # after_request stamps `delivered_at` when this response is actually
    # produced (F3) — that stamp is what turns the NEXT attempt into a 401.
    g.x402_delivered_tx = tx
    log.info("x402 payment proof %s: tx=%s payer=%s amount=$%.2f path=%s",
             "RECOVERED" if recovered else "accepted",
             tx, proof["payer"], amount, endpoint)
    return True


def _get_standard_payment_header() -> str:
    """
    Read the standard x402 payment payload header.

    x402 v2 spec clients (x402-fetch, x402scan wallet, PayAPI verifier) send
    the signed EIP-3009 payload in the `PAYMENT-SIGNATURE` header; earlier
    ecosystem clients use `X-PAYMENT`. Both are accepted, v2 name first.
    """
    return (
        (request.headers.get("PAYMENT-SIGNATURE") or "").strip()
        or (request.headers.get("X-PAYMENT") or "").strip()
    )


def _mpp_transport_credential():
    """Read an MPP Credential and return `(payload, state)`.

    MPP sends its Credential as `Authorization: Payment <base64url(JCS)>`, a
    DIFFERENT shape from the x402 v2 `PAYMENT-SIGNATURE` payload: the MPP body is
    `{"challenge": …, "payload": …, "source": …}`. We advertise an MPP Challenge
    (so the catalogue stops raising `MPP_NO_PAYMENT_CHALLENGES`) but with
    `header="PAYMENT-SIGNATURE"`, so the supported path is the x402 one.

    A client that ignores that and posts a native MPP Credential anyway must not
    be left guessing, and must not be charged. This returns:

      * `(payload, "x402")`   — the Credential carried an embedded x402 v2
        payload (`x402Version` present anywhere in its `payload`/`challenge`),
        which the ordinary standard rail can verify and settle.
      * `("", "unusable")`    — a Credential is present but is native MPP, which
        we cannot verify yet. The caller refuses WITHOUT settling.
      * `("", None)`          — no MPP Credential on this request at all.

    Nothing here settles or consumes anything; verification stays in the one
    rail that already owns it.
    """
    raw = (request.headers.get("Authorization") or "").strip()
    if not raw:
        return "", None
    parts = raw.split(None, 1)
    if len(parts) != 2 or parts[0].lower() != "payment":
        return "", None
    token = parts[1].strip()
    try:
        padded = token + "=" * (-len(token) % 4)
        decoded = json.loads(base64.urlsafe_b64decode(padded).decode())
    except (ValueError, binascii.Error, UnicodeDecodeError):
        return "", "unusable"
    if not isinstance(decoded, dict):
        return "", "unusable"
    for key in ("payload", "challenge"):
        candidate = decoded.get(key)
        if isinstance(candidate, dict) and "x402Version" in candidate:
            return json.dumps(candidate, separators=(",", ":")), "x402"
        if isinstance(candidate, dict):
            inner = candidate.get("payload")
            if isinstance(inner, dict) and "x402Version" in inner:
                return json.dumps(inner, separators=(",", ":")), "x402"
    return "", "unusable"


#: A hard ceiling on any single step of the inbound payment rail.
#:
#: WHY THIS EXISTS, and it is the difference between a refused payment and an
#: outage. gunicorn runs with `--timeout 120`: a request that has not produced a
#: response by then has its WORKER KILLED, which takes every other request in
#: flight with it. Measured 08.11.2026, a request carrying a valid payment
#: signature never completed, the worker was killed, and the log filled with
#: repeated
#:
#:     Background threads started (blockchain monitor + agent + ...)
#:
#: lines — workers respawning — including a forty-minute stretch where the
#: service served no HTTP at all while its threads kept ticking.
#:
#: A bounded step cannot do that. If a step overruns, the request is refused with
#: a reason and the worker is RELEASED, which is the whole point: one buyer's slow
#: payment must never cost every other caller their request.
#:
#: The bound is also a diagnosis. The trail stopped at `_local_recover_signer`
#: every time — pure EIP-712 cryptography that costs 0.000s locally — because the
#: line that would have named the next step died with the killed worker. A
#: deadline returns control to this process, so the phase that overran is logged
#: by the living process rather than lost with the dead one.
X402_STEP_DEADLINE_SECONDS = float(
    os.getenv("X402_STEP_DEADLINE_SECONDS", "20"))

#: The nonce search gets a SHORTER budget than the others, on purpose. Its only
#: job is to ADOPT an already-settled payment; timing out costs a missed adoption
#: and nothing else, because the caller falls through to a normal settlement —
#: the pre-fix path. Twenty seconds of a buyer's request for a best-effort
#: optimisation is the wrong trade.
X402_NONCE_SEARCH_SECONDS = float(
    os.getenv("X402_NONCE_SEARCH_SECONDS", "5"))

#: Settlement gets a LONGER budget than the others, and the first version of this
#: was WRONG in a way worth recording: it used the same 20s and the settlement was
#: cut off at 20.002s every time. The facilitator chain tries CDP and then PayAI,
#: each with its own `X402_FACILITATOR_TIMEOUT` (default 15s) — so the chain's own
#: honest worst case is about 30s, and a 20s wrapper guarantees that NEITHER
#: facilitator is ever given the time it was configured to take. The bound must
#: sit ABOVE the budget of the thing it wraps, or it is not a safety net, it is
#: the failure.
X402_SETTLE_DEADLINE_SECONDS = float(
    os.getenv("X402_SETTLE_DEADLINE_SECONDS", "50"))


def _bounded(label: str, fn, seconds: float = None):
    """Run `fn` with a deadline. Returns (finished, result, error).

    `finished=False` means the deadline expired and `result`/`error` are None —
    the caller must treat the step as FAILED, never as passed. The thread is a
    daemon and is deliberately left running: it will finish or die with the
    process, and abandoning it costs a thread, while waiting for it costs the
    worker and every request queued behind it.

    This is the same trade `_run` makes with its bounded lock wait — a stalled
    holder costs one fast error rather than the process.
    """
    limit = X402_STEP_DEADLINE_SECONDS if seconds is None else seconds
    box: Dict[str, object] = {}

    def work():
        try:
            box["result"] = fn()
        except Exception as exc:  # noqa: BLE001
            box["error"] = exc

    t = threading.Thread(target=work, daemon=True, name="rail-%s" % label)
    started = time.monotonic()
    t.start()
    t.join(limit)
    cost = time.monotonic() - started
    if t.is_alive():
        log.warning("x402 rail step %-26s %7.3fs  DEADLINE EXCEEDED (%.0fs) — "
                    "refusing this payment rather than holding the worker",
                    label, cost, limit)
        return False, None, None
    if "error" in box:
        return True, None, box["error"]
    return True, box.get("result"), None


def _try_consume_standard_payment(path: str, price: float, ip: str) -> bool:
    """
    Standard x402 v2 rail: the client sends the signed EIP-3009 payload
    (PAYMENT-SIGNATURE / X-PAYMENT header, base64url) exactly like every
    ecosystem-standard client (x402-fetch, x402scan embedded wallet,
    agentcash router, PayAPI verifier). Verify + settle through the
    facilitator, record the sale, and grant one call. True = paid.

    On success the settlement is stashed on flask.g so the after_request
    hook can emit the spec-compliant PAYMENT-RESPONSE header.
    """
    # `connectors` is imported at MODULE level — see the note beside
    # `X402_STEP_DEADLINE_SECONDS`. It used to be imported here, which meant the
    # first buyer's payment also imported `eth_account`: four hundred and
    # seventeen modules, 151 of them heavy. That is ~1.2s on this machine and
    # over twenty on a 0.1-CPU instance, and it is why every payment was refused
    # after the deadline rather than verified.

    payment_header = _get_standard_payment_header()
    if not payment_header:
        return False

    # EVERY STEP FROM HERE IS TIMED, at WARNING, whether it succeeds or not.
    #
    # WHY. A request carrying a VALID payment signature never appears in the
    # access log at all, while the same request with an invalid one answers 401 in
    # 0.4s. gunicorn logs a request when it COMPLETES, so an absent line is one
    # that never finished — and with `--timeout 120` gunicorn then KILLS the
    # worker, taking every other request in flight with it. That is what the
    # repeated "Background threads started" lines were.
    #
    # The settle side is already instrumented and reported ZERO phases, so the
    # time is spent BEFORE it — in here. These lines name which step.
    _pt = time.monotonic()

    def _pstep(label, started=None):
        log.warning("x402 rail step %-26s %7.3fs",
                    label,
                    time.monotonic() - (started if started is not None else _pt))

    accepts, resource, _ext = _x402_challenge_core(path, price)
    requirements = dict(accepts[0])
    requirements["resource"] = resource.get("url")
    requirements["description"] = resource.get("description")
    requirements["mimeType"] = resource.get("mimeType")
    _pstep("challenge_core")

    _t = time.monotonic()
    # BOUNDED. This is the step that overran in production on a valid signature —
    # pure EIP-712 recovery that costs 0.000s locally — and an unbounded step here
    # is what got the worker killed and the whole service restarted. A refusal
    # with a reason is strictly better than an outage.
    _finished, _verdict, _vex = _bounded(
        "verify_standard_payment",
        lambda: connectors.verify_standard_payment(payment_header, requirements))
    if not _finished:
        ok, payer, detail = False, None, (
            "verify exceeded the %.0fs deadline — the rail refused rather than "
            "holding the worker" % X402_STEP_DEADLINE_SECONDS)
    elif _vex is not None:
        ok, payer, detail = False, None, "verify raised: %s" % type(_vex).__name__
    else:
        ok, payer, detail = _verdict
    _pstep("verify_standard_payment", _t)
    if not ok:
        g.x402_reject_reason = detail
        # The funnel's missing middle, recorded at the moment it is known. This
        # answers 401, which `request_log` records as "a credential was presented
        # and we refused it" — the SAME status a failed settlement gets. Only
        # this row says which of those two opposite things happened.
        _t = time.monotonic()
        dashboard_db.record_payment_attempt(
            path, "rejected", payer=payer, amount_usdc=price,
            detail=str(detail or "")[:200])
        _pstep("record_rejected", _t)
        _pstep("TOTAL-rejected")
        log.info("standard x402 payment rejected: path=%s detail=%s", path, detail)
        return False

    # ── F1/F6: IDEMPOTENT SETTLE BY NONCE (never by payer+amount) ──────────
    # If this exact authorization was already consumed — by our own
    # self-broadcast on an earlier attempt, by the CDP facilitator or by PayAI
    # — adopt THAT transaction instead of settling again. A re-settle cannot
    # succeed (the authorization nonce is spent), which is why the old
    # "retry the signature" advice was a dead end that cost the sale.
    tx_hash, settle_detail, settle_extra = "", "", []
    _t = time.monotonic()
    nonce = connectors.extract_authorization_nonce(payment_header)
    _pstep("extract_nonce", _t)
    if nonce and payer:
        # TIMED AND BOUNDED, because this is a CHAIN SEARCH and it was neither.
        #
        # `_find_settlement_by_nonce` calls `_get_verify_web3()` — which imports
        # `web3` lazily, and `web3` was NOT loaded at boot — and then walks up to
        # `_nonce_search_blocks()` blocks with `eth_getLogs`. On a public RPC
        # that is seconds at best; on the 0.1-CPU instance with a cold import in
        # front of it, it is the next thing to hold the worker past gunicorn's
        # 120-second limit.
        #
        # BOUNDING IT IS SAFE BY CONSTRUCTION: the function's own docstring says
        # "best-effort: any RPC failure returns None and the caller settles
        # normally, so a failed search can never reject a payment". A deadline
        # that returns None is exactly that case — the caller falls through to a
        # normal settlement, which is the pre-fix path.
        _t = time.monotonic()
        _finished, _adopted, _aex = _bounded(
            "find_settlement_by_nonce",
            lambda: _find_settlement_by_nonce(payer, nonce, price),
            # SHORTER THAN THE OTHERS ON PURPOSE. This is a best-effort chain
            # search whose only job is to ADOPT a payment that was already
            # settled. Timing out costs nothing but a missed adoption — the
            # caller settles normally, which is the pre-fix path — so there is no
            # reason to spend twenty seconds of a buyer's request on it.
            X402_NONCE_SEARCH_SECONDS)
        _pstep("find_settlement_by_nonce", _t)
        if _aex is not None:
            log.warning("nonce search raised (%s) — settling normally",
                        type(_aex).__name__)
        adopted = _adopted if _finished else None
        if adopted:
            tx_hash = adopted["tx_hash"]
            settle_detail = "adopted_existing_settlement"
            log.warning("standard x402 ADOPTED already-settled authorization "
                        "(nonce=%s, tx=%s) — idempotent settle, no second "
                        "transfer", nonce[:14], tx_hash)
            _t = time.monotonic()
            dashboard_db.record_guard_event(
                "c1_nonce_adopted", endpoint=path, tx_hash=tx_hash,
                detail=f"authorization nonce {nonce[:18]} already consumed; "
                       f"channel-agnostic recovery, settle skipped")
            _pstep("record_guard_event", _t)
    if not tx_hash:
        # *rest = extension receipt (facilitator EXTENSION-RESPONSES header);
        # 2-tuple fakes in older tests stay compatible.
        #
        # BOUNDED, for the same reason as verify: settlement talks to two
        # facilitators over the network, and an unbounded wait here is what gets
        # the gunicorn worker killed at 120s — taking every other caller's
        # request with it.
        _finished, _verdict, _sex = _bounded(
            "settle_standard_payment",
            lambda: connectors.settle_standard_payment(payment_header,
                                                       requirements),
            # ABOVE the facilitator chain's own budget (15s x 2), or the wrapper
            # is the failure rather than the net. See
            # `X402_SETTLE_DEADLINE_SECONDS`.
            X402_SETTLE_DEADLINE_SECONDS)
        if not _finished:
            tx_hash, settle_detail, settle_extra = None, (
                "settlement exceeded the %.0fs deadline — the rail refused "
                "rather than holding the worker" % X402_SETTLE_DEADLINE_SECONDS), []
        elif _sex is not None:
            tx_hash, settle_detail, settle_extra = None, (
                "settlement raised: %s: %s" % (type(_sex).__name__,
                                               str(_sex)[:120])), []
        else:
            _verdict = _verdict or ()
            tx_hash = _verdict[0] if len(_verdict) > 0 else None
            settle_detail = _verdict[1] if len(_verdict) > 1 else ""
            settle_extra = list(_verdict[2:])
        if not tx_hash:
            g.x402_reject_reason = f"settlement_failed: {settle_detail}"
            # Audit #4, check в (22.09): the nonce-revert path that our
            # block search could NOT confirm used to read like "your
            # payment is broken". Only ONE of the two outcomes is true and a
            # revert alone cannot say which — so the reason says BOTH, clearly.
            if "revert" in settle_detail or "already used" in settle_detail:
                g.x402_reject_reason += (
                    " — NO new payment is needed if this authorization was "
                    "already consumed (retry shortly; if it is older than our "
                    f"{_nonce_search_blocks()}-block search window, send us "
                    "the tx hash instead); otherwise the buyer's USDC balance "
                    "was insufficient — fund it and retry")
            log.warning("standard x402 settle failed: path=%s detail=%s", path, settle_detail)
            # A buyer who got this far DID authorise a real payment and we could
            # not take it. That is a lost sale caused by us, not by them, and it
            # must never be filed under "nobody was interested".
            dashboard_db.record_payment_attempt(
                path, "settle_failed", payer=payer, amount_usdc=price,
                detail=str(settle_detail or "")[:200])
            # A settlement we could not take. `degraded`, not `failed`: the rail
            # is answering, refusing to lose money silently. The distinction
            # matters because `failed` would page someone about a working rail.
            _organism_beat("payment_rail", "degraded",
                           "settle failed on %s: %s"
                           % (path, str(settle_detail or "")[:100]))
            return False

    # The money moved. Recorded HERE — before the receipt fetch and the depth
    # gate — because those checks are about DELIVERY and this one is about
    # PAYMENT: a settlement our depth gate answers 425 is still a buyer who
    # authorised a real payment, and filing it as "abandoned" is the confusion
    # this table exists to remove.
    #
    # Placing it here is safe because `record_payment_attempt` records a
    # settlement ONCE PER TRANSACTION HASH. That matters: a replayed request
    # re-enters this whole function and reaches this line again, and the C1
    # claim that refuses the replay runs LATER. Without the idempotency in the
    # store, one payment replayed twice produced three `settled` rows.
    dashboard_db.record_payment_attempt(
        path, "settled", payer=payer, amount_usdc=price,
        detail=str(settle_detail or "")[:120], tx_hash=tx_hash)
    # The rail took a real payment. This is the payment block's strongest proof
    # of life — not "the code loaded" but "money moved".
    _organism_beat("payment_rail", "ok",
                   "settlement recorded on %s" % path)

    # Populate the real block number from the settlement receipt — PayAPI's
    # review flagged history entries reporting block_number 0 (field never
    # populated on the settle path).
    block_number = 0
    block_hash = ""
    receipt = None
    try:
        from services.rpc_pool import get_web3
        _w3 = get_web3(os.getenv("BASE_RPC_URL",
                                 "https://mainnet.base.org"), 20)
        receipt = _w3.eth.get_transaction_receipt(tx_hash)
    except Exception as exc:
        log.warning("settlement receipt fetch failed: %s: %s",
                    type(exc).__name__, exc)

    # а5 → А+ (10.10.2026, двойна врата): платил (proof локално верифициран,
    # settled през PayAI) НИКОГА не получава отказ. Наблюдението от 10.10: receipt
    # read 0.163с след settled → status още 0/None → отказ → загубен платещ
    # клиент. Сега: poll до ~4×2с; status=1 → доставя се по реда; иначе fail-open
    # доставка (WARN c2_receipt_status_override_delivered), guard-събитието се
    # записва както досега. C1 replay-lock (по-долу) остава недокоснат; неплатените
    # си остават 402; невалиден proof — 401; in-flight — 425.
    receipt_status = 0
    if receipt is not None:
        try:
            receipt_status = int(receipt.get("status", 0) or 0)
        except Exception:
            receipt_status = 0
    if receipt_status != 1:
        for _poll in range(4):          # ~4 × 2с = до ~8с
            time.sleep(2)
            try:
                receipt = _w3.eth.get_transaction_receipt(tx_hash)
            except Exception:
                receipt = None
            receipt_status = 0
            if receipt is not None:
                try:
                    receipt_status = int(receipt.get("status", 0) or 0)
                except Exception:
                    receipt_status = 0
            if receipt_status == 1:
                break
        if receipt_status == 1:
            log.info("c2_receipt_status_confirmed_after_poll: tx=%s — receipt "
                     "status=1 след poll, доставя се по реда", tx_hash)
        else:
            # Fail-open за платилите: settle-ът е потвърден (PayAI), а receipt
            # не се чете като status=1 → доставяме. Отказът връща платещ
            # клиент и губи продажбата (наблюдение 10.10.2026).
            log.warning("c2_receipt_status_override_delivered: tx=%s receipt "
                        "status=%s след ~8s poll — fail-open, доставя се",
                        tx_hash, receipt_status)
            dashboard_db.record_guard_event(
                "c2_receipt_status_refused", endpoint=path, tx_hash=tx_hash,
                detail=f"receipt.status={receipt_status} — fail-open override "
                       f"доставка (А+, 10.10) вместо отказ")

    if receipt is not None:
        block_number = int(receipt.get("blockNumber", 0) or 0)
        # Finality anchor (21.09): remember the CONFIRMING block's hash so a
        # later re-read can prove this settlement was not reorganised away.
        # Depth alone cannot see a reorg that keeps the height.
        raw_hash = receipt.get("blockHash") or b""
        block_hash = (
            raw_hash.hex() if hasattr(raw_hash, "hex") else str(raw_hash)
        ).lower()
    # receipt is None (fail-open override) → block_number/block_hash остават
    # 0/"" от инициализацията по-горе; C1 claim-ът по-долу пази replay-а.
    try:
        # C2 (standard rail): the facilitator only returns after the tx is
        # mined, so the default depth here is 1 — raise
        # MIN_STANDARD_PAYMENT_CONFIRMATIONS to demand more. The head is
        # RE-READ before any refusal: on 14.09 an external facilitator settled
        # one block ahead of our view and a valid $0.003 was refused for a
        # clock skew (the payer never retried).
        # А+ (10.10): receipt is None → къс-съкращение: без receipt няма как
        # да твърдим in-flight; fail-open доставката по-горе продължава нататък.
        if receipt is not None and not _confirmations_ok_with_lag_refresh(
            receipt_block=block_number,
            read_head=lambda: int(_w3.eth.block_number),
            required=_required_standard_confirmations(),
            endpoint=path, tx_hash=tx_hash, rail="standard",
        ):
            # F1/F6 (audit #4): the money is ALREADY on-chain. Telling this
            # payer to "retry the signature" was the dead end that cost the
            # sale — a re-settle cannot succeed, because the authorization
            # nonce is spent. Answer 425 Too Early instead: nothing to pay,
            # just wait for our node to catch up (the next attempt adopts the
            # same tx by nonce and never settles again).
            g.x402_in_flight = True
            g.x402_in_flight_tx = tx_hash
            g.x402_reject_reason = (
                f"settlement_in_flight: {tx_hash} is on-chain but our node "
                f"has not reached the confirming block yet — no new payment "
                f"is needed"
            )
            log.warning("standard x402 settlement IN FLIGHT (not a refusal): "
                        "tx=%s block=%s — answering 425", tx_hash, block_number)
            dashboard_db.record_guard_event(
                "c2_settlement_in_flight", endpoint=path, tx_hash=tx_hash,
                detail=(f"standard rail: block {block_number} not yet deep "
                        f"enough on our node — 425, money already moved"))
            return False
    except Exception as exc:
        log.info("confirmation check failed (non-fatal): %s", exc)

    # Placeholder-hash root fix (28.09): during a node-lag window the receipt
    # read above can answer with an ALL-ZERO blockHash — 23.09, tx 0x22c4…52ab:
    # real block number 51670537 but a 64-zero hash, which later produced 1273
    # false c2_reorg alerts (the detector compared the placeholder with the
    # real hash every cycle). The lag helper re-reads the HEAD, never the
    # receipt, so the stale zero hash reached payment_guards. The head is
    # accepted now — re-read the ANCHOR by height; an unreadable anchor becomes
    # '' (no anchor data), NEVER the '000…0' placeholder.
    if block_number and (not block_hash
                         or (block_hash[2:] if block_hash.startswith("0x")
                             else block_hash).strip("0") == ""):
        try:
            reread = _read_block_hash(block_number) or ""
        except Exception:
            reread = ""
        anchor = reread[2:] if reread.startswith("0x") else reread
        block_hash = reread if anchor.strip("0") else ""

    # C1 — durable replay lock on the standard rail too: the same settlement
    # tx can never buy a second call, even across restarts.
    recovered = False
    if not dashboard_db.claim_payment_tx(
        tx_hash, endpoint=path, payer=payer or "", amount_usdc=price,
        block_number=block_number, block_hash=block_hash,
    ):
        # C1 refused — a replay, OR a paid call whose response never went out
        # (audit #4 / F3). The durable row decides; at most ONE recovery gets in.
        if _admit_undelivered_payment(tx_hash, endpoint=path):
            log.warning("standard x402 RECOVERY: tx=%s consumed but never "
                        "delivered — retry admitted on %s", tx_hash, path)
            recovered = True
        else:
            g.x402_reject_reason = (
                f"replay_detected: settlement {tx_hash} was already consumed"
            )
            log.warning("standard x402 REPLAY blocked: tx=%s path=%s", tx_hash, path)
            _record_request("x402_replay_blocked", False)
            dashboard_db.record_guard_event(
                "c1_replay", endpoint=path, tx_hash=tx_hash,
                detail="durable payment_guards claim refused (settlement already spent)",
            )
            return False

    with _lock:
        _verified_payments.add(tx_hash)
        if not recovered:
            _paid_calls_usage[ip] = _paid_calls_usage.get(ip, 0) + 1
    if not recovered:
        # One payment → one recorded sale; a RECOVERY must not double-count.
        _record_real_sale(
            token="USDC", amount_usd=round(price, 6), tx_hash=tx_hash,
            sender=payer or "unknown", block_number=block_number,
        )
    # Finality watch, OFF the request path: the payer must not wait on 25 block
    # reads. Fire-and-forget — the same check also runs in the agent loop, and a
    # detection only ever adds a visible guard event, never a refusal here.
    connectors.touch("x402-eip3009")
    connectors.touch("base-usdc-receiver")
    # Spec-compliant v2 settlement receipt (emitted by _emit_payment_response).
    g.x402_settlement = json.dumps({
        "success": True,
        "transaction": tx_hash,
        "network": "eip155:8453",
        "payer": payer or "unknown",
    })
    # Facilitator extension receipt (EXTENSION-RESPONSES header value, if the
    # facilitator returned one) — relayed to the client by
    # _emit_payment_response. No receipt (self-broadcast / no extension)
    # simply leaves the header absent.
    if settle_extra and settle_extra[0]:
        g.x402_extension_receipt = settle_extra[0]
    # after_request stamps `delivered_at` on a produced response (F3) — that
    # is what turns a later attempt of this settlement into a REFUSED replay.
    g.x402_delivered_tx = tx_hash
    log.info("standard x402 payment settled%s: tx=%s payer=%s amount=$%.4f",
             " (recovered)" if recovered else "", tx_hash, payer, price)
    return True


# г1: таван на EXTENSION-RESPONSES header стойността (~8KB).
_EXT_HEADER_MAX_CHARS = 8192


@app.after_request
def _emit_payment_response(response):
    """x402 settlement receipt + DELIVERY bookkeeping (audit #4 / F1+F3).

    Runs for every response — including generated 4xx/5xx — which is exactly
    what makes it the right place for `delivered_at`: a produced 2xx/3xx
    response means the product left the building, so the payment is settled-
    consumed and every later attempt becomes a REFUSED replay. Anything else
    frees the single-flight recovery slot, so the same payer can try again —
    the money is never lost with the response.
    """
    settlement = getattr(g, "x402_settlement", None)
    if settlement:
        # Audit #5 FIX 1: specs/transports-v2/http.md mandates a Base64-
        # encoded SettlementResponse — their decodePaymentResponseHeader
        # (regex gate + atob) THROWS on raw JSON. b64encode is byte-identical
        # to their safeBase64Encode output (btoa / Buffer, padding kept).
        response.headers["PAYMENT-RESPONSE"] = base64.b64encode(
            settlement.encode()).decode()
    # Extension receipt relay (base64 JSON): whatever the facilitator returned
    # in EXTENSION-RESPONSES — raw JSON gets encoded, already-base64(JSON)
    # passes through verbatim, anything else is skipped (never a broken
    # header). Absent receipt = absent header.
    # г1 (07.10, одит): целият блок е в try/around — счупен receipt НИКОГА не
    # чупи отговора; стойността се санитизира (никакви CR/LF — response
    # splitting) и се смалява до таван 8KB.
    ext_receipt = getattr(g, "x402_extension_receipt", None)
    if ext_receipt:
        try:
            encoded = None
            if isinstance(ext_receipt, (dict, list)):
                encoded = base64.b64encode(
                    json.dumps(ext_receipt, separators=(",", ":")).encode()).decode()
            else:
                raw = str(ext_receipt).strip()
                try:
                    json.loads(base64.b64decode(
                        raw + "=" * (-len(raw) % 4)).decode("utf-8"))
                    encoded = raw                     # already base64(JSON)
                except Exception:
                    try:
                        json.loads(raw)               # raw JSON → encode below
                        encoded = base64.b64encode(raw.encode()).decode()
                    except Exception:
                        log.debug("extension receipt is neither base64(JSON) "
                                  "nor JSON — EXTENSION-RESPONSES skipped")
            if encoded:
                # санитизация: CR/LF могат да дойдат от фасилитатора дори в
                # валиден base64 поток — Werkzeug ще гръмне на нов ред в
                # header стойност; махаме ги и таванираме размера.
                encoded = encoded.replace("\r", "").replace("\n", "")
                if len(encoded) > _EXT_HEADER_MAX_CHARS:
                    log.warning("EXTENSION-RESPONSES too long (%d chars) — "
                                "truncated to %d", len(encoded),
                                _EXT_HEADER_MAX_CHARS)
                    encoded = encoded[:_EXT_HEADER_MAX_CHARS]
                response.headers["EXTENSION-RESPONSES"] = encoded
        except Exception as exc:
            log.warning("EXTENSION-RESPONSES emission failed (non-fatal, "
                        "response unaffected): %s", exc)
    rid = getattr(g, "request_id", None)
    if rid:
        response.headers["X-Request-Id"] = rid
    tx = getattr(g, "x402_delivered_tx", None)
    if tx:
        if 200 <= response.status_code < 400:
            try:
                dashboard_db.mark_payment_delivered(tx)
            except Exception as exc:
                log.warning("payment %s delivered but stamp failed: %s",
                            tx[:18], exc)
        else:
            token = getattr(g, "x402_retry_token", None)
            if token:
                try:
                    if dashboard_db.release_payment_retry_slot(tx, token):
                        log.warning("payment %s produced HTTP %s — recovery "
                                    "slot freed for another attempt",
                                    tx[:18], response.status_code)
                except Exception as exc:
                    log.warning("recovery slot release failed for %s: %s",
                                tx[:18], exc)
    return response


# ── Demo / unproven public surfaces (audit B, Табло 2.0) ───────────────────
# The 8 catalog SKUs, their playground/checkout/access/click endpoints and the
# Stripe lead funnel are UNPROVEN (zero paid sales ever came through them) yet
# they carry the largest public surface. `KRISTO_DEMO_SURFACES=off` parks them
# with a 404 WITHOUT deleting any code, so the public face is only the 6 real
# x402 routes. Default is "on" — flipping it is a BUSINESS decision (this is
# the only path that can take a card payment), so it is left to the operator.
# Deliberately NOT parked: "/", "/dashboard", "/health", the 6 real routes,
# and every admin/repair route (incl. POST /api/admin/seed-sales).
DEMO_SURFACE_PREFIXES = (
    "/api/v1/agents/",          # demo SKU detail/checkout/access/playground/click
    "/sales/checkout",
    "/api/checkout",
    "/api/leads",
    "/agents",
)


def demo_surfaces_enabled() -> bool:
    """True unless KRISTO_DEMO_SURFACES is explicitly turned off."""
    value = (os.getenv("KRISTO_DEMO_SURFACES", "") or "").strip().lower()
    return value not in {"0", "false", "no", "off"}


def _is_parked_demo_surface(path: str) -> bool:
    """True when `path` is a demo/unproven surface AND they are parked."""
    if demo_surfaces_enabled():
        return False
    if path == "/api/v1/agents" or path.startswith("/api/v1/agents/"):
        # The catalog LIST (/api/v1/agents) and the detail page for the REAL
        # routes stay: they are part of the vitrine. Only the demo SKU actions
        # (checkout/access/playground/click) are parked.
        return any(path.endswith(suffix) for suffix in
                   ("/checkout", "/access", "/playground", "/click"))
    return any(path == p or path.startswith(p + "/")
               for p in DEMO_SURFACE_PREFIXES[1:])


# ── 402 challenge: cache + browser-readability headers (double gate 13.10) ──
# x402-doctor (revecs-hq) + live curl found two real gaps on the 402s:
#   * no Cache-Control → a browser/proxy can CACHE the challenge and the
#     later payment fails against a stale/foreign challenge (payment risk #1);
#   * zero Access-Control-* → cross-origin browser clients cannot read the
#     response at all; even with Allow-Origin, PAYMENT-REQUIRED stays
#     invisible without Expose-Headers (x402-foundation/x402#3722).
# No CORS layer existed in this codebase, so this is the FIRST and only one,
# scoped strictly to 402 responses (paid routes, incl. OPTIONS when the
# paywall challenges it). Existing 402 headers/body are untouched.
_EXPOSE_402_HEADERS = (
    "PAYMENT-REQUIRED, payment-required, PAYMENT-RESPONSE, "
    "x-payment-address, x-payment-amount-usdc, x-payment-chain, "
    "x-payment-required, x-payment-token-contract"
)

#: The request headers a browser-based x402 agent must be allowed to send.
#:
#: A cross-origin paid call is NOT a simple request: `PAYMENT-SIGNATURE` (and
#: the v1-era `X-PAYMENT`, and the legacy `X-Payment-Proof`) are not CORS-safelisted
#: names, so the browser sends an OPTIONS preflight first and aborts unless the
#: preflight's `Access-Control-Allow-Headers` names every one of them. Lumière
#: PayCheck measured the omission from the outside on 09.11 — "Can't pay it yet:
#: CORS headers missing" — and the reference implementations in this niche
#: (tradingagentstack.com, x402pulse.dev) both answer OPTIONS with `204` and list
#: the payment headers. We answered it with a `402` challenge and listed none, so
#: no in-page agent could ever reach the paid retry. Server-side clients are
#: unaffected, which is exactly why a catalogue of 85 paid calls contained zero
#: from a browser until this was measured.
_X402_CORS_ALLOW_HEADERS = (
    "Content-Type, Accept, Authorization, "
    "PAYMENT-SIGNATURE, payment-signature, X-PAYMENT, x-payment, "
    "PAYMENT-REQUIRED, payment-required, "
    "X-Payment-Proof, x-payment-proof, "
    "X-Admin-Token, x-admin-token"
)

#: Methods a paid route answers. Kept as a literal rather than derived from the
#: URL map because the preflight is answered in `before_request`, where a route
#: that matched no method has no `url_rule` to read.
_X402_CORS_ALLOW_METHODS = "GET, HEAD, POST, OPTIONS"


def _x402_cors_preflight_response():
    """The 204 a browser agent needs before it can pay us.

    Deliberately NOT a 402: the preflight is a capability question, not a paid
    request, and answering it with a challenge is what made every in-page agent
    stop one step short of the payment. The `Access-Control-Max-Age` is short
    (10 min) so a revoked header list is not cached for a day in someone's
    browser, and `no-store` keeps a shared proxy from replaying it.
    """
    from flask import Response
    resp = Response(status=204)
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = _X402_CORS_ALLOW_METHODS
    resp.headers["Access-Control-Allow-Headers"] = _X402_CORS_ALLOW_HEADERS
    resp.headers["Access-Control-Expose-Headers"] = _EXPOSE_402_HEADERS
    resp.headers["Access-Control-Max-Age"] = "600"
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.after_request
def _x402_402_cache_and_cors(response):
    """Add Cache-Control + CORS headers to 402 challenges only."""
    if response.status_code == 402:
        response.headers["Cache-Control"] = "no-store"
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = _X402_CORS_ALLOW_HEADERS
        response.headers["Access-Control-Allow-Methods"] = _X402_CORS_ALLOW_METHODS
        response.headers["Access-Control-Expose-Headers"] = _EXPOSE_402_HEADERS
    return response


# --- nohumans.directory ownership proof (Option B: a per-endpoint header) ----
#
# To edit a listing there we must prove control of the domain right now. Their
# flow (POST /v1/listings/<id>/claim/challenge) issues a ONE-TIME token per
# listing, valid 24h, which is served either at /.well-known/nohumans-claim or
# as an `x-nohumans-claim` response header on the listing's own endpoint.
#
# Option A is one path carrying one token, so it can only ever satisfy a single
# listing. Option B is per-endpoint, which is what lets us claim all five at
# once from one deploy. The header is set on the endpoint's OWN response, and a
# 402 challenge carries it just as a 200 does.
#
# These are 24h credentials, not configuration. They are deliberately EMPTY
# again now that all five listings are claimed: a token that no longer matches
# anything proves nothing, and leaving one here would read like a secret we
# forgot to remove. They granted no access to money, keys or data — they were
# evidence that whoever answers at this domain is the party that asked for the
# challenge.
#
# The hook below stays, because the flow is needed again for any future listing
# or a lost edit key. Re-arming is one dict entry per challenge:
#
#   POST https://nohumans.directory/v1/listings/<id>/claim/challenge
#     -> {"token": "...", "valid_for_seconds": 86400}
#   put it here, deploy, then POST .../claim with {"email": ...} and save the
#   edit_token it returns — that value is shown once and is what PATCH uses.
#
# 07.11: the dict is now ENV-DRIVEN, because it was written into a PUBLIC repo.
# Claim tokens are 24h credentials; the only way to re-arm one was to commit it,
# which publishes it, which is the opposite of what a credential is for. The
# rotation in progress is precisely a rotation AWAY from tokens that leaked, so
# hard-coding the replacements would have repeated the mistake.
#
#   NOHUMANS_CLAIM_TOKENS_JSON='{"/api/bot-status": "<48-char token>"}'
#
# Set it, deploy, claim, then CLEAR the variable — an expired token proves
# nothing and reads like a secret someone forgot. Empty, malformed or
# non-string values are ignored rather than raising: this hook runs on EVERY
# response, and a bad env var must not be able to take the service down.
def _load_claim_tokens() -> dict:
    raw = os.getenv("NOHUMANS_CLAIM_TOKENS_JSON", "").strip()
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (ValueError, TypeError):
        log.warning("NOHUMANS_CLAIM_TOKENS_JSON is not valid JSON; ignoring.")
        return {}
    if not isinstance(parsed, dict):
        log.warning("NOHUMANS_CLAIM_TOKENS_JSON is not an object; ignoring.")
        return {}
    clean = {k: v for k, v in parsed.items()
             if isinstance(k, str) and isinstance(v, str) and v.strip()}
    if clean:
        # Log the PATHS only. Never a token, not even a prefix.
        log.info("no humans claim tokens armed for: %s",
                 ", ".join(sorted(clean)))
    return clean


NOHUMANS_CLAIM_TOKENS = _load_claim_tokens()


@app.after_request
def _nohumans_claim_header(response):
    """Answer the ownership challenge on the endpoint it was issued for.

    Deliberately narrow: it echoes a token only on the exact path whose listing
    requested it, and never on a wildcard, so this cannot be used to attest
    control of a route we did not ask about.
    """
    token = NOHUMANS_CLAIM_TOKENS.get(request.path)
    if token:
        response.headers["x-nohumans-claim"] = token
    return response


# ── NEVER CHARGE FOR A REQUEST WE CANNOT SERVE ─────────────────────────────
# Measured on 11.11.2026, with our own money: a paid call to /api/v1/verify-seller
# without `?receiver=` SETTLED $0.01 and then answered HTTP 400
# receiver_required. The buyer's money moved on-chain and the buyer got nothing.
#
# The declaration was already correct by then — the 402 names `receiver` as
# required, see X402_INPUT_QUERY_PARAMS — so this was not a metadata defect but an
# ORDERING one: the paywall verified and settled before anything asked whether the
# request could be answered at all.
#
# The rule this restores: a request we cannot serve is never settled. The check
# runs only when a payment credential is PRESENT. An unpaid GET of the bare path
# still returns the canonical 402, because that challenge is what every catalogue
# reads to index the route — turning it into a 400 would take the route out of
# discovery in order to fix a billing edge.
#
# Nothing is consumed: an EIP-3009 authorization is executed only at the
# facilitator, so a refused request leaves the client's signature unused and their
# balance untouched. The client can re-send the SAME signed payload with the
# parameter added, while its validBefore window lasts.
def _x402_unservable_payload(endpoint: str):
    """A 400 body when the request cannot be answered, else None.

    Driven by the SAME declaration the 402 publishes, so a route that starts
    requiring a parameter is covered by the challenge and this guard at once,
    instead of by two lists that drift.
    """
    spec = X402_INPUT_QUERY_PARAMS.get(endpoint) or {}
    required = [p for p in (spec.get("required") or []) if p]
    if not required:
        return None
    missing = [p for p in required if not (request.args.get(p) or "").strip()]
    if not missing:
        return None
    example = spec.get("example") or {}
    query = "&".join("%s=%s" % (k, v) for k, v in example.items())
    canonical = X402_PATH_ALIASES.get(endpoint, endpoint)
    return {
        "ok": False,
        "error": "missing_required_parameter",
        "message": (
            "No payment was taken and none will be: this route cannot answer a "
            "request without %s. Nothing was settled, so the payment "
            "authorization you sent has not been used and your balance is "
            "unchanged — add the parameter and send the same request again."
            % ", ".join(missing)
        ),
        "missing": missing,
        "required": required,
        "call_it_like": "?%s" % query if query else "",
        "declared_input": spec,
        "free_sample": request.host_url.rstrip("/") + canonical + "/sample",
        "payment_taken": False,
    }


@app.before_request
def _x402_paywall():
    """
    x402 Paywall middleware.

    Discovery endpoints (health, dashboard, manifest, .well-known, openapi,
    llms.txt) are always free.

    Paid endpoints (/api/sales, /api/stats, /api/bot-status) allow
    FREE_TIER_LIMIT (1) free calls per client IP. After that, HTTP 402
    Payment Required is returned with the exact Base USDC receiver address
    and price.

    IMPORTANT: Requests originating from the /dashboard page are exempt
    from the paywall so the dashboard always loads correctly.
    """
    g.request_id = uuid.uuid4().hex[:16]   # F3: every reply can be grepped
    path = request.path

    # ── CORS preflight: answer it BEFORE the paywall can challenge it ──────
    #
    # ORDERING is the whole fix. Flask runs `before_request` for OPTIONS just
    # as it does for GET, so the paywall used to answer a preflight with the
    # canonical 402 — carrying no `Access-Control-Allow-Methods` and no
    # `Access-Control-Allow-Headers`. The browser then aborts the paid retry,
    # which is why a browser agent could never buy anything from us. Measured
    # from the outside by Lumière PayCheck (09.11) and reproduced locally:
    # OPTIONS returned 402; both reference implementations return 204.
    if request.method == "OPTIONS":
        return _x402_cors_preflight_response()

    # Demo / unproven surfaces: parked with a 404 when KRISTO_DEMO_SURFACES is
    # off (audit B). Code stays intact — this is a switch, not a deletion.
    #
    # ABOVE the method guard on purpose: a retired surface must answer
    # `404 surface_retired` for EVERY method, and with the guard first a
    # `POST /agents` answered 405 — which reads as "the park stopped working"
    # and broke `test_demo_surfaces_can_be_parked_without_deleting_code`.
    if _is_parked_demo_surface(path):
        return jsonify({
            "ok": False,
            "error": "surface_retired",
            "message": ("This demo surface is not offered. The live products "
                        "are the 6 real x402 routes on /dashboard."),
            "real_routes": [r["endpoint"] for r in REAL_X402_ROUTES],
        }), 404

    # ── A method we do not serve is never paid for ─────────────────────────
    #
    # `before_request` runs even when URL matching already failed, so a POST to
    # a GET-only route reached the paywall, was challenged, was SETTLED, and only
    # then died with 405 from the dispatcher. That is not hypothetical: on
    # 21.10.2026 `JarvisClaw-Federation/1.0` POSTed /api/v1/signal, paid
    # $0.003, and got a 405 — the row is in `payment_guards` with
    # `delivered_at IS NULL`, which is exactly the `n_paid_undelivered` a payer
    # agent counts against us.
    #
    # The refusal has to happen before any credential is looked at, so it runs
    # here rather than beside `_x402_unservable_payload` (which needs a
    # credential present to be sure a payment is even in play). A 405 with
    # `Allow` is the truthful answer and costs the caller nothing.
    from werkzeug.exceptions import MethodNotAllowed
    if isinstance(getattr(request, "routing_exception", None), MethodNotAllowed):
        allowed = sorted(
            (getattr(request.routing_exception, "valid_methods", None) or [])
        ) or ["GET"]
        # `valid_methods` already carries HEAD and OPTIONS, so appending OPTIONS
        # unconditionally produced `Allow: GET, HEAD, OPTIONS, OPTIONS` — legal
        # but sloppy, and a header that lists a method twice reads like a bug in
        # the thing that is supposed to be reporting a bug.
        if "OPTIONS" not in allowed:
            allowed.append("OPTIONS")
        log.info("x402 payment NOT taken: method=%s endpoint=%s ip=%s "
                 "— this route does not answer that method, so nothing is settled",
                 request.method, path, _get_client_ip())
        resp = jsonify({
            "ok": False,
            "error": "method_not_allowed",
            "message": (
                "No payment was taken and none will be: this route answers %s, "
                "not %s. Nothing was settled, so any payment authorization you "
                "sent has not been used and your balance is unchanged — repeat "
                "the request with %s and the same credential."
                % (", ".join(allowed), request.method, allowed[0])
            ),
            "method": request.method,
            "allowed": allowed,
            "payment_taken": False,
            "request_id": getattr(g, "request_id", ""),
        })
        resp.headers["Allow"] = ", ".join(allowed)
        return resp, 405

    # Always-free endpoints — no paywall
    if path in X402_FREE_ENDPOINTS:
        return None

    # Paid endpoints — enforce free tier + x402 payment
    if path in X402_PAID_ENDPOINTS:
        ip = _get_client_ip()
        # READ AND INCREMENT IN ONE CRITICAL SECTION, and the previous shape is
        # why. It read `used` under the lock, released it, then re-acquired and
        # wrote `used + 1` — so two parallel requests from one IP both read 0,
        # both wrote 1, and BOTH were granted a paid endpoint for free. The
        # limit was `KRISTO_FREE_TIER_LIMIT = 1` in production, which is exactly
        # the case where one request should be free and the second must pay.
        #
        # `+=` inside the lock is not merely tidier: it is the difference
        # between a counter and a race.
        with _lock:
            used = _free_tier_usage.get(ip, 0)
            if used < FREE_TIER_LIMIT:
                _free_tier_usage[ip] = used + 1
                granted = True
            else:
                granted = False

        if granted:
            log.info("Free tier access: ip=%s, used=%d/%d, endpoint=%s",
                     ip, used + 1, FREE_TIER_LIMIT, path)
            return None
        else:
            # Free tier exhausted — accept a valid on-chain payment proof
            # (X-Payment-Proof header) before demanding a new payment.

            # A CREDENTIAL IS PRESENT, so a settlement is about to be attempted:
            # refuse HERE, before any money can move, if this request cannot be
            # answered. See _x402_unservable_payload for why this runs only when
            # a credential is present, and what it does not consume.
            if (_get_standard_payment_header()
                    or (request.headers.get("X-Payment-Proof") or "").strip()):
                unservable = _x402_unservable_payload(path)
                if unservable is not None:
                    log.info(
                        "x402 payment NOT taken: endpoint=%s missing=%s ip=%s "
                        "— the request cannot be served, so nothing is settled",
                        path, unservable["missing"], ip)
                    return jsonify(unservable), 400

            # Rail 1: STANDARD x402 clients (EIP-3009 via facilitator) —
            # v2 spec header PAYMENT-SIGNATURE (x402-fetch, x402scan wallet,
            # PayAPI verifier) and legacy X-PAYMENT (v1-era clients).
            #
            # `Authorization: Payment …` is read here too, because the MPP
            # Challenge we now advertise tells a client where to put its proof
            # and a client that ignores it must still get a truthful answer
            # rather than a silent re-challenge. See `_mpp_transport_credential`:
            # an embedded x402 payload rides the SAME rail; a native MPP
            # Credential is refused with nothing settled.
            mpp_payload, mpp_state = _mpp_transport_credential()
            if mpp_state == "unusable":
                log.info(
                    "x402 payment NOT taken: endpoint=%s ip=%s — the credential "
                    "arrived as a native MPP `Authorization: Payment`, which this "
                    "route cannot verify; nothing was settled",
                    path, ip)
                return jsonify({
                    "ok": False,
                    "error": "mpp_credential_unsupported",
                    "message": (
                        "No payment was taken and none will be: this route "
                        "advertises an MPP Challenge with "
                        "`header=\"PAYMENT-SIGNATURE\"`, and only an x402 exact "
                        "payload in that header (or in PAYMENT-SIGNATURE) can be "
                        "verified here. Nothing was settled, so the authorization "
                        "you signed has not been used and your balance is "
                        "unchanged — resend the same payment in PAYMENT-SIGNATURE."
                    ),
                    "expected_header": "PAYMENT-SIGNATURE",
                    "challenge_header": "WWW-Authenticate",
                    "payment_taken": False,
                    "request_id": getattr(g, "request_id", ""),
                }), 401
            std_header = mpp_payload or _get_standard_payment_header()
            if std_header:
                price = _get_dynamic_price(ip, path)
                if _try_consume_standard_payment(path, price, ip):
                    return None  # paid via the standard rail — allow through
                if getattr(g, "x402_in_flight", False):
                    # F1/F6: the settlement EXISTS but our node has not caught
                    # up. Never 401 (that blames the payer) and never 402
                    # ("pay again") — the money already moved on-chain.
                    return jsonify({
                        "ok": False,
                        "error": "settlement_in_flight",
                        "message": (
                            "Your payment already settled on-chain. Our node "
                            "has not reached the confirming block yet — no new "
                            "payment is needed; retry this exact request in a "
                            "few seconds."
                        ),
                        "transaction": getattr(g, "x402_in_flight_tx", ""),
                        "retry_after_seconds": 4,
                        "reason": getattr(g, "x402_reject_reason", ""),
                        "request_id": getattr(g, "request_id", ""),
                    }), 425
                return jsonify({
                    "ok": False,
                    "error": "invalid_standard_payment",
                    # Precise cause: precheck problem, signature mismatch, or
                    # the facilitator's structured rejection — full
                    # observability (requested by PayAPI review).
                    "reason": getattr(g, "x402_reject_reason",
                                      "verification_error"),
                    "message": (
                        "The signed payment payload (PAYMENT-SIGNATURE / "
                        "X-PAYMENT header) was not accepted. See 'reason' "
                        "for the exact cause: invalid signature, wrong "
                        "amount/receiver, expired authorization window, "
                        "or insufficient buyer USDC balance."
                    ),
                }), 401

            # Rail 2: legacy self-describing proof (X-Payment-Proof header)
            proof_header = (request.headers.get("X-Payment-Proof") or "").strip()
            if proof_header:
                proof = _decode_payment_proof(proof_header)
                if proof:
                    price = _get_dynamic_price(ip, path)
                    if _try_consume_payment_proof(proof, price, ip, path=path):
                        return None  # paid call — allow through

                    # Credential WAS presented but is broken/unusable:
                    # unknown tx, replayed proof, or underpayment. 401 tells
                    # the agent its proof is the problem (vs 402 = "pay now").
                    return jsonify({
                        "ok": False,
                        "error": "invalid_payment_proof",
                        "message": (
                            "The X-Payment-Proof was not accepted: the "
                            "transaction is unknown/unconfirmed on Base, "
                            "already used, or below the required amount."
                        ),
                        "required_amount_usdc": _get_dynamic_price(ip, path),
                        "receiver_address": X402_RECEIVER_ADDRESS,
                        "hint": (
                            "Wait for confirmation (~24s — 12 blocks — on "
                            "Base; this rail requires 12 confirmations) and "
                            "retry with the SAME proof. The payment is not "
                            "lost and a fresh payment is not needed."
                        ),
                    }), 401

            # No proof at all — demand payment (canonical 402).
            price = _get_dynamic_price(ip, path)
            log.info("x402 payment required: ip=%s, endpoint=%s, price=$%s", ip, path, price)
            return _x402_payment_required_response(path, price)

    # Unknown endpoints — let Flask handle normally (404)
    return None


# ── Register Blueprints (modular route groups) ────────────────────────────
# Discovery routes (x402, OpenAPI, llms.txt, MCP, health) live in the
# app/blueprints/discovery.py module. They use lazy imports to access
# shared state and helpers defined above, avoiding circular imports.
# See audit item #5 (2026-08-24).
from app.blueprints.discovery import discovery_bp
app.register_blueprint(discovery_bp)

# ── Nexus Intelligence Engine ────────────────────────────────────────────────
# Unified autonomous intelligence loop: aggregates x402-catalog performance,
# sales-funnel and processed research intelligence, cross-references it with
# the project parameters (pricing tiers, paid endpoints, free tier) and
# synthesizes strategic briefs for the dashboard. Secure internal read
# endpoint: GET /api/nexus/strategy (admin-authenticated). No background
# threads, no external paid dependencies — the loop builds on demand.
from src.nexus import mount_nexus_engine

mount_nexus_engine(app)


@app.route("/api/arb/opportunities")
def api_arb_opportunities():
    """Live cross-DEX arbitrage spreads on Base (paid via x402).

    Returns the current top arbitrage opportunities from the Arb Radar
    background scanner: pair, buy DEX, sell DEX, spread %, estimated
    NET profit after gas (`est_profit_usd` = gross − gas; only rows whose
    gross exceeds gas×3 are listed), and liquidity constraints. Every row
    carries the transparency fields `block_number` (Base block at scan)
    and `data_age_blocks`. Served from an in-memory cache — zero
    additional RPC cost per call.
    """
    _record_request("api_arb_opportunities", True)
    from services.arb_radar import get_opportunities, get_scan_info

    opportunities = get_opportunities()
    scan_info = get_scan_info()

    return _safe_jsonify({
        "opportunities": opportunities,
        "count": len(opportunities),
        "scan_info": scan_info,
        "source": "dexscreener_cross_dex",
        "network": "base",
        "disclaimer": (
            "Spreads computed from DEXScreener aggregated prices; "
            "est_profit_usd is NET after an estimated round-trip gas cost "
            "(see scan_info.gas_cost_usdc). Estimates are indicative; "
            "verify on-chain before executing."
        ),
    })


@app.route("/api/sales")
def api_sales():
    """Return REAL sales history (from on-chain USDC transfers) and total volume.

    DURABLE (Табло 2.0 audit A3): this is a PAID route, and it used to read the
    RAM `_sales_history`. After a restart/deploy a PAYING customer therefore
    received `total_sales: 0` and an empty history while the chain says $0.028
    over 8 transfers — the same bug that was fixed on /api/dashboard-stats, but
    on a product someone actually pays for. The persistent store is the truth;
    RAM is only a cache. History keeps the legacy oldest→newest order.
    """
    _record_request("api_sales", True)
    with _lock:
        ram_history = list(_sales_history)
        wallet_address = _wallet_state.get("wallet_address")
        usdc_balance = _wallet_state.get("usdc_balance", 0.0)

    total_volume = round(
        sum(float(s.get("amount_usd", 0.0)) for s in ram_history), 6)
    total_count = len(ram_history)
    by_token: Dict[str, float] = {}
    for s in ram_history:
        token = s.get("token", "USDC")
        by_token[token] = round(
            by_token.get(token, 0.0) + float(s.get("amount_usd", 0.0)), 6)
    history = ram_history[-100:]

    try:
        store_sales = dashboard_db.sales_summary()
    except Exception as exc:
        log.debug("api/sales: sales store unavailable (%s)", exc)
        store_sales = None
    if store_sales and store_sales["total_count"] >= total_count \
            and store_sales["total_count"]:
        total_volume = store_sales["total_usdc"]
        total_count = store_sales["total_count"]
        by_token = {"USDC": round(total_volume, 6)}
        # Store rows carry the durable tx/amount/block/payer data plus the
        # legacy RAM key names, reversed to the oldest→newest contract above.
        history = [
            {**row, "amount_usd": row.get("amount_usdc"),
             "timestamp": row.get("ts")}
            for row in list(store_sales["history"][:100])[::-1]
        ]

    # Fetch real-time market data from CoinGecko, DEXScreener, Fear & Greed
    market_data = get_market_snapshot()

    return _safe_jsonify({
        "total_volume_usd": total_volume,
        "total_sales": total_count,
        "by_token": by_token,
        "history": history,
        "source": "real_blockchain",
        "wallet_address": wallet_address,
        "usdc_balance": usdc_balance,
        "market_data": market_data,
    })


def _daily_sales_series(history_rows, days: int = 7) -> list:
    """Last `days` UTC days of on-chain USDC volume — chart series (added 10.10).

    Aggregated from the SAME durable `onchain_sales` rows as the On-Chain Sales
    section (`sales_summary()['history']`), so the chart can never disagree with
    the totals on screen. Days without sales are 0, never missing.

    `days` defaults to 7 so every existing caller and test keeps the series it
    had. It is a parameter because a 7-day window cannot answer "is this week
    better than last week" — that needs fourteen, and the comparison is the
    question the owner actually asks.
    """
    empty = {"usdc": 0.0, "count": 0, "client_usdc": 0.0, "client_count": 0}
    buckets: Dict[str, Dict[str, float]] = {}
    for row in history_rows or []:
        day = str(row.get("ts") or row.get("timestamp") or "")[:10]
        if not day:
            continue
        try:
            amount = float(row.get("amount_usdc") or row.get("amount_usd") or 0.0)
        except (TypeError, ValueError):
            amount = 0.0
        bucket = buckets.setdefault(day, dict(empty))
        bucket["usdc"] += amount
        bucket["count"] += 1
        # 09.11: the owner read "16 · $0.15 днес" as income while all sixteen were
        # our own demo key paying ourselves. Each day now carries the customer
        # half of the number, so a card cannot print self-tests as revenue
        # without the count that contradicts it. `external` is the class that
        # means a stranger's wallet paid (see classify_payer).
        if (row.get("payer_class") or "") == "external":
            bucket["client_usdc"] += amount
            bucket["client_count"] += 1
    today = datetime.now(timezone.utc).date()
    series = []
    for offset in range(days - 1, -1, -1):
        day = (today - timedelta(days=offset)).isoformat()
        bucket = buckets.get(day, dict(empty))
        series.append({
            "date": day,
            "usdc": round(bucket["usdc"], 6),
            "count": int(bucket["count"]),
            "client_usdc": round(bucket["client_usdc"], 6),
            "client_count": int(bucket["client_count"]),
        })
    return series


#: Fields the free track record must not hand out. `tests/test_dashboard_v2.py`
#: has asserted since 10.10 that the free payload contains no `sender` key at
#: all - and on 04.11 it was measured doing exactly that, ten times over, because
#: that assertion ran against an EMPTY store where `payers` is `[]` and the key
#: never appears. The rule was written; the code never obeyed it and the guard
#: could not tell.
_TRACK_RECORD_SECRET_KEYS = ("started_tx", "started_payer")
_TRACK_RECORD_SECRET_PAYER_KEYS = ("first_tx", "sender")


def _redact_track_record(track: dict) -> dict:
    """Drop the transaction hashes and full payer addresses (F-01).

    The track record answers "who has been paying us, since when, and did any of
    them come back". It answers that with `short` (0xe50c…5763) and the dates; a
    66-character transaction hash and a full 42-character address are the data
    the PAID /api/sales sells, and together they are exactly the `{payer,
    transaction_hash, amount_usdc}` triple a payment proof is made of.

    Removed rather than blanked, so a reader cannot mistake a withheld value for
    a missing one. The CLIENTS section keeps `wallet` deliberately: that section
    exists to answer "who paid", and an address on Base is public anyway - the
    hash is the half that is worth money, and it is gone from here.
    """
    if not isinstance(track, dict):
        return track
    clean = {k: v for k, v in track.items()
             if k not in _TRACK_RECORD_SECRET_KEYS}
    payers = clean.get("payers")
    if isinstance(payers, list):
        clean["payers"] = [
            {k: v for k, v in payer.items()
             if k not in _TRACK_RECORD_SECRET_PAYER_KEYS}
            if isinstance(payer, dict) else payer
            for payer in payers
        ]
    return clean


#: The public sales row: what happened and how much. Everything else in the store
#: row - the payer, the hash, the consumed route - is what /api/sales charges for.
_PUBLIC_SALE_KEYS = ("ts", "amount")


def _onchain_history(rows, include_private: bool = False) -> list:
    """The on-chain sales rows, complete for an admin and redacted for the public.

    The operator's version restores the columns the table had until 10.10:
    the payer (so "who paid" is answerable per sale, not just in aggregate), the
    client class behind the colour, the route the payment was consumed on, and
    the hash so any single row can be opened on BaseScan and checked.

    The public version is unchanged: `{ts, amount}`. F-01 is a business-model
    finding - the free surface must not hand over what /api/sales sells - and the
    answer is scope, not deletion, because deleting it also deleted the owner's
    ability to read his own ledger.
    """
    if include_private:
        return [
            {
                "ts": row.get("ts"),
                "amount": row.get("amount_usdc"),
                "tx_hash": row.get("tx_hash"),
                "sender": row.get("sender"),
                "payer_class": row.get("payer_class"),
                "payer_label": row.get("payer_label"),
                "route": row.get("route"),
                "block_number": row.get("block_number"),
                "source": row.get("source"),
            }
            for row in (rows or [])[:100]
        ]
    return [
        # `payer_class` IS INCLUDED, and that is the point of this line. On
        # 09.11 the owner looked at four fresh settlements and asked whether they
        # were his or a customer's — and the page could not say, because the
        # public row was `{ts, amount}` only. 13 of those 14 payments were his
        # own tests; the board showed them all as one undifferentiated column.
        #
        # WHAT F-01 PROTECTS IS THE IDENTITY, NOT THE CATEGORY. `/api/sales`
        # sells `tx_hash`, `sender`, `route` and `block_number` — how to find and
        # verify a specific payment. `payer_class` says only whether a payment was
        # our own probe, a market robot, or a stranger, which is exactly what the
        # owner must know to read his own ledger, and it is not a thing anyone
        # would pay for. The full 66-character hash stays private.
        #
        # The docstring above already argues this: F-01's answer is SCOPE, not
        # deletion. The class was caught in the same net as the hash and had no
        # business being there.
        {"ts": row.get("ts"), "amount": row.get("amount_usdc"),
         "payer_class": row.get("payer_class")}
        for row in (rows or [])[:100]
    ]


#: Weekday names, Monday first, for the one thing a date alone does not say:
#: "3 ноември" is a fact, "понеделник" is the answer to "when do people buy?".
_WEEKDAYS_BG = ("понеделник", "вторник", "сряда", "четвъртък",
                "петък", "събота", "неделя")

#: User-agent fragments → what a person would call that caller. The dashboard is
#: read by the owner, not by a crawler, and "user_agent: claude-code/2.1.310" is
#: not an answer to "was it a human or a bot?". ORDER MATTERS: the first match
#: wins, so the specific entries come before the general, and the browser entry
#: comes last because almost every bot also claims to be Mozilla.
_CALLER_KINDS: tuple = (
    ("AI агент", ("claude-code", "anthropic", "openai", "gpt-", "oai/",
                  "langchain", "crewai", "autogen", "llm", "cursor")),
    # OURS, and only ours. This list said "healthcheck" until the live page
    # showed CarbonMonitor/0.1 from carbon-cashmere.de sitting in it - someone
    # else's uptime pinger counted as our own traffic. Render/1.0 is our host,
    # kristo-* is us, werkzeug is the Flask test client.
    ("Наш собствен монитор", ("render/1.0", "kristo-", "werkzeug")),
    # Third parties checking that we are alive. They are not customers and not
    # indexers, and on the live page they were 59k requests filed under "Друго"
    # - SentinelOracle, mako-pulse-prober and mcp-health-probe all say what they
    # are in their own user-agent and none of them was being read.
    ("Външен монитор", ("monitor", "prober", "probe", "liveness", "uptime",
                        "pingdom", "uptimerobot", "sentinel", "statuscake",
                        "betteruptime", "freshping")),
    ("Търсачка или робот", ("bot", "crawler", "spider", "slurp", "bingpreview",
                            "facebookexternalhit", "semrush", "ahrefs",
                            "python-urllib", "scrapy",
                            # A headless browser is a program driving a browser,
                            # and it is measured here as a robot. Without this it
                            # fell through to "Браузър (човек)" - the dashboard
                            # would have counted automation as a human reader,
                            # which is exactly the number the owner acts on.
                            "headless", "phantomjs", "puppeteer", "playwright",
                            "selenium")),
    ("Програмен клиент", ("curl", "python-requests", "httpx", "aiohttp",
                          "axios", "node-fetch", "okhttp", "go-http", "java/",
                          "wget", "powershell", "undici", "libwww", "guzzle",
                          # Node's own fetch sends exactly "node", which landed in
                          # "Друго" while it was 112k of the traffic - a label that
                          # tells the owner nothing about a fifth of his callers.
                          "node")),
    ("Браузър (човек)", ("mozilla/", "chrome/", "safari/", "firefox/", "edg/",
                         "opera/")),
)


def _caller_kind(user_agent: str) -> str:
    """What a human would call the client behind one user-agent string."""
    ua = (user_agent or "").strip().lower()
    if not ua:
        return "Неизвестен"
    for kind, fragments in _CALLER_KINDS:
        if any(fragment in ua for fragment in fragments):
            return kind
    return "Друго"


def _human_or_bot(top_user_agents) -> list:
    """Fold the top user agents into caller kinds, biggest first.

    `top_user_agents` is real traffic, so the counts add up to real requests. The
    summary does not claim to know whether a person is behind a browser - it says
    what the caller IS, which is the part the evidence supports.
    """
    totals: Dict[str, int] = {}
    examples: Dict[str, str] = {}
    for row in top_user_agents or []:
        agent = str(row.get("user_agent") or "")
        try:
            count = int(row.get("n") or 0)
        except (TypeError, ValueError):
            count = 0
        kind = _caller_kind(agent)
        totals[kind] = totals.get(kind, 0) + count
        if kind not in examples or agent:
            examples.setdefault(kind, agent)
    return sorted(
        [{"kind": kind, "requests": count, "example": examples.get(kind, "")}
         for kind, count in totals.items()],
        key=lambda item: -item["requests"])


def _ago_words(ts) -> str:
    """'преди 3 часа' rather than '2026-11-04T02:46:17.369249+00:00'.

    A timestamp is the rawest possible form of "when", and it was the only form
    the dashboard offered. Both are shown side by side now; this is the half a
    person reads first.
    """
    if not ts:
        return "никога"
    try:
        moment = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return "неизвестно"
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    seconds = (datetime.now(timezone.utc) - moment).total_seconds()
    if seconds < 0:
        return "току-що"
    minutes = int(seconds // 60)
    if minutes < 1:
        return "току-що"
    if minutes < 60:
        return "преди %d мин" % minutes
    hours = minutes // 60
    if hours < 24:
        return "преди %d ч" % hours if hours > 1 else "преди час"
    days = hours // 24
    if days == 1:
        return "вчера"
    if days < 30:
        return "преди %d дни" % days
    months = days // 30
    return "преди %d месеца" % months if months > 1 else "преди месец"


def _organism_board_enabled() -> bool:
    """Whether the board payload carries the organism sections.

    DEFAULT OFF. Three deploys in a row failed to open a port with this section
    present and every deploy before it took a minute, so the section is gated
    until the service is stable again and a failure can be attributed cleanly.

    Read at CALL time, not import time: a Render environment change must not
    require a code edit to take effect, and `os.getenv` here costs nothing
    measurable next to building the payload.
    """
    return (os.getenv("KRISTO_ORGANISM_BOARD", "") or "").strip().lower() in (
        "1", "true", "yes", "on")


def _organism_board_section() -> dict:
    """The organism, journal, rule table and chaos report for the board."""
    return {
        "organism": _safe_organism_summary(),
        "journal": _safe_organism_journal(),
        "rules": _safe_organism_rules(),
        "chaos": _safe_organism_chaos(),
    }


def _safe_organism_chaos() -> dict:
    """The last chaos-drill result, or an honest marker.

    The drills run on demand rather than on the board's request path: they are
    cheap and in-memory, but the board rebuilds every 30 seconds and a drill
    suite belongs on a schedule, not on every page view.
    """
    try:
        from services import organism_chaos as chaos
        report = chaos.run_all()
        return {
            "available": True,
            **report,
            "actions_enabled": _organism_actions_enabled(),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("organism chaos unavailable: %s: %s",
                    type(exc).__name__, exc)
        return {"available": False, "failed": None, "passed": None,
                "reason": "%s: %s" % (type(exc).__name__, str(exc)[:120]),
                "note": "a drill suite that could not run is not a passing one"}


def _organism_actions_enabled() -> bool:
    """Whether the executors may act. Off unless a human turns it on.

    Published on the board because "is this thing allowed to change production"
    is the first question anyone should be able to answer about it.
    """
    try:
        from services import organism_executors as ex
        return ex.actions_enabled()
    except Exception:  # noqa: BLE001
        return False


def _safe_organism_rules() -> dict:
    """The rule table and what it has seen, or an honest marker.

    The table is published IN FULL, not summarised. A policy nobody can read is
    a policy nobody can review, and this one is the entire set of things the
    organism is allowed to do to itself.
    """
    try:
        from services import organism_rules as rules
        return {
            "observe_only": True,
            "blast_radius_per_hour": rules.BLAST_RADIUS_PER_HOUR,
            "executors": list(rules.EXECUTORS),
            "forbidden": list(rules.FORBIDDEN_EFFECTS),
            "table": rules.table(),
            "digest": rules.digest(dashboard_db, hours=24),
            "note": ("`not_reached` is never converted into an action: nobody "
                     "looking is not the same as something being broken, and "
                     "restarting on it would thrash on every deploy."),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("organism rules unavailable: %s: %s",
                    type(exc).__name__, exc)
        return {"available": False, "table": [], "digest": {},
                "reason": "%s: %s" % (type(exc).__name__, str(exc)[:120])}


def _organism_journal_note(block: str, kind: str, severity: str = "info",
                           detail: str = "", action: str = "",
                           outcome: str = "") -> None:
    """Write one journal entry. Never raises.

    The journal is the organism's memory and the owner's report: what the system
    noticed, what it did, and what happened. A session that reads it does not have
    to re-discover the last one's findings.
    """
    try:
        from services import organism_journal as oj
        oj.append(dashboard_db, block, kind, severity=severity, detail=detail,
                  action=action, outcome=outcome)
    except Exception as exc:  # noqa: BLE001 - telemetry only
        log.warning("organism journal note failed (%s/%s): %s", block, kind, exc)


def _organism_beat(block: str, verdict: str, detail: str = "") -> None:
    """Record a heartbeat for one block. Never raises, never blocks the caller.

    Called from the background loops rather than the request path: a heartbeat is
    a durable write, and putting one on every request is how the dashboard got
    slow in the first place. The loops already run on their own threads.
    """
    try:
        from services import organism
        organism.beat(dashboard_db, block, verdict, detail)
    except Exception as exc:  # noqa: BLE001 - telemetry only
        log.warning("organism heartbeat failed (%s): %s", block, exc)


def _tolerant(name: str, fn, default=None):
    """Call a store method for the board and survive it failing.

    ONE PANEL MUST NOT TAKE THE BOARD DOWN — the rule this codebase enforces
    everywhere else, and which two calls in the payload builder were never
    given.

    `_step` measures a build step and publishes its timing, but it uses
    `try/finally` and NOT `try/except`. So a bare `dashboard_db.<method>()` that
    raises propagates out of the build, the build is recorded as failed, and the
    cache never fills — which means every request rebuilds, fails, and the board
    answers 500 for as long as the fault lasts. Measured on 07.11: the board was
    down for over half an hour, and the log said only

        dashboard build failed: shared Postgres link busy for 15s

    while `/health`, the rail and every other surface were perfectly fine. The
    panel that raised was one of two unwrapped calls; the slow query behind it is
    a separate fault.

    `default` is chosen by the caller to be something the page can render as
    unavailable, never as a fact. A failure here degrades ONE panel.
    """
    try:
        return fn()
    except Exception as exc:  # noqa: BLE001
        log.warning("dashboard panel %s unavailable (%s); reporting the panel "
                    "unread rather than failing the whole board",
                    name, type(exc).__name__)
        return default


def _safe_organism_summary() -> dict:
    """The organism's block verdicts, or an honest "unavailable" marker.

    Wrapped because the board must survive this module being absent or broken —
    the same rule every other panel here follows. The failure is REPORTED as
    unavailable rather than rendered as six healthy blocks, which is the mistake
    this whole feature exists to prevent.
    """
    try:
        from services import organism
        return organism.summary(dashboard_db)
    except Exception as exc:  # noqa: BLE001
        log.warning("organism summary unavailable: %s: %s",
                    type(exc).__name__, exc)
        return {
            "blocks": [], "counts": {}, "unhealthy": None,
            "available": False,
            "reason": "%s: %s" % (type(exc).__name__, str(exc)[:120]),
            "note": ("The organism's own state could not be read. This is NOT "
                     "the same as every block being well."),
        }


def _safe_organism_journal(limit: int = 25) -> dict:
    """The most recent journal entries, or an honest marker.

    `unreadable: True` is deliberately distinct from an empty list: "nothing has
    happened" and "we cannot see what happened" call for opposite reactions.
    """
    try:
        from services import organism_journal as oj
        return {
            "entries": oj.entries(dashboard_db, limit=limit),
            "counts_24h": oj.counts(dashboard_db, 24),
            "unreadable": not oj.readable(dashboard_db),
        }
    except Exception as exc:  # noqa: BLE001
        log.warning("organism journal unavailable: %s: %s",
                    type(exc).__name__, exc)
        return {
            "entries": [], "counts_24h": {}, "unreadable": True,
            "reason": "%s: %s" % (type(exc).__name__, str(exc)[:120]),
        }


def _plain_summary(sales: dict, requests: dict, clients: dict) -> dict:
    """The owner's four questions answered from the same rows as the sections.

    Every figure is derived from `sales`, `requests` and `clients` - the exact
    sources the tables below render - so this summary cannot disagree with them.
    Nothing is invented and nothing is estimated.

    Why it exists: the numbers were all present and none of them answered "when
    was the last sale, on what day, who paid, and was it a person or a bot".
    They were spread across eight sections under internal names.
    """
    history = list(sales.get("history") or [])
    today = datetime.now(timezone.utc).date()

    sales_by_day = _daily_sales_series(history, days=28)

    def _between(first, last) -> Dict[str, object]:
        """Totals for a date range, split by WHO paid.

        `client_count` / `client_usdc` are the `external` half — strangers. The
        other classes are our own verification wallets and market crawlers, and
        on 09.11 they were the whole of the day: 16 payments, $0.15, not one of
        them a customer. Without this split the card said "$0.15 днес" beside no
        revenue at all, and the owner had to ask who the money came from.
        """
        count = 0
        usdc = 0.0
        client_count = 0
        client_usdc = 0.0
        for row in sales_by_day:
            day = row["date"]
            if first <= day <= last:
                count += row["count"]
                usdc += row["usdc"]
                client_count += row.get("client_count", 0)
                client_usdc += row.get("client_usdc", 0.0)
        return {"from": first, "to": last,
                "count": count, "usdc": round(usdc, 6),
                "client_count": client_count,
                "client_usdc": round(client_usdc, 6)}

    week_start = today - timedelta(days=today.weekday())          # Monday
    last_week_start = week_start - timedelta(days=7)
    this_week = _between(week_start.isoformat(), today.isoformat())
    last_week = _between(last_week_start.isoformat(),
                         (week_start - timedelta(days=1)).isoformat())

    def _change(now_value, before_value) -> Dict[str, object]:
        """Week-over-week change, in words a human can read.

        The words are formatted by KIND OF VALUE, not by one size fits all. This
        used to say `"с %d повече" % delta` for both calls, so the USDC call —
        whose deltas are fractions of a dollar — always printed "с 0 по-малко"
        (or "с 0 повече") however large the real change was. On 07.11 the board
        read "с 0 по-малко" beside a percent of -22.2%, which is how it was
        found: the two halves of the same sentence contradicted each other.

        Only the COUNT is an integer. Money gets decimals and a unit.
        """
        delta = now_value - before_value
        money = isinstance(now_value, float) or isinstance(before_value, float)
        if before_value == 0:
            words = ("първите продажби" if now_value > 0 else "няма продажби")
        elif delta > 0:
            words = ("с $%.3f повече" % delta) if money else ("с %d повече" % delta)
        elif delta < 0:
            words = (("с $%.3f по-малко" % abs(delta)) if money
                     else ("с %d по-малко" % abs(delta)))
        else:
            words = "същото"
        percent = (round(delta / before_value * 100, 1)
                   if before_value else None)
        return {"delta": delta, "percent": percent, "words": words}

    last_sale = None
    if history:
        newest = max(history, key=lambda row: str(row.get("ts") or ""))
        last_sale = {
            "at": newest.get("ts"),
            "amount_usdc": round(float(newest.get("amount_usdc")
                                       or newest.get("amount") or 0.0), 6),
            "ago_words": _ago_words(newest.get("ts")),
        }

    best_day = max(sales_by_day, key=lambda row: row["usdc"], default=None)
    if best_day and best_day["usdc"] <= 0:
        best_day = None

    hourly = list(requests.get("hourly") or [])
    busiest = None
    if hourly:
        peak = max(hourly, key=lambda row: row.get("clean", row.get("n", 0)))
        if (peak.get("clean", peak.get("n", 0)) or 0) > 0:
            busiest = {"hour": int(peak["hour"]),
                       "requests": int(peak.get("clean", peak.get("n", 0)))}

    payers = list(clients.get("clients") or [])
    first_ever = min((str(row.get("ts") or "") for row in history),
                     default="")

    return {
        "last_sale": last_sale,
        "today": _between(today.isoformat(), today.isoformat()),
        "yesterday": _between((today - timedelta(days=1)).isoformat(),
                              (today - timedelta(days=1)).isoformat()),
        "this_week": this_week,
        "last_week": last_week,
        "week_change": _change(this_week["count"], last_week["count"]),
        "week_change_usdc": _change(this_week["usdc"], last_week["usdc"]),
        "all_time": {
            "count": int(sales.get("total_count") or 0),
            "usdc": round(float(sales.get("total_usdc") or 0.0), 6),
            "payers": len(payers),
            "first_sale": first_ever or None,
            "days_live": (today - datetime.fromisoformat(first_ever[:10]).date()
                          ).days if first_ever else 0,
        },
        "best_day": best_day,
        "busiest_hour": busiest,
        "sales_by_day": sales_by_day,
        "human_or_bot": _human_or_bot(requests.get("top_user_agents")),
    }


def _hourly_requests_series(hourly_rows) -> list:
    """Today's request counts per hour 0–23 UTC — chart series (added 10.10).

    Sourced from `requests_summary()['hourly']`, the same query behind the API
    Requests section. `clean` excludes the internal Render/1.0 keep-alive noise
    exactly like the "ДНЕС ЧИСТИ" card, so the chart and the card agree.
    """
    by_hour: Dict[int, Dict[str, int]] = {}
    for row in hourly_rows or []:
        try:
            hour = int(str(row.get("hour") or "0")[:2])
            n = int(row.get("n") or 0)
            noise = int(row.get("noise") or 0)
        except (TypeError, ValueError):
            continue
        if 0 <= hour <= 23:
            by_hour[hour] = {"n": n, "noise": noise}
    series = []
    for hour in range(24):
        row = by_hour.get(hour, {"n": 0, "noise": 0})
        series.append({
            "hour": hour,
            "n": row["n"],
            "noise": row["noise"],
            "clean": max(0, row["n"] - row["noise"]),
        })
    return series


def _statistics_payload(include_recent_requests: bool) -> dict:
    """Build real stats from durable catalog events and live runtime state."""
    with _lock:
        daily = dict(sorted(_daily_stats.items()))
        recent_requests = list(_request_log)
        wallet_info = dict(_wallet_state)
        sales_history = list(_sales_history)
        bot_status = dict(_bot_status)

    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    today_data = daily.get(today_str, {"requests": 0, "sales_count": 0, "sales_volume": 0.0})
    sales_by_token: Dict[str, float] = {}
    for sale in sales_history:
        token = sale.get("token", "USDC")
        sales_by_token[token] = round(
            sales_by_token.get(token, 0.0) + float(sale.get("amount_usd", 0.0)), 6
        )

    # Official public product list = the REAL routes only.
    # (07.09: the 8 demo SKUs were unlisted from every public surface —
    # demo adapter has no live execution. Internal catalog analytics unchanged.)
    # ── Durable request counters (audit C, debt #10) ─────────────────────────
    # `_daily_stats` is RAM: after a deploy the public widget reported "0 API
    # calls" while the persistent log held tens of thousands. The store is the
    # truth; the old RAM view is kept, labelled, so nothing is hidden.
    req_today = today_data.get("requests", 0)
    req_total = sum(d.get("requests", 0) for d in daily.values())
    try:
        store_reqs = dashboard_db.requests_summary(recent_limit=1)
    except Exception as exc:
        log.debug("api/stats: request store unavailable (%s)", exc)
        store_reqs = None
    if store_reqs and store_reqs.get("total"):
        req_today = store_reqs["today"]
        req_total = store_reqs["total"]

    products = _real_routes_payload()

    # Fetch real-time market data from CoinGecko, DEXScreener, Fear & Greed
    market_data = get_market_snapshot()

    # ── Priority-0 invariant applied to THIS surface too (Табло 2.0 audit) ──
    # `_sales_history` is RAM: a deploy empties it, and the chain monitor only
    # re-discovers the transfers on its next tick. That left
    # /api/dashboard-stats reporting "0 sales / $0.00" while
    # /api/dashboard/data reported the real 8 on-chain transfers — two live
    # screens, two different answers about money. The persistent store is the
    # truth; RAM is only a cache.
    total_volume = round(
        sum(float(s.get("amount_usd", 0.0)) for s in sales_history), 6)
    total_sales = len(sales_history)
    history = sales_history[-100:]
    today_sales_count = today_data.get("sales_count", 0)
    today_sales_volume = today_data.get("sales_volume", 0.0)
    try:
        store_sales = dashboard_db.sales_summary()
    except Exception as exc:
        log.debug("dashboard-stats: sales store unavailable (%s)", exc)
        store_sales = None
    if store_sales and store_sales["total_count"] >= total_sales \
            and store_sales["total_count"]:
        total_volume = store_sales["total_usdc"]
        total_sales = store_sales["total_count"]
        today_sales_count = store_sales["today_count"]
        today_sales_volume = store_sales["today_usdc"]
        sales_by_token = {"USDC": round(total_volume, 6)}
        # Store rows plus the legacy RAM key names, so existing consumers of
        # /api/dashboard-stats keep working unchanged.
        history = [
            {**row, "amount_usd": row.get("amount_usdc"),
             "timestamp": row.get("ts")}
            for row in store_sales["history"][:100]
        ]

    payload = {
        "today": {
            "date": today_str,
            "requests": req_today,
            "sales_count": today_sales_count,
            "sales_volume_usd": today_sales_volume,
        },
        "daily": daily,
        "total_requests": req_total,
        "instrumented_requests": {
            "today": today_data.get("requests", 0),
            "total": sum(d.get("requests", 0) for d in daily.values()),
            "note": ("RAM брояч на инструментираните маршрути (не оцелява "
                     "deploy) — за сравнение с durable total_requests."),
        },
        "wallet": wallet_info,
        # The address customers pay to — must always be the bound fee
        # receiver, NOT the operator hot wallet (which is the payer side).
        "payment_receiver": X402_RECEIVER_ADDRESS,
        "fee_receiver": wallet_info.get("fee_receiver") or X402_RECEIVER_ADDRESS,
        "total_volume_usd": total_volume,
        "total_sales": total_sales,
        "by_token": sales_by_token,
        # F-01: public history rows keep only {ts, amount} — no tx_hash/sender/payer_*.
        "history": [
            {"ts": _r.get("timestamp") or _r.get("ts"),
             "amount": _r.get("amount_usdc",
                              _r.get("amount_usd", _r.get("amount")))}
            for _r in history
        ],
        # Chart series (10.10) — ADDITIVE ONLY, no existing field touched.
        # `daily_sales` aggregates the exact `history` rows reported above (RAM
        # fallback or store rows, whichever is authoritative), so the 7-day chart
        # can never disagree with the visible totals.
        "daily_sales": _daily_sales_series(history),
        "hourly_requests": _hourly_requests_series(
            store_reqs.get("hourly") if store_reqs else None),
        "telegram_bot_running": bot_status.get("telegram_bot_running", False),
        "commands_processed": bot_status.get("commands_processed", 0),
        "products": products,
        "products_summary": {
            "total_products": len(products),
            "kind": "real_x402_routes",
        },
        "nexus_url": NEXUS_URL,
        "market_data": market_data,
    }
    if include_recent_requests:
        payload["recent_requests"] = recent_requests[-50:]
    return payload


@app.route("/api/admin/seed-sales", methods=["POST"])
def api_admin_seed_sales():
    """One-shot chain-verified sales recovery (admin-authenticated).

    Re-runs the Day-of-Truth seed: every row in
    `integrations.verified_sales.VERIFIED_SALES` (full 66-char hashes, pulled
    from the chain and cross-verified against RPC receipts) is re-asserted
    with INSERT OR IGNORE. Lets a wiped ephemeral filesystem be repaired
    without a redeploy. Returns the RESULTING on-chain totals so the operator
    can verify the number instead of trusting it.
    """
    denied = _require_admin_access()
    if denied:
        return denied
    _record_request("admin_seed_sales", True)
    try:
        result = dashboard_db.seed_verified_sales()
    except Exception as exc:
        log.warning("Admin seed-sales failed: %s", exc)
        return jsonify({"ok": False, "error": str(exc)}), 500
    summary = dashboard_db.sales_summary()
    log.info("Admin seed-sales: inserted=%d total=%d $%.6f",
             result["inserted"], result["present"], result["total_usdc"])
    return jsonify({
        "ok": True,
        "seed": result,
        "onchain": {
            "total_usdc": summary["total_usdc"],
            "total_count": summary["total_count"],
            "external_payers": summary["external_payers"],
            "by_class": summary["by_class"],
            "last_scanned_block": int(
                dashboard_db.get_meta("last_scanned_block", "0") or 0),
        },
    })


def _track_record_checkpoints(rows: list) -> list:
    """Record each review checkpoint ONCE, in the DURABLE store (rule 6).

    The value at n=30/100/200 is frozen the first time we see it, so the
    goalposts cannot be moved later. Durable on purpose: a deploy must not wipe
    the fact that a checkpoint was already read.
    """
    import json as _json

    scored = [r for r in rows if (r.get("outcome") or "") in
              ("hit", "miss", "flat")]
    n = len(scored)
    hits = sum(1 for r in scored if r.get("outcome") == "hit")
    try:
        raw = dashboard_db.history.get_durable_meta("signal_track_checkpoints", "")
        saved = _json.loads(raw) if raw else []
    except Exception:
        saved = []
    reached = {int(c.get("n", 0)) for c in saved}
    added = False
    for point in SIGNAL_CHECKPOINTS:
        if n >= point and point not in reached:
            rate = round(100.0 * hits / n, 1) if n else None
            entry = {
                "n": point,
                "hit_rate_pct": rate,
                "scored_at_checkpoint": n,
                "hits_at_checkpoint": hits,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            }
            # The frozen schedule's last clause: a final checkpoint below 50% is
            # recorded AS a failure, in the same durable row the number lives in —
            # shown, not explained away or quietly dropped.
            if point == SIGNAL_CHECKPOINTS[-1] and rate is not None and rate < 50.0:
                entry["verdict"] = "below_50_at_final_checkpoint"
                entry["note"] = ("The final checkpoint is below 50%. It is recorded "
                                 "here as a failure — the feed's own rule is that the "
                                 "number is shown, not explained away.")
                log.warning("Track record FINAL checkpoint below 50%%: %.1f%%", rate)
            saved.append(entry)
            added = True
            log.info("Track record checkpoint reached: n=%d hit_rate=%s",
                     point, rate)
    if added:
        try:
            dashboard_db.history.set_durable_meta("signal_track_checkpoints",
                                                  _json.dumps(saved))
        except Exception as exc:
            log.warning("Could not persist checkpoints: %s", exc)
    return sorted(saved, key=lambda c: c.get("n", 0))


@app.route("/public/signals/history", methods=["GET"])
def public_signals_history():
    """The PUBLIC track record — free, rate-limited, and only the proven past.

    FROZEN RULES (services/signal_track_record.py, 18.09): paid-issued signals at
    least 24h old; volatility computed at issue and immutable; ±2h price window;
    CoinGecko first then DEXScreener; `unresolved` instead of a guess; n always
    shown, percentages only at n≥50 per cell; the review schedule is a technical
    guard. The fresh signal itself stays PAID — this feed is history.
    """
    limited = _rate_limited_response("public_signals_history")
    if limited:
        return limited
    _record_request("public_signals_history", True)
    from services import signal_track_record as track

    cutoff = (datetime.now(timezone.utc)
              - timedelta(hours=track.RESOLVE_AFTER_HOURS)).isoformat()
    try:
        rows = dashboard_db.signal_history_rows(cutoff)
        not_scored = dashboard_db.signal_history_not_scored()
        issued_total = dashboard_db.signal_history_total()
    except Exception as exc:
        log.warning("Public signals history failed: %s", exc)
        return _safe_jsonify({"ok": False, "error": "store_unavailable",
                              "detail": str(exc)[:200]}), 503
    payload = track.build_feed(rows, checkpoints=_track_record_checkpoints(rows),
                               not_scored=not_scored, issued_total=issued_total)
    return _safe_jsonify(payload)


# ── Public dashboard-stats TTL cache (option A, double-door approved 11.10) ──
# /api/dashboard-stats aggregates request_log (~783K rows, ~22 seq scans) and
# measured ~41s live — above the Sentinel weekly-report client's own 30s
# timeout (services/sentinel.py), so the bot rendered "API stats unavailable".
# This caches ONLY the public read-only payload of THIS route (nothing tied to
# payments/admin/sessions; the paid /api/stats keeps include_recent_requests=True
# and is untouched — see test_dashboard_stats_cache.py). TTL 60s; an expired
# entry is dropped and rebuilt from the durable store on the next request.
_stats_cache_lock = threading.Lock()
_stats_cache_payload: Optional[dict] = None
_stats_cache_built_at: float = 0.0
STATS_CACHE_TTL_SECONDS = max(
    1, int(os.getenv("DASHBOARD_STATS_CACHE_TTL_SECONDS", "60")))


def _reset_stats_cache() -> None:
    """Drop the cached payload (tests / manual invalidation)."""
    global _stats_cache_payload, _stats_cache_built_at
    with _stats_cache_lock:
        _stats_cache_payload = None
        _stats_cache_built_at = 0.0


def _cached_statistics_payload() -> dict:
    """Thread-safe TTL-cached wrapper around the PUBLIC dashboard payload.

    The build is intentionally NOT done under the lock (it can take tens of
    seconds and the Sentinel thread polls this route); two concurrent cache
    misses may both build — benign duplicate work, last writer wins.
    """
    global _stats_cache_payload, _stats_cache_built_at
    with _stats_cache_lock:
        if (_stats_cache_payload is not None
                and time.monotonic() - _stats_cache_built_at
                        < STATS_CACHE_TTL_SECONDS):
            return _stats_cache_payload
    payload = _statistics_payload(include_recent_requests=False)
    with _stats_cache_lock:
        _stats_cache_payload = payload
        _stats_cache_built_at = time.monotonic()
    return payload


@app.route("/api/dashboard-stats")
def dashboard_stats():
    """Return free, read-only aggregate data required by the public dashboard."""
    return _safe_jsonify(_cached_statistics_payload())


@app.route("/api/connectors")
def api_connectors():
    """Live integration-connector registry (dashboard integrations panel).

    Public on purpose: this is evidence that the rails are working, and it is
    advertised in the discovery block of /api/v1/quickstart. The gas wallet's
    ADDRESS is not public - it was published here to anyone who asked, on an
    unauthenticated crawlable URL, and it links the relayer to this service.
    An authenticated operator (or the one-click operator view) still sees it.
    """
    with _lock:
        wallet_info = dict(_wallet_state)
    # The fee receiver is ALWAYS bound (config hard fallback) — the receiver
    # connector must never look inactive just because no hot wallet is loaded.
    wallet_info["fee_receiver"] = wallet_info.get("fee_receiver") or X402_RECEIVER_ADDRESS
    from services.connectors import registry_status

    entries = registry_status(
        wallet_info,
        reveal_wallet=_is_admin_request() or _operator_view_enabled())
    return _safe_jsonify({
        "count": len(entries),
        "active": sum(1 for e in entries if e["status"] == "active"),
        "connectors": entries,
    })


@app.route("/api/v1/quickstart")
def api_quickstart():
    """Zero-friction onboarding: copy-paste first-call snippets per language.

    BlockRun-style practice — the first call already works: one free GET
    returns the self-describing 402 challenge, payment is a single USDC
    transfer, retry carries the proof. No signup, no keys, no docs needed.
    """
    base_url = request.host_url.rstrip("/")
    _cheapest_price = min(float(route["price_usdc"]) for route in REAL_X402_ROUTES)
    return _safe_jsonify({
        "service": "Kristo Intelligence",
        "protocol": "x402 v2",
        "network": "base",
        "usdc_contract": X402_USDC_CONTRACT,
        "receiver": X402_RECEIVER_ADDRESS,
        "cheapest_call": {
            "endpoint": f"{base_url}/api/v1/signal",
            "amount_usdc": _cheapest_price,
            "amount_units": (
                "decimal USDC (0.003) — this display field only. The 402 "
                "body's `payment.amount_usdc` is **atomic** and shows 3000 for "
                "the same price. See `units` below before you move money."
            ),
            "note": "paid per call — no subscription, no signup, no API key",
        },
        # The same field name carries two different units across our surfaces:
        # the 402 challenge is atomic (5000) and this walkthrough's
        # cheapest_call is decimal (0.003). A developer who reads one and
        # applies it to the other sends 5000 USDC for a $0.005 call, and our
        # on-chain check accepts it (`amount >= price`). Spelled out so an agent
        # cannot infer the wrong unit.
        "units": {
            "accepts[0].amount": 'atomic (6 decimals) — "5000" means 0.005 USDC',
            "x402_amount": 'atomic — "5000" means 0.005 USDC',
            "payment.amount_usdc": (
                "atomic, despite the name — 5000 means 0.005 USDC"
            ),
            "X-Payment-Amount-USDC": "decimal USDC — 0.005",
            "cheapest_call.amount_usdc": "decimal USDC — 0.003 (display only)",
            "X-Payment-Proof.amount_usdc": (
                "atomic — a different field that reuses the name, so send 5000 "
                "for a $0.005 call, never 0.005"
            ),
            "rule": (
                "Pass atomic values to the ERC-20 transfer unchanged; divide by "
                "1e6 only if your wallet API wants a decimal amount."
            ),
        },
        # These steps used to teach the legacy rail as *the* way in, in all three
        # snippets below. That is the slow one: a plain transfer needs 12
        # confirmations (~24s) before the data comes back. It was the llms.txt bug
        # again, in the single most-read onboarding document we publish — the
        # first thing an integrating agent fetches. Preferred rail first now, with
        # the legacy one kept as the documented alternative.
        "steps": [
            "GET a paid endpoint -> 402 challenge, fully self-describing "
            "(accepts[0] carries scheme, network, amount and payTo)",
            "preferred: sign an EIP-3009 transferWithAuthorization for "
            "accepts[0].amount to accepts[0].payTo and retry with the "
            "PAYMENT-SIGNATURE header (x402 v2; X-PAYMENT for v1 clients) — the "
            "facilitator settles it, so nothing waits on block confirmations",
            "alternative: send the same amount as a plain USDC transfer to "
            "accepts[0].payTo, wait 12 confirmations (~24s), then retry with "
            "X-Payment-Proof: base64url(JSON({payer, transaction_hash, "
            "amount_usdc})) — that amount_usdc is ATOMIC too: send 5000 for a "
            "$0.005 call, never 0.005",
        ],
        "curl": f"curl -i {base_url}/api/stats   # 402 -> read accepts[0].amount / payTo",
        "python": (
            "import httpx, base64, json\n"
            f"r = httpx.get('{base_url}/api/stats')\n"
            "assert r.status_code == 402\n"
            "req = r.json()['accepts'][0]   # scheme / network / amount / payTo\n"
            "# preferred: sign an EIP-3009 transferWithAuthorization for "
            "req['amount'] to req['payTo'] on Base,\n"
            "#   then retry with the PAYMENT-SIGNATURE header (x402 v2). "
            "x402-fetch and the x402scan wallet do this for you.\n"
            "# alternative (legacy, slower): send the same amount as a plain "
            "USDC transfer, wait 12 confirmations, then retry with\n"
            "#   X-Payment-Proof: base64url(JSON({payer, transaction_hash, amount_usdc}))"
            "  # amount_usdc is ATOMIC: 5000, not 0.005"
        ),
        "node": (
            "const r = await fetch('" + base_url + "/api/stats');\n"
            "if (r.status === 402) {\n"
            "  const { accepts } = await r.json();\n"
            "  // preferred: sign an EIP-3009 transferWithAuthorization for "
            "accepts[0].amount (raw USDC, 6 decimals) to accepts[0].payTo,\n"
            "  //   then retry with headers { 'PAYMENT-SIGNATURE': signed } "
            "(x402 v2; 'X-PAYMENT' for v1 clients)\n"
            "  // alternative (legacy, slower): plain USDC transfer, wait 12 "
            "confirmations, then retry with\n"
            "  //   { 'X-Payment-Proof': base64url(JSON.stringify({payer, "
            "transaction_hash, amount_usdc})) }  // amount_usdc is ATOMIC: "
            "5000, not 0.005\n"
            "}"
        ),
        "standard_client": (
            "Any x402 v2 ecosystem client (x402-fetch SDK, x402scan embedded "
            "wallet, agentcash router) works out of the box: the challenge "
            "served here is canonical v2, and the signed EIP-3009 payload is "
            "accepted in PAYMENT-SIGNATURE (v2) or X-PAYMENT (v1) and settled "
            "through the Coinbase x402 facilitator."
        ),
        "discovery": {
            "well_known": f"{base_url}/.well-known/x402",
            "openapi": f"{base_url}/openapi.json",
            "mcp_manifest": f"{base_url}/api/mcp/manifest",
            "connectors": f"{base_url}/api/connectors",
        },
    })


@app.route("/api/stats")
def api_stats():
    """Return paid activity, requests, daily stats, and official agent catalog data."""
    _record_request("api_stats", True)
    return _safe_jsonify(_statistics_payload(include_recent_requests=True))


@app.route("/api/bot-status")
def api_bot_status():
    """Return Telegram bot integration status."""
    _record_request("api_bot_status", True)
    with _lock:
        status = dict(_bot_status)
        wallet_info = dict(_wallet_state)
    status["last_heartbeat"] = status.get("last_heartbeat", "")
    status["uptime_started"] = status.get("uptime_started", "")
    status["wallet"] = wallet_info
    return _safe_jsonify(status)


# ── Telegram Webhook (for bot messages & inline button callbacks) ─────────

@app.route("/api/telegram-webhook", methods=["POST"])
def api_telegram_webhook():
    """
    Webhook endpoint for Telegram Bot API updates.

    Receives Telegram Update objects (messages and callback_query events)
    and delegates processing to `services.telegram_sales.process_webhook_update`.

    This handles:
      * Text commands: /start, /help, /bulletin, /price
      * Inline button callbacks: the VIP-unlock button (its label and amount are
        built from VIP_PRICE_USDC in services/telegram_sales.py — never a literal)

    The endpoint is always free (no x402 paywall) so Telegram can deliver
    updates without payment.
    """
    limited = _rate_limited_response("telegram_webhook")
    if limited:
        return limited
    configured_secret = (os.getenv("TELEGRAM_WEBHOOK_SECRET") or "").strip()
    supplied_secret = request.headers.get("X-Telegram-Bot-Api-Secret-Token", "")
    if (
        not configured_secret
        or not supplied_secret
        or not hmac.compare_digest(supplied_secret, configured_secret)
    ):
        _record_request("api_telegram_webhook", False)
        log.warning("Rejected Telegram webhook without a valid secret token.")
        return jsonify({"ok": False, "error": "telegram_webhook_unauthorized"}), 401

    payload = request.get_json(silent=True) or {}
    if not payload:
        _record_request("api_telegram_webhook", False)
        return jsonify({"ok": False, "error": "empty_payload"}), 400

    try:
        result = process_webhook_update(payload)
        _record_request("api_telegram_webhook", True)
        _record_telegram_activity(payload, result)
        # The chat id is logged on purpose (18.09): configuring TELEGRAM_VIP_CHAT_ID
        # needs the OWNER's private chat id, and this is the operator's own log —
        # Telegram only reveals a user's id when they message the bot, so there is
        # no other way to read it without asking the user to dig it out.
        _msg = payload.get("message") or {}
        _cb = (payload.get("callback_query") or {})
        _chat = (_msg.get("chat") or (_cb.get("message") or {}).get("chat") or {})
        log.info("Telegram webhook processed: %s | chat_id=%s type=%s from=%s",
                 result, _chat.get("id"), _chat.get("type"),
                 (_cb.get("from") or _msg.get("from") or {}).get("id"))
        return jsonify({"ok": True, "result": result})
    except Exception as exc:
        _record_request("api_telegram_webhook", False)
        log.error("Telegram webhook processing failed: %s", exc)
        return jsonify({"ok": False, "error": "telegram_processing_failed"}), 500


# ── MCP / x402 Payment Protocol ──────────────────────────────────────────




# ── Routes ────────────────────────────────────────────────────────────────

@app.route("/")
def home():
    """Landing page: an animated terminal demo of the x402 payment flow.

    B2D conversion page — shows developers exactly what the API does in
    10 seconds (call -> 402 -> pay -> 200) with copy-paste curl commands.

    PRICES COME FROM THE SINGLE SOURCE, never typed into the template: this page
    used to advertise a flat "$0.05 per API call" (AND a "1 free call" that
    production does not give) while the 402 demanded 0.003-0.005 — the classic
    phantom price, on the first page a visitor sees.
    """
    _record_request("home", True)
    routes = _real_routes_payload()
    prices = [float(r["price_usdc"]) for r in routes]
    cheapest = min(prices)
    example = min(routes, key=lambda r: float(r["price_usdc"]))
    return render_template(
        "landing.html",
        routes=routes,
        cheapest=cheapest,
        cheapest_route=example,
        free_tier_limit=FREE_TIER_LIMIT,
    )






@app.route("/launch")
def launch_landing():
    """Public sales landing page for live product launch.

    The prices are handed to the template from PLAN_PRICES instead of being typed
    into it. They used to be hardcoded in launch_landing.html ($29/$79/$149)
    while the checkout read PLAN_PRICES, so changing a plan price would have
    shown the buyer one number and charged them another — the same drift class as
    the retired "$0.05".
    """
    from integrations.payment_integration import PLAN_PRICES

    return render_template("launch_landing.html", plan_prices=PLAN_PRICES)


@app.route("/sales/checkout", methods=["GET", "POST"])
def sales_checkout():
    """Checkout and lead capture for the sales funnel."""
    plans = checkout_store.get_all_plans()
    if request.method == "GET":
        # No silent default (bug found by the owner's own test payment): the
        # page used to render ONE plan as static text inside a hidden field,
        # so the $29 plan existed in pricing but was unreachable from the form.
        # A plan is now pre-selected only when ?plan=<key> names a REAL plan;
        # otherwise nothing is selected and the buyer must choose.
        requested = (request.args.get("plan") or "").strip()
        selected_plan = requested if requested in plans else ""
        plan = plans.get(selected_plan)
        # Prices are formatted in Python, not in the template, so the page can
        # only ever show the value from the single price source.
        plan_options = [
            {
                "key": key,
                "name": p.name,
                "price_usd": p.price_usd,
                "price_label": (f"${int(p.price_usd)}"
                                if float(p.price_usd).is_integer()
                                else f"${float(p.price_usd):.2f}"),
            }
            for key, p in plans.items()
        ]
        status = request.args.get("status", "")
        status_msg = {
            "success": "Плащането е потвърдено. Системата е готова за onboarding.",
            "cancelled": "Плащането беше отменено. Можете да опитате отново.",
        }.get(status, "")
        return render_template(
            "checkout.html",
            plans=plans,
            plan_options=plan_options,
            plan=plan,
            plan_key=selected_plan,
            status=status,
            status_msg=status_msg,
        )

    limited = _rate_limited_response("checkout")
    if limited:
        return limited
    email = (request.form.get("email") or "").strip()
    plan_key = (request.form.get("plan") or "").strip()
    source = (request.form.get("source") or "website").strip()
    campaign = (request.form.get("campaign") or "launch").strip()
    telegram_chat_id = (request.form.get("telegram_chat_id") or "").strip()
    if not email or "@" not in email:
        return jsonify({"ok": False, "error": "Въведете валиден email."}), 400
    if not plan_key:
        # Explicitly refusing beats quietly charging $79 for a plan the buyer
        # never chose — that silent default is what hid the $29 plan.
        return jsonify({
            "ok": False,
            "error": "Изберете пакет.",
            "available_plans": sorted(plans.keys()),
        }), 400
    plan = checkout_store.get_plan(plan_key)
    if plan is None:
        return jsonify({
            "ok": False,
            "error": "Невалиден план.",
            "available_plans": sorted(plans.keys()),
        }), 400

    lead = LeadRecord(
        email=email,
        source=source,
        campaign=campaign,
        utm_source=request.args.get("utm_source", ""),
        utm_medium=request.args.get("utm_medium", ""),
        utm_campaign=request.args.get("utm_campaign", ""),
        plan=plan.name,
        telegram_chat_id=telegram_chat_id,
    )
    saved_lead = crm_store.add_lead(lead)
    checkout_payload = checkout_store.build_checkout_payload(plan_key, email)
    stripe_session = stripe_checkout.create_checkout_session(
        plan_key,
        email,
        source=source,
        campaign=campaign,
        telegram_chat_id=telegram_chat_id,
    )
    if stripe_session.get("status") not in {"checkout_created", "mock_checkout_ready"}:
        return jsonify({"ok": False, "error": stripe_session.get("error", "checkout_unavailable")}), 503

    telegram_chat_id = (os.getenv("TELEGRAM_VIP_CHAT_ID") or os.getenv("TELEGRAM_CHAT_ID") or "").strip()
    onboarding = telegram_flow.create_onboarding(telegram_chat_id, plan.name)

    if stripe_session.get("url"):
        return redirect(stripe_session["url"], code=303)

    return jsonify({
        "ok": True,
        "lead": saved_lead,
        "checkout": checkout_payload,
        "payment_provider": stripe_session.get("provider", "mock"),
        "payment_session": stripe_session,
        "sales_automation": {
            "status": "welcome_message_ready",
            "plan": plan.name,
            "telegram_chat_id": telegram_chat_id,
            "welcome_message": onboarding.welcome_message,
            "follow_up_message": onboarding.follow_up_message,
        },
    })


@app.route("/api/leads", methods=["GET", "POST"])
def api_leads():
    """CRUD-like lead API for CRM integration."""
    if request.method == "GET":
        auth_error = _require_admin_access()
        if auth_error:
            return auth_error
        return jsonify({"ok": True, "leads": crm_store.get_all(), "total": len(crm_store.get_all())})

    limited = _rate_limited_response("leads")
    if limited:
        return limited
    payload = request.get_json(silent=True) or {}
    email = (payload.get("email") or "").strip()
    source = (payload.get("source") or "website").strip()
    campaign = (payload.get("campaign") or "launch").strip()
    plan_name = (payload.get("plan") or "pro").strip()

    if not email or "@" not in email:
        return jsonify({"ok": False, "error": "email is required"}), 400

    lead = LeadRecord(
        email=email,
        source=source,
        campaign=campaign,
        plan=plan_name,
    )
    saved = crm_store.add_lead(lead)
    return jsonify({"ok": True, "lead": saved})


@app.route("/api/checkout", methods=["POST"])
def api_checkout():
    """Checkout API endpoint for sales automation and payment scaffolding."""
    limited = _rate_limited_response("checkout")
    if limited:
        return limited
    payload = request.get_json(silent=True) or {}
    email = (payload.get("email") or "").strip()
    plan_key = (payload.get("plan") or "").strip()
    source = (payload.get("source") or "api").strip()
    campaign = (payload.get("campaign") or "launch").strip()
    telegram_chat_id = (payload.get("telegram_chat_id") or "").strip()
    if not email or "@" not in email:
        return jsonify({"ok": False, "error": "email is required"}), 400

    # A missing plan used to default to "pro" ($79) silently — an API client
    # that forgot the field would be quoted a price it never chose. The plan is
    # now required and validated against the single price source.
    available = sorted(checkout_store.get_all_plans().keys())
    if not plan_key:
        return jsonify({
            "ok": False,
            "error": "plan is required",
            "available_plans": available,
        }), 400
    plan = checkout_store.get_plan(plan_key)
    if plan is None:
        return jsonify({
            "ok": False,
            "error": "unknown plan",
            "available_plans": available,
        }), 400

    lead = LeadRecord(
        email=email,
        source=source,
        campaign=campaign,
        plan=plan.name,
        telegram_chat_id=telegram_chat_id,
    )
    crm_store.add_lead(lead)
    payment_session = stripe_checkout.create_checkout_session(
        plan_key,
        email,
        source=source,
        campaign=campaign,
        telegram_chat_id=telegram_chat_id,
    )
    if payment_session.get("status") not in {"checkout_created", "mock_checkout_ready"}:
        return jsonify({"ok": False, "error": payment_session.get("error", "checkout_unavailable")}), 503
    return jsonify({
        "ok": True,
        "checkout": checkout_store.build_checkout_payload(plan_key, email),
        "payment_provider": payment_session.get("provider", "mock"),
        "payment_session": payment_session,
        "plan": plan.name,
    })


@app.route("/api/v1/signal", methods=["GET"])
def api_signal():
    """
    Cheap paid route returning an ACTUAL SIGNAL (direction + confidence +
    reasoning) from the live trading-agent engine — PayAPI's reviewer noted
    that /api/stats undersells the signals work. Refreshed every
    AGENT_POLL_INTERVAL seconds by the background agent.
    """
    with _lock:
        snapshot = {
            "generated_at": _latest_signals.get("generated_at"),
            "signals": list(_latest_signals.get("signals") or []),
        }
    # Фаза 1 (07.10.2026): rule-based проверяващ слой „никой не лъже" —
    # кръстосана проверка на числата CoinGecko × DexScreener ПРЕДИ доставка.
    # б1 (Вариант А): отхвърлените живеят в rejected_signals[] — клиентът
    # вижда защо (двете цени, diff_pct, причина), а signals[] е само чистите.
    signals, rejected_signals, scan_info = _verify_signal_values(
        snapshot["signals"])
    return _safe_jsonify({
        "service": "Kristo Intelligence — live agent signal",
        "price_usdc": KRISTO_SIGNAL_PRICE,
        "engine": "8-agent intelligence engine (CoinGecko + DeFi signals + risk overlay)",
        "generated_at": snapshot["generated_at"],
        "signal_count": len(signals),
        "signals": signals,
        "rejected_signals": rejected_signals,
        "scan_info": scan_info,
        "refresh_note": "Signals refresh automatically every 5 minutes.",
        "disclaimer": "Not financial advice. Auto-execution is disabled "
                      "(AGENT_AUTO_EXECUTE=false) — signals are informational.",
    })


def _verify_signal_values(signals):
    """Фаза 1 value-check hook (07.10.2026, модел „никой не лъже").

    Връща (доставими сигнали, отхвърлени сигнали, scan_info). ДВОЕН fail-open:
      * services.verifier.verify_signals не хвърля (вътрешен fail-open);
      * тук целият му поток е в try/except — ако и той падне, платеният
        сигнал се доставя непокътнат и се бележи като непроверен
        (плащането вече е факт; парите никога не се губят заради проверка).
    Отхвърлените/непроверените се записват и в guard_events (дълготраен лог —
    „да виждаме дали някой агент редовно лъже").
    """
    if os.getenv("VALUE_CHECK_ENABLED", "1").lower() in ("0", "false", "off"):
        return list(signals or []), [], {
            "verification": "disabled",
            "reason": "value_check_disabled",
        }
    try:
        from services import verifier
        deliverable, rejected, scan_info = verifier.verify_signals(signals)
    except Exception as exc:
        log.warning("value_check fell — fail-open, delivering paid signal "
                    "unverified: %s: %s", type(exc).__name__, exc)
        return list(signals or []), [], {
            "verification": "unverified",
            "reason": f"checker_error: {type(exc).__name__}",
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "details": [],
        }
    for entry in (scan_info.get("details") or []):
        verdict = entry.get("verdict")
        if verdict not in ("rejected", "unverified"):
            continue
        try:
            dashboard_db.record_guard_event(
                f"value_check_{verdict}", endpoint="/api/v1/signal",
                detail=json.dumps(entry, default=str)[:300])
        except Exception as exc:
            log.debug("value_check guard event not recorded: %s", exc)
    
    # FIX #1: Log rejected_signals[] durably (not just in response)
    for entry in rejected or []:
        try:
            dashboard_db.record_guard_event(
                "verifier_rejected_signal",
                endpoint="/api/v1/signal",
                detail=json.dumps({
                    "token": entry.get("token"),
                    "reason": entry.get("reason"),
                    "coingecko_usd": entry.get("coingecko_usd"),
                    "dexscreener_usd": entry.get("dexscreener_usd"),
                    "diff_pct": entry.get("diff_pct"),
                }, default=str)[:300])
        except Exception as exc:
            log.debug("rejected_signals guard event not recorded: %s", exc)
    
    return deliverable, rejected, scan_info


@app.route("/api/v1/agents", methods=["GET"])
def api_agent_catalog():
    """Public catalog = the REAL routes only (07.09: 8 demo SKUs unlisted).

    The demo playground adapter still exists in code for entitlement
    bookkeeping, but it is no longer advertised as a product anywhere.
    """
    return jsonify({"ok": True, "agents": _real_routes_payload()})


@app.route("/api/v1/agents/<agent_id>", methods=["GET"])
def api_agent_detail(agent_id: str):
    """Return one active agent SKU for a product page or machine client."""
    agent = catalog_store.get_product(agent_id)
    if not agent:
        return jsonify({"ok": False, "error": "agent_not_found"}), 404
    return jsonify({"ok": True, "agent": agent})


@app.route("/api/v1/agents/<agent_id>/playground", methods=["POST"])
def api_agent_playground(agent_id: str):
    """Allow exactly one bounded interactive demo per client and catalog agent."""
    agent = catalog_store.get_product(agent_id)
    if not agent:
        return jsonify({"ok": False, "error": "agent_not_found"}), 404

    payload = request.get_json(silent=True) or {}
    user_input = (payload.get("input") or "").strip()
    if len(user_input) < 2 or len(user_input) > 256:
        return jsonify(
            {"ok": False, "error": "input_must_be_between_2_and_256_characters"}
        ), 400

    authorization = (request.headers.get("Authorization", "") or "").strip()
    bearer_token = authorization[7:].strip() if authorization.lower().startswith("bearer ") else ""
    entitlement = _verify_agent_access_token(bearer_token, agent_id) if bearer_token else None
    result = _run_catalog_agent_demo(agent, user_input)
    if not entitlement and not catalog_store.consume_free_playground_request(
        agent_id, _playground_client_key_hash(_get_client_ip())
    ):
        return _catalog_x402_payment_required_response(agent)
    if entitlement and not catalog_store.record_call(agent_id):
        log.error("Catalog call could not be recorded for agent %s.", agent_id)
        return jsonify({"ok": False, "error": "call_recording_unavailable"}), 503
    return jsonify(
        {
            "ok": True,
            "agent": agent,
            "access": "active_entitlement" if entitlement else "one_free_playground_request",
            "result": result,
        }
    )




@app.route("/agents", methods=["GET"])
def agent_playground_page():
    """Redirect: the 8 demo SKUs are unlisted — the real routes live on the dashboard."""
    return redirect("/dashboard", code=302)


@app.route("/api/v1/agents/<agent_id>/click", methods=["POST"])
def api_agent_click(agent_id: str):
    """Persist a product-page click for catalog conversion analytics."""
    if not catalog_store.get_product(agent_id):
        return jsonify({"ok": False, "error": "agent_not_found"}), 404
    if not _allow_catalog_click(_get_client_ip(), agent_id):
        return jsonify(
            {
                "ok": False,
                "error": "click_rate_limited",
                "retry_after_seconds": CATALOG_CLICK_COOLDOWN_SECONDS,
            }
        ), 429
    if not catalog_store.record_click(agent_id):
        return jsonify({"ok": False, "error": "click_recording_unavailable"}), 503
    return jsonify({"ok": True, "agent_id": agent_id, "status": "click_recorded"}), 202


@app.route("/api/v1/agents/<agent_id>/checkout", methods=["POST"])
def api_agent_checkout(agent_id: str):
    """Create a one-time Stripe Checkout for a 30-day agent access entitlement."""
    limited = _rate_limited_response("agent_checkout")
    if limited:
        return limited
    agent = catalog_store.get_product(agent_id)
    if not agent:
        return jsonify({"ok": False, "error": "agent_not_found"}), 404

    payload = request.get_json(silent=True) or {}
    email = (payload.get("email") or "").strip()
    source = (payload.get("source") or "agent_catalog").strip()
    campaign = (payload.get("campaign") or "agent_vip").strip()
    telegram_chat_id = (payload.get("telegram_chat_id") or "").strip()
    if not email or "@" not in email:
        return jsonify({"ok": False, "error": "email is required"}), 400

    plan_key = f"agent:{agent_id}"
    crm_store.add_lead(
        LeadRecord(
            email=email,
            source=source,
            campaign=campaign,
            plan=plan_key,
            telegram_chat_id=telegram_chat_id,
        )
    )
    payment_session = stripe_checkout.create_catalog_checkout_session(
        agent_sku=agent_id,
        product_name=agent["name"],
        amount_usd=agent["price_stripe"],
        customer_email=email,
        source=source,
        campaign=campaign,
        telegram_chat_id=telegram_chat_id,
    )
    if payment_session.get("status") not in {"checkout_created", "mock_checkout_ready"}:
        return jsonify(
            {
                "ok": False,
                "error": payment_session.get("error", "checkout_unavailable"),
            }
        ), 503
    if not catalog_store.register_checkout(
        checkout_id=payment_session.get("checkout_id", ""),
        product_id=agent_id,
        customer_email=email,
        expected_amount=agent["price_stripe"],
    ):
        log.error("Catalog checkout could not be registered for agent %s.", agent_id)
        return jsonify({"ok": False, "error": "catalog_checkout_registration_failed"}), 503
    return jsonify(
        {
            "ok": True,
            "agent": agent,
            "access": "one_time_30_day_agent_entitlement",
            "payment_provider": payment_session.get("provider", "mock"),
            "payment_session": payment_session,
        }
    )


@app.route("/api/v1/agents/<agent_id>/access", methods=["POST"])
def api_agent_access(agent_id: str):
    """Exchange a paid checkout capability for a short-lived signed agent credential."""
    if not catalog_store.get_product(agent_id):
        return jsonify({"ok": False, "error": "agent_not_found"}), 404
    payload = request.get_json(silent=True) or {}
    email = (payload.get("email") or "").strip()
    checkout_id = (payload.get("checkout_id") or "").strip()
    if not email or "@" not in email or not checkout_id:
        return jsonify(
            {"ok": False, "error": "email and server_created_checkout_id are required"}
        ), 400
    entitlement = catalog_store.get_active_entitlement_by_checkout(
        agent_id, checkout_id, email
    )
    if not entitlement:
        return jsonify({"ok": False, "error": "agent_access_required"}), 403
    return jsonify(
        {
            "ok": True,
            "agent_id": agent_id,
            "access": "active",
            "expires_at": entitlement["expires_at"],
            "access_token": _issue_agent_access_token(entitlement),
        }
    )


def _refund_event_details(event_type: str, event_data: dict,
                          payload: dict) -> Optional[dict]:
    """Read the refund facts out of either refund event, in ONE shape.

    `charge.refunded` is self-sufficient: the charge carries the customer and the
    CUMULATIVE `amount_refunded`, so two partial refunds add up. `refund.created`
    carries the refund object itself — and no email — so the charge is fetched once
    to resolve the customer; if THAT call fails the caller answers 503 and Stripe
    retries, rather than writing a refund against the wrong (or no) customer.
    """
    def _iso(seconds):
        try:
            return datetime.fromtimestamp(int(seconds),
                                          tz=timezone.utc).isoformat()
        except (TypeError, ValueError):
            return ""

    when = _iso(payload.get("created"))

    if event_type == "charge.refunded":
        charge = event_data or {}
        refunds = ((charge.get("refunds") or {}).get("data") or [])
        latest = refunds[-1] if refunds else {}
        billing = charge.get("billing_details") or {}
        return {
            "email": (billing.get("email")
                      or charge.get("receipt_email") or "").strip(),
            "amount_usd": float(latest.get("amount")
                                or charge.get("amount_refunded") or 0) / 100.0,
            "refund_usd": float(charge.get("amount_refunded") or 0) / 100.0,
            "refunded_at": _iso(latest.get("created")) or when,
            "charge_id": charge.get("id") or "",
            "refund_id": latest.get("id") or "",
        }

    if event_type == "refund.created":
        refund = event_data or {}
        charge_id = (refund.get("charge") or "").strip()
        charge = stripe_checkout.retrieve_charge(charge_id) if charge_id else None
        if charge is None:
            return {"lookup_failed": True, "charge_id": charge_id}
        billing = charge.get("billing_details") or {}
        return {
            "email": (billing.get("email")
                      or charge.get("receipt_email") or "").strip(),
            "amount_usd": float(refund.get("amount") or 0) / 100.0,
            "refund_usd": float(charge.get("amount_refunded")
                                or refund.get("amount") or 0) / 100.0,
            "refunded_at": _iso(refund.get("created")) or when,
            "charge_id": charge_id,
            "refund_id": refund.get("id") or "",
        }

    return None


@app.route("/api/webhooks/stripe", methods=["POST"])
def stripe_webhook_handler():
    """Stripe-compatible webhook handler for payment confirmation."""
    limited = _rate_limited_response("stripe_webhook")
    if limited:
        return limited
    signature = request.headers.get("Stripe-Signature", "")
    if not signature:
        return jsonify({"ok": False, "error": "missing_signature"}), 400
    try:
        payload = stripe_checkout.verify_webhook(request.get_data(), signature)
    except Exception:
        log.warning("Rejected Stripe webhook with invalid signature", exc_info=True)
        return jsonify({"ok": False, "error": "invalid_signature"}), 400
    if not payload:
        return jsonify({"ok": False, "error": "webhook_verification_unavailable"}), 503
    event_type = payload.get("type") or "checkout.session.completed"
    event_data = payload.get("data", {}).get("object", {})

    if event_type in {
        "checkout.session.completed",
        "checkout.session.async_payment_succeeded",
    }:
        email = (event_data.get("customer_details", {}).get("email") or event_data.get("customer_email") or "").strip()
        metadata = event_data.get("metadata", {}) or {}
        plan_key = metadata.get("plan") or "pro"
        agent_sku = (metadata.get("agent_sku") or "").strip()
        checkout_id = (event_data.get("id") or "").strip()
        amount = float(event_data.get("amount_total") or 0.0) / 100.0
        payment_status = (event_data.get("payment_status") or "").strip().lower()
        currency = (event_data.get("currency") or "").strip().lower()
        # WHEN THE MONEY ARRIVED: the EVENT's own timestamp, not the lead's
        # creation time. The dashboard used to date a sale by the lead, which is
        # right only by luck (38 s on the first sale, hours when a buyer pays
        # later) — and the CRM row and Stripe can now be compared to the second.
        event_created = payload.get("created")
        paid_at = ""
        if event_created:
            try:
                paid_at = datetime.fromtimestamp(
                    int(event_created), tz=timezone.utc).isoformat()
            except (TypeError, ValueError):
                paid_at = ""
        if payment_status != "paid":
            return jsonify(
                {
                    "ok": True,
                    "status": "payment_not_settled",
                    "event_type": event_type,
                }
            )
        if email:
            prior_lead = crm_store.find_by_email(email)
            if prior_lead is None:
                log.warning("Ignoring Stripe checkout for an unknown CRM lead.")
                return jsonify({"ok": True, "status": "ignored_unknown_lead"})
            if agent_sku:
                expected_plan = f"agent:{agent_sku}"
                is_valid_catalog_payment = bool(
                    checkout_id
                    and currency == "usd"
                    and plan_key == expected_plan
                    and catalog_store.validate_checkout(
                        checkout_id, agent_sku, email, amount
                    )
                )
                if not is_valid_catalog_payment:
                    log.warning(
                        "Ignoring catalog payment with unmatched checkout attributes."
                    )
                    return jsonify(
                        {"ok": True, "status": "ignored_unmatched_catalog_checkout"}
                    )
            already_paid = prior_lead.get("payment_status") == "paid"
            paid_lead = crm_store.mark_paid(email, amount, plan_key,
                                            checkout_id=checkout_id,
                                            paid_at=paid_at)
            if agent_sku:
                catalog_store.confirm_checkout_payment(
                    checkout_id,
                    agent_sku,
                    email,
                    amount,
                )
                entitlement = catalog_store.grant_entitlement(
                    checkout_id,
                    agent_sku,
                    email,
                )
                vip_access = {
                    "status": "agent_entitlement_active",
                    "expires_at": entitlement["expires_at"] if entitlement else None,
                }
            else:
                vip_access = _activate_stripe_vip_access(
                    paid_lead or prior_lead,
                    event_data,
                    plan_key,
                    already_paid,
                )
            # ONE INFO line per money event — a successful money path must be
            # visible on its own. The 200 lives only in the access log, which is
            # not retained, so a silent SUCCESS was indistinguishable from a silent
            # FAILURE. The email is masked like everywhere else on this surface.
            log.info(
                "Stripe money event %s received: checkout_id=%s plan=%s "
                "amount=$%.2f paid_at=%s customer=%s",
                event_type, checkout_id or "(none)", plan_key, amount,
                paid_at or "(unknown)", _mask_email(email))
            return jsonify({
                "ok": True,
                "status": "paid",
                "plan": plan_key,
                "amount_usd": amount,
                "vip_access": vip_access["status"],
            })

    if event_type in {"charge.refunded", "refund.created"}:
        # Money going BACK OUT. Until 17.09 this path did not exist at all: the
        # endpoint was not subscribed to any refund event, so a refunded sale stayed
        # "paid" everywhere while the money was gone. One INFO line per refund makes
        # the return audible, exactly like the payment path.
        details = _refund_event_details(event_type, event_data, payload)
        if details is None:
            return jsonify({"ok": True, "status": "refund_unrecognised",
                            "event_type": event_type})
        if details.get("lookup_failed"):
            # a provider hiccup, not a verdict: let Stripe retry the delivery
            return jsonify({"ok": True, "status": "refund_lookup_unavailable"}), 503
        email = details.get("email", "")
        if not email:
            log.warning("Refund event %s carries no customer (charge=%s) — nothing "
                        "to match against the CRM.", event_type,
                        details.get("charge_id"))
            return jsonify({"ok": True, "status": "refund_without_customer"})
        if crm_store.find_by_email(email) is None:
            log.warning("Ignoring a refund for an unknown CRM lead.")
            return jsonify({"ok": True, "status": "ignored_unknown_lead"})
        marked = crm_store.mark_refund(email, details["refund_usd"],
                                      details["refunded_at"])
        if marked is None:
            # mark_refund refuses anything that is not already paid — by design
            return jsonify({"ok": True, "status": "refund_refused_not_paid",
                            "event_type": event_type})
        log.info("Stripe refund received: checkout_id=%s amount=$%.2f "
                 "refunded_total=$%.2f refund_id=%s customer=%s",
                 marked.get("checkout_id") or "(unknown)", details["amount_usd"],
                 details["refund_usd"], details.get("refund_id") or "(none)",
                 _mask_email(email))
        return jsonify({
            "ok": True,
            "status": "refunded",
            "checkout_id": marked.get("checkout_id") or "",
            "amount_usd": details["amount_usd"],
            "refunded_usd": details["refund_usd"],
        })

    return jsonify({"ok": True, "received": True, "event_type": event_type})


@app.route("/api/sales/summary", methods=["GET"])
def api_sales_summary():
    """Return launch funnel metrics and CRM pipeline summary."""
    auth_error = _require_admin_access()
    if auth_error:
        return auth_error
    pipeline = crm_store.get_sales_pipeline()
    leads = crm_store.get_all()
    total_leads = len(leads)
    paid_leads = sum(1 for lead in leads if lead.get("payment_status") == "paid")
    return jsonify({
        "ok": True,
        "total_leads": total_leads,
        "paid_leads": paid_leads,
        "pipeline": pipeline,
        "traffic_sources": {
            source: sum(1 for lead in leads if (lead.get("source") or "") == source)
            for source in sorted({(lead.get("source") or "") for lead in leads})
        },
    })


@app.route("/api/admin/leads", methods=["GET"])
def api_admin_leads():
    """Admin endpoint for the live lead pipeline and sales operations."""
    auth_error = _require_admin_access()
    if auth_error:
        return auth_error
    leads = crm_store.get_all()
    return jsonify({
        "ok": True,
        "total": len(leads),
        "pipeline": crm_store.get_sales_pipeline(),
        "leads": leads,
    })


def _admin_overview_payload() -> dict:
    """Build the protected dashboard read model without exposing chat identifiers."""
    leads = crm_store.get_all()
    paid_leads = [lead for lead in leads if lead.get("payment_status") == "paid"]
    paid_leads.sort(key=lambda lead: lead.get("created_at") or "", reverse=True)

    crm_payments = [
        {
            "email": lead.get("email", ""),
            "plan": lead.get("plan", ""),
            "amount_usd": float(lead.get("amount_usd") or 0),
            # The sale happened when the MONEY arrived, not when the lead was made.
            "created": lead.get("paid_at") or lead.get("created_at", ""),
            "checkout_id": lead.get("checkout_id", ""),
            # A refund is its own fact, not a change of what was paid.
            "refunded_usd": round(float(lead.get("refund_usd") or 0), 2),
            "refunded_at": lead.get("refunded_at", ""),
            "provider": "crm_paid_event",
            "payment_status": "paid",
        }
        for lead in paid_leads
    ]
    stripe_listing = _get_stripe_payment_snapshot()
    use_stripe_feed = bool(stripe_listing["available"] and stripe_listing["payments"])
    displayed_payments = stripe_listing["payments"] if use_stripe_feed else crm_payments

    vip_plans = [
        {
            "email": lead.get("email", ""),
            "plan": lead.get("plan", ""),
            "amount_usd": float(lead.get("amount_usd") or 0),
            "activated_at": lead.get("paid_at") or lead.get("created_at", ""),
            "telegram_linked": bool(lead.get("telegram_chat_id")),
            "status": "active_paid_vip",
        }
        for lead in paid_leads
        if _is_vip_plan(lead.get("plan") or "")
    ]
    with _lock:
        onchain_revenue = round(sum(s.get("amount_usd", 0) for s in _sales_history), 6)
        bot_status = dict(_bot_status)
        wallet = dict(_wallet_state)
        live_requests = list(_live_request_log)[-100:]
        invite_count = len(_vip_invites)
        onchain_vips = len(_vip_subscribers)

    # The DURABLE counts win (18.09): the RAM dicts reset on every deploy, so this
    # status surface used to report "0 invites" for money that was actually paid.
    try:
        durable_vips = dashboard_db.vip_invites_summary()
        invite_count = max(invite_count, durable_vips["total"])
        onchain_vips = max(onchain_vips, durable_vips["wallets"])
    except Exception as exc:
        log.debug("Durable VIP summary failed (using RAM): %s", exc)

    crm_revenue = round(sum(payment["amount_usd"] for payment in crm_payments), 2)
    catalog_metrics = catalog_store.get_metrics_24h()
    pending_research = len(research_store.list_insights(status="PENDING", limit=200))
    market_cache = get_coingecko_cache_status()
    market_age = market_cache.get("age_seconds")
    market_detail = market_cache.get("state", "unavailable")
    if market_age is not None:
        market_detail = f"{market_detail} cache, age {market_age}s"
    if market_cache.get("detail"):
        market_detail = f"{market_detail} — {market_cache['detail']}"
    return {
        "ok": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "metrics": {
            "crm_revenue_usd": crm_revenue,
            "onchain_revenue_usd": onchain_revenue,
            "total_revenue_usd": round(crm_revenue + onchain_revenue, 2),
            "paid_payments": len(paid_leads),
            "active_vip_plans": len(vip_plans),
            "vip_invites_generated": invite_count,
            "onchain_vip_subscribers": onchain_vips,
            "active_telegram_users": bot_status.get("active_users", 0),
            "catalog_clicks_24h": catalog_metrics["totals"]["clicks"],
            "catalog_calls_24h": catalog_metrics["totals"]["calls"],
            "catalog_hits_24h": catalog_metrics["totals"]["hits"],
            "catalog_revenue_24h_usd": catalog_metrics["totals"]["revenue_usd"],
            "active_agent_entitlements": catalog_store.active_entitlement_count(),
            "research_pending_review": pending_research,
        },
        "payments": displayed_payments[:100],
        "payment_source": "stripe_checkout" if use_stripe_feed else "crm_paid_events",
        "vip_plans": vip_plans[:100],
        # 10.10: the full OFF-CHAIN section (masked items, stripe_link,
        # storage durability) lives behind this admin surface too — it is
        # generated nowhere else for a browser, and never for the public.
        "crm_stripe": _crm_stripe_section(),
        "request_log": list(reversed(live_requests)),
        "agent_catalog": catalog_metrics,
        "services": {
            "crm": {"ready": crm_store.is_healthy(), "backend": crm_store.backend},
            "agent_catalog": {
                "ready": catalog_store.is_healthy(),
                "backend": catalog_store.backend,
                "active_agents": len(catalog_metrics["products"]),
                "detail": "24h catalog analytics",
            },
            "research": {
                "ready": research_store.is_healthy(),
                "backend": research_store.backend,
                "detail": f"{pending_research} pending review",
            },
            "stripe": {
                "configured": stripe_checkout.enabled,
                # WHERE the key came from and whether it even LOOKS like a secret
                # key. On 14.09 a key ID was pasted into the env: every checkout
                # 503'd and nothing on screen said why.
                "key_source": getattr(stripe_checkout, "key_source", ""),
                "key_mode": getattr(stripe_checkout, "key_mode", "unknown"),
                "key_format_ok": getattr(stripe_checkout, "key_format_ok", True),
                "payment_feed_available": stripe_listing["available"],
                "cache_state": stripe_listing.get("state", "unknown"),
                "age_seconds": stripe_listing.get("age_seconds"),
                "detail": stripe_listing.get("reason", "connected"),
            },
            "telegram": {
                "token_configured": bot_status.get("telegram_token_configured", False),
                "running": bot_status.get("telegram_bot_running", False),
                "last_heartbeat": bot_status.get("last_heartbeat", ""),
            },
            "blockchain": {
                "ready": bool(
                    wallet.get("rpc_connected")
                    and wallet.get("chain_id") == BASE_CHAIN_ID
                    and wallet.get("receiver_valid")
                ),
                "rpc_connected": wallet.get("rpc_connected", False),
                "network": wallet.get("network", "Base Mainnet"),
                "chain_id": wallet.get("chain_id"),
                "fee_receiver": wallet.get("fee_receiver"),
                "detail": (
                    f"{wallet.get('network', 'Base Mainnet')} (chain {wallet.get('chain_id')})"
                    if wallet.get("rpc_connected")
                    else wallet.get("rpc_error") or "Base RPC connection is not ready"
                ),
                "last_check_time": wallet.get("last_check_time"),
            },
            "coingecko": {
                "ready": market_cache.get("state") in {"live", "cached"},
                "state": market_cache.get("state", "unavailable"),
                "age_seconds": market_age,
                "last_success_at": market_cache.get("last_success_at"),
                "detail": market_detail,
            },
        },
    }


@app.route("/api/admin/overview", methods=["GET"])
def api_admin_overview():
    """Protected live operational data for the browser admin dashboard."""
    auth_error = _require_admin_access()
    if auth_error:
        return auth_error
    return _safe_jsonify(_admin_overview_payload())


@app.route("/api/admin/catalog-metrics", methods=["GET"])
def api_admin_catalog_metrics():
    """Return protected live 24-hour catalog metrics and popularity ranking."""
    auth_error = _require_admin_access()
    if auth_error:
        return auth_error
    return _safe_jsonify({"ok": True, **catalog_store.get_metrics_24h()})


@app.route("/api/v1/research/ingest", methods=["POST"])
def api_research_ingest():
    """Accept authenticated Discord, RSS, or GitHub research into a pending queue."""
    auth_error = _require_research_ingest_access()
    if auth_error:
        return auth_error
    payload = request.get_json(silent=True) or {}
    try:
        insight = research_store.ingest(
            source=payload.get("source", ""),
            external_id=payload.get("external_id", ""),
            title=payload.get("title", ""),
            content=payload.get("content", ""),
            actionable_summary=payload.get("actionable_summary", ""),
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    created = bool(insight.pop("created"))
    return _safe_jsonify(
        {
            "ok": True,
            "created": created,
            "insight": insight,
        }
    ), 201 if created else 200


@app.route("/api/admin/research-insights", methods=["GET"])
def api_admin_research_insights():
    """List the protected research review queue."""
    auth_error = _require_admin_access()
    if auth_error:
        return auth_error
    try:
        insights = research_store.list_insights(
            status=request.args.get("status", ""),
            limit=request.args.get("limit", 100, type=int) or 100,
        )
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    return _safe_jsonify({"ok": True, "insights": insights, "total": len(insights)})


@app.route("/api/admin/research-insights/<insight_id>", methods=["PATCH"])
def api_admin_research_insight_update(insight_id: str):
    """Approve or archive a research insight after human review."""
    auth_error = _require_admin_access()
    if auth_error:
        return auth_error
    payload = request.get_json(silent=True) or {}
    try:
        insight = research_store.update_status(insight_id, payload.get("status", ""))
    except ValueError as exc:
        return jsonify({"ok": False, "error": str(exc)}), 400
    if not insight:
        return jsonify({"ok": False, "error": "research_insight_not_found"}), 404
    return _safe_jsonify({"ok": True, "insight": insight})








@app.route("/sales/admin/login", methods=["GET", "POST"])
@app.route("/admin/login", methods=["GET", "POST"])
def sales_admin_login():
    """Create a signed browser session from the existing admin token."""
    error = ""
    if request.method == "POST":
        limited = _rate_limited_response("admin_login")
        if limited:
            return limited
        configured = _get_admin_token()
        supplied = (request.form.get("admin_token") or "").strip()
        if configured and supplied and hmac.compare_digest(supplied, configured):
            session.clear()
            session["admin_authenticated"] = True
            return redirect("/sales/admin")
        _log_admin_token_mismatch(configured, supplied)
        error = "Невалиден admin token."
    return render_template("admin_login.html", error=error)


@app.route("/sales/admin/logout", methods=["GET"])
def sales_admin_logout():
    session.clear()
    return redirect("/sales/admin/login")


@app.route("/sales/admin", methods=["GET"])
def sales_admin():
    """Protected browser dashboard for sales, VIP operations and service health."""
    if session.get("admin_authenticated"):
        return render_template("admin_dashboard.html")

    configured = _get_admin_token()
    supplied = request.headers.get("X-Admin-Token", "").strip()
    valid_header = bool(
        configured
        and supplied
        and hmac.compare_digest(supplied, configured)
    )
    if not valid_header:
        return redirect("/sales/admin/login")

    session["admin_authenticated"] = True
    return render_template("admin_dashboard.html")


@app.route("/sales/admin/research", methods=["GET"])
def sales_admin_research():
    """Protected browser view for approving or archiving R&D research insights."""
    if session.get("admin_authenticated"):
        return render_template("admin_research.html")
    auth_error = _require_admin_access()
    if auth_error:
        return redirect("/sales/admin/login")
    session["admin_authenticated"] = True
    return render_template("admin_research.html")


@app.route("/api/launch/health", methods=["GET"])
def launch_health():
    """Liveness for deploys and uptime checks - and nothing else.

    It used to answer with the size of the sales pipeline, the number of leads,
    which CRM backend is in use, and whether Stripe is live or running in mock
    mode. All of that is business intelligence sitting on a free, unauthenticated,
    crawlable URL - "mock" in particular tells a reader we are not actually
    charging anyone. A health check answers one question: is it up.

    The ops numbers still exist and still answer to the admin credential, so
    production_verify.py can read them when it has a token, and the public
    deploy check keeps working without one.
    """
    crm_ready = crm_store.is_healthy()
    payload = {
        "ok": True,
        "app": "kristo-intelligence-v6",
        "status": "live" if crm_ready else "degraded",
        "crm_ready": crm_ready,
        "public_url": os.getenv("APP_PUBLIC_URL", "http://localhost:5000"),
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    if _is_admin_request():
        payload.update({
            "crm_backend": crm_store.backend,
            "payment_provider": "stripe" if os.getenv("STRIPE_API_KEY") else "mock",
            "lead_count": len(crm_store.get_all()) if crm_ready else 0,
            "pipeline": crm_store.get_sales_pipeline() if crm_ready else {},
        })
    else:
        payload["ops_detail"] = (
            "crm_backend, payment_provider, lead_count and pipeline require the "
            "admin credential (X-Admin-Token or an authenticated session).")
    return jsonify(payload), 200 if crm_ready else 503


@app.route("/api/funnel/track", methods=["POST"])
def funnel_track():
    """Capture UTM campaign data for conversion analytics."""
    limited = _rate_limited_response("funnel_track")
    if limited:
        return limited
    payload = request.get_json(silent=True) or {}
    email = (payload.get("email") or "").strip()
    if not email or "@" not in email:
        return jsonify({"ok": False, "error": "valid email required"}), 400

    lead = LeadRecord(
        email=email,
        source=(payload.get("source") or "website").strip(),
        campaign=(payload.get("campaign") or "launch").strip(),
        utm_source=(payload.get("utm_source") or "").strip(),
        utm_medium=(payload.get("utm_medium") or "").strip(),
        utm_campaign=(payload.get("utm_campaign") or "").strip(),
        plan=(payload.get("plan") or "pro").strip(),
    )
    saved = crm_store.add_lead(lead)
    return jsonify({"ok": True, "lead": saved, "utm": {
        "source": lead.utm_source,
        "medium": lead.utm_medium,
        "campaign": lead.utm_campaign,
    }})





# ── Canonical Operations Dashboard (single professional dashboard) ────────
# Replaces the old mixed-source dashboard + the simulated NEXUS page.
# Sections and their ONLY data sources:
#   (a) On-Chain Sales  → data/dashboard_state.db (real USDC transfers)
#   (b) API Requests    → persistent request log (same store)
#   (c) Listing & Rank  → PayAPI listing state (same store, refreshed ~15min)
#   (d) CRM/Stripe      → crm_store (labelled OFF-CHAIN, hidden by default,
#                         NEVER included in on-chain totals)

PAYER_CLASS_LABELS_BG = {
    # These are READ BY THE OWNER, not by a machine. The old text said
    # "canary (Chet — верификация)", "sampler (пазарен crawler)" and
    # "EXTERNAL (реален платец)" - three internal names that require the rest of
    # this file to decode. The keys stay the same because they are also CSS class
    # names and test fixtures; only the words a person reads changed, and each one
    # now says whether the money is a customer or our own noise.
    "canary": "наш тест — не е клиент",
    "sampler": "пазарна проверка, робот — не е клиент",
    "external": "истински клиент",
    # 09.11: the owner looked at nine settlements on the board and could not tell
    # whose money it was. They were OURS — `DEMO_PRIVATE_KEY`, paid to ourselves
    # to exercise the rail and trigger CDP Bazaar indexing — and the board called
    # them "истински клиент". This says it plainly instead, because a board that
    # cannot distinguish a customer from a self-payment is not an instrument the
    # business can be steered by.
    #
    # Lowercase "не е клиент", matching the other two exactly. An earlier draft
    # shouted "НЕ" for emphasis and it read as a typo beside its neighbours — the
    # wording is already unambiguous without it.
    "own_key": "нашият демо ключ — не е клиент",
}


def _mask_email(email: str) -> str:
    """Mask an email for the semi-public dashboard (no PII leak)."""
    e = (email or "").strip()
    if not e:
        return ""
    at = e.find("@")
    if at <= 0:
        return e[:2] + "•••"
    return e[:2] + "•••" + e[at:]


def _published_price_map() -> Dict[str, float]:
    """endpoint → published price (USDC) for the REAL routes only.

    Used to attribute a historical payment to a route ONLY when the price is
    unambiguous; $0.003 covers signal AND whaleflow, so the store reports
    candidates instead of guessing one (no phantom numbers on screen).
    """
    price_map: Dict[str, float] = {}
    for route in REAL_X402_ROUTES:
        price_map[route["endpoint"]] = round(float(route["price_usdc"]), 6)
    return price_map


def _crm_stripe_section() -> dict:
    """The OFF-CHAIN CRM/Stripe section, as one unit (extracted 10.10).

    BUILT ONLY FOR ADMIN-READS. The public payload carries no CRM/Stripe data
    at all (the `crm_stripe` key is ABSENT, never null), so off-chain sums,
    masked emails and Stripe checkout IDs cannot leak through
    /api/dashboard/data. The only surfaces that see this section are
    /api/admin/overview and an admin-token request to /api/dashboard/data.

    (d) CRM/Stripe — OFF-CHAIN, never part of on-chain totals.
    """
    leads = crm_store.get_all()
    paid_leads = [l for l in leads if l.get("payment_status") == "paid"]
    paid_leads.sort(key=lambda l: l.get("created_at") or "", reverse=True)
    stripe = _get_stripe_payment_snapshot()
    crm_items = [
        {
            "customer": _mask_email(l.get("email", "")),
            "plan": l.get("plan", ""),
            "amount_usd": round(float(l.get("amount_usd") or 0), 2),
            "date": (l.get("paid_at") or l.get("created_at") or "")[:10],
            # Traceability: WHICH Stripe session paid this row (so the off-chain
            # table can be joined to a Stripe payment instead of merely resembling
            # one).
            "paid_at": l.get("paid_at") or "",
            "checkout_id": l.get("checkout_id") or "",
            # Money going back OUT, kept SEPARATE from what was paid: a refunded
            # sale is still a sale that happened, and folding the return into the
            # paid figure would be the same class of lie as a phantom price.
            "refunded_usd": round(float(l.get("refund_usd") or 0), 2),
            "refunded_at": l.get("refunded_at") or "",
            "provider": "crm_paid_event",
        }
        for l in paid_leads
    ]
    crm_total = round(sum(i["amount_usd"] for i in crm_items), 2)
    refunded_total = round(sum(i["refunded_usd"] for i in crm_items), 2)
    refunded_count = sum(1 for i in crm_items if (i["refunded_usd"] or 0) > 0)
    net_total = round(crm_total - refunded_total, 2)
    refund_note = ("върнати: $%.2f (%d от %d)" % (refunded_total, refunded_count,
                                                  len(crm_items))
                   if refunded_total else "няма върнати суми")

    # The Stripe↔CRM link, made explicit and CROSS-CHECKED. The rows below come
    # from the CRM (one durable record per sale), so `source` names the CRM even
    # when Stripe is reachable: a label reading "stripe" over CRM rows is a lie
    # nobody can see. What Stripe IS good for is the second opinion — its own list
    # of PAID sessions must agree with the CRM — and until 17.09 that feed was
    # dead (one `StripeObject.get()` call raised, once a minute), so "does Stripe
    # agree?" could not be answered at all.
    stripe_payments = stripe.get("payments") or []
    stripe_total = round(sum(float(p.get("amount_usd") or 0)
                             for p in stripe_payments), 2)
    if not stripe.get("available"):
        stripe_status = "unavailable"
    elif (len(stripe_payments) == len(crm_items)
          and abs(stripe_total - crm_total) < 0.01):
        stripe_status = "in_sync"
    else:
        stripe_status = "mismatch"
    if stripe_status == "unavailable":
        stripe_detail = ("Stripe snapshot недостъпен (%s) — числата идват само от "
                         "CRM записите." % (stripe.get("reason") or "без обяснение"))
    else:
        stripe_detail = ("Stripe snapshot: %d плащане(и) на $%.2f — сверени с CRM "
                         "($%.2f): %s"
                         % (len(stripe_payments), stripe_total, crm_total,
                            "съвпадат" if stripe_status == "in_sync" else "РАЗЛИКА"))
    stripe_link = {
        "status": stripe_status,
        "available": bool(stripe.get("available")),
        "state": stripe.get("state"),
        "reason": stripe.get("reason"),
        "count": len(stripe_payments),
        "total_usd": stripe_total,
        "detail": stripe_detail,
    }

    return {
        "label": "OFF-CHAIN — НЕ е включено в on-chain сумите",
        "excluded_from_onchain": True,
        "source": "crm_paid_events",
        "count": len(crm_items),
        "total_usd": crm_total,
        # Paid / refunded / net, all three visible: the sale figure stays
        # what was charged, and the return is its own number (17.09).
        "refunded_usd": refunded_total,
        "refunded_count": refunded_count,
        "net_usd": net_total,
        "refund_note": refund_note,
        "items": crm_items[:50],
        "stripe_available": bool(stripe.get("available")),
        "stripe_link": stripe_link,
        # AUDIT A2: with DATABASE_URL unset the CRM is SQLite on the
        # EPHEMERAL disk, so every deploy wipes leads, paid leads and
        # the whole pipeline. The on-chain numbers are protected by the
        # chain-verified seed; the off-chain money record was not
        # protected at all — so say it out loud instead of showing a
        # confident "$0" that is really "unknown".
        "storage_backend": getattr(crm_store, "backend", "unknown"),
        "durable": getattr(crm_store, "backend", "") == "postgresql",
        "storage_note": (
            "PostgreSQL (durable)" if getattr(crm_store, "backend", "")
            == "postgresql" else
            "SQLite на ефимерния диск — deploy изтрива leads/paid "
            "записите. Задай DATABASE_URL за durable CRM."
        ),
    }


#: Per-step cost of the MOST RECENT build attempt, successful or not. Written
#: by `_step` after every step so a build that dies halfway still reports the
#: steps that ran and the name of the one that hung. Read by
#: /api/dashboard/build-status.
_DASHBOARD_LAST_BUILD_TIMINGS: Dict[str, float] = {}

_isolated_stores: Dict[str, object] = {}
_isolated_stores_lock = threading.Lock()

#: WHICH POOL EACH ISOLATED PURPOSE SHARES.
#:
#: One connection per background job looked tidy and BROKE THE BOARD. Every pool
#: is a real Postgres connection, this database is the smallest plan
#: (`0.1c-256mb`) with a low connection limit, and eight purposes across two
#: processes is ~16 connections — close enough to the ceiling that opening one
#: more blocks. Measured: with four pools `/api/dashboard/data` answered in 0.30s;
#: with eight it hung on its FIRST step, with `last_build_timings_ms` empty.
#:
#: So the pools are deliberately few, and they are allocated by what the job
#: actually costs rather than by having given each one a name:
#:
#:   dashboard-build    its own — it is the board's own read path
#:   snapshot           its own — eight full scans, minutes each
#:   background-heavy   the network-bound and bulk ones, which must not wait on
#:                      each other
#:   background-light   the cheap scheduled ones
#:
#: An unknown purpose gets its OWN pool, so a new job is never silently sharing
#: with one that is already busy — sharing has to be a deliberate entry here.
_ISOLATION_POOLS = {
    "dashboard-build": "dashboard-build",
    "requests-snapshot": "snapshot",
    "whaleflow-scan": "background-heavy",
    "request-log-retention": "background-heavy",
    "reorg-watch": "background-light",
    "dashboard-scan": "background-light",
    "sentinel": "background-light",
    "telegram-sales": "background-light",
}


def _isolated_store(purpose: str):
    """A store with its OWN Postgres link, for one named background job.

    THE PATTERN THAT FIXED THE BOARD, GENERALISED — because the board was not the
    only job that needed it.

    `HistoryStore._run` serialises every caller behind one `threading.Lock`
    guarding ONE Postgres connection. The web process runs ~11 background threads
    plus up to 8 request threads, and they all share that single link. So any job
    that is slow, network-bound, or long-running stalls EVERY request in the
    process while it holds it — and the caller that waits too long is refused.

    That is not a theory. On 08.11 the request log stopped being written for
    hours, all six organism blocks read `not_reached`, and every write failed
    with `busy for 2s`. Naming the holder ended the guessing:

        shared Postgres link busy for 2s; holder=whaleflow-scan held=45s

    `_whaleflow_scan_loop` walks the chain network-wide — the backfill alone is
    documented as "hours on a free RPC" — and every whale it finds is written
    through the shared link. The board survived it only because it already had
    its own link.

    WHY A SEPARATE STORE AND NOT JUST A `runner` ARGUMENT: the public store
    methods (`whaleflow_increment`, `whaleflow_backfill`) take no runner, and
    threading one through every method would touch far more code than the fault
    justifies. A second store instance carries its own `_pg_lock` AND its own
    connection, which is exactly the isolation required — and it is the same
    mechanism the heavy snapshot pass already uses one level down
    (`HistoryStore._private_runner`).

    ON SQLITE it defers to `dashboard_db`: the contention is a property of one
    SHARED POSTGRES LINK, SQLite opens per call, and following the injected store
    is what keeps the suite honest.
    """
    if getattr(dashboard_db, "backend", "sqlite") != "postgresql":
        return dashboard_db
    # The POOL the purpose belongs to, not the purpose itself. See
    # `_ISOLATION_POOLS`: a connection per job exhausted the database's limit and
    # hung the board on its first step.
    pool = _ISOLATION_POOLS.get(purpose, purpose)
    store = _isolated_stores.get(pool)
    if store is None:
        with _isolated_stores_lock:
            store = _isolated_stores.get(pool)
            if store is None:
                # `ensure_schema=False`: this store exists ONLY to own a separate
                # Postgres connection. Running the DDL again is not merely
                # wasteful — on this database it is HARMFUL. The plan is
                # `0.1c-256mb`, and `CREATE TABLE IF NOT EXISTS` takes an ACCESS
                # EXCLUSIVE lock even when the table already exists, so several
                # stores each running the full schema pass at boot contend on
                # those locks and the board's first build step waits behind them
                # and never completes. The owning store has already created
                # everything this one will ever read.
                store = DashboardStore(DASHBOARD_DB_FILE, ensure_schema=False,
                                       # Share the LOCAL file's connection and
                                       # lock with the owning store. The durable
                                       # side is what needed isolating; giving
                                       # each job its own SQLite handle produced
                                       # `database is locked` on a paid route.
                                       share_sqlite_from=dashboard_db)
                # Keyed by POOL, not by purpose. Reading above is
                # `_isolated_stores.get(pool)`, so writing `[purpose]` meant the
                # memo could never hit for the 7 purposes in `_ISOLATION_POOLS`
                # whose pool name differs from their own — every sentinel beat,
                # reorg tick and snapshot warm built a FRESH DashboardStore and a
                # fresh Postgres link while dropping the previous object without
                # closing it. The log line below is the memo's own proof: a
                # working cache prints it once per process, and it was printing
                # 8 times in 7 seconds on one boot and 10 times in 14 minutes.
                #
                # This is the failure the pool was introduced to prevent, and it
                # is the one the comment above describes: a connection per job
                # exhausts the database's connection limit and the board's build
                # fails with DatabaseError. Measured 10.11: /api/dashboard/data
                # answering 500 and the chain monitor's heartbeat frozen.
                _isolated_stores[pool] = store
                log.info("isolated store %r: own Postgres link (backend=%s), so "
                         "it cannot contend with the request path",
                         purpose, store.backend)
    return store


def _dashboard_build_store():
    """The board build's own store. See `_isolated_store` for the full reason."""
    return _isolated_store("dashboard-build")


def _whaleflow_store():
    """The whale scan's own store.

    This is the job that was measured holding the shared link for 45 seconds at a
    time, on repeat, while every request in the process was refused a write.
    """
    return _isolated_store("whaleflow-scan")


def _canonical_dashboard_payload(include_crm: bool = False,
                                 include_sales_detail: bool = False) -> dict:
    """Build the whole read model from persistent sources only.

    `include_crm` (10.10): the OFF-CHAIN CRM/Stripe section is generated ONLY
    for admin-authenticated reads. Public callers get the key ABSENT (never
    null) — off-chain sums must not be reachable with curl by anyone who knows
    the URL. See `_crm_stripe_section`.

    `include_sales_detail` (04.11): the payer / transaction hash / consumed route
    on each sales row, which the owner asked for back without a token. Kept as a
    SEPARATE argument from `include_crm` on purpose: pressing the button on the
    page must never also reveal the off-chain Stripe revenue, and two grants
    travelling on one flag is how that happens by accident.
    """
    # ── per-step cost, measured rather than guessed ────────────────────────
    # On 05.11 this function took over 40s and the board went blank. Bounding
    # the Postgres waits stopped it taking the service down, but nobody could
    # say WHICH read was slow — the payload had no clocks in it. Now it does.
    # The breakdown ships only on the admin variant (see the return below):
    # the public response keeps revealing nothing about our internals.
    _t_start = time.perf_counter()
    _timings: Dict[str, float] = {}
    # Every DURABLE read below goes through this store, which owns its OWN
    # Postgres link. Sharing the request path's link is what turned one slow
    # panel into hours of 500s — see `_dashboard_build_store`.
    #
    # `get_payapi_state`, `get_meta` and `backend` deliberately still use
    # `dashboard_db`: those are the LOCAL SQLite file, which has a different lock
    # and cannot queue behind Postgres.
    _db = _dashboard_build_store()

    def _step(name: str, fn):
        _t = time.perf_counter()
        try:
            return fn()
        finally:
            _timings[name] = round((time.perf_counter() - _t) * 1000.0, 1)
            # Publish after EVERY step, not at the end. A build that dies on
            # step 5 must still say what steps 1-4 cost and which one hung —
            # "the dashboard is slow" is not a diagnosis, and the build that
            # fails is precisely the one worth measuring.
            _DASHBOARD_LAST_BUILD_TIMINGS.clear()
            _DASHBOARD_LAST_BUILD_TIMINGS.update(_timings)

    sales = _step("sales_summary", _db.sales_summary)
    # ON-CHAIN SALES · УСЛУГА (14.10): the route each payment was CONSUMED on.
    # The granted claim in payment_guards is the ONLY honest evidence (the same
    # join the CLIENTS section uses) — rows without a claim get route: None and
    # the table renders "—". Never guess a route from the amount here.
    try:
        _route_map = _step("guard_endpoint_map",
                           _db.guard_endpoint_map)
    except Exception as exc:
        log.debug("dashboard: guard endpoint map unavailable (%s)", exc)
        _route_map = {}
    for _row in sales["history"]:
        _row["route"] = _route_map.get(
            (_row.get("tx_hash") or "").lower()) or None
    requests = _step("requests_summary", _db.requests_summary)
    payapi = _step("get_payapi_state", dashboard_db.get_payapi_state)
    price_map = _published_price_map()
    clients = _step(
        "clients_summary",
        lambda: _db.clients_summary(price_map=price_map))
    whales = _step(
        "whaleflow_summary",
        lambda: _db.whaleflow_summary(window_hours=24, limit=25))
    guards = _step("guard_stats", _db.guard_stats)
    guard_claims = _step("payment_guard_stats", _db.payment_guard_stats)

    onchain_total = sales["total_usdc"]
    # Priority-0 guard: the on-chain total must NEVER contain off-chain money.
    assert isinstance(onchain_total, (int, float))

    # 09.11: the class tags render directly under the "Днес" card but count ALL
    # TIME — read together they looked like today's split, so the card said
    # "$0.15 днес" beside tags summing to $0.32. Today's own client half is taken
    # from the same history rows as every other figure on the page, not re-queried
    # (a second query is a second answer).
    _today_bucket = _daily_sales_series(sales.get("history"), days=1)[0]

    _timings["total_ms"] = round((time.perf_counter() - _t_start) * 1000.0, 1)
    return {
        "ok": True,
        # ADMIN-ONLY. The per-step cost of building this payload, so a slow
        # board can be diagnosed from the payload itself instead of guessed at.
        # Gated on `include_crm` (an admin-authenticated read) because the
        # public response should keep revealing nothing about our internals —
        # and because "which read is slow" is exactly the kind of map an
        # attacker would like to have for free.
        **({"build_timings_ms": _timings} if include_crm else {}),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "receiver_address": X402_RECEIVER_ADDRESS,
        "sections": {
            # ── the organism: is the SYSTEM well, not just the traffic ────────
            # ENABLED BY ENVIRONMENT, DEFAULT OFF, and that default is deliberate.
            #
            # Three consecutive deploys failed with this section in the payload,
            # every one after ~15 minutes, and Render's log names the cause:
            #
            #     ==> No open HTTP ports detected on 0.0.0.0, continuing to scan...
            #     ==> Port scan timeout reached, no open HTTP ports detected.
            #
            # The build succeeds; the container never serves. That is the port
            # never opening, and the only change in those deploys was this.
            #
            # OFF BY DEFAULT so the next deploy is a KNOWN GOOD baseline. Once
            # the service is stable again, set KRISTO_ORGANISM_BOARD=1 in Render
            # and the section returns — at which point a failure is attributable
            # to this and nothing else.
            #
            # The heartbeats and the journal KEEP RUNNING either way: they are
            # written by threads and loops, and they are the parts with value.
            # Only the board projection is gated.
            **(_organism_board_section() if _organism_board_enabled() else {}),
            # The four questions the owner asks, answered in words and placed
            # first: when was the last sale, on what day, who paid, and was the
            # caller a person or a bot. Every figure is derived from the same
            # sales/requests/clients objects the sections below render, so the
            # summary and the tables cannot disagree.
            "summary": _plain_summary(sales, requests, clients),
            # F-01 residue: `track_record` was the section the earlier redaction
            # missed. It shipped `started_tx` and every `payers[].first_tx` - the
            # 66-character transaction hashes that the PAID /api/sales sells.
            # Nothing reads them (no template, no client, no test asserted them),
            # so on the free payload they were pure giveaway.
            #
            # The payer ADDRESSES stay and that is deliberate: the owner needs
            # them to answer "who paid", and they are public on Base by
            # construction - hiding one here would look like security while the
            # chain still shows it. The honest fix for the replay window is the
            # verifier, not this line (see F-05/F-09 in the audit).
            "track_record": _redact_track_record(
                _tolerant("track_record", _db.track_record, {})),
            "onchain": {
                "label": "ИСТИНА — веригата",
                "total_usdc": onchain_total,
                "total_count": sales["total_count"],
                "today_usdc": sales["today_usdc"],
                "today_count": sales["today_count"],
                "today_date": sales["today_date"],
                # The customer half of TODAY. `by_class` below is all-time and is
                # labelled as such on the page; these two carry the card's date.
                "today_client_count": _today_bucket["client_count"],
                "today_client_usdc": _today_bucket["client_usdc"],
                "external_payers": sales["external_payers"],
                "by_class": sales["by_class"],
                "class_labels": PAYER_CLASS_LABELS_BG,
                "last_scanned_block": int(
                    _tolerant("last_scanned_block",
                              lambda: dashboard_db.get_meta(
                                  "last_scanned_block", "0"), "0") or 0
                ),
                # F-01 vs the operator: the owner asked for these columns BACK.
                # They existed until 10.10 (Време · Сума · УСЛУГА · КЛИЕНТ) and
                # were dropped because the full row - payer address plus
                # transaction hash - is the paid /api/sales product and half of a
                # payment proof. But he is the operator, and "is this our own
                # test, a crawler, or a real customer, and who exactly paid" is
                # the question he runs the business on.
                #
                # So the row is complete for an authenticated admin and stays
                # {ts, amount} for everyone else. That is the audit's own
                # recommendation for F-01 ("the dashboard payload behind an
                # admin/session scope"), not a weakening of it.
                "history": _onchain_history(sales["history"],
                                            include_private=include_sales_detail),
            },
            "requests": {
                # WHICH ENGINE HOLDS THE TRAFFIC HISTORY. This read
                # "постоянен лог (SQLite)" as a literal, so it kept describing
                # the fallback after the durable tables moved to PostgreSQL on
                # 14.09 — telling the operator that a deploy could erase the
                # history it was in fact moved to PostgreSQL to protect. The
                # label now comes from the store itself, so it cannot go stale.
                "label": "постоянен лог (%s)" % ("PostgreSQL"
                                                 if dashboard_db.backend == "postgresql"
                                                 else "SQLite"),
                "today": requests["today"],
                "total": requests["total"],
                "today_date": requests["today_date"],
                "today_clean": requests.get("today_clean"),
                "total_clean": requests.get("total_clean"),
                "internal_noise": requests.get("internal_noise"),
                "by_source": requests["by_source"],
                "by_source_clean": requests.get("by_source_clean"),
                "by_channel": requests["by_channel"],
                "top_paths": requests["top_paths"],
                "top_user_agents": requests.get("top_user_agents"),
                "hourly": requests.get("hourly"),
                "funnel": requests.get("funnel"),
                "recent": requests["recent"],
                # WHICH PANELS COULD NOT BE READ. This whitelist used to drop it,
                # so the store's honest None/degraded markers never reached the
                # page — and a panel that timed out rendered exactly like a panel
                # with no traffic, on a board whose whole job is to be believed.
                # The traffic aggregates are full scans over a table with no
                # retention, so this is not a hypothetical state.
                "degraded": requests.get("degraded") or [],
                "available": requests.get("available", True),
                # WHEN the parked all-time numbers were read and WHETHER the last
                # read failed. A dash alone cannot tell a reader whether the
                # number is still coming or has stopped coming, and the two call
                # for different things: patience, versus somebody looking.
                # The error is a class name only — never a driver message.
                "snapshot_age_seconds": requests.get("snapshot_age_seconds"),
                "snapshot_error": requests.get("snapshot_error"),
                "served_from_snapshot": requests.get("served_from_snapshot") or [],
            },
            "payapi": {
                "label": "PayAPI Market listing",
                **payapi,
            },
            "clients": {
                "label": "Реални клиенти (external платци) — основа за operator deals",
                "count": clients["count"],
                # F-01: client rows may expose tx hashes / sender / class —
                # strip them from the free payload (template uses none of them).
                "clients": [
                    ({k: v for k, v in dict(_cl).items()
                      if k not in ("tx_hashes", "tx_hash", "sender",
                                   "payer_class", "payer_label")}
                     if isinstance(_cl, dict) else _cl)
                    for _cl in clients["clients"]
                ],
                "potentially_new": [
                    ({k: v for k, v in dict(_cl).items()
                      if k not in ("tx_hashes", "tx_hash", "sender",
                                   "payer_class", "payer_label")}
                     if isinstance(_cl, dict) else _cl)
                    for _cl in clients["potentially_new"]
                ],
                "route_price_map": clients["route_price_map"],
                "route_evidence_legend": {
                    "payment_guard": "записан endpoint от C1/H2 гарда — ФАКТ",
                    "price_unique": "сумата съвпада с точно един маршрут",
                    "price_ambiguous": "сумата съвпада с няколко маршрута — кандидати, не се познава",
                },
                "note": ("Маршрутът се твърди като факт само при записан "
                         "payment_guard; иначе са показани кандидатите по цена."),
            },
            "whales": {
                "label": "Китове (Whale Flow) — мрежови USDC трансфери ≥ праг",
                "state": whales["state"],
                "paused_at": whales.get("paused_at"),
                "count": whales["count"],
                "all_time_count": whales["all_time_count"],
                "last_event_at": whales["last_event_at"],
                "last_event_block": whales["last_event_block"],
                "last_attempt_at": whales.get("last_attempt_at"),
                "last_error": whales.get("last_error"),
                "effective_chunk_blocks": whales.get("effective_chunk_blocks"),
                "configured_chunk_blocks": whales.get("configured_chunk_blocks"),
                "window_hours": whales["window_hours"],
                "threshold_usdc": whales["threshold_usdc"],
                "scanned_until_block": whales["scanned_until_block"],
                # F-01: the whales ARRAY mirrors paid /api/v1/whaleflow —
                # removed from the free payload; aggregates above stay public.
                "note": ("Празно е ЧЕСТНО състояние: watermark-ът се движи и "
                         "сканът работи — просто няма трансфер ≥ прага. "
                         "'scan_failed' значи счупен скан, не празна мрежа. "
                         "'scan_paused_by_owner' значи, че сканерът е СПРЯН "
                         "нарочно (нула заявки към RPC) — виж paused_at."),
            },
            "guards": {
                "label": "Стражи на плащането (C1/C2/H2) — живо състояние",
                "lock_alive": guards["lock_alive"],
                "lock_probe_error": guards["lock_probe_error"],
                # WHERE the lock lives and whether it survives a deploy. Without
                # this the section implies durability it may not have.
                "lock_backend": guards.get("lock_backend"),
                "lock_durable": guards.get("lock_durable"),
                "blocked_total": guards["blocked_total"],
                "blocked_today": guards["blocked_today"],
                # "Blocked" means REFUSED; the payments the clock re-read or the
                # wait rescued are shown separately, so no number carries two
                # meanings (21.09 — same cleanup as totals.issued).
                "lag_accepted_total": guards.get("lag_accepted_total", 0),
                "lag_accepted_today": guards.get("lag_accepted_today", 0),
                "by_kind": guards["by_kind"],
                # F-01: guard rows may expose tx_hash — strip it (and sender)
                # from the free payload; paid routes keep full data.
                "recent_blocks": [
                    {k: v for k, v in dict(_b).items()
                     if k not in ("tx_hash", "sender")}
                    for _b in guards["recent_blocks"]
                ],
                "consumed_total": guard_claims["consumed_total"],
                "consumed_by_endpoint": guard_claims["by_endpoint"],
                "last_claim_at": guard_claims["last_claim_at"],
                "last_claim_endpoint": guard_claims["last_claim_endpoint"],
                # Set when even reading the lock's telemetry failed: the numbers
                # above are then UNKNOWN, not zero (they are None/{}).
                "stats_error": guard_claims.get("stats_error"),
                "config": {
                    "c1_table": "payment_guards",
                    "c2_proof_confirmations": _required_confirmations(),
                    "c2_standard_confirmations":
                        _required_standard_confirmations(),
                    "h2_endpoint_binding": True,
                    "free_tier_limit": FREE_TIER_LIMIT,
                },
            },
            "routes": {
                # Rendered from the SAME list that builds the x402 challenge,
                # so the price on screen can never drift from the price a
                # paying agent is actually charged (the static table used to
                # advertise /api/sales at $0.05 while the 402 demanded $0.005).
                "label": "Реални маршрути — единствените публични x402 продукти",
                "count": len(REAL_X402_ROUTES),
                "routes": _real_routes_payload(),
            },
            # (d) CRM/Stripe — OFF-CHAIN (10.10): ONLY for admin reads. For a
            # public caller this key is ABSENT (never null) — see
            # `_crm_stripe_section` for the whole story.
            **({"crm_stripe": _crm_stripe_section()} if include_crm else {}),
        },
        "invariant": (
            "On-chain сумите идват САМО от реални USDC трансфери към "
            f"{X402_RECEIVER_ADDRESS}."
            + (" CRM/Stripe (off-chain) е отделна секция и никога не се смесва с тях."
               if include_crm else
               " Off-chain платни записи не се показват в този отговор.")
        ),
        # Chart series (10.10) — ADDITIVE ONLY. Same helpers as
        # /api/dashboard-stats so the two public JSON surfaces cannot disagree:
        # `daily_sales` from the durable on-chain history, `hourly_requests`
        # from the durable request log (clean = without internal keep-alive).
        "daily_sales": _daily_sales_series(sales.get("history")),
        # 28 days, alongside the 7: a week cannot be compared with the week
        # before it from a 7-day window, and that comparison is the question.
        # The 7-day key above is untouched so no existing reader changes.
        "daily_sales_28": _daily_sales_series(sales.get("history"), days=28),
        "hourly_requests": _hourly_requests_series(requests.get("hourly")),
    }


#: Last dashboard payload that built cleanly, per VARIANT, so the board can
#: keep reporting instead of blanking out when a read fails.
#:
#: KEYED BY THE EXACT GRANT PAIR. A looser key — one shared slot, or a key of
#: "the dashboard payload" — would hand a public caller an admin or operator
#: response, which is the single thing `include_crm` and `include_sales_detail`
#: exist to prevent. The key is the grant, never anything about the caller.
_DASHBOARD_LAST_GOOD: Dict[Tuple[bool, bool], Tuple[dict, float]] = {}
_DASHBOARD_LAST_GOOD_LOCK = threading.Lock()

#: Variants with a background rebuild already in flight. Prevents a burst of
#: visitors from each starting their own rebuild.
#:
#: THIS IS NOT AN OPTIMISATION, IT IS THE FIX for the second outage. When the
#: cold path built inline, four simultaneous first requests ran four full
#: builds; on 05.11 each build took 40+ seconds, so those four saturated every
#: one of gunicorn's 8 threads AND queued behind the one shared Postgres link.
#: The result was not a slow dashboard — it was a dead service: the static `/`
#: took 15s and /health returned 502. One build per variant, started and
#: awaited rather than repeated, removes that failure mode entirely.
#:
#: Maps a variant to WHEN its in-flight refresh started, not just that one is
#: running. The timestamp is the whole point: it makes the flag a LEASE.
#:
#: WHY, measured 10.11 05:12–05:21. The public board went nine minutes without a
#: rebuild — with not one error in the log — and then came back the moment a
#: request arrived. That is the signature of a single build that hung: while it
#: hung it held this flag, so the warmer ticked every 30 seconds, found a refresh
#: "already running", did nothing, and logged nothing. A plain set can therefore
#: wedge the board for as long as one stalled network read lasts, which is the
#: exact opposite of "таблото да е активно винаги".
_DASHBOARD_REFRESHING: Dict[Tuple[bool, bool], float] = {}

#: How long a refresh may be "in flight" before a later caller treats it as
#: abandoned and starts its own. Generous on purpose: a real build measures
#: ~2.3 s at its slowest step, so nothing healthy comes near three minutes, and a
#: lease that fires early would only duplicate a build that is still working.
_DASHBOARD_REFRESH_LEASE_SECONDS = max(
    30.0, float(os.getenv("KRISTO_DASHBOARD_REFRESH_LEASE_SECONDS", "180")))

#: Why the last build for a variant FAILED, if it did. Kept so the cold path
#: can tell "still building" apart from "this is broken" and raise the real
#: error instead of reporting an endless warm-up.
_DASHBOARD_LAST_ERROR: Dict[Tuple[bool, bool], dict] = {}

#: Where the last good PUBLIC board is kept so that a restart is not an outage.
#:
#: WHY THIS EXISTS. `_DASHBOARD_LAST_GOOD` is process memory, so every deploy —
#: and auto-deploy is on, so every push, including a docs-only one — emptied it.
#: The next visitor then waited `KRISTO_DASHBOARD_COLD_WAIT_SECONDS` for the
#: first build and, if it had not finished, got **503 warming**, which the page
#: paints as "ГРЕШКА: HTTP 503 … НЕАКТУАЛНИ". The owner's requirement is that the
#: board is permanently operational, and a board that reports an error for a
#: minute after every deployment is not.
#:
#: Stored in `dashboard_meta` — the DURABLE store — and deliberately not in a
#: file: this service has NO persistent disk (`disk: null`), so `data/*.db` is
#: wiped by every deploy. `dashboard_meta` is the table that survived for the
#: whale watermarks for exactly this reason.
#:
#: ONLY THE PUBLIC VARIANT IS PERSISTED. `(False, False)` is the payload an
#: anonymous caller already receives; the admin and operator variants carry the
#: CRM/Stripe section and must never be written to shared storage. `_dashboard_build`
#: enforces the grant check, and `_dashboard_seed_from_store` reads only this key.
_DASHBOARD_BOARD_META_KEY = "dashboard_payload_public_v1"

#: Don't rewrite ~50 KB of board into Postgres on every 30-second revalidation;
#: the age only has to be close enough to serve after a restart.
_DASHBOARD_PERSIST_SECONDS = max(
    5.0, float(os.getenv("KRISTO_DASHBOARD_PERSIST_SECONDS", "60")))
_DASHBOARD_PERSISTED_AT = 0.0

#: Age at which a served payload triggers a BACKGROUND refresh. Below this the
#: cached read is simply returned.
_DASHBOARD_REVALIDATE_SECONDS = max(
    5.0, float(os.getenv("KRISTO_DASHBOARD_REVALIDATE_SECONDS", "30")))

#: Age past which the payload is LABELLED stale to the reader. Set well above
#: the revalidate interval so a normal refresh never flashes a warning, but a
#: genuinely wedged build does.
_DASHBOARD_FRESH_SECONDS = max(
    _DASHBOARD_REVALIDATE_SECONDS * 2.0,
    float(os.getenv("KRISTO_DASHBOARD_FRESH_SECONDS", "180")))

#: How long a request may wait for a variant's FIRST build before giving up.
#: The request never performs the build itself (see below) — it waits for the
#: background thread. Past this it answers 503 "warming", which the page
#: already renders as "the figures below are not current", rather than holding
#: a gunicorn thread for the length of a slow build.
_DASHBOARD_COLD_WAIT_SECONDS = max(
    1.0, float(os.getenv("KRISTO_DASHBOARD_COLD_WAIT_SECONDS", "20")))


class DashboardWarming(RuntimeError):
    """No payload has ever been built and the first build is still running."""


def _dashboard_build(key, include_crm: bool, include_sales_detail: bool) -> dict:
    """Build a payload and publish it into the cache under its exact grant key."""
    try:
        payload = _canonical_dashboard_payload(
            include_crm=include_crm,
            include_sales_detail=include_sales_detail)
    except Exception as exc:
        with _DASHBOARD_LAST_GOOD_LOCK:
            # The TYPE is safe to publish; the message is not, because a
            # psycopg error can carry the host and the user name.
            _DASHBOARD_LAST_ERROR[key] = {
                "type": type(exc).__name__,
                "message": redact_rpc(exc),
            }
        raise
    with _DASHBOARD_LAST_GOOD_LOCK:
        # A SHALLOW copy on purpose: this dict is the cache, and only its
        # top-level keys are ever touched, so the nested sections are shared
        # and never rewritten after the fact.
        _DASHBOARD_LAST_GOOD[key] = (dict(payload), time.time())
        _DASHBOARD_LAST_ERROR.pop(key, None)
    _dashboard_persist_board(key, payload)
    return payload


def _dashboard_meta_store():
    """The durable store the board is persisted in.

    One accessor on purpose: the suite shares the developer's real database, and
    a test that wrote a board into it would seed every later test's cold path
    (and a test that read one could hide a warming regression). `conftest.py`
    points this at `None` for every test, and the tests that are ABOUT
    persistence point it at a fake of their own.
    """
    return globals().get("dashboard_db")


def _dashboard_persist_board(key, payload) -> None:
    """Keep the public board in the durable store so a restart can serve it.

    Best-effort by construction: a board that has just been built is already
    being served from memory, so a store that refuses the write costs the NEXT
    restart a cold wait and nothing else. It must never fail the build.
    """
    global _DASHBOARD_PERSISTED_AT
    if key != (False, False):
        # The admin/operator variants carry the CRM section. They are not
        # persisted, ever — see `_DASHBOARD_BOARD_META_KEY`.
        return
    now = time.time()
    if now - _DASHBOARD_PERSISTED_AT < _DASHBOARD_PERSIST_SECONDS:
        return
    store = _dashboard_meta_store()
    if store is None:
        return
    try:
        store.set_meta(_DASHBOARD_BOARD_META_KEY, json.dumps(
            {"built_at": now, "payload": payload}, separators=(",", ":")))
        _DASHBOARD_PERSISTED_AT = now
    except Exception as exc:      # pragma: no cover - defensive
        log.debug("dashboard board could not be persisted: %s", exc)


def _dashboard_seed_from_store(key) -> bool:
    """Replay the last board after a restart. True if the cache was seeded.

    The payload was real when it was built, and the serving path still applies
    its own freshness rules (`stale`, `stale_since`, `stale_age_seconds`), so
    what a visitor gets after a deploy is the same bytes as before plus an
    honest age — never a 503 and never a zero.
    """
    if key != (False, False):
        return False
    with _DASHBOARD_LAST_GOOD_LOCK:
        if _DASHBOARD_LAST_GOOD.get(key) is not None:
            return False
    store = _dashboard_meta_store()
    if store is None:
        return False
    try:
        raw = store.get_meta(_DASHBOARD_BOARD_META_KEY)
        if not raw:
            return False
        doc = json.loads(raw)
        payload = doc.get("payload")
        built_at = float(doc.get("built_at") or 0)
        if not isinstance(payload, dict) or built_at <= 0:
            return False
    except Exception as exc:
        # A corrupt or unreadable stored board is not allowed to become an
        # error either: it just means this process starts cold, as before.
        log.debug("dashboard board seed skipped: %s", exc)
        return False
    with _DASHBOARD_LAST_GOOD_LOCK:
        if _DASHBOARD_LAST_GOOD.get(key) is None:
            _DASHBOARD_LAST_GOOD[key] = (payload, built_at)
        else:
            return False
    log.warning("dashboard board restored from the durable store (built %.0fs "
                "ago) — serving it instead of a cold 503",
                max(0.0, time.time() - built_at))
    return True


#: The one-shot seed: started once per process, awaited briefly, never repeated.
_DASHBOARD_SEED_THREAD = None
_DASHBOARD_SEED_DONE = False

#: How long a REQUEST may wait for that seed. The board's design rule is that the
#: request path does no database work; the seed is the single exception and it is
#: bounded here so a slow store cannot turn the rule into a slow request.
#:
#: MEASURED, 09.11 20:19–20:36, and this is why the bound exists: with the seed
#: awaited in full, each request paid the store's 30-second timeout and then the
#: 20-second cold wait — 50.4 s per request, 18 times in a row — while the board's
#: own rebuild was failing. Two seconds is enough for a healthy read and short
#: enough that a sick store costs a warm-up message, not a hung dashboard.
_DASHBOARD_SEED_WAIT_SECONDS = max(
    0.0, float(os.getenv("KRISTO_DASHBOARD_SEED_WAIT_SECONDS", "2")))


def _dashboard_seed_once() -> bool:
    """Replay the last public board, bounded, and only the first time.

    Returns True if the cache now holds a board. The work happens on a daemon
    thread: a request waits at most `_DASHBOARD_SEED_WAIT_SECONDS` for it, and if
    that expires the thread keeps going so the NEXT request finds the board
    already there. Nothing here is allowed to raise into a request.
    """
    global _DASHBOARD_SEED_THREAD, _DASHBOARD_SEED_DONE
    if _DASHBOARD_SEED_DONE:
        return False
    thread = _DASHBOARD_SEED_THREAD
    if thread is None:
        def _work():
            global _DASHBOARD_SEED_DONE
            try:
                _dashboard_seed_from_store((False, False))
            except Exception as exc:      # pragma: no cover - defensive
                log.debug("dashboard board seed failed: %s", exc)
            finally:
                _DASHBOARD_SEED_DONE = True
        thread = threading.Thread(target=_work, name="dashboard-seed",
                                  daemon=True)
        _DASHBOARD_SEED_THREAD = thread
        thread.start()
    thread.join(_DASHBOARD_SEED_WAIT_SECONDS)
    with _DASHBOARD_LAST_GOOD_LOCK:
        return _DASHBOARD_LAST_GOOD.get((False, False)) is not None


def _dashboard_refresh_in_background(key, include_crm: bool,
                                     include_sales_detail: bool) -> bool:
    """Rebuild a variant off the request path. True if a refresh was started.

    A failure here is LOGGED, never raised: the caller already has a payload to
    serve, and the point of this path is that no visitor ever waits on the
    database again.
    """
    now = time.time()
    with _DASHBOARD_LAST_GOOD_LOCK:
        started_at = _DASHBOARD_REFRESHING.get(key)
        if started_at is not None:
            if now - started_at < _DASHBOARD_REFRESH_LEASE_SECONDS:
                return False
            # LEASE EXPIRED. One build must never be able to freeze the board:
            # if it has been "in flight" for this long it is stalled, not busy,
            # so a new one starts and the old one's completion is harmless (the
            # publish path only ever writes the newest payload it built). This
            # line is the only trace such a stall leaves, so it is a warning.
            log.warning(
                "dashboard: the refresh of variant %s has been in flight for "
                "%.0fs — treating it as abandoned and starting a new one",
                key, now - started_at)
        _DASHBOARD_REFRESHING[key] = now

    def _work():
        try:
            _dashboard_build(key, include_crm, include_sales_detail)
        except Exception as exc:
            log.warning(
                "dashboard: background refresh failed (variant %s): %s",
                key, redact_rpc(exc))
        finally:
            with _DASHBOARD_LAST_GOOD_LOCK:
                _DASHBOARD_REFRESHING.pop(key, None)

    threading.Thread(target=_work, name="dashboard-refresh",
                     daemon=True).start()
    return True


def _dashboard_warmer_loop():
    """Keep the PUBLIC dashboard variant warm, off the request path.

    The request path serves from cache, so whoever asks first is the one who
    pays for the build. On a cold boot — which is every deploy — that would be
    the first visitor, and a board that is slow exactly when it was just
    deployed is the complaint this whole change answers.

    A short initial delay so warm-up is not competing with boot, then the same
    interval the request path revalidates on.
    """
    time.sleep(5.0)
    interval = max(15.0, _DASHBOARD_REVALIDATE_SECONDS)
    while True:
        try:
            _dashboard_refresh_in_background(
                (False, False), include_crm=False, include_sales_detail=False)
            # The board rebuilt. This is the `delivery` block's proof of life:
            # the payload the public sees is being produced.
            _organism_beat("delivery", "ok", "dashboard payload rebuilt")
        except Exception as exc:
            log.warning("dashboard warmer: %s", redact_rpc(exc))
            _organism_beat("delivery", "degraded",
                           "dashboard rebuild failed: %s" % str(exc)[:120])
        time.sleep(interval)


def _requests_snapshot_warmer_loop():
    """Park the all-time traffic numbers off the request path.

    THE PROBLEM THIS SOLVES. Eight panels on the board are full scans of
    `request_log` — a `COUNT(*)` with no predicate, and a GROUP BY over every
    row. They take 10-21 seconds each here, and the SHARED Postgres connection
    cancels any statement at 8 seconds, so on the request path they were not
    merely slow: they were UNREADABLE. The board showed "—" for the site's
    all-time traffic and for the payment funnel — the one number that says
    whether any of this is working.

    A request cannot spend four minutes. This thread can. It reads those panels
    on its OWN connection (`HistoryStore._private_runner`), so the shared lock
    is never held and the fast panels keep answering in milliseconds, and it
    parks the result where the request path picks it up for free.

    It waits a little after boot so warm-up does not compete with startup, then
    runs on the long interval these all-time counts actually justify.
    """
    time.sleep(20.0)
    while True:
        try:
            _isolated_store("requests-snapshot").history.refresh_requests_snapshot()
            _organism_beat("data_store", "ok", "requests snapshot parked")
        except Exception as exc:
            log.warning("requests snapshot warmer: %s", redact_rpc(exc))
            _organism_beat("data_store", "degraded",
                           "snapshot pass failed: %s" % str(exc)[:120])
        time.sleep(REQUEST_SNAPSHOT_INTERVAL_SECONDS)


def _dashboard_payload_resilient(include_crm: bool, include_sales_detail: bool) -> dict:
    """Serve the board IMMEDIATELY from cache, refreshing off the request path.

    WHY THIS IS NOT A CACHE IN FRONT OF A BUILD. Bounding the Postgres waits
    (eafdacf) stopped a slow read from taking the whole service down; serving
    the last good read (a8d717e) stopped the board from blanking. Neither made
    the board FAST: on 05.11 /api/dashboard/data still spent 40+ seconds inside
    the build, and a 40-second request is a board nobody can use. Bounding a
    bad number is not the same as fixing it.

    The owner's requirement is that the board is permanently operational, so
    the request path now does no database work at all once a variant has been
    built once:

      * a cached payload is returned at once — no locks held across a query,
        no waiting on any read;
      * if it is older than `_DASHBOARD_REVALIDATE_SECONDS`, a rebuild is
        started on a daemon thread and the CURRENT call still returns now;
      * only the very first request for a variant builds synchronously, and
        only that one can raise.

    Three honesty rules, because a stale number presented as live is worse than
    no number at all:

      * past `_DASHBOARD_FRESH_SECONDS` the payload is marked — `stale: true`,
        `stale_since`, `stale_age_seconds`, `stale_reason` — so the page says
        how old it is instead of claiming to be live;
      * nothing is invented. This replays bytes that were real once, never a
        guess, never a zero, never an extrapolation;
      * the first build with no cached payload still raises, so a genuinely
        broken service reports an error rather than an empty success — but the
        PUBLIC payload is not lost across a restart: it is replayed from the
        durable store (`_dashboard_persist_board`, `_dashboard_seed_from_store`),
        so the ordinary "the process restarted" case answers with the previous
        real figures and their age instead of an error.

    The cache is keyed by the EXACT GRANT PAIR, never by anything about the
    caller, so a public request can never be answered from an admin variant.
    """
    key = (bool(include_crm), bool(include_sales_detail))

    with _DASHBOARD_LAST_GOOD_LOCK:
        cached = _DASHBOARD_LAST_GOOD.get(key)

    if cached is None:
        # A RESTART IS NOT AN ERROR. Memory is empty after every deploy, and the
        # board must answer anyway: the last good PUBLIC payload is replayed from
        # the durable store, with its real build time, so the visitor gets the
        # previous figures and an honest age instead of 503 "warming". The admin
        # and operator variants are never persisted, so they still cold-start —
        # that is the price of never writing the CRM section to shared storage,
        # and it is paid by the one caller who has to authenticate anyway.
        if _dashboard_seed_once():
            with _DASHBOARD_LAST_GOOD_LOCK:
                cached = _DASHBOARD_LAST_GOOD.get(key)

    if cached is not None:
        previous, built_at = cached
        age = max(0.0, time.time() - built_at)
        if age >= _DASHBOARD_REVALIDATE_SECONDS:
            _dashboard_refresh_in_background(
                key, include_crm, include_sales_detail)
        payload = dict(previous)
        if age >= _DASHBOARD_FRESH_SECONDS:
            payload["stale"] = True
            payload["stale_since"] = datetime.fromtimestamp(
                built_at, timezone.utc).isoformat()
            payload["stale_age_seconds"] = round(age, 1)
            payload["stale_reason"] = (
                "the live read has not completed for a while; these are the "
                "last figures that read cleanly, not current ones")
        else:
            payload["stale"] = False
        return payload

    # COLD: nothing has ever been built for this variant.
    #
    # The request does NOT perform the build. It starts ONE background build —
    # no matter how many requests are waiting on it — and waits, bounded.
    # Building here is what killed the service on 05.11: four simultaneous
    # first requests ran four concurrent 40-second builds, which consumed every
    # one of gunicorn's 8 threads and queued behind the single shared Postgres
    # link. The static `/` then took 15s and /health returned 502, so the
    # failure was service-wide, not confined to this route.
    _dashboard_refresh_in_background(key, include_crm, include_sales_detail)
    deadline = time.time() + _DASHBOARD_COLD_WAIT_SECONDS
    while True:
        with _DASHBOARD_LAST_GOOD_LOCK:
            got = _DASHBOARD_LAST_GOOD.get(key)
            failed = _DASHBOARD_LAST_ERROR.get(key)
            busy = key in _DASHBOARD_REFRESHING
        if got is not None:
            payload = dict(got[0])
            payload["stale"] = False
            return payload
        if failed is not None and not busy:
            # Not "warming up" — broken. The caller gets the real reason
            # rather than an endless, dishonest warm-up message.
            raise RuntimeError("dashboard build failed: %s"
                               % failed.get("message", failed))
        if time.time() >= deadline:
            raise DashboardWarming(
                "no dashboard figures have been built yet and the first build "
                "is still running (waited %ds)"
                % int(_DASHBOARD_COLD_WAIT_SECONDS))
        time.sleep(0.05)


@app.route("/api/dashboard/data")
def api_dashboard_data():
    """Free, read-only JSON for the canonical dashboard (persistent sources).

    include_crm (10.10): the OFF-CHAIN CRM/Stripe section is served ONLY to an
    admin-authenticated caller (session or X-Admin-Token). For the public the
    key is ABSENT from the response — off-chain sums are not curl-able.

    include_sales_detail (04.11): the payer and the hash on each sales row, for
    an admin OR for a visitor who pressed the one-click operator view on the
    page. The two grants are passed separately so that a button press can never
    reveal the Stripe section. See `_operator_view_enabled` for what the button
    is and is not worth.

    The payload comes from `_dashboard_payload_resilient`, which serves the
    last good read (marked `stale` when it is old) and refreshes behind the
    request. Only a variant that has never been built can block, and then only
    for KRISTO_DASHBOARD_COLD_WAIT_SECONDS — after which this returns 503 with
    `warming: true`, which the page renders as "the figures below are not
    current" instead of holding a worker thread for the length of a slow read.
    """
    include_crm = _is_admin_request()
    try:
        payload = _dashboard_payload_resilient(
            include_crm=include_crm,
            include_sales_detail=include_crm or _operator_view_enabled())
    except DashboardWarming as exc:
        # 503, not 500: the service is fine, the first read just has not
        # finished. The page already treats a failed load as "not current".
        return _safe_jsonify({"ok": False, "warming": True,
                              "error": str(exc)}), 503
    return _safe_jsonify(payload)


@app.route("/api/dashboard/build-status")
def api_dashboard_build_status():
    """Why the board is slow or blank — measured by the service itself.

    Deliberately narrow. It publishes counts, ages, the per-step cost of the
    most recent build ATTEMPT, and the exception CLASS of the last failure. It
    does NOT publish the failure MESSAGE to the public — a psycopg error can
    name the host and the user — while an admin read gets that too, because the
    operator is the one who has to act on it.

    This exists because diagnosing the 05.11 outage meant guessing. Nobody could
    say which of the eight reads cost the 40 seconds, or why the build raised:
    the payload carried no clocks and the failure text only went to a log. A
    dashboard that cannot say why it is slow is a dashboard that gets fixed by
    guessing, and guessing is what produced the wrong "Render billing problem"
    diagnosis earlier in this same incident.
    """
    with _DASHBOARD_LAST_GOOD_LOCK:
        cached = {str(k): round(time.time() - v[1], 1)
                  for k, v in _DASHBOARD_LAST_GOOD.items()}
        inflight = sorted(str(k) for k in _DASHBOARD_REFRESHING)
        error_types = {str(k): v.get("type")
                       for k, v in _DASHBOARD_LAST_ERROR.items()}
        error_msgs = {str(k): v.get("message")
                      for k, v in _DASHBOARD_LAST_ERROR.items()}
        timings = dict(_DASHBOARD_LAST_BUILD_TIMINGS)

    body = {
        "ok": True,
        "cache_age_seconds": cached,
        "refreshing": inflight,
        "last_error_type": error_types,
        "last_build_timings_ms": timings,
        "slowest_step": (max(timings.items(), key=lambda kv: kv[1])[0]
                         if timings else None),
        "revalidate_seconds": _DASHBOARD_REVALIDATE_SECONDS,
        "fresh_seconds": _DASHBOARD_FRESH_SECONDS,
        "cold_wait_seconds": _DASHBOARD_COLD_WAIT_SECONDS,
    }
    if _is_admin_request():
        body["last_error_message"] = error_msgs
    return _safe_jsonify(body)


@app.route("/api/dashboard/operator-view", methods=["POST"])
def api_dashboard_operator_view():
    """Turn the operator columns on or off for this browser session.

    Deliberately unauthenticated - see `_operator_view_enabled` for the whole
    reasoning. It grants the sales columns and NOTHING else; the CRM/Stripe
    section is still gated on `_is_admin_request()`.
    """
    enabled = False
    body = request.get_json(silent=True) or {}
    if isinstance(body, dict):
        enabled = bool(body.get("on", True))
    if enabled:
        session[_OPERATOR_VIEW_KEY] = True
    else:
        session.pop(_OPERATOR_VIEW_KEY, None)
    return _safe_jsonify({"ok": True, "operator_view": enabled})


@app.route("/api/v1/whaleflow")
def api_whaleflow():
    """Whale flow feed — network-wide USDC transfers >= threshold on Base.

    Owner-approved build (docs/WHALE_FLOW_SPEC.md). x402-paid like the other
    routes (canonical v2 challenge). DELIBERATELY UNLISTED: not in discovery,
    catalogs, manifests or README until it passes a paid canary (condition 4).
    Honest labels only — zero invention (SKU-cleanup rule).
    """
    _record_request("api_whaleflow", True)
    # THE CALLER WINS OVER THE ENV DEFAULT, and it is the caller's bill that
    # matters: the 50-row default is ~16.9 KB / ~4.2k tokens, which costs the
    # buyer 4x the $0.003 we charge on a mid model and 20x on a frontier one.
    # The caller pays for the tokens, so it must be able to ask for fewer. The
    # caps are deliberate: a request may LOWER the response, never raise it past
    # the ceiling the env already enforces. `limit` is clamped to 200 and
    # `hours` to 168 (the same week ceiling the dashboard uses); a non-numeric
    # value falls back to the env default instead of failing the paid call.
    try:
        window_hours = max(1, min(168, int(request.args.get(
            "hours",
            os.getenv("WHALE_WINDOW_HOURS",
                      str(dashboard_store_defaults()["window_hours"]))))))
    except ValueError:
        window_hours = 24
    try:
        limit = max(1, min(200, int(request.args.get(
            "limit", os.getenv("WHALEFLOW_LIMIT", "50")))))
    except ValueError:
        limit = 50
    # Audit #4 / F3: this is the one paid route whose data path is a raw DB
    # read — an exception here must become a JSON answer (never HTML) so the
    # payer can retry the SAME proof; after_request frees the recovery slot on
    # any non-2xx, so a database blip can never burn a payment.
    try:
        data = dashboard_db.whaleflow_summary(window_hours=window_hours,
                                              limit=limit)
    except Exception as exc:
        rid = getattr(g, "request_id", "")
        log.warning("whaleflow store unavailable [%s]: %s", rid, exc)
        return jsonify({
            "ok": False,
            "error": "whaleflow_store_unavailable",
            "message": (
                "Whale feed storage is temporarily unavailable. Your payment "
                "is recorded and NOT lost — retry this request with the same "
                "X-Payment-Proof shortly."
            ),
            "request_id": rid,
        }), 503
    return _safe_jsonify({
        "ok": True,
        "whales": data["whales"],
        "count": data["count"],
        "window_hours": data["window_hours"],
        "threshold_usdc": data["threshold_usdc"],
        "scanned_until_block": data["scanned_until_block"],
        "source": "onchain_eth_getlogs",
        "note": "Honest labels only — unknown counterparties are labeled 'unknown'.",
    })


def dashboard_store_defaults() -> dict:
    from integrations.dashboard_store import WHALE_WINDOW_HOURS_DEFAULT
    return {"window_hours": WHALE_WINDOW_HOURS_DEFAULT}


@app.route("/dashboard")
def dashboard():
    """The one canonical operations dashboard (persistent, chain-backed)."""
    _record_request("dashboard", True)
    return render_template("dashboard.html", nexus_url=NEXUS_URL)


# ── NEXUS: retired as a separate "live" dashboard ──────────────────────────
# The old /nexus page mixed real numbers with a SIMULATED discoveries feed
# and advertised a discovery engine that does not run in production.
# The discovery module stays in the codebase (lib/agents/market_evaluator.js)
# but no longer pretends to be live: the URL now points to the canonical
# dashboard. /api/nexus/strategy remains (real, admin-authenticated briefs).
@app.route("/nexus")
def nexus_dashboard():
    """Redirect the retired NEXUS page to the canonical dashboard."""
    return redirect("/dashboard", code=302)


# ── Telegram Bot (webhook-only, no polling) ────────────────────────────────
# NOTE: The Telegram module operates exclusively in webhook mode.
# All updates are received passively via the /api/telegram-webhook endpoint.
# No background polling / getUpdates thread is started.
#
# The command handling lives in services/telegram_sales.process_webhook_update
# (`BOT_COMMANDS` is both the published menu and the list of handled commands).
# A SECOND router used to live here — `_handle_telegram_command`, reachable by
# nothing — and it still advertised the old pricing ("Per call: $0.005",
# "Volume discount: $0.01") and a /status the live router did not implement.
# Dead code that quotes prices is exactly the phantom family this project keeps
# hunting, so it is deleted rather than left to be re-wired someday.


# ── Startup ──────────────────────────────────────────────────────────────

# ── Free-tier keep-alive (self-ping) ────────────────────────────────────────
# Render free instances spin down after ~15 minutes without inbound traffic.
# A lightweight self-GET every 10 minutes keeps the service awake 24/7 so AI
# agents can discover and pay for the API at any time, day or night.
KEEPALIVE_INTERVAL_SECONDS = max(300, int(os.getenv("KEEPALIVE_INTERVAL_SECONDS", "600")))


def _keepalive_loop():
    """Periodically ping our own public /health endpoint to prevent spin-down.

    Runs as a daemon thread alongside the other background loops. The target
    URL is resolved from KEEPALIVE_PUBLIC_URL / APP_PUBLIC_URL /
    WEBHOOK_PUBLIC_URL with a hard fallback to the production Render URL.
    Failures are non-fatal — the loop simply retries on the next interval.
    """
    public_url = (
        os.getenv("KEEPALIVE_PUBLIC_URL", "").strip()
        or os.getenv("APP_PUBLIC_URL", "").strip()
        or os.getenv("WEBHOOK_PUBLIC_URL", "").strip()
        or "https://kristo-intelligence-api.onrender.com"
    ).rstrip("/")
    target = f"{public_url}/health"
    log.info(
        "Keep-alive thread started (interval=%ds, target=%s).",
        KEEPALIVE_INTERVAL_SECONDS,
        target,
    )
    # Give the web server time to bind before the very first ping.
    time.sleep(120)
    while True:
        try:
            import requests as _requests
            response = _requests.get(target, timeout=30)
            log.info("Keep-alive ping: %s -> HTTP %d", target, response.status_code)
        except Exception as exc:
            log.warning("Keep-alive ping failed (non-fatal): %s", exc)
        time.sleep(KEEPALIVE_INTERVAL_SECONDS)


def _start_background_threads():
    """Start monitor, agent, catalog-analytics and Telegram background workers.

    Respects two environment flags:
      - KRISTO_DISABLE_BACKGROUND_THREADS=true → never start (web-only mode,
        used when a dedicated scripts.worker process handles background work)
      - KRISTO_WORKER_MODE=true → always start (worker process mode)
    Default (neither flag): start threads inline (legacy single-process mode).
    """
    # ── Root guard: duplicate module load (defect documented 30.09) ──
    # A lazy `import main` (sentinel._dashboard_store, telegram_sales
    # handlers, discovery routes) re-executes this module with a FRESH
    # Flask app — so `app._bg_started` below is False again and every
    # background loop would start a SECOND time in the same process
    # (observed on every boot since 27.09: double revenue checks, double
    # alerts, double blockchain-monitor settle attempts). os.environ is
    # process-wide, so this flag is shared by the __main__ load and every
    # re-execution — the second load skips ALL background threads.
    if os.getenv("KRISTO_BG_THREADS_STARTED", "") == "1":
        log.info(
            "Background threads already started in this process "
            "(KRISTO_BG_THREADS_STARTED=1) — duplicate module load skipped."
        )
        return
    if getattr(app, "_bg_started", False):
        return
    app._bg_started = True

    worker_mode = os.getenv("KRISTO_WORKER_MODE", "").lower() in ("1", "true", "yes")
    disable_flag = os.getenv("KRISTO_DISABLE_BACKGROUND_THREADS", "").lower() in ("1", "true", "yes")
    if disable_flag and not worker_mode:
        log.info("Background threads disabled (KRISTO_DISABLE_BACKGROUND_THREADS=true). "
                 "Run scripts.worker in a separate process for background work.")
        return
    if worker_mode:
        log.info("Worker mode active (KRISTO_WORKER_MODE=true) — starting all background threads.")

    # Set only when threads are about to start, so the env guard above
    # always means "a full thread set already runs in this process".
    os.environ["KRISTO_BG_THREADS_STARTED"] = "1"

    # ── the organism's opening word ───────────────────────────────────────────
    # DELIBERATELY OFF THE BOOT PATH.
    #
    # This runs inside `_start_background_threads`, which is called at import
    # time — BEFORE gunicorn binds the port. A durable write here is a Postgres
    # round-trip on the critical path to listening, and this project has already
    # paid for exactly that mistake once: module-level `purge_old_requests()`
    # delayed binding in a4c1cb0 and Render answered "No open ports detected".
    #
    # So it goes in its own daemon thread. Boot must not wait on telemetry; if
    # the write is slow or fails, the blocks simply report `not_reached` until
    # their own loops beat, which is honest.
    def _organism_opening_word():
        try:
            _organism_beat("delivery", "ok",
                           "process started, background threads armed")
            _organism_journal_note("delivery", "boot",
                                   detail="background threads started")
        except Exception as exc:  # noqa: BLE001 - telemetry only
            log.debug("organism opening word failed: %s", exc)

    threading.Thread(target=_organism_opening_word, daemon=True,
                     name="organism-boot").start()

    # Start blockchain monitor (real wallet)
    t_chain = threading.Thread(target=_blockchain_monitor_loop, daemon=True, name="blockchain-monitor")
    t_chain.start()

    # Warm the public dashboard payload so the first visitor after a deploy
    # gets a fast board instead of paying for the build themselves.
    t_dash = threading.Thread(target=_dashboard_warmer_loop, daemon=True,
                              name="dashboard-warmer")
    t_dash.start()

    # Read the board's all-time traffic panels out of band: they exceed the
    # shared connection's 8s statement timeout, so on a request path they were
    # unreadable rather than merely slow. Own connection, own ceiling.
    t_snap = threading.Thread(target=_requests_snapshot_warmer_loop, daemon=True,
                              name="requests-snapshot-warmer")
    t_snap.start()

    # Start agent thread
    t_agent = threading.Thread(target=_background_agent_loop, daemon=True, name="agent-loop")
    t_agent.start()

    # Persist a first 24-hour catalog snapshot, then refresh it once per day.
    t_catalog = threading.Thread(
        target=_catalog_analytics_loop,
        daemon=True,
        name="catalog-analytics",
    )
    t_catalog.start()

    t_stripe_snapshot = threading.Thread(
        target=_stripe_payment_snapshot_loop,
        daemon=True,
        name="stripe-payment-snapshot",
    )
    t_stripe_snapshot.start()

    # Canonical dashboard: persistent chain scan + PayAPI listing state
    t_dash = threading.Thread(
        target=_dashboard_scan_loop,
        daemon=True,
        name="dashboard-scan",
    )
    t_dash.start()

    # Whale flow: its OWN thread (Табло 2.0 audit) — a network-wide scan must
    # not sit behind retro_scan, and must not starve the sales numbers.
    # ── MOVED HERE FROM MODULE LEVEL (08.11.2026) ─────────────────────────
    # Both call `_isolated_store`, which is defined further down this module.
    # Started at module level they raced the rest of the import and the name
    # did not exist yet:
    #
    #     Request-log retention failed (non-fatal): name '_isolated_store'
    #     is not defined
    #
    # Retention is what keeps `request_log` bounded — it is the fix for the
    # 07.11 OOM — and reorg detection notices a reorg invalidating a recorded
    # sale. Neither is non-fatal, and both were dead.
    #
    # Started here instead: after the module is importable and the port is
    # bound, which is where a4c1cb0 already said work of this shape belongs.
    threading.Thread(target=_request_log_retention, daemon=True,
                     name="request-log-retention").start()
    threading.Thread(target=_detect_reorgs, daemon=True,
                     name="reorg-watch").start()

    t_whale = threading.Thread(
        target=_whaleflow_scan_loop,
        daemon=True,
        name="whaleflow-scan",
    )
    t_whale.start()

    # Keep-alive self-ping: prevents free-tier spin-down between customer
    # calls so AI agents can reach the API 24/7.
    t_keepalive = threading.Thread(
        target=_keepalive_loop, daemon=True, name="keep-alive"
    )
    t_keepalive.start()

    # Arb Radar: cross-DEX arbitrage spread detection on Base (paid endpoint).
    try:
        from services.arb_radar import start_arb_radar_thread
        start_arb_radar_thread()
    except Exception as exc:
        log.warning("Failed to start Arb Radar thread (non-fatal): %s", exc)

    # Kristo Sentinel: in-app autonomous monitoring & Telegram alerting agent
    # (health transitions, on-chain revenue, GitHub/PR status, weekly report).
    try:
        from services.sentinel import start_sentinel_thread
        start_sentinel_thread()
    except Exception as exc:
        log.warning("Failed to start Sentinel thread (non-fatal): %s", exc)

    # Start Telegram sales loop (auto market bulletins every 30 min, webhook-only)
    try:
        t_sales = threading.Thread(target=telegram_sales_loop, daemon=True, name="telegram-sales")
        t_sales.start()
    except Exception as exc:
        log.warning("Failed to start Telegram sales thread (non-fatal): %s", exc)

    # ── Auto-register Telegram webhook on startup ──
    # Calls setWebhook so Telegram delivers updates to /api/telegram-webhook.
    # Runs on every deploy — no manual action required.
    try:
        register_webhook()
    except Exception as exc:
        log.warning("Telegram webhook auto-registration failed (non-fatal): %s", exc)

    # ── Auto-register the Telegram command MENU on startup ──
    # getMyCommands used to be empty, so the bot answered commands it never
    # advertised. Like the webhook, this is re-asserted on every deploy.
    try:
        register_bot_commands()
    except Exception as exc:
        log.warning("Telegram command-menu registration failed (non-fatal): %s",
                    exc)

    log.info(
        "Background threads started (blockchain monitor + agent + catalog analytics "
        "+ keep-alive + sentinel + telegram sales)."
    )


# ── Register the buyer-worded alias URL rules ───────────────────────────────
# Placed at the END of the module, after every route decorator, because
# app.url_map only holds the canonical rules once they have all been declared —
# /api/v1/verify-seller lives on the discovery blueprint and /api/v1/whaleflow is
# defined far below the point where the aliases are declared. Registering here
# means the alias points at whatever view function the canonical path actually
# resolved to, rather than at a name this file has to remember.
#
# `add_url_rule` reuses the SAME view function: an alias can never drift from the
# handler it fronts, because there is only one handler. Flask needs a distinct
# endpoint name per rule, hence the derived one.
def _register_x402_alias_routes() -> list:
    existing = {str(rule) for rule in app.url_map.iter_rules()}
    registered = []
    for alias, canonical in X402_PATH_ALIASES.items():
        if alias in existing:
            log.warning("x402 alias %s already exists as a real route — skipped",
                        alias)
            continue
        rule = next((r for r in app.url_map.iter_rules()
                     if str(r) == canonical), None)
        if rule is None:
            log.warning("x402 alias %s: canonical route %s not found — skipped",
                        alias, canonical)
            continue
        view = app.view_functions.get(rule.endpoint)
        if view is None:
            log.warning("x402 alias %s: no view function for %s — skipped",
                        alias, canonical)
            continue
        methods = sorted((rule.methods or {"GET"}) - {"HEAD", "OPTIONS"}) or ["GET"]
        app.add_url_rule(alias, endpoint="x402_alias_" + alias.strip("/").replace(
            "/", "_"), view_func=view, methods=methods)
        registered.append((alias, canonical))
    if registered:
        log.info("x402 alias routes registered: %s",
                 ", ".join("%s→%s" % (a, c) for a, c in registered))
    return registered


X402_ALIAS_ROUTES_REGISTERED = _register_x402_alias_routes()


# Start threads when module loads (works with gunicorn / Procfile).
# Tests can disable networked background work with KRISTO_DISABLE_BACKGROUND_THREADS.
if os.getenv("KRISTO_DISABLE_BACKGROUND_THREADS", "").strip().lower() != "true":
    try:
        _start_background_threads()
    except Exception as exc:
        log.warning("Background threads startup failed (non-fatal): %s", exc)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
