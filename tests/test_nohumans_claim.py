"""The nohumans.directory ownership proof, and the narrowness it promises.

To edit a listing at nohumans.directory we have to prove we control the domain
right now. Their flow issues a one-time token per listing, valid 24h, served
either at /.well-known/nohumans-claim or as an `x-nohumans-claim` response
header on that listing's own endpoint. Option A is a single path carrying a
single token, so it can satisfy one listing at a time; the header is per
endpoint, which is what lets all five be claimed from one deploy.

Two things matter and both are tested here:

  1. Each endpoint answers with ITS token, on the response it actually returns.
     A paid route answers a probe with 402, and a 402 carries headers like any
     other response — if the token only appeared on a 200 we would never be able
     to claim a paid listing at all.
  2. It is scoped to the exact path. It must not appear on a sibling route, on a
     prefix, or on an unrelated page: attesting control of a route we did not
     ask about would be a false claim, and the header is an assertion, not a
     decoration.
"""
import pytest

import main


EXPECTED = {
    "/api/v1/signal": "2d52eadbf764a778c57b2ed19c110b9d39a56f81b1849f81",
    "/api/stats": "f2446848a73ab9d79e9bc99e890a46de16e5b5e1fe5b5bd0",
    "/api/bot-status": "cda8738d60c49a8751045eb66192196c2ebdaeb220f75d6d",
    "/api/sales": "9063455b59fcf97cb626c9b9ff781cca8e9ba998b0ef3160",
    "/api/v1/whaleflow": "f5852d1f47864ed1f103732fe03be4aabbeae6deec0cfbef",
}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    main.app.config["TESTING"] = True
    return main.app.test_client()


def test_every_claimed_listing_has_a_token_to_serve():
    """The dict and the listings must not drift apart silently."""
    assert set(main.NOHUMANS_CLAIM_TOKENS) == set(EXPECTED)
    for path, token in EXPECTED.items():
        assert main.NOHUMANS_CLAIM_TOKENS[path] == token
        assert len(token) == 48, (path, len(token))


@pytest.mark.parametrize("path", sorted(EXPECTED))
def test_each_endpoint_serves_its_own_token(client, path):
    """On whichever response it gives — 402 challenge or free-tier 200."""
    r = client.get(path)
    assert r.headers.get("x-nohumans-claim") == EXPECTED[path], (
        f"{path} answered {r.status_code} without its own claim token")


@pytest.mark.parametrize("path", sorted(EXPECTED))
def test_the_token_survives_a_402(client, path):
    """The case that matters: a paid listing's probe is a 402.

    If the header were attached only to successful responses, every paid
    listing here would be unclaimable.
    """
    main._free_tier_usage.clear()
    main._free_tier_usage["127.0.0.1"] = 999        # exhaust the free tier
    r = client.get(path)
    if r.status_code == 402:
        assert r.headers.get("x-nohumans-claim") == EXPECTED[path], (
            "a 402 must still carry the proof header")


def test_a_sibling_route_never_borrows_a_token(client):
    """Prefixes and neighbours must not attest control of anything."""
    for path in ("/", "/health", "/api/v1/signals", "/api/v1/signal/sample",
                 "/api/stats/sample", "/llms.txt", "/api/v1/quickstart"):
        r = client.get(path)
        assert r.headers.get("x-nohumans-claim") is None, (
            f"{path} volunteered a claim token it was not issued")


def test_a_wildcard_or_unknown_path_gets_nothing(client):
    r = client.get("/api/v1/whaleflow/extra")
    assert r.headers.get("x-nohumans-claim") is None
    assert "/api/v1/whaleflow/extra" not in main.NOHUMANS_CLAIM_TOKENS
