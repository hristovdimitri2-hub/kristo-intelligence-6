"""Regression tests for the Nexus Intelligence Engine.

Covers the unified loop end to end:
  * mount_nexus_engine() wiring (idempotent, blueprint + extension)
  * GET /api/nexus/strategy auth semantics (401 without admin, 200 with)
  * pulse-source collection from the durable stores (catalog/funnel/research)
  * gap-analysis rules (monetization, discovery, funnel, research productization)
  * integration: seeded data surfaces real briefs through the HTTP endpoint
"""

import pytest


@pytest.fixture()
def nexus_env(monkeypatch, tmp_path):
    """Isolated app + fresh durable stores wired into the Nexus engine."""
    monkeypatch.setenv("ADMIN_API_TOKEN", "nexus-admin-token")
    monkeypatch.setenv("SESSION_SECRET", "nexus-session-secret")
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    import main
    from integrations.catalog_store import create_catalog_store
    from integrations.crm_store import CRMStore
    from integrations.research_store import ResearchInsightStore
    from src.nexus import mount_nexus_engine

    catalog = create_catalog_store(tmp_path / "catalog.db")
    crm = CRMStore(tmp_path / "crm.db")
    research = ResearchInsightStore(tmp_path / "research.db")
    monkeypatch.setattr(main, "catalog_store", catalog)
    monkeypatch.setattr(main, "crm_store", crm)
    monkeypatch.setattr(main, "research_store", research)

    engine = mount_nexus_engine(main.app, force_rebuild=True)
    engine.invalidate()

    yield main, main.app.test_client(), catalog, crm, research, engine

    engine.invalidate()


def test_mount_registers_blueprint_and_extension(nexus_env):
    main, client, *_ = nexus_env
    assert main.app.extensions.get("nexus_engine") is not None
    assert "nexus_intel" in main.app.blueprints
    rules = [str(r) for r in main.app.url_map.iter_rules() if str(r) == "/api/nexus/strategy"]
    assert len(rules) == 1  # idempotent mounting → exactly one route


def test_strategy_endpoint_requires_admin(nexus_env):
    _, client, *_ = nexus_env
    response = client.get("/api/nexus/strategy")
    assert response.status_code == 401
    assert response.get_json()["error"] == "admin_auth_required"


def test_strategy_endpoint_returns_briefs_and_context(nexus_env):
    _, client, catalog, crm, research, _ = nexus_env
    # Seed: an agent that attracts clicks but never converts → monetization gap.
    catalog.record_click("ai-sentiment-narrative-pulse")
    catalog.record_click("ai-sentiment-narrative-pulse")
    catalog.record_click("ai-sentiment-narrative-pulse")
    from integrations.crm_store import LeadRecord

    crm.add_lead(LeadRecord(email="lead@example.com", source="test", campaign="nexus"))
    research.ingest(
        source="github",
        title="Developers want real-time gas alerts",
        content="Pain point thread: developers ask for gas alerting micro-APIs.",
        actionable_summary="Ship a gas-alert agent priced at the rug-risk tier.",
    )
    research.update_status(
        research.list_insights(status="PENDING", limit=1)[0]["id"], "APPROVED"
    )

    response = client.get(
        "/api/nexus/strategy", headers={"X-Admin-Token": "nexus-admin-token"}
    )
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["ok"] is True
    assert isinstance(payload["briefs"], list)
    assert payload["summary"]["total_briefs"] == len(payload["briefs"])

    context = payload["context"]
    assert context["project"]["paid_endpoints"]
    assert context["project"]["pricing_tiers"]["stats"] > 0
    assert context["funnel"]["leads_total"] == 1
    assert any(a["id"] == "ai-sentiment-narrative-pulse" for a in context["agents"])

    brief_ids = [b["id"] for b in payload["briefs"]]
    assert "monetization_gap:ai-sentiment-narrative-pulse" in brief_ids
    assert "research:productization" in brief_ids
    assert "funnel:followup-gap" in brief_ids


def test_engine_cache_and_invalidate(nexus_env):
    _, _, _, _, _, engine = nexus_env
    first = engine.build_strategy()
    second = engine.build_strategy()
    assert first is second  # TTL cache returns the same snapshot
    engine.invalidate()
    third = engine.build_strategy()
    assert third is not first


def test_aggregator_is_resilient_to_failing_sources(nexus_env):
    from src.nexus.nexus_core import NexusAggregator

    class BrokenSource:
        name = "broken-pulse"

        def collect(self):
            raise RuntimeError("collector down")

    aggregator = NexusAggregator(project_params_provider=lambda: {})
    aggregator.register_source(BrokenSource())
    collected = aggregator.collect()
    assert collected["items"] == []
    assert collected["sources"][0]["status"] == "error"
    # cross_reference still yields a coherent (empty) context
    context = aggregator.cross_reference(collected)
    assert context["agents"] == [] and context["funnel"] == {}


def test_aggregator_deduplicates_repeated_sources(nexus_env):
    from src.nexus.nexus_core import NexusAggregator, PulseSource

    class Dummy(PulseSource):
        name = "dummy"

        def collect(self):
            return [{"kind": "x", "ref_id": "1", "title": "t", "metrics": {}}]

    aggregator = NexusAggregator(project_params_provider=lambda: {})
    aggregator.register_source(Dummy())
    aggregator.register_source(Dummy())
    assert len(aggregator.collect()["sources"]) == 1


def test_synthesizer_prioritizes_high_first(nexus_env):
    from src.nexus.synthesizer import StrategicSynthesizer

    context = {
        "agents": [
            {
                "id": "a",
                "name": "A",
                "clicks_24h": 10,
                "payments_24h": 0,
                "revenue_24h": 0.0,
                "popularity_rank": 1,
                "price_usdc": 0.005,
                "calls_24h": 0,
            }
        ],
        "funnel": {"leads_total": 4, "paid_count": 0, "conversion_rate": 0.0},
        "research": {"approved": 0, "recent_titles": []},
    }
    result = StrategicSynthesizer().synthesize(context)
    priorities = [b["priority"] for b in result["briefs"]]
    order = {"high": 0, "medium": 1, "low": 2}
    assert priorities == sorted(priorities, key=lambda p: order.get(p, 9))
    assert "monetization_gap:a" in [b["id"] for b in result["briefs"]]
    assert "funnel:followup-gap" in [b["id"] for b in result["briefs"]]


def test_synthesizer_detects_research_productization_only_when_approved(nexus_env):
    from src.nexus.synthesizer import StrategicSynthesizer

    base = {"agents": [], "funnel": {"leads_total": 0, "paid_count": 0}}
    assert not any(
        b["id"] == "research:productization"
        for b in StrategicSynthesizer().synthesize(
            {**base, "research": {"approved": 0, "recent_titles": []}}
        )["briefs"]
    )
    assert any(
        b["id"] == "research:productization"
        for b in StrategicSynthesizer().synthesize(
            {**base, "research": {"approved": 2, "recent_titles": ["t"]}}
        )["briefs"]
    )


def test_synthesizer_flags_catalog_wide_discovery_gap(nexus_env):
    from src.nexus.synthesizer import StrategicSynthesizer

    agents = [
        {
            "id": f"agent-{i}",
            "name": f"Agent {i}",
            "clicks_24h": 0,
            "payments_24h": 0,
            "revenue_24h": 0.0,
            "popularity_rank": i + 1,
            "price_usdc": 0.005,
            "calls_24h": 0,
        }
        for i in range(5)
    ]
    briefs = StrategicSynthesizer().synthesize(
        {"agents": agents, "funnel": {}, "research": {"approved": 0}}
    )["briefs"]
    assert "discovery_gap:catalog-wide" in [b["id"] for b in briefs]