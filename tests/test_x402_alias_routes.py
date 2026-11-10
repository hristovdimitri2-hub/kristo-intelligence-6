# -*- coding: utf-8 -*-
"""The buyer-worded alias routes — five claims, each of them checked.

WHY THIS FILE EXISTS. The CDP catalogue's search ranks on the words a resource
PUBLISHES. When the aliases were added the premise was written down as "the words
in a resource URL"; that premise was measured on 10.11.2026 and is wrong. CDP does
not read the URL at all: the query "verify seller" misses /api/v1/verify-seller —
a literal substring of that path — while /api/v1/seller-check, the same handler at
the same price, ranks #2 of 17, and the only difference between those two rows is
their `tags` and their description. Every row that wins a query contains the
buyer's words verbatim in one of those two fields.

The original problem was real (we ranked first for our own name and host and were
absent for every word a buyer types); only the mechanism was mis-stated. The
aliases were the first fix — they are the rows that carry buyer-worded tags and
descriptions. The second fix, asserted below, gives the canonical routes their own
tags too, because until 10.11.2026 all seven of them published the same five
generic words, none of which was the job any of them does.

An alias is only legitimate if it is the SAME product: same price, same receiver,
same handler, same output example — under a name a buyer can find. Every one of
those is asserted here rather than assumed, and the deliberate omissions
(/api/stats and /api/bot-status, whose responses do not earn the names buyers
search for) are asserted too, so a later edit has to argue with a test to add
them back.
"""
import pytest

ALIASES = {
    "/api/v1/whale-alerts": ("/api/v1/whaleflow", "whale alerts"),
    "/api/v1/trading-signals": ("/api/v1/signal", "trading signals"),
    "/api/v1/arbitrage-opportunities": ("/api/arb/opportunities", "arbitrage"),
    "/api/v1/seller-check": ("/api/v1/verify-seller", "seller"),
    "/api/v1/onchain-sales": ("/api/sales", "on-chain sales"),
}


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-admin-token")
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    import main
    main._free_tier_usage.clear()
    # Exhaust the free tier so every paid route answers the 402 challenge body.
    main._free_tier_usage["127.0.0.1"] = 999
    yield main.app.test_client(), main
    main._free_tier_usage.clear()


def _challenge(client, path):
    r = client.get(path)
    assert r.status_code == 402, f"{path} answered {r.status_code}, not 402"
    return r.get_json()


# ── the alias is a paid route, not a free back door ─────────────────────────

def test_every_alias_is_registered_and_paywalled(client):
    """A registered route that is NOT in the paid set would be worse than no
    alias at all: a second, unpaywalled door to the same product."""
    app_client, main = client
    registered = {str(rule) for rule in main.app.url_map.iter_rules()}
    for alias in ALIASES:
        assert alias in registered, f"{alias} is not a registered route"
        assert alias in main.X402_PAID_ENDPOINTS, (
            f"{alias} is routable but not in X402_PAID_ENDPOINTS — a free "
            "back door to a paid product")
        assert alias not in main.X402_FREE_ENDPOINTS
        _challenge(app_client, alias)


def test_every_alias_is_in_the_payment_funnel(client):
    """A paid route missing from FUNNEL_ROUTES is invisible in the funnel; the
    whale flow was exactly that gap until 13.09."""
    _app_client, main = client
    from integrations.dashboard_store import FUNNEL_ROUTES
    for alias in ALIASES:
        assert alias in FUNNEL_ROUTES, f"{alias} would be invisible in the funnel"


# ── it is the same product: same price, same money, same handler ────────────

def test_an_alias_costs_exactly_what_its_canonical_route_costs(client):
    app_client, main = client
    for alias, (canonical, _words) in ALIASES.items():
        a = _challenge(app_client, alias)
        b = _challenge(app_client, canonical)
        assert a["accepts"][0]["amount"] == b["accepts"][0]["amount"], (
            f"{alias} charges {a['accepts'][0]['amount']} where {canonical} "
            f"charges {b['accepts'][0]['amount']}")
        # ...and the alias is deliberately NOT a row in the published price map:
        # that map is what server.json and the dearest-route invariant read whole,
        # so a duplicate entry would advertise a product we do not sell.
        assert alias not in main.X402_PRICE_MAP, (
            f"{alias} was added to X402_PRICE_MAP — price aliases by resolution, "
            "not by a second published row")
        assert main.X402_PRICE_MAP[canonical] == (
            int(b["accepts"][0]["amount"]) / 1_000_000)


def test_an_alias_pays_the_same_receiver_on_the_same_chain(client):
    """A second name must not become a second payTo — that is how a mistyped
    alias turns into a payment nobody receives."""
    app_client, _main = client
    for alias, (canonical, _words) in ALIASES.items():
        a = _challenge(app_client, alias)["accepts"][0]
        b = _challenge(app_client, canonical)["accepts"][0]
        for field in ("payTo", "asset", "network", "scheme"):
            assert a[field] == b[field], f"{alias}.{field} != {canonical}.{field}"


def test_an_alias_serves_the_very_same_view_function(client):
    """Two handlers for one response is two things to keep true, and one of them
    eventually stops being true. The alias must resolve to the same object."""
    _app_client, main = client
    rules = {str(r): r for r in main.app.url_map.iter_rules()}
    for alias, (canonical, _words) in ALIASES.items():
        alias_rule, canon_rule = rules[alias], rules[canonical]
        assert (main.app.view_functions[alias_rule.endpoint]
                is main.app.view_functions[canon_rule.endpoint]), (
            f"{alias} and {canonical} do not share a view function")


def test_an_alias_declares_the_same_output_example(client):
    app_client, main = client
    for alias, (canonical, _words) in ALIASES.items():
        assert (main._BAZAAR_OUTPUT_EXAMPLES[alias]
                is main._BAZAAR_OUTPUT_EXAMPLES[canonical]), (
            f"{alias} publishes its own copy of the output example")


# ── it files itself under its own name, which is the entire point ───────────

def test_an_alias_files_itself_under_its_own_url(client):
    """If the challenge advertised the canonical URL, an indexer would file the
    alias under the canonical path and the new vocabulary would buy nothing."""
    app_client, _main = client
    for alias in ALIASES:
        url = _challenge(app_client, alias)["resource"]["url"]
        assert url.endswith(alias), (
            f"{alias} advertised resource.url={url!r} — the alias must be the "
            "URL an indexer reads")


def test_an_alias_says_what_it_does_in_the_words_a_buyer_types(client):
    """Same product, said differently. A description identical to the canonical
    one would mean the alias added a URL and no vocabulary."""
    app_client, _main = client
    for alias, (canonical, words) in ALIASES.items():
        desc = _challenge(app_client, alias)["resource"]["description"]
        canon_desc = _challenge(app_client, canonical)["resource"]["description"]
        assert desc and desc != canon_desc, f"{alias} reuses the canonical text"
        assert words in desc.lower(), (
            f"{alias} does not say {words!r} in its own description: {desc!r}")


def test_an_alias_spends_its_tags_on_its_own_job(client):
    """The bazaar spec caps `tags` at five, so an alias cannot inherit the generic
    set and add to it — and a generic set on a specifically named route is what
    made the canonical routes unfindable. Constraints here are the spec's."""
    app_client, main = client
    for alias in ALIASES:
        res = _challenge(app_client, alias)["resource"]
        tags = res["tags"]
        assert tags == main.X402_RESOURCE_TAGS[alias], (
            f"{alias} does not publish its own tags")
        assert len(tags) <= 5, f"{alias} has {len(tags)} tags (max 5)"
        assert len(set(tags)) == len(tags), f"{alias} repeats a tag"
        for tag in tags:
            assert len(tag) <= 32 and all(" " <= ch <= "~" for ch in tag), tag
        # It must be its OWN set, not the generic one under a new URL. A word or
        # two may legitimately be shared — "crypto" is a fair description of a
        # trading-signal route — so the bar is that most slots go to its own job.
        assert tags != main.X402_DEFAULT_RESOURCE_TAGS, (
            f"{alias} inherited the generic tag set unchanged")
        own = [t for t in tags if t not in main.X402_DEFAULT_RESOURCE_TAGS]
        assert len(own) >= 3, (
            f"{alias} spends only {len(own)} of {len(tags)} tag slots on its own "
            f"job: {tags}")


def test_every_canonical_route_also_spends_its_tags_on_its_own_job(client):
    """The second half of the 10.11 fix, and the one that was missing for a month.

    Until this change only the aliases had an entry in X402_RESOURCE_TAGS; all
    seven canonical routes fell back to X402_DEFAULT_RESOURCE_TAGS and published
    the SAME five words — crypto, whale-tracking, x402, arbitrage, signals. None
    of those five is the job any of the seven does, and CDP matches tags. The
    measurement: "verify seller" misses /api/v1/verify-seller while its alias,
    whose tags are its own job's words, ranks #2 of 17.

    The same honesty bar as the alias test applies, and it bites harder here:
    /api/stats must not claim the words "market stats" (its response is this
    service's own counters plus a market snapshot), and /api/bot-status must not
    claim a generic "bot health" for other people's bots. What the tags claim is
    what the response returns."""
    app_client, main = client
    # Seven routes, and the two that were deliberately left without an alias are
    # exactly the two the old generic tag set hurt most — they had no second row
    # to be found by.
    canonical = sorted(set(main.X402_PATH_ALIASES.values())
                       | {"/api/stats", "/api/bot-status"})
    assert len(canonical) == 7, "the canonical paid surface is seven routes"
    for route in canonical:
        tags = _challenge(app_client, route)["resource"]["tags"]
        assert tags == main.X402_RESOURCE_TAGS[route], (
            f"{route} does not publish its own tags — it fell back to the "
            "generic set, which is the defect this test exists for")
        assert tags != main.X402_DEFAULT_RESOURCE_TAGS, (
            f"{route} still publishes the generic tag set verbatim")
        assert len(tags) <= 5 and len(set(tags)) == len(tags), tags
        for tag in tags:
            assert len(tag) <= 32 and all(" " <= ch <= "~" for ch in tag), tag
        own = [t for t in tags if t not in main.X402_DEFAULT_RESOURCE_TAGS]
        assert len(own) >= 3, (
            f"{route} spends only {len(own)} of {len(tags)} tag slots on its own "
            f"job: {tags}")

    # The two honest limits are asserted as words, not as intentions.
    stats_tags = " ".join(_challenge(app_client, "/api/stats")["resource"]["tags"])
    assert "market-stats" not in stats_tags and "market stats" not in stats_tags, (
        "/api/stats does not return market cap or volume — it must not claim "
        "the words the endpoints that do are found by")
    bot_desc = _challenge(app_client, "/api/bot-status")["resource"]["description"]
    assert "this service" in bot_desc, (
        "/api/bot-status reports OUR bot — the description has to say whose bot "
        "it is, not offer a generic bot health check")


def test_every_canonical_description_opens_with_the_buyers_words(client):
    """CDP does not read the resource URL; it reads this string. So the first
    clause has to be the words the job is asked for in, and the rest must still
    describe what the response actually returns."""
    app_client, main = client
    openings = {
        "/api/v1/signal": "crypto trading signal",
        "/api/v1/whaleflow": "whale flow",
        "/api/v1/verify-seller": "verify an x402 seller",
        "/api/bot-status": "telegram bot status",
    }
    for route, opener in openings.items():
        desc = _challenge(app_client, route)["resource"]["description"]
        assert desc.lower().startswith(opener), (
            f"{route} does not open with {opener!r}: {desc[:90]!r}")
        assert len(desc) >= 120, (
            f"{route}'s description is too short to be a pitch: {desc!r}")
    # And the buyer's words must differ per route — a shared opening would mean
    # the vocabulary was not spent, only the generic set re-typed.
    texts = {r: _challenge(app_client, r)["resource"]["description"]
             for r in main.X402_RESOURCE_TAGS}
    assert len(set(texts.values())) == len(texts), (
        "two routes publish the same description")


# ── the deliberate omissions, which a later edit must argue with ────────────


def test_two_routes_were_left_without_an_alias_on_purpose(client):
    """/api/stats answers with this service's own counters plus an ETH price; the
    measured demand for "crypto market stats" comes from endpoints returning real
    market cap and volume, and we would lose that comparison on substance, after
    taking the buyer's money. /api/bot-status reports OUR Telegram bot, while the
    demand for "bot health check" is an agent probing its own endpoint. A name
    that overpromises is worth one $0.005 sale and a permanent trust loss, so
    neither route gets one until its response earns the name."""
    _app_client, main = client
    aliased = set(main.X402_PATH_ALIASES.values())
    assert "/api/stats" not in aliased, "/api/stats must not pose as market data"
    assert "/api/bot-status" not in aliased, (
        "/api/bot-status must not pose as a generic bot health check")
    assert set(main.X402_PATH_ALIASES) == set(ALIASES), (
        "the alias set changed — say why in this file and in X402_PATH_ALIASES")
    assert len(main.X402_PAID_ENDPOINTS) == 12, (
        "7 canonical routes + 5 aliases is the paid surface; %d found"
        % len(main.X402_PAID_ENDPOINTS))
