"""Viral & chain-reaction distribution layer — public trust surface.

Public, unauthenticated routes (rate-limited via the application limiter):
  * GET /api/public/activity            — anonymized recent x402 unlocks
                                          + verified Nexus signals
                                          (JSON default, ?format=html wall,
                                          ?format=text syndication block)
  * GET /.well-known/kristo-agent.json  — agent-friendly discovery manifest
  * GET /api/agent-manifest             — alias of the manifest

No PII is ever emitted: see src/nexus/activity.py for the anonymization
contract enforced by construction.
"""

from __future__ import annotations

from typing import Any, Dict

from flask import Blueprint, current_app, jsonify, render_template, request


def _build_feed() -> Dict[str, Any]:
    """Wire the feed builder to the application's live data lazily."""
    import main  # deferred — avoids circular imports
    from .activity import build_activity_feed

    engine = current_app.extensions.get("nexus_engine")
    strategy = engine.build_strategy() if engine is not None else {}
    return build_activity_feed(
        request_log_provider=lambda: list(main._request_log),
        sales_history_provider=lambda: list(main._sales_history),
        catalog_metrics_provider=lambda: main.catalog_store.get_metrics_24h(),
        nexus_signals_provider=lambda: strategy,
    )


def _build_agent_manifest() -> Dict[str, Any]:
    """Machine-readable manifest: endpoints, USDC pricing, payment how-to."""
    import main  # deferred — avoids circular imports
    from config import BASE_USDC_CONTRACT, get_base_fee_receiver

    catalog = main.catalog_store.get_catalog()
    price_map: Dict[str, float] = dict(main.X402_PRICE_MAP)
    fallback = float(main.BASE_FEE_AMOUNT_USDC)
    labels = {
        "/api/stats": "DeFi market snapshot (top movers, volume, sentiment)",
        "/api/sales": "Real-time market evaluator data",
        "/api/bot-status": "Live trading-agent intelligence status",
        "/api/arb/opportunities": "Cross-DEX arbitrage opportunities on Base",
    }
    endpoints = []
    for path in sorted(main.X402_PAID_ENDPOINTS):
        price = float(price_map.get(path, fallback))
        endpoints.append(
            {
                "path": path,
                "label": labels.get(path, path.rsplit("/", 1)[-1].replace("-", " ").title()),
                "price_usdc": price,
                "price_raw": str(int(round(price * 1_000_000))),
                "demo": f"{path}?demo=true",
                "requires": "x402 payment after the free tier",
            }
        )
    return {
        "service": "Kristo Intelligence",
        "description": (
            "Base-chain DeFi & on-chain intelligence for AI agents — "
            "pay-per-call via the x402 protocol in USDC."
        ),
        "protocol": {
            "name": "x402",
            "network": "base",
            "chain_id": main.X402_CHAIN_ID,
            "asset": "USDC",
            "asset_contract": BASE_USDC_CONTRACT,
            "receiver": get_base_fee_receiver(),
        },
        "free_tier": {"requests_per_client": main.FREE_TIER_LIMIT},
        "payment_flow": [
            "1. GET the endpoint — a 402 challenge returns the exact amount and payTo address",
            "2. Send the USDC transfer on Base (chain 8453) and wait for confirmation",
            "3. Retry with the X-Payment-Proof header (base64 of {payer, transaction_hash, amount})",
            "4. Receive the data — one verified on-chain unlock per call",
        ],
        "endpoints": endpoints,
        "agent_catalog": [
            {
                "id": p.get("id"),
                "name": p.get("name"),
                "category": p.get("category"),
                "price_usdc": p.get("price_usdc"),
            }
            for p in main.catalog_store.get_catalog()
        ],
        "discovery": {
            "openapi": "/openapi.json",
            "llms": "/llms.txt",
            "x402_discovery": "/.well-known/x402.json",
            "agents": "/agents.json",
            "mcp": "/mcp.json",
            "public_activity": "/api/public/activity",
        },
        "homepage": "https://kristo-intelligence-api.onrender.com",
    }


def create_distribution_blueprint() -> Blueprint:
    bp = Blueprint("viral_distribution", __name__)

    @bp.get("/api/public/activity")
    def public_activity() -> Any:
        """Anonymized proof-of-traction feed — no auth by design."""
        from main import _rate_limited_response  # deferred

        limited = _rate_limited_response("public_activity")
        if limited:
            return limited

        feed = _build_feed()
        fmt = (request.args.get("format") or "json").strip().lower()
        if fmt == "text":
            from .syndication import format_activity_digest

            return current_app.response_class(
                format_activity_digest(feed) + "\n",
                mimetype="text/plain",
            )
        if fmt == "html":
            return render_template("public_activity.html", feed=feed)
        return jsonify({"ok": True, **feed})

    @bp.get("/.well-known/kristo-agent.json")
    @bp.get("/api/agent-manifest")
    def agent_manifest() -> Any:
        """Agent-friendly discovery manifest: data endpoints + USDC pricing + how-to."""
        return jsonify({"ok": True, **_build_agent_manifest()})

    return bp
