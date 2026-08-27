from datetime import datetime, timedelta, timezone

import pytest

from integrations.catalog_store import CatalogStore


def test_catalog_store_seeds_eight_agents_and_calculates_24h_metrics(tmp_path):
    store = CatalogStore(tmp_path / "catalog.db")
    products = store.get_catalog()

    assert len(products) == 8
    assert {
        "whaleflow-radar",
        "cross-venue-signal-divergence",
        "token-launch-rug-risk-scanner",
        "defi-yield-risk-optimizer",
        "gas-route-optimizer",
        "ai-sentiment-narrative-pulse",
        "smart-contract-security-triage",
        "signal-to-channel-publisher",
    } == {product["id"] for product in products}
    assert all(0.001 <= product["price_x402"] <= 0.25 for product in products)
    assert all(
        {
            "id",
            "name",
            "description",
            "category",
            "price_x402",
            "price_stripe",
            "click_count",
            "call_count",
            "total_revenue",
            "is_active",
            "last_updated",
        }.issubset(product)
        for product in products
    )

    assert store.record_click("whaleflow-radar", event_id="click-1") is True
    assert store.record_click("whaleflow-radar", event_id="click-1") is False
    assert store.record_call("whaleflow-radar", event_id="call-1") is True
    assert store.record_payment("whaleflow-radar", 19.0, event_id="payment-1") is True
    assert store.record_payment("whaleflow-radar", 19.0, event_id="payment-1") is False

    payload = store.get_metrics_24h()
    whale = next(product for product in payload["products"] if product["id"] == "whaleflow-radar")

    assert whale["clicks_24h"] == 1
    assert whale["calls_24h"] == 1
    assert whale["hits_24h"] == 2
    assert whale["payments_24h"] == 1
    assert whale["sales_24h"] == 1
    assert whale["revenue_24h"] == 19.0
    assert whale["conversion_rate_24h"] == 100.0
    assert whale["popularity_rank"] == 1
    assert payload["top_selling_agent"]["id"] == "whaleflow-radar"

    reference = datetime(2026, 8, 20, tzinfo=timezone.utc)
    entitlement = store.grant_entitlement(
        "cs_entitlement_1",
        "whaleflow-radar",
        "buyer@example.com",
        now=reference,
    )
    assert entitlement["status"] == "active"
    assert store.get_active_entitlement("whaleflow-radar", "buyer@example.com")
    assert (
        store.get_active_entitlement(
            "whaleflow-radar",
            "buyer@example.com",
            now=reference + timedelta(days=31),
        )
        is None
    )


@pytest.fixture()
def catalog_client(monkeypatch, tmp_path):
    monkeypatch.setenv("ADMIN_API_TOKEN", "catalog-admin-token")
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    import main
    from integrations.crm_store import CRMStore

    monkeypatch.setattr(main, "catalog_store", CatalogStore(tmp_path / "catalog.db"))
    monkeypatch.setattr(main, "crm_store", CRMStore(tmp_path / "crm.db"))
    return main, main.app.test_client()


def test_click_endpoint_and_admin_catalog_metrics(catalog_client):
    _, client = catalog_client

    click = client.post(
        "/api/v1/agents/whaleflow-radar/click",
        headers={"X-Event-Id": "catalog-click-1"},
    )
    assert click.status_code == 202
    assert click.get_json()["status"] == "click_recorded"

    duplicate = client.post("/api/v1/agents/whaleflow-radar/click")
    assert duplicate.status_code == 429
    assert duplicate.get_json()["error"] == "click_rate_limited"

    assert client.post("/api/v1/agents/not-real/click").status_code == 404
    catalog = client.get("/api/v1/agents")
    assert catalog.status_code == 200
    assert len(catalog.get_json()["agents"]) == 8

    metrics = client.get(
        "/api/admin/catalog-metrics",
        headers={"X-Admin-Token": "catalog-admin-token"},
    )
    assert metrics.status_code == 200
    payload = metrics.get_json()
    assert len(payload["products"]) == 8
    whale = next(product for product in payload["products"] if product["id"] == "whaleflow-radar")
    assert whale["clicks_24h"] == 1


def test_verified_stripe_webhook_attributes_catalog_revenue(catalog_client, monkeypatch):
    main, client = catalog_client
    main.crm_store.add_lead(
        main.LeadRecord(
            email="buyer@example.com",
            source="catalog",
            campaign="agent_vip",
            plan="agent:whaleflow-radar",
        )
    )
    assert main.catalog_store.register_checkout(
        checkout_id="cs_catalog_payment_1",
        product_id="whaleflow-radar",
        customer_email="buyer@example.com",
        expected_amount=19.0,
    )
    monkeypatch.setattr(
        main.stripe_checkout,
        "verify_webhook",
        lambda _payload, _signature: {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_catalog_payment_1",
                    "customer_email": "buyer@example.com",
                    "amount_total": 1900,
                    "currency": "usd",
                    "payment_status": "paid",
                    "metadata": {
                        "plan": "agent:whaleflow-radar",
                        "agent_sku": "whaleflow-radar",
                    },
                }
            },
        },
    )
    monkeypatch.setattr(
        main,
        "_activate_stripe_vip_access",
        lambda *_args: pytest.fail("Agent purchases must not grant generic VIP access"),
    )

    response = client.post(
        "/api/webhooks/stripe",
        data=b"verified-payload",
        headers={"Stripe-Signature": "verified-signature"},
    )

    assert response.status_code == 200
    assert response.get_json()["vip_access"] == "agent_entitlement_active"
    metrics = main.catalog_store.get_metrics_24h()
    whale = next(product for product in metrics["products"] if product["id"] == "whaleflow-radar")
    assert whale["payments_24h"] == 1
    assert whale["revenue_24h"] == 19.0
    access = client.post(
        "/api/v1/agents/whaleflow-radar/access",
        json={
            "email": "buyer@example.com",
            "checkout_id": "cs_catalog_payment_1",
        },
    )
    assert access.status_code == 200
    assert access.get_json()["access"] == "active"
    assert access.get_json()["access_token"].startswith("ki1.")

    duplicate = client.post(
        "/api/webhooks/stripe",
        data=b"verified-payload",
        headers={"Stripe-Signature": "verified-signature"},
    )
    assert duplicate.status_code == 200
    assert main.catalog_store.get_metrics_24h()["totals"]["payments"] == 1


def test_catalog_webhook_rejects_unregistered_or_unsettled_checkout(
    catalog_client, monkeypatch
):
    main, client = catalog_client
    main.crm_store.add_lead(
        main.LeadRecord(
            email="buyer@example.com",
            source="catalog",
            campaign="agent_vip",
            plan="agent:whaleflow-radar",
        )
    )
    monkeypatch.setattr(
        main.stripe_checkout,
        "verify_webhook",
        lambda _payload, _signature: {
            "type": "checkout.session.completed",
            "data": {
                "object": {
                    "id": "cs_unregistered_catalog_payment",
                    "customer_email": "buyer@example.com",
                    "amount_total": 1900,
                    "currency": "usd",
                    "payment_status": "paid",
                    "metadata": {
                        "plan": "agent:whaleflow-radar",
                        "agent_sku": "whaleflow-radar",
                    },
                }
            },
        },
    )

    response = client.post(
        "/api/webhooks/stripe",
        data=b"verified-payload",
        headers={"Stripe-Signature": "verified-signature"},
    )

    assert response.status_code == 200
    assert response.get_json()["status"] == "ignored_unmatched_catalog_checkout"
    assert main.crm_store.find_by_email("buyer@example.com")["payment_status"] == "pending"
    metrics = main.catalog_store.get_metrics_24h()
    whale = next(product for product in metrics["products"] if product["id"] == "whaleflow-radar")
    assert whale["payments_24h"] == 0