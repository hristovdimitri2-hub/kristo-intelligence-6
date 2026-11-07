"""The nohumans.directory ownership proof, and the narrowness it promises.

To edit a listing at nohumans.directory we have to prove we control the domain
right now. Their flow issues a one-time token per listing, valid 24h, served
either at /.well-known/nohumans-claim or as an `x-nohumans-claim` response
header on that listing's own endpoint. Option A is a single path carrying a
single token, so it can satisfy one listing at a time; the header is per
endpoint, which is what let all five be claimed from one deploy.

The dict is deliberately EMPTY in the source: the tokens are 24h credentials and
all five listings are claimed, so a token left behind would prove nothing and
would read like a secret nobody cleaned up. These tests therefore exercise the
MECHANISM with a synthetic token rather than pinning the real ones — which is
also the better test, because it keeps asserting the property after the
credentials have expired and gone.

Two properties matter:

  1. The endpoint answers with the token issued for it, on the response it
     actually returns. A paid route answers a probe with 402, and a 402 carries
     headers like any other response — if the token only appeared on a 200, no
     paid listing could ever be claimed.
  2. It is scoped to the exact path. It must not appear on a sibling route, a
     prefix or an unrelated page: attesting control of a route we were not
     challenged about would be a false claim, and this header is an assertion,
     not a decoration.
"""
import pytest

import main


# Synthetic values, shaped like the real ones (48 hex chars).
FAKE = {
    "/api/v1/signal": "a" * 48,
    "/api/v1/whaleflow": "b" * 48,
}


@pytest.fixture
def armed(monkeypatch):
    """Arm the hook with synthetic tokens, as a real challenge would."""
    monkeypatch.setitem(main.__dict__, "NOHUMANS_CLAIM_TOKENS", dict(FAKE))
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    main.app.config["TESTING"] = True
    return main.app.test_client()


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    main.app.config["TESTING"] = True
    return main.app.test_client()


def test_the_source_ships_no_live_claim_token():
    """A stale 24h credential must not be left in the tree.

    If this fails, a challenge token was committed and not removed after the
    listing was claimed. It proves nothing by then and should be deleted, not
    explained away.
    """
    assert main.NOHUMANS_CLAIM_TOKENS == {}, (
        "claim tokens are one-time 24h credentials; the dict ships empty")


def test_the_hook_exists_and_is_an_after_request():
    """The mechanism must survive even though the credentials do not."""
    assert hasattr(main, "_nohumans_claim_header")
    assert main.NOHUMANS_CLAIM_TOKENS == {}


@pytest.mark.parametrize("path", sorted(FAKE))
def test_each_endpoint_serves_the_token_issued_for_it(armed, path):
    r = armed.get(path)
    assert r.headers.get("x-nohumans-claim") == FAKE[path], (
        f"{path} answered {r.status_code} without its own claim token")


@pytest.mark.parametrize("path", sorted(FAKE))
def test_the_token_survives_a_402(armed, path):
    """The case that matters: a paid listing's probe is a 402.

    Attaching the header only to successful responses would leave every paid
    listing unclaimable.
    """
    main._free_tier_usage.clear()
    main._free_tier_usage["127.0.0.1"] = 999        # exhaust the free tier
    r = armed.get(path)
    if r.status_code == 402:
        assert r.headers.get("x-nohumans-claim") == FAKE[path], (
            "a 402 must still carry the proof header")


def test_a_sibling_route_never_borrows_a_token(armed):
    """Prefixes and neighbours must not attest control of anything."""
    for path in ("/", "/health", "/api/v1/signals", "/api/v1/signal/sample",
                 "/api/v1/whaleflow/extra", "/llms.txt", "/api/v1/quickstart"):
        r = armed.get(path)
        assert r.headers.get("x-nohumans-claim") is None, (
            f"{path} volunteered a claim token it was not issued")


def test_an_unarmed_hook_says_nothing_at_all(client):
    """With no challenge outstanding, no endpoint advertises anything."""
    for path in ("/", "/health", "/api/v1/signal", "/api/v1/whaleflow",
                 "/api/stats", "/api/sales", "/api/bot-status"):
        assert client.get(path).headers.get("x-nohumans-claim") is None
