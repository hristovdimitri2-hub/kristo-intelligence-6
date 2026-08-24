import pytest

from integrations.catalog_store import CatalogStore
from integrations.crm_store import CRMStore
from integrations.research_store import ResearchInsightStore


@pytest.fixture()
def v6_client(monkeypatch, tmp_path):
    monkeypatch.setenv("ADMIN_API_TOKEN", "v6-admin-token")
    monkeypatch.setenv("SESSION_SECRET", "v6-session-secret")
    monkeypatch.setenv("RESEARCH_INGEST_TOKEN", "v6-research-token")
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    monkeypatch.delenv("TRUST_PROXY_HEADERS", raising=False)
    monkeypatch.delenv("TRUSTED_PROXY_IPS", raising=False)
    import main

    monkeypatch.setattr(main, "catalog_store", CatalogStore(tmp_path / "catalog.db"))
    monkeypatch.setattr(main, "crm_store", CRMStore(tmp_path / "crm.db"))
    monkeypatch.setattr(main, "research_store", ResearchInsightStore(tmp_path / "research.db"))
    with main._stripe_snapshot_lock:
        main._stripe_snapshot = {
            "available": False,
            "payments": [],
            "reason": "test snapshot",
            "fetched_at": None,
            "state": "pending",
        }
    return main, main.app.test_client()


def test_dynamic_x402_discovery_and_one_free_agent_demo(v6_client):
    main, client = v6_client

    discovery = client.get("/.well-known/x402.json")
    assert discovery.status_code == 200
    payload = discovery.get_json()
    assert payload["service"] == "Kristo Intelligence v6"
    assert payload["payment"]["settlement_status"] == "discovery_only"
    assert len(payload["agents"]) == 8
    assert all(agent["endpoint"].endswith("/playground") for agent in payload["agents"])

    first = client.post(
        "/api/v1/agents/whaleflow-radar/playground",
        json={"input": "ETH"},
        environ_base={"REMOTE_ADDR": "198.51.100.10"},
    )
    assert first.status_code == 200
    assert first.get_json()["access"] == "one_free_playground_request"
    assert first.get_json()["result"]["mode"] == "playground_demo"

    exhausted = client.post(
        "/api/v1/agents/whaleflow-radar/playground",
        json={"input": "ETH"},
        environ_base={"REMOTE_ADDR": "198.51.100.10"},
    )
    assert exhausted.status_code == 402
    assert exhausted.get_json()["upgrade"]["stripe_checkout"].endswith("/checkout")
    assert main.catalog_store.get_metrics_24h()["totals"]["calls"] == 1


def test_research_ingest_is_deduplicated_and_requires_review(v6_client):
    _, client = v6_client
    body = {
        "source": "github",
        "external_id": "issue-77",
        "title": "Review liquidity anomaly",
        "content": "A monitored repository flagged a liquidity anomaly.",
        "actionable_summary": "Validate against on-chain sources before publishing.",
    }
    assert client.post("/api/v1/research/ingest", json=body).status_code == 401
    created = client.post(
        "/api/v1/research/ingest",
        json=body,
        headers={"X-Research-Ingest-Token": "v6-research-token"},
    )
    assert created.status_code == 201
    assert created.get_json()["created"] is True
    insight_id = created.get_json()["insight"]["id"]

    duplicate = client.post(
        "/api/v1/research/ingest",
        json=body,
        headers={"X-Research-Ingest-Token": "v6-research-token"},
    )
    assert duplicate.status_code == 200
    assert duplicate.get_json()["created"] is False

    queued = client.get(
        "/api/admin/research-insights?status=PENDING",
        headers={"X-Admin-Token": "v6-admin-token"},
    )
    assert queued.status_code == 200
    assert queued.get_json()["total"] == 1
    approved = client.patch(
        f"/api/admin/research-insights/{insight_id}",
        json={"status": "APPROVED"},
        headers={"X-Admin-Token": "v6-admin-token"},
    )
    assert approved.status_code == 200
    assert approved.get_json()["insight"]["status"] == "APPROVED"


def test_admin_overview_uses_cached_stripe_snapshot(v6_client, monkeypatch):
    main, client = v6_client
    calls = []

    def listing():
        calls.append(True)
        return {
            "available": True,
            "payments": [{"email": "buyer@example.com", "amount_usd": 19.0}],
            "reason": "connected",
        }

    monkeypatch.setattr(main.stripe_checkout, "list_recent_completed_payments", listing)
    main._refresh_stripe_payment_snapshot()
    headers = {"X-Admin-Token": "v6-admin-token"}
    first = client.get("/api/admin/overview", headers=headers)
    second = client.get("/api/admin/overview", headers=headers)

    assert first.status_code == 200
    assert second.status_code == 200
    assert len(calls) == 1
    assert first.get_json()["payment_source"] == "stripe_checkout"
    assert first.get_json()["services"]["stripe"]["cache_state"] == "fresh"


def test_admin_overview_exposes_transparent_agent_revenue_table_data(v6_client):
    main, client = v6_client
    assert main.catalog_store.record_click("whaleflow-radar", event_id="transparent-hit")
    assert main.catalog_store.record_payment(
        "whaleflow-radar", 0.05, event_id="transparent-sale"
    )
    main._wallet_state.update(
        {
            "rpc_connected": True,
            "chain_id": 8453,
            "receiver_valid": True,
            "network": "Base Mainnet",
        }
    )

    overview = client.get(
        "/api/admin/overview", headers={"X-Admin-Token": "v6-admin-token"}
    )
    assert overview.status_code == 200
    payload = overview.get_json()
    whale = next(
        product
        for product in payload["agent_catalog"]["products"]
        if product["id"] == "whaleflow-radar"
    )
    assert len(payload["agent_catalog"]["products"]) == 8
    assert whale["hits_24h"] == 1
    assert whale["sales_24h"] == 1
    assert whale["revenue_24h"] == 0.05
    assert payload["services"]["blockchain"]["ready"] is True
    assert payload["services"]["blockchain"]["network"] == "Base Mainnet"


def test_paid_access_needs_checkout_capability_and_forwarded_ip_cannot_bypass(v6_client):
    main, client = v6_client
    remote = {"REMOTE_ADDR": "198.51.100.10"}

    first = client.post(
        "/api/v1/agents/whaleflow-radar/playground",
        json={"input": "ETH"},
        headers={"X-Forwarded-For": "203.0.113.1"},
        environ_base=remote,
    )
    assert first.status_code == 200
    spoofed_retry = client.post(
        "/api/v1/agents/whaleflow-radar/playground",
        json={"input": "ETH"},
        headers={"X-Forwarded-For": "203.0.113.99"},
        environ_base=remote,
    )
    assert spoofed_retry.status_code == 402

    assert main.catalog_store.grant_entitlement(
        "cs_secure_capability",
        "whaleflow-radar",
        "buyer@example.com",
    )
    raw_email = client.post(
        "/api/v1/agents/whaleflow-radar/access",
        json={"email": "buyer@example.com"},
    )
    assert raw_email.status_code == 400
    wrong_checkout = client.post(
        "/api/v1/agents/whaleflow-radar/access",
        json={"email": "buyer@example.com", "checkout_id": "guessed"},
    )
    assert wrong_checkout.status_code == 403
    credential = client.post(
        "/api/v1/agents/whaleflow-radar/access",
        json={"email": "buyer@example.com", "checkout_id": "cs_secure_capability"},
    )
    assert credential.status_code == 200
    token = credential.get_json()["access_token"]

    paid_retry = client.post(
        "/api/v1/agents/whaleflow-radar/playground",
        json={"input": "ETH"},
        headers={"Authorization": f"Bearer {token}"},
        environ_base=remote,
    )
    assert paid_retry.status_code == 200
    assert paid_retry.get_json()["access"] == "active_entitlement"


def test_free_demo_limit_survives_catalog_store_reinitialization(v6_client, tmp_path, monkeypatch):
    main, client = v6_client
    remote = {"REMOTE_ADDR": "198.51.100.42"}
    first = client.post(
        "/api/v1/agents/whaleflow-radar/playground",
        json={"input": "ETH"},
        environ_base=remote,
    )
    assert first.status_code == 200

    replacement = CatalogStore(tmp_path / "catalog.db")
    monkeypatch.setattr(main, "catalog_store", replacement)
    after_restart = client.post(
        "/api/v1/agents/whaleflow-radar/playground",
        json={"input": "ETH"},
        environ_base=remote,
    )
    assert after_restart.status_code == 402
    assert replacement.get_metrics_24h()["totals"]["calls"] == 1