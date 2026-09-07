"""Catalog cleanup (07.09): the 8 demo SKUs are unlisted from public surfaces.

Guards:
  * discovery (/.well-known/x402.json) = exactly the 5 REAL routes
  * /api/v1/agents = the same 5, zero SKU names
  * /agents page redirects to /dashboard (no demo storefront)
  * /api/dashboard-stats products = real routes, no SKU name leaks
  * /api/mcp/manifest never contained SKUs — stays clean
  * the demo playground door still WORKS in code (unadvertised, by design)
"""

import pytest

SKU_FRAGMENTS = (
    "whaleflow", "WhaleFlow", "gas-route", "sentiment-narrative",
    "rug-risk-scanner", "security-triage", "channel-publisher",
    "Divergence", "yield-risk",
)

REAL_ENDPOINTS = {
    "/api/v1/signal", "/api/stats", "/api/arb/opportunities",
    "/api/bot-status", "/api/sales",
}


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-admin-token")
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    import main
    from integrations.catalog_store import create_catalog_store
    from integrations.dashboard_store import DashboardStore

    monkeypatch.setattr(main, "catalog_store", create_catalog_store(tmp_path / "catalog.db"))
    monkeypatch.setattr(main, "dashboard_db", DashboardStore(tmp_path / "dash.db"))
    return main.app.test_client()


def _assert_no_sku_leak(blob: str, where: str) -> None:
    for fragment in SKU_FRAGMENTS:
        assert fragment not in blob, f"demo SKU '{fragment}' leaked in {where}"


def test_discovery_lists_exactly_the_five_real_routes(client):
    resp = client.get("/.well-known/x402.json")
    assert resp.status_code == 200
    payload = resp.get_json()
    agents = payload["agents"]
    assert len(agents) == 5
    assert {a["endpoint"] for a in agents} == REAL_ENDPOINTS
    assert all(a["method"] == "GET" for a in agents)
    _assert_no_sku_leak(resp.get_data(as_text=True), "x402.json")


def test_agents_catalog_json_lists_real_routes_only(client):
    resp = client.get("/api/v1/agents")
    assert resp.status_code == 200
    agents = resp.get_json()["agents"]
    assert {a["endpoint"] for a in agents} == REAL_ENDPOINTS
    _assert_no_sku_leak(resp.get_data(as_text=True), "/api/v1/agents")


def test_agents_page_redirects_to_dashboard(client):
    resp = client.get("/agents")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/dashboard")
    _assert_no_sku_leak(resp.get_data(as_text=True), "/agents")


def test_dashboard_stats_have_no_sku_leak(client):
    resp = client.get("/api/dashboard-stats")
    assert resp.status_code == 200
    payload = resp.get_json()
    assert {p["endpoint"] for p in payload["products"]} == REAL_ENDPOINTS
    _assert_no_sku_leak(resp.get_data(as_text=True), "/api/dashboard-stats")


def test_mcp_manifest_stays_sku_free(client):
    resp = client.get("/api/mcp/manifest")
    assert resp.status_code == 200
    _assert_no_sku_leak(resp.get_data(as_text=True), "/api/mcp/manifest")


def test_dashboard_page_shows_real_routes_section(client):
    resp = client.get("/dashboard")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "Реални маршрути" in html
    for endpoint in REAL_ENDPOINTS:
        assert endpoint in html, f"missing real route {endpoint} on dashboard"
    _assert_no_sku_leak(html, "/dashboard")


def test_demo_door_still_functional_but_unadvertised(client):
    """The demo adapter stays in code (item 4 of the cleanup) — it must still
    run, but must not be reachable from any listing surface."""
    demo = client.post(
        "/api/v1/agents/whaleflow-radar/playground",
        json={"input": "ETH"},
        environ_base={"REMOTE_ADDR": "198.51.100.77"},
    )
    assert demo.status_code == 200
    assert demo.get_json()["result"]["mode"] == "playground_demo"
