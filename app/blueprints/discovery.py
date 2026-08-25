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


@discovery_bp.route("/api/mcp/manifest")
def api_mcp_manifest():
    """MCP (Model Context Protocol) manifest for AI agent M2M payments."""
    from main import (
        _record_request,
        MICRO_FEE_USDC,
        VIP_MONTHLY_USDC,
        VIP_THRESHOLD_USDC,
    )
    from config import get_base_fee_receiver

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
                    "description": "Pay-per-call: 0.10 USDC per API request",
                    "access": "single API call",
                    "endpoints": ["/api/stats", "/api/sales", "/api/bot-status"],
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
    """OpenAPI 3.0 specification for AI agent discovery."""
    from main import (
        X402_CHAIN,
        X402_CHAIN_ID,
        X402_FEE_USDC,
        X402_RECEIVER_ADDRESS,
        X402_USDC_CONTRACT,
        FREE_TIER_LIMIT,
    )

    base_url = request.host_url.rstrip("/")
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
        },
        "servers": [{"url": base_url}],
        "paths": {
            "/api/stats": {
                "get": {
                    "summary": "Market activity and daily stats",
                    "x402": {"cost_usdc": X402_FEE_USDC, "free_tier_eligible": True},
                    "responses": {
                        "200": {"description": "Successful response with stats data"},
                        "402": {"description": "Payment Required — free tier exhausted, send USDC to receiver"},
                    },
                }
            },
            "/api/sales": {
                "get": {
                    "summary": "Real on-chain sales history",
                    "x402": {"cost_usdc": X402_FEE_USDC, "free_tier_eligible": True},
                    "responses": {
                        "200": {"description": "Successful response with sales history"},
                        "402": {"description": "Payment Required — free tier exhausted, send USDC to receiver"},
                    },
                }
            },
            "/api/bot-status": {
                "get": {
                    "summary": "Telegram bot integration status",
                    "x402": {"cost_usdc": X402_FEE_USDC, "free_tier_eligible": True},
                    "responses": {
                        "200": {"description": "Successful response with bot status"},
                        "402": {"description": "Payment Required — free tier exhausted, send USDC to receiver"},
                    },
                }
            },
            "/api/mcp/manifest": {
                "get": {
                    "summary": "MCP/x402 payment manifest (free)",
                    "x402": {"cost_usdc": 0.0, "free_tier_eligible": False},
                    "responses": {"200": {"description": "Machine-readable payment manifest"}},
                }
            },
            "/.well-known/x402.json": {
                "get": {
                    "summary": "x402 discovery file (free)",
                    "x402": {"cost_usdc": 0.0, "free_tier_eligible": False},
                    "responses": {"200": {"description": "x402 payment discovery metadata"}},
                }
            },
            "/openapi.json": {
                "get": {
                    "summary": "This OpenAPI specification (free)",
                    "x402": {"cost_usdc": 0.0, "free_tier_eligible": False},
                    "responses": {"200": {"description": "OpenAPI 3.0 specification"}},
                }
            },
            "/llms.txt": {
                "get": {
                    "summary": "LLM-friendly API description (free)",
                    "x402": {"cost_usdc": 0.0, "free_tier_eligible": False},
                    "responses": {"200": {"description": "Plain-text API description for LLMs"}},
                }
            },
            "/health": {
                "get": {
                    "summary": "Health check (free)",
                    "x402": {"cost_usdc": 0.0, "free_tier_eligible": False},
                    "responses": {"200": {"description": "Service health status"}},
                }
            },
            "/dashboard": {
                "get": {
                    "summary": "HTML dashboard (free)",
                    "x402": {"cost_usdc": 0.0, "free_tier_eligible": False},
                    "responses": {"200": {"description": "HTML dashboard page"}},
                }
            },
            "/api/v1/agents/{agent_id}/playground": {
                "post": {
                    "summary": "One bounded free catalog-agent demo per client",
                    "x402": {
                        "catalog_driven_pricing": True,
                        "settlement_status": "discovery_only",
                        "free_playground_requests_per_client": 1,
                    },
                    "parameters": [
                        {
                            "name": "agent_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {
                        "200": {"description": "Bounded demo execution completed"},
                        "402": {"description": "Free demo used; response includes x402 and Stripe upgrade paths"},
                        "404": {"description": "Unknown agent"},
                    },
                }
            },
        },
        "components": {
            "securitySchemes": {
                "x402": {
                    "type": "apiKey",
                    "in": "header",
                    "name": "X-Payment-Address",
                    "description": f"x402 payment: send {X402_FEE_USDC} USDC on Base to {X402_RECEIVER_ADDRESS}",
                }
            }
        },
    }
    return jsonify(spec)


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
