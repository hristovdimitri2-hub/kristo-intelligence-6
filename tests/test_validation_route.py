# -*- coding: utf-8 -*-
"""GET /validation — public trust page: free, factual, HTML + JSON.

Pins the three facts the page states (uptime 23/23, $0.003 unchanged,
third-party audit of 2026-10-18: 20 transfers / 0.225 USDC exact match),
its free-entry status in the paywall allowlist, and the Accept-based
content negotiation. Also guards the tone: factual wording only.
"""
import pytest


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-admin-token")
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    import main
    main._free_tier_usage.clear()
    yield main.app.test_client()
    main._free_tier_usage.clear()


def test_validation_is_on_the_free_allowlist():
    import main
    assert "/validation" in main.X402_FREE_ENDPOINTS


def test_validation_html_states_the_facts(client):
    r = client.get("/validation")
    assert r.status_code == 200
    assert "text/html" in r.content_type
    html = r.get_data(as_text=True)
    for fact in (
        "23 of 23 days green",
        "$0.003 per call",
        "unchanged since launch",
        "Reddit, 2026-10-18",
        "20 transfers",
        "0.225 USDC",
        "exact match with our ledger",
        "https://x402.nsgoods.org/proof/payability-report-2026-10-18.json",
        'href="/openapi.json"',
        'href="/dashboard"',
    ):
        assert fact in html, f"missing fact: {fact}"


def test_validation_tone_is_factual(client):
    html = client.get("/validation").get_data(as_text=True).lower()
    for ad in ("world-class", "#1 ", "revolutionary", "best api",
               "unbeatable", "sign up now"):
        assert ad not in html, f"promotional wording: {ad}"


def test_validation_json_when_client_asks(client):
    r = client.get("/validation", headers={"Accept": "application/json"})
    assert r.status_code == 200
    assert "application/json" in r.content_type
    d = r.get_json()
    assert d["uptime"] == {"days_green": 23, "days_total": 23}
    assert d["price_usd_per_call"] == 0.003
    assert d["price_note"] == "unchanged since launch"
    audit = d["third_party_audit"]
    assert audit["transfers"] == 20
    assert audit["total_usdc"] == 0.225
    assert audit["date"] == "2026-10-18"
    assert audit["report"].startswith("https://x402.nsgoods.org/")
    assert d["links"]["documentation"] == "/openapi.json"
    assert d["links"]["payment_history"] == "/dashboard"
    assert d["status"] in ("operational", "degraded", "unknown")


def test_validation_stays_free_with_exhausted_tier(client):
    """The allowlist must beat the paywall: 200 even with a burnt-out tier."""
    import main
    main._free_tier_usage["127.0.0.1"] = 999
    try:
        r = client.get("/validation")
        assert r.status_code == 200
    finally:
        main._free_tier_usage.pop("127.0.0.1", None)