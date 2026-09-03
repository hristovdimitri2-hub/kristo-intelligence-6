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


@discovery_bp.route("/mcp/sse")
def mcp_sse():
    """MCP Server-Sent Events endpoint — Streamable HTTP transport.

    Lets MCP-native clients (Claude Desktop, Cursor, Continue) discover and
    call the paid Kristo endpoints as tools. GET returns an SSE stream with
    tool definitions; tool CALLS happen through the regular paid endpoints
    (the 402 paywall is the payment layer).

    Protocol notes:
    - We implement the minimal, spec-compliant handshake: endpoint event +
      initialize/tools/list JSON-RPC support over the SSE stream.
    - Tool schemas advertise the x402 price so the AGENT (or its operator)
    can decide to pay before calling.
    """
    from main import (
        X402_CHAIN_ID,
        X402_FEE_USDC,
        X402_RECEIVER_ADDRESS,
        X402_USDC_CONTRACT,
        VIP_MONTHLY_USDC,
    )

    base_url = request.host_url.rstrip("/")
    server_info = {
        "protocolVersion": "2024-11-05",
        "capabilities": {"tools": {}},
        "serverInfo": {
            "name": "kristo-intelligence",
            "version": "1.0.0",
            "title": "Kristo Intelligence — DeFi signals (x402/USDC on Base)",
        },
    }
    tools = [
        {
            "name": "get_market_stats",
            "description": (
                "Market activity, daily stats, and live market data "
                "(CoinGecko, DEXScreener, Fear & Greed). Paid via x402."
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
                "Real on-chain sales history (USDC transfers to the Kristo "
                "fee receiver). Paid via x402."
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
            "description": "Telegram bot integration status. Paid via x402.",
            "inputSchema": {"type": "object", "properties": {},
                            "additionalProperties": False},
            "x402": {"price_usdc": X402_FEE_USDC, "chain_id": X402_CHAIN_ID,
                     "receiver": X402_RECEIVER_ADDRESS,
                     "token_contract": X402_USDC_CONTRACT,
                     "endpoint": f"{base_url}/api/bot-status"},
        },
    ]
    messages = [
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
    ]

    def generate():
        # SSE stream: endpoint announcement + initialize + tools/list.
        yield "event: endpoint\n"
        yield f"data: {base_url}/mcp/sse\n\n"
        import json as _json
        yield "event: message\n"
        yield "data: " + _json.dumps({"jsonrpc": "2.0", "id": 0,
                                      "result": server_info}) + "\n\n"
        yield "event: message\n"
        yield "data: " + _json.dumps({"jsonrpc": "2.0", "id": 1,
                                      "result": {"tools": tools}}) + "\n\n"

    resp = Response(generate(), mimetype="text/event-stream")
    resp.headers["Cache-Control"] = "no-cache"
    resp.headers["X-Accel-Buffering"] = "no"
    return resp


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


@discovery_bp.route("/api/mcp/manifest")
def api_mcp_manifest():
    """MCP (Model Context Protocol) manifest for AI agent M2M payments."""
    from main import (
        _record_request,
        MICRO_FEE_USDC,
        VIP_MONTHLY_USDC,
        VIP_THRESHOLD_USDC,
    )
    from config import get_base_fee_receiver, KRISTO_SIGNAL_PRICE, KRISTO_ARB_PRICE

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
                    "description": f"Pay-per-call: {MICRO_FEE_USDC} USDC per API request",
                    "access": "single API call",
                    "endpoints": ["/api/stats", "/api/sales", "/api/bot-status",
                                  "/api/arb/opportunities", "/api/v1/signal"],
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
    from main import X402_RECEIVER_ADDRESS, X402_FEE_USDC, FREE_TIER_LIMIT

    base_url = request.host_url.rstrip("/")
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
        ],
        "ownershipProofs": [X402_RECEIVER_ADDRESS],
        "instructions": (
            "Every unpaid call returns HTTP 402 with a canonical x402 v2 challenge: "
            "send the exact USDC amount from the 402 body (from $0.003/call, USDC on "
            "Base, chain 8453) to " + X402_RECEIVER_ADDRESS + f" {tier_note}. "
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
            "payment": f"Send {X402_FEE_USDC} USDC on Base to {X402_RECEIVER_ADDRESS}",
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

    base_url = request.host_url.rstrip("/")
    # x-payment-info shared block for all paid operations
    payment_info = {
        "protocols": ["x402"],
        "price": {
            "mode": "fixed",
            "currency": "USD",
            "amount": str(X402_FEE_USDC),
        },
        "free_tier_limit": FREE_TIER_LIMIT,
        "receiver": X402_RECEIVER_ADDRESS,
        "chain": X402_CHAIN,
        "chain_id": X402_CHAIN_ID,
        "token_contract": X402_USDC_CONTRACT,
    }
    # Standard 402 response with required payment headers
    response_402 = {
        "description": "Payment Required — free tier exhausted, send USDC to receiver",
        "headers": {
            "X-Payment-Required": {"schema": {"type": "string"}},
            "X-Payment-Address": {"schema": {"type": "string"}},
            "X-Payment-Amount-USDC": {"schema": {"type": "string"}},
        },
    }

    def _paid_op(summary, description):
        return {
            "summary": summary,
            "description": description,
            "x-payment-info": payment_info,
            "x402": {"cost_usdc": X402_FEE_USDC, "free_tier_eligible": True},
            "security": [{"x402": []}],
            "responses": {
                "200": {"description": "Successful response"},
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
                        f"x402 payment: send {X402_FEE_USDC} USDC on Base to "
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
    """LLM-friendly plain-text description of the API for AI agent discovery."""
    from main import (
        X402_CHAIN_ID,
        X402_FEE_USDC,
        X402_RECEIVER_ADDRESS,
        X402_USDC_CONTRACT,
        FREE_TIER_LIMIT,
        VIP_MONTHLY_USDC,
    )

    base_url = request.host_url.rstrip("/")
    content = f"""# Kristo Intelligence API

> AI-powered DeFi trading signals and crypto market intelligence.
> Uses the x402 payment protocol — pay with USDC on Base.

## Payment (x402 Protocol)

- Chain: Base (chain_id: {X402_CHAIN_ID})
- Currency: USDC
- Token contract: {X402_USDC_CONTRACT}
- Receiver address: {X402_RECEIVER_ADDRESS}
- Price per API call: ${X402_FEE_USDC} USDC
- Free tier: {FREE_TIER_LIMIT} free call(s) per client, then payment required
- Monthly VIP: ${VIP_MONTHLY_USDC} USDC (unlimited for 30 days)

## How to Pay

1. Send exactly {X402_FEE_USDC} USDC on the Base network to {X402_RECEIVER_ADDRESS}
2. Wait for on-chain confirmation (usually ~2 seconds on Base)
3. Retry the desired endpoint with the `X-Payment-Proof` header:
   `base64url(JSON({{"payer": "<your wallet>", "transaction_hash": "<tx hash>", "amount_usdc": {X402_FEE_USDC}}}))`
4. The server verifies the transfer on-chain and grants access automatically

For unlimited access, send {VIP_MONTHLY_USDC} USDC for a Monthly VIP subscription.

## Endpoints

### Paid (requires x402 payment after free tier)

- GET /api/stats — Market activity and daily stats (${X402_FEE_USDC} USDC)
- GET /api/sales — Real on-chain sales history (${X402_FEE_USDC} USDC)
- GET /api/bot-status — Telegram bot status (${X402_FEE_USDC} USDC)

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
