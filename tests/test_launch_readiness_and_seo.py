import pytest

from integrations.catalog_store import CatalogStore
from integrations.crm_store import CRMStore
from integrations.marketplace_store import MarketplaceGovernanceStore
from integrations.stripe_checkout import StripeCheckoutService


@pytest.fixture()
def launch_client(monkeypatch, tmp_path):
    monkeypatch.setenv("ADMIN_API_TOKEN", "launch-admin-token")
    monkeypatch.setenv("SESSION_SECRET", "launch-session-secret")
    monkeypatch.setenv("RESEARCH_INGEST_TOKEN", "launch-research-token")
    monkeypatch.setenv("AGENT_ACCESS_TOKEN_SECRET", "launch-agent-token-secret")
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("APP_PUBLIC_URL", raising=False)
    monkeypatch.delenv("TELEGRAM_VIP_CHAT_ID", raising=False)
    monkeypatch.delenv("KRISTO_ALLOW_MOCK_PAYMENTS", raising=False)
    import main

    monkeypatch.setattr(main, "catalog_store", CatalogStore(tmp_path / "catalog.db"))
    monkeypatch.setattr(main, "crm_store", CRMStore(tmp_path / "crm.db"))
    governance = MarketplaceGovernanceStore(tmp_path / "marketplace.db")
    governance.ensure_active_contract(
        main.AGENT_CONTRACT_VERSION, main.catalog_manifest(main.catalog_store.get_catalog())
    )
    monkeypatch.setattr(main, "marketplace_store", governance)
    return main, main.app.test_client()


def test_launch_health_is_strictly_blocked_until_production_gates_are_verified(launch_client):
    _, client = launch_client

    response = client.get("/api/launch/health")

    assert response.status_code == 503
    payload = response.get_json()
    assert payload["ok"] is False
    assert payload["status"] == "launch_blocked"
    assert payload["readiness"]["ready"] is False
    assert payload["readiness"]["checks"]["crm_persistence"]["ready"] is False
    assert payload["readiness"]["checks"]["external_smoke_tests"]["ready"] is False


def test_public_seo_entry_points_are_available_and_do_not_index_admin(launch_client):
    _, client = launch_client

    home = client.get("/")
    agents = client.get("/agents")
    robots = client.get("/robots.txt")
    sitemap = client.get("/sitemap.xml")

    assert home.status_code == 200
    assert b"public sale" not in home.data.lower()
    assert b"/sales/checkout?plan=pro" not in home.data
    assert b"rel=\"canonical\"" in home.data
    assert agents.status_code == 200
    assert b'rel="canonical"' in agents.data
    assert robots.status_code == 200
    assert b"Disallow: /sales/admin" in robots.data
    assert sitemap.status_code == 200
    assert b"/agents" in sitemap.data
    assert b"/sales/admin" not in sitemap.data


def test_runtime_discovery_documents_launch_readiness(launch_client):
    _, client = launch_client

    openapi = client.get("/openapi.json")
    llms = client.get("/llms.txt")

    assert openapi.status_code == 200
    assert "/api/launch/health" in openapi.get_json()["paths"]
    assert llms.status_code == 200
    assert b"/api/launch/health" in llms.data


def test_mock_checkout_is_rejected_for_a_browser_reachable_environment(monkeypatch):
    monkeypatch.setenv("KRISTO_ALLOW_MOCK_PAYMENTS", "true")
    monkeypatch.setenv("APP_PUBLIC_URL", "https://app.example.com")
    monkeypatch.delenv("STRIPE_API_KEY", raising=False)
    monkeypatch.delenv("KRISTO_ENV", raising=False)

    checkout = StripeCheckoutService().create_checkout_session(
        "pro", "buyer@example.com"
    )

    assert checkout["status"] == "checkout_error"
    assert checkout["error"] == "stripe_not_configured"