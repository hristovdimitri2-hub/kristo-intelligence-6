import pytest


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-admin-token")
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    monkeypatch.setenv("KRISTO_ALLOW_MOCK_PAYMENTS", "true")
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
    assert response.get_json() == {
        "status": "ok",
        "database": {"backend": "sqlite", "ready": True},
    }


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