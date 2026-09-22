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

import json
import queue
import secrets
import threading
import time

from flask import Blueprint, Response, jsonify, request

discovery_bp = Blueprint("discovery", __name__)


@discovery_bp.route("/health")
def health():
    """Service health check (free, no paywall).

    Liveness semantics: returns 200 whenever the web service and its
    database are up — this is what platform health checks (Render, Docker)
    and the keep-alive loop rely on. Blockchain connectivity is reported
    informationally: the public Base RPC is rate-limited (429s) and must
    never take the whole API offline. The background monitor keeps retrying
    and resumes scanning from the last checked block, so no incoming
    payment is ever missed during an RPC hiccup.
    """
    from main import _lock, _wallet_state, crm_store
    from config import BASE_CHAIN_ID

    crm_ready = crm_store.is_healthy()
    with _lock:
        wallet = dict(_wallet_state)
    blockchain_ready = bool(
        wallet.get("rpc_connected")
        and wallet.get("chain_id") == BASE_CHAIN_ID
        and wallet.get("receiver_valid")
    )
    return jsonify(
        status="ok" if crm_ready and blockchain_ready else "degraded",
        service="up",
        database={"backend": crm_store.backend, "ready": crm_ready},
        blockchain={
            "ready": blockchain_ready,
            "network": wallet.get("network", "Base Mainnet"),
            "chain_id": wallet.get("chain_id"),
            "fee_receiver": wallet.get("fee_receiver"),
        },
    ), 200 if crm_ready else 503


def _mcp_tools(base_url):
    """Shared MCP tool definitions — served identically by the SSE endpoint
    (/mcp/sse) and the Streamable HTTP endpoint (POST /mcp). Each tool
    advertises its x402 price so the agent can pay before calling; paid
    calls still flow through the regular 402 paywall."""
    from main import (
        X402_CHAIN_ID,
        X402_FEE_USDC,
        X402_RECEIVER_ADDRESS,
        X402_USDC_CONTRACT,
    )

    return [
        {
            "name": "get_market_stats",
            "description": (
                "Read-only operation — no side effects, no parameters. Returns "
                "the live Base market snapshot: aggregated activity, daily "
                "request/sales counters, the official agent catalog, and "
                "real-time market data (CoinGecko, DEXScreener, Fear & Greed). "
                "Use it for market context and price/indicator lookups; use "
                "get_onchain_sales for paid-call revenue and get_bot_status for "
                "integration health. Paid via x402 (HTTP 402 challenge with the "
                "exact USDC amount and receiver on Base)."
            ),
            "inputSchema": {"type": "object", "properties": {},
                            "additionalProperties": False},
            "x402": {"price_usdc": X402_FEE_USDC, "chain_id": X402_CHAIN_ID,
                     "receiver": X402_RECEIVER_ADDRESS,
                     "token_contract": X402_USDC_CONTRACT,
                     "endpoint": f"{base_url}/api/stats"},
        },
        {
            "name": "get_onchain_sales",
            "description": (
                "Read-only operation — no side effects, no parameters. Returns "
                "the real on-chain payment history to this service's fee "
                "receiver on Base: total_volume_usd, total_sales, by_token, up "
                "to 100 history rows (tx hash, payer, amount, block, "
                "timestamp), source=\"real_blockchain\", plus the wallet state "
                "and a market snapshot. Use it when you need provable revenue "
                "or settlement evidence; use get_market_stats for prices and "
                "get_bot_status for integration health. Paid via x402 (HTTP 402 "
                "challenge with the exact USDC amount and receiver on Base)."
            ),
            "inputSchema": {"type": "object", "properties": {},
                            "additionalProperties": False},
            "x402": {"price_usdc": X402_FEE_USDC, "chain_id": X402_CHAIN_ID,
                     "receiver": X402_RECEIVER_ADDRESS,
                     "token_contract": X402_USDC_CONTRACT,
                     "endpoint": f"{base_url}/api/sales"},
        },
        {
            "name": "get_bot_status",
            "description": (
                "Read-only operation — no side effects, no parameters. Returns "
                "the service's Telegram integration status as JSON: "
                "telegram_bot_running, telegram_token_configured, "
                "last_heartbeat, uptime_started, messages_sent, active_users, "
                "commands_processed, vip_invites_sent, plus the wallet state. "
                "Use it to confirm this service's own monitoring is alive (and "
                "its heartbeat recent) before trusting other outputs; use "
                "get_market_stats for market data or get_onchain_sales for "
                "provable revenue. Paid via x402 (HTTP 402 challenge with the "
                "exact USDC amount and receiver on Base)."
            ),
            "inputSchema": {"type": "object", "properties": {},
                            "additionalProperties": False},
            "x402": {"price_usdc": X402_FEE_USDC, "chain_id": X402_CHAIN_ID,
                     "receiver": X402_RECEIVER_ADDRESS,
                     "token_contract": X402_USDC_CONTRACT,
                     "endpoint": f"{base_url}/api/bot-status"},
        },
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
                "version": "1.0.0",
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
        MICRO_FEE_USDC,
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
                    "price_usdc": MICRO_FEE_USDC,
                    "description": f"Pay-per-call: from {KRISTO_SIGNAL_PRICE} USDC per API request (per-endpoint pricing in 'endpoints.available')",
                    "access": "single API call",
                    "endpoints": ["/api/stats", "/api/sales", "/api/bot-status",
                                  "/api/arb/opportunities", "/api/v1/signal",
                                  "/api/v1/whaleflow"],
                },
                {
                    "id": "vip_monthly",
                    "name": "Monthly VIP",
                    "price_usdc": VIP_MONTHLY_USDC,
                    "description": "Unlimited monthly access + Telegram VIP group invite",
                    "access": "unlimited for 30 days",
                    "endpoints": ["ALL"],
                    "bonus": "Telegram VIP group invite code",
                },
            ],
        },
        "endpoints": {
            "base_url": base_url,
            "available": [
                {"path": "/api/stats", "method": "GET", "cost_usdc": MICRO_FEE_USDC,
                 "description": "Market activity and daily stats"},
                {"path": "/api/sales", "method": "GET", "cost_usdc": MICRO_FEE_USDC,
                 "description": "Real on-chain sales history"},
                {"path": "/api/bot-status", "method": "GET", "cost_usdc": MICRO_FEE_USDC,
                 "description": "Telegram bot status"},
                {"path": "/api/arb/opportunities", "method": "GET", "cost_usdc": KRISTO_ARB_PRICE,
                 "description": "Live cross-DEX arbitrage spreads on Base (60s refresh)"},
                {"path": "/api/v1/signal", "method": "GET", "cost_usdc": KRISTO_SIGNAL_PRICE,
                 "description": "Trading-agent signals (action, confidence, price_usd, reasoning) for ETH/ONDO/KAITO/DEGEN"},
                {"path": "/api/v1/whaleflow", "method": "GET", "cost_usdc": KRISTO_WHALEFLOW_PRICE,
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
            "vip_threshold": f"Payments >= ${VIP_THRESHOLD_USDC} USDC automatically generate a Telegram VIP invite code",
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
          "resources": ["https://host/api/stats", ...],
          "ownershipProofs": ["0x..."]
        }

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
        "resources": [
            f"{base_url}/api/stats",
            f"{base_url}/api/sales",
            f"{base_url}/api/bot-status",
            f"{base_url}/api/arb/opportunities",
            f"{base_url}/api/v1/signal",
            f"{base_url}/api/v1/whaleflow",
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
        VIP_MONTHLY_USDC,
    )
    from config import KRISTO_SIGNAL_PRICE, KRISTO_ARB_PRICE

    # Cheapest real route price — the same derived-floor rule as the OpenAPI
    # security blurb: never quote one flat amount for routes that differ.
    _cheapest = min(float(KRISTO_SIGNAL_PRICE), float(KRISTO_ARB_PRICE))

    base_url = request.host_url.rstrip("/")
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
            "price_per_call_usdc": X402_FEE_USDC,
            "free_tier_limit": FREE_TIER_LIMIT,
            "monthly_vip_usdc": VIP_MONTHLY_USDC,
        },
        "tools": [
            {
                "name": "get_market_stats",
                "description": "Get market activity, daily stats, the official eight-agent catalog, and real-time market data (CoinGecko, DEXScreener, Fear & Greed)",
                "endpoint": f"{base_url}/api/stats",
                "method": "GET",
                "cost_usdc": X402_FEE_USDC,
                "free_tier_eligible": True,
            },
            {
                "name": "get_sales_history",
                "description": "Get real on-chain sales history (USDC transfers) and live market snapshot",
                "endpoint": f"{base_url}/api/sales",
                "method": "GET",
                "cost_usdc": X402_FEE_USDC,
                "free_tier_eligible": True,
            },
            {
                "name": "get_bot_status",
                "description": "Get Telegram bot integration status and wallet info",
                "endpoint": f"{base_url}/api/bot-status",
                "method": "GET",
                "cost_usdc": X402_FEE_USDC,
                "free_tier_eligible": True,
            },
            {
                "name": "get_mcp_manifest",
                "description": "Get the full MCP/x402 payment manifest (free)",
                "endpoint": f"{base_url}/api/mcp/manifest",
                "method": "GET",
                "cost_usdc": 0.0,
                "free_tier_eligible": False,
            },
            {
                "name": "get_x402_discovery",
                "description": "Get x402 payment discovery metadata (free)",
                "endpoint": f"{base_url}/.well-known/x402.json",
                "method": "GET",
                "cost_usdc": 0.0,
                "free_tier_eligible": False,
            },
            {
                "name": "get_openapi_spec",
                "description": "Get OpenAPI 3.0 specification (free)",
                "endpoint": f"{base_url}/openapi.json",
                "method": "GET",
                "cost_usdc": 0.0,
                "free_tier_eligible": False,
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
    - security + securitySchemes for x402 authentication
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
    _cheapest = min(float(KRISTO_ARB_PRICE), float(KRISTO_SIGNAL_PRICE),
                    float(KRISTO_WHALEFLOW_PRICE))

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
            "amount": str(X402_FEE_USDC),
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

        `cost_usdc` overrides the flat per-call price advertised in
        x-payment-info/x402. Omitting it keeps the historical X402_FEE_USDC
        behaviour, so the original operations stay byte-identical.
        """
        cost = X402_FEE_USDC if cost_usdc is None else cost_usdc
        if cost == X402_FEE_USDC:
            op_payment_info = payment_info
        else:
            op_payment_info = dict(payment_info)
            op_payment_info["price"] = {
                **payment_info["price"],
                "amount": str(cost),
            }
        return {
            "summary": summary,
            "description": description,
            "x-payment-info": op_payment_info,
            "x402": {"cost_usdc": cost, "free_tier_eligible": True},
            "security": [{"x402": []}],
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
            "version": "6.0.0",
            "description": "AI-powered DeFi trading signals and crypto market intelligence. "
                           "Uses x402 payment protocol — USDC on Base.",
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
                "price_per_call_usdc": X402_FEE_USDC,
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
            )},
            "/api/sales": {"get": _paid_op(
                "Real on-chain sales history",
                "Returns verified on-chain sales transactions from the Base ecosystem, including amounts, token pairs, and timestamps.",
            )},
            "/api/bot-status": {"get": _paid_op(
                "Telegram bot integration status",
                "Returns the current status of the Telegram sales bot, including last bulletin time, subscriber count, and operational metrics.",
            )},
            "/api/arb/opportunities": {"get": _paid_op(
                "Cross-DEX arbitrage radar",
                "Live cross-DEX arbitrage spreads on Base (DEXScreener), refreshed every 60 seconds.",
                KRISTO_ARB_PRICE,
            )},
            "/api/v1/signal": {"get": _paid_op(
                "Live DeFi trading signal",
                "Live DeFi trading signal: action, confidence and one-line reasoning for ETH/ONDO/KAITO/DEGEN — refreshed under 5 minutes from live market data.",
                KRISTO_SIGNAL_PRICE,
            )},
            "/api/v1/whaleflow": {"get": _paid_op(
                "Live whale flow",
                "Live whale flow: USDC transfers >= $5M on Base with labeled counterparties — scanned continuously (freshness follows the RPC provider's limits; the response always states the block scanned to).",
                KRISTO_WHALEFLOW_PRICE,
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
        "components": {
            "securitySchemes": {
                "x402": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-Payment-Address",
                    "description": (
                        "x402 payment: send the EXACT USDC amount stated by the "
                        f"endpoint's 402 challenge (from ${_cheapest:.3f}) on Base to "
                        f"{X402_RECEIVER_ADDRESS}. After payment, retry the endpoint "
                        "with X-Payment-Address header set to the sender wallet address."
                    ),
                }
            }
        },
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
    pages = [
        ("/", "1.0", "daily"),
        ("/dashboard", "0.9", "hourly"),
        ("/nexus", "0.8", "daily"),
        ("/agents", "0.8", "daily"),
        ("/launch", "0.7", "weekly"),
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
        VIP_MONTHLY_USDC,
        # Audit #6 BREAK 2: these two were used below but missing from the
        # import list -> NameError -> LIVE 500 on /agents.json (the suite
        # never called this route, so 405 tests stayed green).
        KRISTO_ARB_PRICE,
        KRISTO_SIGNAL_PRICE,
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
            "price_per_call_usdc": X402_FEE_USDC,
            "free_tier_limit": FREE_TIER_LIMIT,
            "monthly_vip_usdc": VIP_MONTHLY_USDC,
        },
        "endpoints": [
            {"path": "/api/stats", "method": "GET",
             "description": "Market activity, daily stats, live market data",
             "cost_usdc": X402_FEE_USDC},
            {"path": "/api/sales", "method": "GET",
             "description": "Real on-chain sales history (USDC transfers)",
             "cost_usdc": X402_FEE_USDC},
            {"path": "/api/bot-status", "method": "GET",
             "description": "Telegram bot integration status",
             "cost_usdc": X402_FEE_USDC},
            {"path": "/api/arb/opportunities", "method": "GET",
             "description": "Live cross-DEX arbitrage spreads on Base (60s refresh)",
             "cost_usdc": KRISTO_ARB_PRICE},
            {"path": "/api/v1/signal", "method": "GET",
             "description": "Trading-agent signals (action, confidence, price_usd, reasoning) for ETH/ONDO/KAITO/DEGEN",
             "cost_usdc": KRISTO_SIGNAL_PRICE},
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
    )

    base_url = request.host_url.rstrip("/")
    return jsonify({
        "schema_version": "v1",
        "name_for_human": "Kristo Intelligence",
        "name_for_model": "kristo_intelligence",
        "description_for_human": (
            "AI-powered DeFi trading signals and crypto market intelligence on "
            "Base. Pay per request with USDC via the x402 protocol — no API keys."
        ),
        "description_for_model": (
            "Fetch DeFi market stats, real on-chain USDC sales history, and "
            "bot integration status. Paid endpoints cost "
            f"{X402_FEE_USDC} USDC per call via x402 (HTTP 402): send USDC on "
            f"Base (chain {X402_CHAIN_ID}) to {X402_RECEIVER_ADDRESS}, then "
            "retry with the X-Payment-Proof header. One free call per client."
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
            "price_per_call_usdc": X402_FEE_USDC,
            "free_tier_limit": FREE_TIER_LIMIT,
            "proof_header": "X-Payment-Proof",
            "client_package": "kristo-x402-client (npm)",
        },
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

1. Call the endpoint you want and read `accepts[0].amount` / `accepts[0].payTo`
   from the 402 body (the amount differs per route)
2. Send exactly that amount of USDC on Base to {X402_RECEIVER_ADDRESS}
3. Wait for on-chain confirmation (usually ~2 seconds on Base)
4. Retry the desired endpoint with the `X-Payment-Proof` header:
   `base64url(JSON({{"payer": "<your wallet>", "transaction_hash": "<tx hash>", "amount_usdc": <the amount you sent>}}))`
5. The server verifies the transfer on-chain and grants access automatically

## Endpoints

### Paid (x402 — one payment unlocks one call)

{paid_lines}

### Free (always accessible)

- GET /.well-known/x402.json — x402 payment discovery metadata
- GET /openapi.json — OpenAPI 3.0 specification
- GET /llms.txt — This file (LLM-friendly API description)
- GET /api/mcp/manifest — MCP/x402 machine-readable manifest
- GET /health — Service health check
- GET /dashboard — HTML dashboard

## Base URL

{base_url}

## HTTP 402 Response

When payment is required, the API returns HTTP 402 with:
- JSON body containing payment details (receiver address, amount, chain)
- Headers: X-Payment-Required, X-Payment-Address, X-Payment-Amount-USDC

## Discovery Files

- x402: {base_url}/.well-known/x402.json
- OpenAPI: {base_url}/openapi.json
- LLMs: {base_url}/llms.txt
- MCP Manifest: {base_url}/api/mcp/manifest
"""
    return Response(content, mimetype="text/plain")
