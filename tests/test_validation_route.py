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


def test_validation_html_carries_x402_trust_section(client):
    """Trust profile, badge, claim4/4, scoring note, endpoint pages, date."""
    html = client.get("/validation").get_data(as_text=True)
    assert 'href="https://x402-trust.com/endpoint/139372"' in html
    assert 'href="https://x402-trust.com/trust/search?q=kristo"' in html
    assert "badge.svg?resource=" in html          # badge image
    assert "4/4 complete" in html                # claim status
    assert "24 hours" in html                    # cache cadence
    assert "technical fit" in html               # scoring explained
    assert "https://x402-trust.com/trust/leaderboard" in html  # weights link
    assert "Last checked" in html and "2026-10-19" in html
    # всеки основен платен endpoint има Trust страница
    for ep_id in (122932, 139367, 139372, 139339, 139342, 139366):
        assert f"/endpoint/{ep_id}" in html, ep_id
    # старите фактове оцеляват
    assert "23 of 23 days green" in html
    assert "$0.003 per call" in html


def test_validation_json_carries_x402_trust_block(client):
    r = client.get("/validation", headers={"Accept": "application/json"})
    d = r.get_json()
    trust = d["x402_trust"]
    assert trust["profile"].endswith("/endpoint/139372")
    assert trust["last_checked"] == "2026-10-19"
    assert "4/4" in trust["claim"]
    assert len(trust["paid_endpoints"]) == 6
    grades = {e["path"]: e["grade"] for e in trust["paid_endpoints"]}
    assert grades["/api/v1/signal"] == "A"
    assert grades["/api/stats"] == "B"
    # непроверени числа (weights%) не бива да присъстват
    raw = r.get_data(as_text=True)
    assert "30%" not in raw and "20%" not in raw