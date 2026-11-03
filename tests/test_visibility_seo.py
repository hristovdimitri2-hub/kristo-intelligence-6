"""VISIBILITY GUARDS — what a search engine and an AI crawler are actually told.

`sitemap.xml` is the one file a crawler trusts without checking anything. Before
this guard it listed /dashboard, /nexus and /agents — three URLs that all serve
the SAME noindex dashboard HTML (verified live: an identical 45,971-byte
response) — so it asked crawlers to index three duplicate pages that each answer
"do not index me". At the same time /validation, a real content page with an
8,670-byte body, was missing from the sitemap entirely.

Nothing asserted any of this before, which is exactly how those two opposite
problems survived side by side for so long.
"""
from __future__ import annotations

import re
import struct
from pathlib import Path

import pytest


README = Path(__file__).resolve().parent.parent / "README.md"


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("KRISTO_FREE_TIER_LIMIT", "0")
    import main
    from integrations.dashboard_store import DashboardStore

    monkeypatch.setattr(main, "FREE_TIER_LIMIT", 0, raising=False)
    monkeypatch.setattr(main, "dashboard_db",
                        DashboardStore(tmp_path / "dashboard_state.db"))
    return main.app.test_client(), main


#: Pages a crawler SHOULD index: distinct content, no noindex.
INDEXABLE = ("/", "/validation", "/launch")

#: URLs that must stay out of the sitemap: noindex, and duplicates of /dashboard.
NOT_INDEXABLE = ("/dashboard", "/nexus", "/agents")


def _sitemap(app_client):
    response = app_client.get("/sitemap.xml")
    assert response.status_code == 200, "/sitemap.xml -> %s" % response.status_code
    return response.get_data(as_text=True)


def _paths(xml):
    """Reduce sitemap <loc> values to the bare path a crawler would request."""
    return [re.sub(r"^https?://[^/]+", "", loc) or "/"
            for loc in re.findall(r"<loc>(.*?)</loc>", xml)]


def test_sitemap_lists_every_page_we_want_indexed(client):
    app_client, _main = client
    paths = _paths(_sitemap(app_client))
    missing = [path for path in INDEXABLE if path not in paths]
    assert not missing, "sitemap omits %s" % missing


def test_sitemap_omits_pages_that_refuse_to_be_indexed(client):
    app_client, _main = client
    paths = _paths(_sitemap(app_client))
    listed = [path for path in NOT_INDEXABLE if path in paths]
    assert not listed, (
        "sitemap asks crawlers to index %s, which serve noindex duplicate HTML"
        % listed)


def test_every_html_page_in_the_sitemap_is_reachable_and_indexable(client):
    app_client, _main = client
    for path in _paths(_sitemap(app_client)):
        response = app_client.get(path)
        assert response.status_code == 200, "%s -> %s" % (path, response.status_code)
        if "text/html" not in (response.headers.get("Content-Type") or ""):
            continue
        body = response.get_data(as_text=True).lower()
        assert "noindex" not in body, (
            "%s is listed in the sitemap but tells crawlers not to index it" % path)


def test_robots_txt_points_at_the_sitemap_and_blocks_only_the_admin_area(client):
    app_client, _main = client
    body = app_client.get("/robots.txt").get_data(as_text=True)
    assert "sitemap.xml" in body
    disallowed = re.findall(r"^Disallow:\s*(\S+)", body, re.M)
    assert disallowed == ["/api/admin/"], (
        "robots.txt disallows more than the admin area: %s" % disallowed)


def test_llms_txt_teaches_the_standard_x402_rail(client):
    """An agent that reads llms.txt must be able to pay the STANDARD way.

    The file used to document only the legacy X-Payment-Proof header: it never
    named PAYMENT-SIGNATURE, never named the canonical PAYMENT-REQUIRED response
    header, and promised "~2 seconds" confirmation for a rail that actually
    needs 12 confirmations (~24s). Every agent that trusted it built a slow
    legacy proof and waited the wrong amount of time - while the standard rail
    the whole x402 ecosystem speaks went unmentioned.
    """
    app_client, _main = client
    body = app_client.get("/llms.txt").get_data(as_text=True)
    for token in ("PAYMENT-SIGNATURE", "X-PAYMENT", "PAYMENT-REQUIRED",
                  "EIP-3009", "X-Payment-Proof"):
        assert token in body, "llms.txt never mentions %s" % token
    assert "12 confirmations" in body, (
        "llms.txt must state how long the legacy proof rail really takes")
    assert "~2 seconds" not in body, (
        "llms.txt still promises the old, wrong confirmation time")


def test_every_indexable_page_carries_social_and_canonical_metadata(client):
    """A shared link must render a card; a crawler must learn the canonical URL.

    Before this, all three indexable pages had NO og:image, NO twitter:card, NO
    canonical and NO JSON-LD, and two of them had no meta description at all.
    A link pasted anywhere showed a bare URL, and no rich result was possible.
    """
    app_client, _main = client
    for path in INDEXABLE:
        body = app_client.get(path).get_data(as_text=True)
        for tag in ('rel="canonical"', 'property="og:title"',
                    'property="og:description"', 'property="og:image"',
                    'name="twitter:card"', 'application/ld+json',
                    'name="description"'):
            assert tag in body, "%s is missing %s" % (path, tag)


def test_the_share_image_exists_and_is_the_shape_crawlers_expect(client):
    """og:image must point at a real 1200x630 file - never at a 404."""
    app_client, _main = client
    response = app_client.get("/static/og/kristo-og.png")
    assert response.status_code == 200, (
        "og:image target is missing: HTTP %s" % response.status_code)
    assert "image/png" in response.headers.get("Content-Type", "")
    raw = response.get_data()
    assert raw[:8] == b"\x89PNG\r\n\x1a\n", "the share image is not a PNG"
    width, height = struct.unpack(">II", raw[16:24])
    assert (width, height) == (1200, 630), \
        "share image is %dx%d, not 1200x630" % (width, height)


def test_indexnow_key_is_served_at_the_root(client):
    """IndexNow ownership proof: the file must be reachable and byte-exact.

    IndexNow is the only indexing channel that needs no account and no login, so
    it is the one we can open ourselves. It verifies ownership by fetching
    /<key>.txt and comparing it to the key we submit - if the file is missing or
    wrong, every submission is silently rejected with HTTP 403.
    """
    app_client, _main = client
    from app.blueprints.discovery import INDEXNOW_KEY

    assert len(INDEXNOW_KEY) >= 8, "an IndexNow key must be at least 8 characters"
    assert INDEXNOW_KEY.isalnum(), "an IndexNow key must be hex/alphanumeric"

    response = app_client.get("/%s.txt" % INDEXNOW_KEY)
    assert response.status_code == 200, (
        "the IndexNow key file is not served: HTTP %s" % response.status_code)
    assert response.get_data(as_text=True).strip() == INDEXNOW_KEY


def test_the_indexnow_route_does_not_shadow_the_other_root_files(client):
    """The key rule is a literal path, so robots.txt and sitemap.xml survive."""
    app_client, _main = client
    robots = app_client.get("/robots.txt")
    sitemap = app_client.get("/sitemap.xml")
    assert robots.status_code == 200
    assert sitemap.status_code == 200
    assert "Sitemap:" in robots.get_data(as_text=True)
    assert "<urlset" in sitemap.get_data(as_text=True)


def test_llms_txt_advertises_the_free_sample_of_every_paid_route(client):
    """A new agent must be able to see our response shape without paying first.

    All six paid routes have a free /sample twin, and all six are on the paywall
    allowlist - but before this, none of them were advertised anywhere. The first
    thing an agent could learn about our data was its price, which is the hardest
    possible way to be discovered.
    """
    app_client, main = client
    body = app_client.get("/llms.txt").get_data(as_text=True)
    for route in main.REAL_X402_ROUTES:
        endpoint = route["endpoint"]
        assert "%s/sample" % endpoint in body, (
            "llms.txt does not advertise the free sample for %s" % endpoint)


def test_readme_prices_match_the_live_price_map(client):
    """The storefront must not quote a price the 402 challenges do not demand.

    README.md now prints all six route prices. A number typed into a document is
    exactly how the old phantom "$0.05" survived four separate cleanups, so the
    table is checked against the single price source rather than trusted.
    """
    _app_client, main = client
    expected = {route["endpoint"]: round(float(route["price_usdc"]), 6)
                for route in main.REAL_X402_ROUTES}

    stated = {}
    for line in README.read_text(encoding="utf-8").splitlines():
        match = re.match(r"\|\s*`GET ([^`]+)`\s*\|\s*([0-9.]+)\s*\|", line)
        if match:
            stated[match.group(1)] = round(float(match.group(2)), 6)

    assert stated, "README.md no longer contains a price table"
    assert stated == expected, (
        "README prices drifted from the live price map:\n"
        "  README: %s\n  live  : %s"
        % (sorted(stated.items()), sorted(expected.items())))


def test_readme_advertises_the_free_sample_of_every_paid_route(client):
    """A reader of the storefront must learn they can try us for free."""
    _app_client, main = client
    text = README.read_text(encoding="utf-8")
    for route in main.REAL_X402_ROUTES:
        endpoint = route["endpoint"]
        assert "%s/sample" % endpoint in text, (
            "README.md does not advertise the free sample for %s" % endpoint)


def test_readme_does_not_quote_a_retired_phantom_price():
    """The exact strings that kept coming back must never return."""
    text = README.read_text(encoding="utf-8")
    for banned in (r"\$0\.05", r"\$0\.10", r"0\.05\s*USDC",
                   r"1 free call", r"first call is free"):
        assert not re.search(banned, text, re.I), (
            "README.md revived the phantom string %s" % banned)


# ── The machine-readable specs are how agents find us ───────────────────────
# A route missing from one of these does not exist for whatever reads it.
# /agents.json shipped with 5 of the 6 real routes and /mcp.json with 3 of 6, so
# /api/v1/whaleflow, /api/v1/signal and /api/arb/opportunities were invisible to
# every agent that trusted those two files. Nothing called these routes either,
# which is how /mcp.json kept a NameError (a missing import) that would have been
# a live 500 — the same failure "Audit #6 BREAK 2" recorded on /agents.json.

MACHINE_SPECS = (
    "/agents.json",
    "/.well-known/x402.json",
    "/.well-known/x402",
    "/api/mcp/manifest",
    "/mcp.json",
    "/openapi.json",
    "/.well-known/ai-plugin.json",
)


def test_every_machine_spec_answers_and_lists_every_paid_route(client):
    app_client, main = client
    for path in MACHINE_SPECS:
        response = app_client.get(path)
        assert response.status_code == 200, (
            "%s answered HTTP %s — a spec that 500s is a spec no agent reads"
            % (path, response.status_code))
        body = response.get_data(as_text=True)
        missing = [route["endpoint"] for route in main.REAL_X402_ROUTES
                   if route["endpoint"] not in body]
        assert not missing, (
            "%s does not mention %s" % (path, ", ".join(missing)))


def test_no_machine_spec_promises_a_free_call_we_cannot_give(client):
    """FREE_TIER_LIMIT is 0 in production, so a free call is a false promise."""
    app_client, _main = client
    for path in MACHINE_SPECS:
        body = app_client.get(path).get_data(as_text=True)
        for banned in (r"one free call", r"\b1 free call\b", r"first call is free",
                       r"unlimited monthly access", r"unlimited for \d+ days"):
            assert not re.search(banned, body, re.I), (
                "%s still promises %r" % (path, banned))


def test_no_machine_spec_sells_the_unimplemented_monthly_vip(client):
    """$29 buys a Telegram invite code, not API access — so it must not be
    advertised as a machine-purchasable tier that unlocks the API."""
    app_client, _main = client
    for path in MACHINE_SPECS:
        body = app_client.get(path).get_data(as_text=True)
        assert "monthly_vip_usdc" not in body, (
            "%s advertises a monthly_vip_usdc machine tier again" % path)

    manifest = app_client.get("/api/mcp/manifest").get_json()
    tiers = {tier["id"]: tier for tier in manifest["payment"]["tiers"]}
    assert tiers["vip_monthly"]["api_access_granted"] is False
    assert tiers["vip_monthly"]["unlimited_api_access"] is False
    assert tiers["vip_monthly"]["endpoints"] == []


def test_machine_specs_quote_the_real_prices(client):
    """A spec that quotes a flat fee for routes that differ is a spec that
    overcharges the reader."""
    app_client, main = client
    expected = {route["endpoint"]: float(route["price_usdc"])
                for route in main.REAL_X402_ROUTES}

    agents = app_client.get("/agents.json").get_json()
    for entry in agents["endpoints"]:
        assert float(entry["cost_usdc"]) == expected[entry["path"]], (
            "/agents.json quotes %s for %s" % (entry["cost_usdc"], entry["path"]))

    mcp = app_client.get("/mcp.json").get_json()
    for entry in mcp["tools"]:
        path = entry["endpoint"].split("onrender.com")[-1]
        if path in expected:
            assert float(entry["cost_usdc"]) == expected[path]

    # And every listed sample route must actually be free, or the "try before
    # you pay" invitation is a paid route wearing a free label.
    for endpoint in expected:
        assert app_client.get("%s/sample" % endpoint).status_code == 200


def test_validation_page_states_the_real_suite_size(client, request):
    """/validation exists to state facts a stranger can check.

    It advertised "550/550 tests green ... last run 2026-10-30" while the suite
    had grown past 568 — and the number was typed into the JSON facts block and
    the HTML panel separately, so the two could drift apart as well as go stale.
    Both now read one constant, and this fails if it falls behind the suite.
    """
    app_client, _main = client

    html = app_client.get("/validation").get_data(as_text=True)
    stated = re.search(r"(\d+)/(\d+) tests green", html)
    assert stated, "/validation no longer states a test count"
    passed, total = int(stated.group(1)), int(stated.group(2))
    assert passed == total, "/validation states %d/%d tests" % (passed, total)

    facts = app_client.get("/validation",
                           headers={"Accept": "application/json"}).get_json()
    suite = facts["test_suite"]
    assert (suite["passed"], suite["total"]) == (passed, total), (
        "the JSON facts and the HTML panel disagree: suite=%s says %s/%s, "
        "the page says %d/%d"
        % (suite["framework"], suite["passed"], suite["total"], passed, total))
    assert re.match(r"\d{4}-\d{2}-\d{2}$", suite["last_run"]), suite["last_run"]

    collected = request.session.testscollected
    assert passed >= collected, (
        "/validation advertises %d tests but this run collected %d — the page "
        "understates the suite" % (passed, collected))
    if collected >= 400:                      # only meaningful on a full run
        assert passed == collected, (
            "/validation advertises %d tests but the full suite collected %d; "
            "update SUITE_TESTS_PASSED in app/blueprints/discovery.py"
            % (passed, collected))


def test_readme_test_count_agrees_with_the_suite_and_with_validation(
        client, request):
    """Two public surfaces state the suite size, so they must state the same one.

    README.md advertised 561 while the suite had reached 569 — the very drift
    that had already been fixed once on /validation. A number a stranger can
    check is only worth publishing if something fails when it goes stale, so this
    checks all three against each other: the two README mentions, /validation,
    and the suite that actually ran.
    """
    app_client, _main = client
    text = README.read_text(encoding="utf-8")

    tree = re.search(r"# Test suite \((\d+) tests\)", text)
    bullet = re.search(r"\*\*(\d+) automated tests\*\*", text)
    assert tree and bullet, "README.md no longer states the suite size"
    assert tree.group(1) == bullet.group(1), (
        "README.md states two different counts: %s in the repository layout, "
        "%s in the verification list" % (tree.group(1), bullet.group(1)))

    stated = int(tree.group(1))
    facts = app_client.get("/validation",
                           headers={"Accept": "application/json"}).get_json()
    assert stated == facts["test_suite"]["passed"], (
        "README.md says %d tests while /validation says %d — two public "
        "surfaces disagree about the same checkable fact"
        % (stated, facts["test_suite"]["passed"]))

    collected = request.session.testscollected
    assert stated >= collected, (
        "README.md advertises %d tests but this run collected %d"
        % (stated, collected))
    if collected >= 400:
        assert stated == collected, (
            "README.md advertises %d tests but the full suite collected %d"
            % (stated, collected))


def test_launch_page_quotes_the_price_the_checkout_will_charge(client):
    """The landing page and the checkout must quote the same number.

    launch_landing.html hardcoded $29/$79/$149 while the checkout read
    PLAN_PRICES. Nobody would have noticed until a price changed, and then the
    buyer would have seen one figure and been charged another — the same drift
    class as the retired "$0.05", and the reason the number is no longer typed
    into the template at all.
    """
    app_client, _main = client
    from integrations.payment_integration import PLAN_PRICES

    body = app_client.get("/launch").get_data(as_text=True)
    for key, value in PLAN_PRICES.items():
        expected = "$%g" % float(value)
        assert expected in body, (
            "/launch does not show %s = %s from PLAN_PRICES" % (key, expected))

    template = (Path(__file__).resolve().parent.parent
                / "templates" / "launch_landing.html").read_text(
                    encoding="utf-8")
    assert not re.search(r"\$\d", template), (
        "launch_landing.html hardcodes a price again; it must be rendered from "
        "PLAN_PRICES")


def test_every_document_the_readme_points_at_exists():
    """A storefront that links to a missing file reads as abandoned."""
    text = README.read_text(encoding="utf-8")
    referenced = sorted(set(re.findall(r"`(docs/[A-Za-z0-9_./-]+\.md)`", text)))
    assert referenced, "README no longer points at any document"
    for relative in referenced:
        assert (README.parent / relative).is_file(), (
            "README points at %s, which does not exist" % relative)


def test_the_dated_buyer_audit_warns_that_its_numbers_are_superseded():
    """docs/MYSTERY_AGENT_REPORT.md is cited by the README as proof of rigour.

    Its body is a true record of 2026-08-29 — then /api/sales really did cost
    0.05, and standard x402 payloads really were not honoured. Left unmarked it
    reads as a current claim, and it is the worst possible one: it quotes a price
    10x too high AND tells a spec client it cannot pay us at all. The banner is
    what keeps the history honest without letting it mislead, so it must stay.
    """
    doc = (README.parent / "docs" / "MYSTERY_AGENT_REPORT.md").read_text(
        encoding="utf-8")

    assert "SUPERSEDED" in doc, (
        "the 2026-08-29 audit no longer warns that its figures are superseded")
    assert "0.005" in doc, (
        "the banner must state the current /api/sales price, not only the old one")
    assert "not yet honoured" in doc, (
        "the body should keep its historical claim — it is the record")
    assert doc.index("SUPERSEDED") < doc.index("50000"), (
        "the warning has to come before the superseded figure it corrects")


def test_every_free_sample_quotes_the_price_its_route_charges(client):
    """A sample's disclaimer is the first thing a prospective buyer reads.

    All six carried a typed "$0.005 USDC". When /api/v1/whaleflow moved to the
    $0.003 tier the other five were updated and that one was not — so the free
    sample we hand out to attract buyers overquoted the product by 67%, on a live
    route, with nothing failing. The disclaimer is generated from the price map
    now and this keeps it that way.
    """
    app_client, main = client

    for route in main.REAL_X402_ROUTES:
        endpoint = route["endpoint"]
        price = float(route["price_usdc"])
        body = app_client.get("%s/sample" % endpoint).get_json()
        match = re.search(r"\$([0-9.]+) USDC", body.get("disclaimer", ""))
        assert match, "%s/sample states no price at all" % endpoint
        assert abs(float(match.group(1)) - price) < 1e-9, (
            "%s/sample says $%s while the route charges $%s"
            % (endpoint, match.group(1), price))

    source = (Path(__file__).resolve().parent.parent
              / "app" / "blueprints" / "discovery.py").read_text(encoding="utf-8")
    assert not re.search(r'"disclaimer":\s*"Static[^"]*\$[0-9]', source), (
        "a sample disclaimer hardcodes a price again; it must call "
        "_sample_disclaimer()")


def test_landing_page_demos_the_fast_rail_before_the_slow_one(client):
    """The homepage shows "the exact x402 handshake an autonomous agent performs".

    It demonstrated only the legacy rail and captioned it "~2s" — while that rail
    waits 12 confirmations, about 24 seconds — and the stat card above the fold
    promised that same ~2s. A visitor read a latency the demonstrated path could
    not deliver, on the page with the most traffic we have.
    """
    app_client, _main = client
    html = app_client.get("/").get_data(as_text=True)

    assert "PAYMENT-SIGNATURE" in html, (
        "the homepage no longer shows the preferred x402 v2 rail")
    assert "X-Payment-Proof" in html, (
        "the legacy rail should stay named as the alternative")
    assert html.index("PAYMENT-SIGNATURE") < html.index("X-Payment-Proof"), (
        "the homepage still presents the 24-second legacy rail first")
    assert "12 confirmations" in html, (
        "the legacy rail's real cost must be stated, not left to the reader")


def test_the_vip_threshold_says_it_applies_to_one_payment(client):
    """"Payments >= $0.1 USDC" read as a running total; the code means one transfer.

    main.py:884 tests a single transfer's amount, and no route costs anywhere near
    $0.1 — the dearest is $0.005 — so as originally worded no ordinary customer
    could ever reach the invite it promised. Same family as the volume discount
    that could never trigger, and the "$29 unlocks the API" claim that was never
    true: a promise that is unreachable is a promise that is false.
    """
    app_client, main = client
    body = app_client.get("/api/mcp/manifest").get_data(as_text=True)
    match = re.search(r'"vip_threshold":"(.*?)"', body)
    assert match, "/api/mcp/manifest no longer states a VIP threshold"
    note = match.group(1)

    assert "single payment" in note.lower(), (
        "the threshold must say it applies to one transfer, not a cumulative total")

    dearest = max(float(route["price_usdc"]) for route in main.REAL_X402_ROUTES)
    assert "$%.3f" % dearest in note, (
        "the note should name the dearest route so the gap is visible")
    assert dearest < main.VIP_THRESHOLD_USDC, (
        "a route now costs as much as the VIP threshold — the note needs rewriting")
