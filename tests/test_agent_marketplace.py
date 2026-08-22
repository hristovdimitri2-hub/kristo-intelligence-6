from copy import deepcopy

import pytest

from integrations.marketplace_store import MarketplaceGovernanceStore
from services import agent_runtime


def _product(agent_id):
    return {
        "id": agent_id,
        "name": agent_runtime.AGENT_CONTRACTS[agent_id]["name"],
        "category": agent_runtime.AGENT_CONTRACTS[agent_id]["category"],
        "price_x402": agent_runtime.AGENT_CONTRACTS[agent_id]["price_x402"],
        "price_stripe": agent_runtime.AGENT_CONTRACTS[agent_id]["price_stripe"],
    }


def test_document_executor_is_deterministic_and_has_provenance():
    result = agent_runtime.execute_agent(
        _product("cross-venue-signal-divergence"),
        {"input": "# Heading\nRevenue: 12.5%\nSource https://example.com/report"},
    )

    assert result["contract_version"] == "2.0"
    assert result["status"] == "ok"
    assert result["data"]["sections"][0]["heading"] == "Heading"
    assert result["data"]["links"] == ["https://example.com/report"]
    assert result["provenance"][0]["name"] == "caller-supplied document"


def test_live_chain_executor_labels_stale_provider_state(monkeypatch):
    monkeypatch.setattr(
        agent_runtime,
        "fetch_coingecko_prices",
        lambda symbols: {"ethereum": {"usd": 3200.0}},
    )
    monkeypatch.setattr(
        agent_runtime,
        "fetch_dexscreener_pairs",
        lambda chain, limit: [{"chainId": chain, "pairAddress": "pair"}],
    )
    monkeypatch.setattr(
        agent_runtime,
        "get_coingecko_cache_status",
        lambda: {"state": "stale", "detail": "provider cooldown"},
    )

    result = agent_runtime.execute_agent(
        _product("token-launch-rug-risk-scanner"), {"input": "ethereum"}
    )

    assert result["status"] == "ok"
    assert result["freshness"]["state"] == "stale"
    assert result["provenance"][0]["state"] == "stale"
    assert result["data"]["market"]["usd"] == 3200.0


def test_change_monitor_requires_baseline_before_access_is_consumed():
    product = _product("smart-contract-security-triage")
    with pytest.raises(ValueError, match="input_must_be_between"):
        agent_runtime.validate_agent_payload(product, {"input": "current"})

    result = agent_runtime.execute_agent(
        product, {"baseline": "alpha\nbeta", "input": "alpha\ngamma"}
    )
    assert result["data"]["changed"] is True
    assert result["data"]["added_lines"] == ["gamma"]
    assert result["data"]["removed_lines"] == ["beta"]


def test_contract_governance_and_scout_reports_are_isolated(tmp_path):
    store = MarketplaceGovernanceStore(tmp_path / "marketplace.db")
    manifest = {"contract_version": "2.0", "agents": [{"id": "whaleflow-radar"}]}
    active = store.ensure_active_contract("2.0", manifest)
    assert active["status"] == "ACTIVE"
    assert store.active_contract()["manifest"] == manifest

    run = store.record_scout_report(
        {
            "generated_at": "2026-08-21T00:00:00+00:00",
            "status": "PARTIAL",
            "observations": [
                {
                    "source": "first_party_catalog",
                    "category": "research_utility",
                    "score": 8.0,
                    "evidence_url": "/api/admin/catalog-metrics",
                    "summary": "Observed usage.",
                    "state": "observed",
                }
            ],
        }
    )
    latest = store.latest_scout_report()
    assert run["status"] == "PARTIAL"
    assert latest["run_id"] == run["run_id"]
    assert latest["report"]["observations"][0]["source"] == "first_party_catalog"


def test_catalog_seed_does_not_overwrite_existing_metadata_without_activation(tmp_path):
    from integrations.catalog_store import CatalogStore

    store = CatalogStore(tmp_path / "catalog.db")
    with store._connect() as conn:
        conn.execute(
            "UPDATE agent_skus SET name = ? WHERE id = ?",
            ("Previously approved name", "whaleflow-radar"),
        )
    store.seed_catalog()
    assert store.get_product("whaleflow-radar")["name"] == "Previously approved name"
    store.apply_catalog_metadata()
    assert store.get_product("whaleflow-radar")["name"] == "Web Evidence"


def test_catalog_checkout_payment_is_idempotently_attributed(tmp_path):
    from integrations.catalog_store import CatalogStore

    store = CatalogStore(tmp_path / "catalog.db")
    assert store.register_checkout("checkout-1", "whaleflow-radar", "buyer@example.com", 0.10)
    assert store.confirm_checkout_payment(
        "checkout-1", "whaleflow-radar", "buyer@example.com", 0.10
    )
    assert not store.confirm_checkout_payment(
        "checkout-1", "whaleflow-radar", "buyer@example.com", 0.10
    )
    assert store.get_metrics_24h()["totals"]["payments"] == 1


def test_draft_contract_cannot_publish_or_execute_catalog_routes(monkeypatch, tmp_path):
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    import main
    from integrations.catalog_store import CatalogStore

    monkeypatch.setattr(main, "catalog_store", CatalogStore(tmp_path / "catalog.db"))
    governance = MarketplaceGovernanceStore(tmp_path / "marketplace.db")
    governance.ensure_contract_draft(
        main.AGENT_CONTRACT_VERSION, main.catalog_manifest(main.catalog_store.get_catalog())
    )
    monkeypatch.setattr(main, "marketplace_store", governance)

    client = main.app.test_client()
    catalog = client.get("/api/v1/agents")
    execution = client.post(
        "/api/v1/agents/cross-venue-signal-divergence/playground",
        json={"input": "Example document"},
    )
    x402 = client.get("/.well-known/x402.json").get_json()
    mcp = client.get("/mcp.json").get_json()
    legacy_mcp = client.get("/api/mcp/manifest").get_json()
    openapi = client.get("/openapi.json").get_json()
    llms = client.get("/llms.txt").get_data(as_text=True)
    assert catalog.status_code == 503
    assert execution.status_code == 503
    assert catalog.get_json()["error"] == "catalog_contract_approval_required"
    contract = client.get("/api/v1/catalog/contract").get_json()
    assert contract["status"] == "approval_required"
    assert "manifest" not in contract
    assert x402["catalog_status"] == "approval_required"
    assert x402["agents"] == []
    assert mcp["catalog_status"] == "approval_required"
    assert mcp["agents"] == []
    assert legacy_mcp["catalog"]["status"] == "approval_required"
    assert legacy_mcp["catalog"]["agents"] == []
    assert openapi["info"]["x-kristo-catalog"]["status"] == "approval_required"
    assert openapi["info"]["x-kristo-catalog"]["agents"] == []
    assert "cross-venue-signal-divergence" not in llms


def test_incompatible_contract_manifest_cannot_mutate_catalog(monkeypatch, tmp_path):
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    monkeypatch.setenv("ADMIN_API_TOKEN", "marketplace-admin-token")
    import main
    from integrations.catalog_store import CatalogStore

    store = CatalogStore(tmp_path / "catalog.db")
    monkeypatch.setattr(main, "catalog_store", store)
    governance = MarketplaceGovernanceStore(tmp_path / "marketplace.db")
    manifest = main.catalog_manifest(store.get_catalog())
    incompatible = deepcopy(manifest)
    incompatible["contract_version"] = "3.0"
    incompatible["agents"][0]["input_schema"] = {"type": "object", "properties": {}}
    governance.ensure_contract_draft("3.0", incompatible)
    monkeypatch.setattr(main, "marketplace_store", governance)

    before = store.get_product("whaleflow-radar")["name"]
    response = main.app.test_client().post(
        "/api/admin/catalog-contract/activate",
        headers={"X-Admin-Token": "marketplace-admin-token"},
        json={"version": "3.0"},
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "manifest_runtime_incompatible"
    assert store.get_product("whaleflow-radar")["name"] == before
    assert governance.active_contract() is None


def test_versioned_activation_and_rollback_restore_executable_catalog(monkeypatch, tmp_path):
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    monkeypatch.setenv("ADMIN_API_TOKEN", "marketplace-admin-token")
    import main
    from integrations.catalog_store import CatalogStore

    store = CatalogStore(tmp_path / "catalog.db")
    monkeypatch.setattr(main, "catalog_store", store)
    governance = MarketplaceGovernanceStore(tmp_path / "marketplace.db")
    v20 = main.catalog_manifest(store.get_catalog())
    governance.ensure_contract_draft("2.0", v20)
    v21 = deepcopy(v20)
    v21["contract_version"] = "2.1"
    v21_agent = next(agent for agent in v21["agents"] if agent["id"] == "whaleflow-radar")
    v21_agent["name"] = "Web Evidence Pro"
    v21_agent["price_x402"] = 0.12
    governance.ensure_contract_draft("2.1", v21)
    monkeypatch.setattr(main, "marketplace_store", governance)
    client = main.app.test_client()
    headers = {"X-Admin-Token": "marketplace-admin-token"}

    assert client.post(
        "/api/admin/catalog-contract/activate", headers=headers, json={"version": "2.0"}
    ).status_code == 200
    first = client.get("/api/v1/agents").get_json()
    first_agent = next(agent for agent in first["agents"] if agent["id"] == "whaleflow-radar")
    assert first["contract_version"] == "2.0"
    assert first_agent["name"] == "Web Evidence"

    def assert_discovery_versions(expected_version):
        catalog_payload = client.get("/api/v1/agents").get_json()
        mcp_manifest = client.get("/api/mcp/manifest").get_json()
        x402 = client.get("/.well-known/x402.json").get_json()
        mcp = client.get("/mcp.json").get_json()
        openapi = client.get("/openapi.json").get_json()
        catalog_ids = {agent["id"] for agent in catalog_payload["agents"]}
        catalog_prices = {agent["id"]: agent["price_x402"] for agent in catalog_payload["agents"]}

        assert catalog_payload["contract_version"] == expected_version
        assert mcp_manifest["version"] == "2.0"
        assert mcp_manifest["catalog"]["contract_version"] == expected_version
        assert x402["contract_version"] == expected_version
        assert mcp["contract_version"] == expected_version
        assert openapi["info"]["x-kristo-catalog"]["contract_version"] == expected_version
        assert {agent["id"] for agent in mcp_manifest["catalog"]["agents"]} == catalog_ids
        assert {agent["id"] for agent in mcp_manifest["endpoints"]["agents"]} == catalog_ids
        assert {agent["id"] for agent in x402["agents"]} == catalog_ids
        assert {agent["id"].removeprefix("agent_").replace("_", "-") for agent in mcp["agents"]} == catalog_ids
        assert {agent["id"] for agent in openapi["info"]["x-kristo-catalog"]["agents"]} == catalog_ids
        assert {
            agent["id"]: agent["price_usdc"] for agent in mcp_manifest["catalog"]["agents"]
        } == catalog_prices
        assert f"contract_version {expected_version}" in client.get("/llms.txt").get_data(as_text=True)

    assert_discovery_versions("2.0")

    assert client.post(
        "/api/admin/catalog-contract/activate", headers=headers, json={"version": "2.1"}
    ).status_code == 200
    revised = client.get("/api/v1/agents").get_json()
    revised_agent = next(agent for agent in revised["agents"] if agent["id"] == "whaleflow-radar")
    assert revised["contract_version"] == "2.1"
    assert revised_agent["name"] == "Web Evidence Pro"
    assert revised_agent["price_x402"] == 0.12
    assert_discovery_versions("2.1")
    revised_execution = client.post(
        "/api/v1/agents/cross-venue-signal-divergence/playground",
        json={"input": "# Heading\nRevenue: 12.5%\nSource https://example.com/report"},
        environ_base={"REMOTE_ADDR": "203.0.113.21"},
    )
    assert revised_execution.status_code == 200
    revised_payload = revised_execution.get_json()
    assert revised_payload["contract_version"] == "2.1"
    assert revised_payload["agent"]["contract_version"] == "2.1"
    assert revised_payload["result"]["contract_version"] == "2.1"

    assert client.post(
        "/api/admin/catalog-contract/rollback", headers=headers, json={"version": "2.0"}
    ).status_code == 200
    restored = client.get("/api/v1/agents").get_json()
    restored_agent = next(agent for agent in restored["agents"] if agent["id"] == "whaleflow-radar")
    assert restored["contract_version"] == "2.0"
    assert restored_agent["name"] == "Web Evidence"
    expected = next(agent for agent in v20["agents"] if agent["id"] == "whaleflow-radar")
    assert restored_agent["price_x402"] == expected["price_x402"]
    assert_discovery_versions("2.0")
    restored_execution = client.post(
        "/api/v1/agents/cross-venue-signal-divergence/playground",
        json={"input": "# Heading\nRevenue: 12.5%\nSource https://example.com/report"},
        environ_base={"REMOTE_ADDR": "203.0.113.20"},
    )
    assert restored_execution.status_code == 200
    restored_payload = restored_execution.get_json()
    assert restored_payload["contract_version"] == "2.0"
    assert restored_payload["agent"]["contract_version"] == "2.0"
    assert restored_payload["result"]["contract_version"] == "2.0"


def test_failed_sqlite_transition_restores_catalog_metadata(monkeypatch, tmp_path):
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    monkeypatch.setenv("ADMIN_API_TOKEN", "marketplace-admin-token")
    import main
    from integrations.catalog_store import CatalogStore

    class FailingGovernanceStore(MarketplaceGovernanceStore):
        def rollback_contract(self, version):
            return None

    store = CatalogStore(tmp_path / "catalog.db")
    governance = FailingGovernanceStore(tmp_path / "marketplace.db")
    manifest = main.catalog_manifest(store.get_catalog())
    revised = deepcopy(manifest)
    revised["contract_version"] = "2.1"
    next(agent for agent in revised["agents"] if agent["id"] == "whaleflow-radar")["name"] = "Uncommitted"
    governance.ensure_contract_draft("2.1", revised)
    monkeypatch.setattr(main, "catalog_store", store)
    monkeypatch.setattr(main, "marketplace_store", governance)

    response = main.app.test_client().post(
        "/api/admin/catalog-contract/activate",
        headers={"X-Admin-Token": "marketplace-admin-token"},
        json={"version": "2.1"},
    )
    assert response.status_code == 503
    assert response.get_json()["error"] == "catalog_contract_activation_failed"
    assert store.get_product("whaleflow-radar")["name"] == "Web Evidence"
    assert governance.active_contract() is None