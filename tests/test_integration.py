import pytest


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-admin-token")
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    monkeypatch.setenv("KRISTO_ALLOW_MOCK_PAYMENTS", "true")
    monkeypatch.delenv("APP_PUBLIC_URL", raising=False)
    monkeypatch.delenv("KRISTO_ENV", raising=False)
    monkeypatch.delenv("STRIPE_API_KEY", raising=False)
    monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
    import main
    from integrations.crm_store import CRMStore
    from integrations.stripe_checkout import StripeCheckoutService

    monkeypatch.setattr(main, "crm_store", CRMStore(tmp_path / "crm.db"))
    monkeypatch.setattr(main, "stripe_checkout", StripeCheckoutService())
    return main.app.test_client()


def test_health_endpoint(client):
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["status"] == "ok"
    assert payload["database"]["backend"] == "sqlite"
    assert payload["database"]["ready"] is True
    assert payload["database"]["audit_backend"] in {"postgresql", "unavailable"}
    assert isinstance(payload["database"]["audit_ready"], bool)
    assert payload["blockchain"]["network"] == "Base Mainnet"
    assert payload["blockchain"]["chain_id"] == 8453
    assert "ready" in payload["blockchain"]


def test_public_dashboard_stats_are_free_and_use_official_catalog(client):
    response = client.get("/api/dashboard-stats")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["products_summary"]["total_products"] == 8
    assert len(payload["products"]) == 8
    assert "recent_requests" not in payload
    assert all(0.01 <= product["price_usdc"] <= 0.25 for product in payload["products"])
    assert payload["total_volume_usd"] == 0.0
    assert payload["total_sales"] == 0
    assert "telegram_bot_running" in payload


def test_lead_capture_and_checkout(client):
    lead = client.post(
        "/api/leads",
        json={
            "email": "integration@example.com",
            "source": "test",
            "campaign": "integration",
        },
    )
    assert lead.status_code == 200
    assert lead.get_json()["ok"] is True

    checkout = client.post(
        "/api/checkout",
        json={"email": "integration@example.com", "plan": "pro"},
    )
    assert checkout.status_code == 200
    payload = checkout.get_json()
    assert payload["ok"] is True
    assert payload["plan"] == "Pro"
    assert payload["payment_session"]["provider"] in {"mock", "mock_fallback", "stripe"}