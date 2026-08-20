import json

import pytest


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-admin-token")
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    import main
    from integrations.crm_store import CRMStore

    monkeypatch.setattr(main, "crm_store", CRMStore(tmp_path / "crm.db"))
    main._free_tier_usage.clear()
    return main.app.test_client()


def test_admin_routes_require_token(client):
    assert client.get("/api/admin/leads").status_code == 401
    sales_dashboard = client.get("/sales/admin")
    assert sales_dashboard.status_code == 302
    assert sales_dashboard.headers["Location"].endswith("/sales/admin/login")
    invalid_header_dashboard = client.get(
        "/sales/admin",
        headers={"X-Admin-Token": "stale-or-invalid-token"},
    )
    assert invalid_header_dashboard.status_code == 302
    assert invalid_header_dashboard.headers["Location"].endswith("/sales/admin/login")
    assert client.get("/api/sales/summary").status_code == 401


def test_admin_routes_accept_server_token(client):
    response = client.get(
        "/api/admin/leads",
        headers={"X-Admin-Token": "test-admin-token"},
    )
    assert response.status_code == 200
    assert response.get_json()["ok"] is True


def test_browser_admin_login_trims_configured_and_supplied_token(client, monkeypatch):
    monkeypatch.setenv("ADMIN_API_TOKEN", "  test-admin-token  ")

    response = client.post(
        "/sales/admin/login",
        data={"admin_token": "  test-admin-token  "},
    )

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/sales/admin")


def test_invalid_browser_admin_login_logs_metadata_without_token(caplog, client):
    import main

    caplog.set_level("WARNING", logger="kristo.v5.main")
    response = client.post(
        "/sales/admin/login",
        data={"admin_token": "wrong-token-value"},
    )

    assert response.status_code == 200
    assert "Невалиден admin token." in response.get_data(as_text=True)
    assert "Admin token mismatch" in caplog.text
    assert "configured_length=" in caplog.text
    assert "supplied_length=" in caplog.text
    assert "test-admin-token" not in caplog.text
    assert "wrong-token-value" not in caplog.text


def test_stripe_webhook_requires_signature(client):
    response = client.post(
        "/api/webhooks/stripe",
        data=json.dumps({"type": "checkout.session.completed"}),
        content_type="application/json",
    )
    assert response.status_code == 400
    assert response.get_json()["error"] == "missing_signature"


def test_referer_cannot_bypass_x402(client, monkeypatch):
    import main

    monkeypatch.setitem(main._free_tier_usage, "127.0.0.1", 1)
    response = client.get(
        "/api/stats",
        headers={"Referer": "http://localhost:5000/dashboard"},
    )
    assert response.status_code == 402