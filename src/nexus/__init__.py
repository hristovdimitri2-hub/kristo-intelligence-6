"""Nexus Intelligence Engine — unified autonomous intelligence loop.

Aggregates x402 catalog performance, sales-funnel and research intelligence
from the durable stores, cross-references them with the project parameters
(pricing tiers, paid endpoints, funnel metrics) and synthesizes actionable
strategic briefs exposed via the internal ``GET /api/nexus/strategy`` endpoint.

Zero external paid dependencies: everything runs natively inside the
existing Flask/Render backend with no background spam automations.
"""

from __future__ import annotations

from .nexus_core import (
    CatalogPulseSource,
    FunnelPulseSource,
    NexusAggregator,
    NexusEngine,
    PulseSource,
    ResearchPulseSource,
)
from .synthesizer import StrategicSynthesizer
from .blueprint import create_nexus_blueprint

__all__ = [
    "CatalogPulseSource",
    "FunnelPulseSource",
    "NexusAggregator",
    "NexusEngine",
    "PulseSource",
    "ResearchPulseSource",
    "StrategicSynthesizer",
    "create_nexus_blueprint",
    "mount_nexus_engine",
]


def _resolve_main_attr(name: str):
    """Resolve an attribute on the main application module lazily.

    Lazy resolution (instead of capturing the object at mount time) keeps the
    engine test-friendly: tests swap ``main.crm_store``/``main.catalog_store``
    via ``monkeypatch.setattr`` and the engine transparently uses the new
    instances on its next build cycle.
    """
    import main

    return getattr(main, name)


def _project_params() -> dict:
    """Cross-reference target: current pricing tiers and API surface.

    Single source of truth remains ``config.py`` (KRISTO_* price constants);
    the endpoint -> price map is resolved from the running application module.
    """
    from config import (
        BASE_FEE_AMOUNT_USDC,
        BASE_USDC_CONTRACT,
        KRISTO_ARB_PRICE,
        KRISTO_RUG_PRICE,
        KRISTO_SALES_PRICE,
        KRISTO_STATS_PRICE,
        KRISTO_WHALE_PRICE,
        get_base_fee_receiver,
    )
    import main

    return {
        "pricing_tiers": {
            "stats": KRISTO_STATS_PRICE,
            "sales": KRISTO_SALES_PRICE,
            "arb_opportunities": KRISTO_ARB_PRICE,
            "rug_risk": KRISTO_RUG_PRICE,
            "whale_activity": KRISTO_WHALE_PRICE,
        },
        "paid_endpoints": sorted(main.X402_PAID_ENDPOINTS),
        "endpoint_prices": dict(main.X402_PRICE_MAP),
        "free_tier_limit": main.FREE_TIER_LIMIT,
        "fee_usdc": BASE_FEE_AMOUNT_USDC,
        "usdc_contract": BASE_USDC_CONTRACT,
        "fee_receiver": get_base_fee_receiver(),
        "chain_id": main.X402_CHAIN_ID,
    }


def build_default_engine() -> NexusEngine:
    """Wire the engine to the application's durable stores lazily."""
    aggregator = NexusAggregator(
        project_params_provider=_project_params,
        sources=[
            CatalogPulseSource(lambda: _resolve_main_attr("catalog_store")),
            FunnelPulseSource(lambda: _resolve_main_attr("crm_store")),
            ResearchPulseSource(lambda: _resolve_main_attr("research_store")),
        ],
    )
    return NexusEngine(aggregator=aggregator, synthesizer=StrategicSynthesizer())


def mount_nexus_engine(app, force_rebuild: bool = False) -> NexusEngine:
    """Mount the Nexus Intelligence Engine onto the Flask application.

    Idempotent: repeated calls return the already-mounted engine unless
    ``force_rebuild`` is True (used by tests to re-wire stores). Registers the
    ``/api/nexus/strategy`` blueprint and stores the engine under
    ``app.extensions["nexus_engine"]``. No background threads are started —
    the loop is built on-demand per request behind a short TTL cache.
    """
    extensions = getattr(app, "extensions", None)
    if extensions is None:
        extensions = app.extensions = {}
    existing = extensions.get("nexus_engine")
    if existing is not None and not force_rebuild:
        return existing

    engine = build_default_engine()
    extensions["nexus_engine"] = engine

    from .blueprint import create_nexus_blueprint
    from .distribution import create_distribution_blueprint

    if "nexus_intel" not in app.blueprints:
        app.register_blueprint(create_nexus_blueprint())
    if "viral_distribution" not in app.blueprints:
        app.register_blueprint(create_distribution_blueprint())
    return engine
