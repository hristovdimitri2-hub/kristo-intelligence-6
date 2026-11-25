# -*- coding: utf-8 -*-
"""GET /validation — public trust page: free, factual, HTML + JSON.

Pins the facts the page states ($0.003-$0.005 range, third-party audit of
2026-10-18: 20 transfers / 0.225 USDC exact match), the invariants of the dated
figures it repeats from others (uptime window, x402-trust grades), its free-entry
status in the paywall allowlist, and the Accept-based content negotiation. Also
guards the tone: factual wording only.

The figures dated in the past are checked for shape and provenance, not for value:
freezing today's number is what let this file assert "grade B" for /api/stats long
after the source had moved to "A", and "23 of 23 days green" while the page had
stopped saying when those 23 days ended.
"""
import re

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
    # The price facts are derived, not typed: the page must span the real range
    # rather than quote the cheapest route alone.
    import main
    _prices = sorted(float(route["price_usdc"]) for route in main.REAL_X402_ROUTES)

    for fact in (
        "$%.3f" % _prices[0],
        "$%.3f" % _prices[-1],
        "Reddit, 2026-10-18",
        "20 transfers",
        "0.225 USDC",
        "exact match with our ledger",
        "https://x402.nsgoods.org/proof/payability-report-2026-10-18.json",
        'href="/openapi.json"',
        'href="/dashboard"',
    ):
        assert fact in html, f"missing fact: {fact}"


def test_the_uptime_line_is_rendered_from_the_dated_measurement(client,
                                                               monkeypatch):
    """Move the data and check the HTML follows — not that a number matches.

    The page used to type "23 of 23 days green" into its HTML while the JSON facts
    carried their own copy, and the number never said when those 23 days ended. The
    first version of this test only asserted the two agreed, which proved nothing:
    both said 23, so a hand-typed literal would have passed it exactly as the
    derived one did. Typing the literal back is what the mutation check caught.

    Patching the constants is what makes the claim testable. If the HTML follows
    them to an unlikely pair, it is reading the data; if it does not, the guard
    fails with the values it actually rendered.
    """
    from app.blueprints import discovery

    monkeypatch.setattr(discovery, "UPTIME_DAYS_GREEN", 17)
    monkeypatch.setattr(discovery, "UPTIME_DAYS_TOTAL", 19)
    monkeypatch.setattr(discovery, "UPTIME_MEASURED_TO", "1999-01-02")

    json_facts = client.get(
        "/validation", headers={"Accept": "application/json"}).get_json()
    assert json_facts["uptime"] == {
        "days_green": 17, "days_total": 19, "measured_to": "1999-01-02"}

    html = client.get("/validation").get_data(as_text=True)
    flat = " ".join(html.split())
    assert "17 of 19 days" in flat, (
        "the HTML uptime line does not follow the data it is supposed to render: "
        "it should read '17 of 19 days' but the page says something else")
    assert "1999-01-02" in flat, (
        "the uptime window must print the date it was measured to, from the data")


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
    # The uptime figure is a dated measurement, so assert its invariants and that
    # it carries the date it was taken, rather than freezing today's numbers: a
    # frozen number is exactly what let the trust grades below read "B" for five
    # of six routes while the source had moved on to "A".
    uptime = d["uptime"]
    assert 0 <= uptime["days_green"] <= uptime["days_total"]
    assert re.match(r"^\d{4}-\d{2}-\d{2}$", uptime["measured_to"]), (
        "the uptime window must state the date it was measured to")
    # This assertion used to read `d["price_usd_per_call"] == 0.003` — the test
    # was written to match the code, and the code quoted the cheapest route while
    # four of six charge $0.005. Checked against the route table now.
    import main
    _prices = [float(route["price_usdc"]) for route in main.REAL_X402_ROUTES]
    assert d["price_usd_per_call_min"] == min(_prices)
    assert d["price_usd_per_call_max"] == max(_prices)
    assert "unchanged since launch" not in d["price_note"], (
        "these prices have changed; the page must not claim otherwise")
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
    """Profile, live badge, claim status, their published model — no typed grades.

    This test used to require the four-part model "technical fit / transparency /
    ecosystem presence / operational confidence" in the HTML. That model appears
    nowhere on x402-trust.com; we had been describing a third party's scoring
    wrongly, on our own trust page, and pinning it in a test made it permanent.
    The published model is the three-component one asserted below.
    """
    html = client.get("/validation").get_data(as_text=True)
    flat = " ".join(html.split())
    assert 'href="https://x402-trust.com/endpoint/139372"' in html
    assert 'href="https://x402-trust.com/trust/search?q=kristo"' in html
    assert "badge.svg?resource=" in html          # badge image, served live
    assert "4/4 complete" in html                # claim status
    assert "24 hours" in html                    # cache cadence
    assert "https://x402-trust.com/trust/leaderboard" in html  # weights link
    # ...and the route to the live grades, plus the manage page for the claim.
    assert "/trust/search?q=kristo" in flat
    assert "/verify/kristo-intelligence-api.onrender.com" in flat

    # Their published model, with the weights they publish.
    assert ("0.45 × technical reliability + 0.30 × spec compliance "
            "+ 0.25 × economic reputation") in flat
    assert "0.40 × observed age" in flat and "0.15 × latency" in flat

    # The invented model must not come back, and neither must a typed copy of
    # somebody else's moving measurement: the per-endpoint grade list went stale
    # saying "grade A" on six routes while every live grade was B.
    for invented in ("technical fit", "ecosystem presence",
                     "operational confidence"):
        assert invented not in flat, invented
    for typed_grade in ("grade A", "grade B", "grade C"):
        assert typed_grade not in flat, (
            "the page types one of x402 Trust's grades (%s); it is served live "
            "by them and cannot be kept current here" % typed_grade)

    # The badge image is live, but its alt text is static - so the alt must not
    # name a grade. It said "grade B" while the profile it links to said "A",
    # which is a stale claim in the one place a screen reader and an LLM read.
    trusted = client.get(
        "/validation", headers={"Accept": "application/json"}).get_json()
    alt = trusted["x402_trust"]["badge"]
    assert "alt=" in alt
    for grade in ('"A"', '"B"', '"C"', "grade A", "grade B", "grade C"):
        assert grade not in alt, (
            "the badge alt text pins a grade (%s); it is served live and the alt "
            "cannot be kept current: %s" % (grade, alt))
    assert "recommendation proceed" not in alt, (
        "the alt also pinned a recommendation, and their live recommendation for "
        "this endpoint is avoid: %s" % alt)

    # всеки основен платен endpoint има Trust страница
    assert "/endpoint/139372" in html
    # ...но не и остарялата единна цена: страницата трябва да покрива диапазона
    # The page quotes the CATALOGUE's range, because the catalogue is what it
    # lists. Reading the whole price map here would demand a price on the page
    # for a route the page does not list — the demand census is paid and priced
    # but paywall-only as of 24.11.2026, and `_cheapest_route_price` /
    # `_dearest_route_price` have always been computed over REAL_X402_ROUTES.
    import main as _m
    _prices = [float(route["price_usdc"]) for route in _m.REAL_X402_ROUTES]
    floor = "$%.3f" % min(_prices)
    ceiling = "$%.3f" % max(_prices)
    assert floor in html and ceiling in html
    assert "$0.003 per call" not in html


def test_validation_json_carries_x402_trust_block(client):
    r = client.get("/validation", headers={"Accept": "application/json"})
    d = r.get_json()
    trust = d["x402_trust"]
    assert trust["profile"].endswith("/endpoint/139372")
    assert "4/4" in trust["claim"]
    assert trust["grades_live_at"].endswith("/trust/search?q=kristo")
    assert trust["manage"].endswith(
        "/verify/kristo-intelligence-api.onrender.com")
    assert "0.45" in trust["scoring_note"] and "0.30" in trust["scoring_note"]
    assert "0.40 × observed age" in trust["scoring_note"]
    assert "technical fit" not in trust["scoring_note"], (
        "the scoring note describes a model x402-trust.com does not publish")

    # These are somebody else's measurements, recomputed by them daily. The copy
    # of them that used to live here advertised grade A on six routes long after
    # every live grade had moved to B — a stale claim, on a trust page, in the
    # direction that flattered us. The field it lived in is gone, and so is the
    # date stamp that made a lagging copy look deliberate. If either returns, the
    # copy returns with it.
    assert "paid_endpoints" not in trust, (
        "a typed copy of x402 Trust's per-endpoint grades is back in /validation")
    assert "last_checked" not in trust, (
        "a dated copy of x402 Trust's grades is back in /validation")

    # Every route the price table advertises must be one we really sell, and the
    # table must cover all of them — this is the check that would have caught the
    # "six routes" prose and the route that was missing from the old grade list.
    import main
    real = {route["endpoint"] for route in main.REAL_X402_ROUTES}
    assert {e["path"] for e in d["endpoints"]} == real

    # Only the weights they actually publish may appear as percentages.
    raw = r.get_data(as_text=True)
    assert "45%" not in raw and "30%" not in raw and "25%" not in raw, (
        "percentages are not how x402-trust publishes its weights; use the "
        "coefficients as written")


def test_validation_dates_its_so_called_recent_payments(client):
    """The list is called "recent", so the page must say how recent.

    On 2026-11-03 the newest row was 4.7 days old. A settlement list that has
    stopped moving reads as a dead product, and that reading is fair — but the
    page should state where the list ends instead of letting a buyer assume the
    silence means activity.
    """
    facts = client.get("/validation",
                       headers={"Accept": "application/json"}).get_json()
    payments = facts["recent_payments"]
    assert payments, "the page no longer lists any settlement"
    assert facts["payments_count"] == len(payments)
    assert facts["payments_as_of"] == max(p["settled_at"] for p in payments), (
        "payments_as_of must be the newest date actually listed")