"""The $1.00 seller-verification route: what it promises, and what it refuses.

This is the first route we sell above $1, and the only one that does real RPC
work per call instead of serving a snapshot. That makes two things matter more
here than anywhere else:

  - the price is read from the single price source, so the challenge cannot
    quote a number of its own
  - a bad request is refused BEFORE anything is read, and a chain failure is
    reported as a failure — never as a clean zero. A buyer who paid $1 and got
    `"unique_payers": 0` because the RPC blinked has been told a lie, and this
    product's whole reason to exist is not telling that one.

NO TEST HERE TOUCHES THE NETWORK. The engine reads a live chain, so a single
unstubbed call would turn a unit test into a multi-minute eth_getLogs walk — and
would make the suite depend on an RPC provider being up. The autouse fixture
below replaces the engine for every test; the ones that need a different answer
replace it again with their own.
"""
import json

import pytest

import main
import services.seller_audit as sa


RECEIVER = "0xd4cdA900839c0feD4374EE37EA0dbe8E4C6fd08f"


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """Every path through this route resolves to a stub, never a chain read."""
    monkeypatch.setattr(sa, "_CACHE", {})
    seen = {}

    def stub(receiver, days=7, **kw):
        seen["receiver"] = receiver
        seen["days"] = days
        return sa.build_audit(
            [{"tx_hash": "0x" + "ab" * 32,
              "payer": "0x1111111111111111111111111111111111111111",
              "amount_usdc": 0.003, "block_number": 1}],
            {"complete": True, "lookback_days": days, "scanned_blocks": 10,
             "failed_ranges": 0, "split_retries": 0},
            receiver=receiver, days=days)

    monkeypatch.setattr(sa, "audit_receiver", stub)
    return seen


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    main._free_tier_usage.clear()
    main.app.config["TESTING"] = True
    return main.app.test_client()


@pytest.fixture
def no_free_tier(client):
    main._free_tier_usage.clear()
    main._free_tier_usage["127.0.0.1"] = 999
    return client


# ── pricing ────────────────────────────────────────────────────────────────

def test_the_price_comes_from_the_single_source():
    """No literal anywhere: the map and the catalog read the same constant."""
    from config import KRISTO_VERIFY_SELLER_PRICE
    assert main.X402_PRICE_MAP["/api/v1/verify-seller"] == KRISTO_VERIFY_SELLER_PRICE
    route = [r for r in main.REAL_X402_ROUTES
             if r["endpoint"] == "/api/v1/verify-seller"]
    assert len(route) == 1
    assert route[0]["price_usdc"] == KRISTO_VERIFY_SELLER_PRICE


def test_it_is_priced_above_a_dollar():
    """The tier is the point, not an accident.

    A census of 143.8M x402 settlements found payments of $1 or more carry 72.5%
    of all value from under 8% of the traffic, and this is our most expensive
    route to serve, so it must not drift down into the $0.003 tier unnoticed.
    """
    assert main.X402_PRICE_MAP["/api/v1/verify-seller"] >= 1.0


def test_the_route_is_paid_and_its_sample_is_not():
    assert "/api/v1/verify-seller" in main.X402_PAID_ENDPOINTS
    assert "/api/v1/verify-seller/sample" in main.X402_FREE_ENDPOINTS
    assert "/api/v1/verify-seller" not in main.X402_FREE_ENDPOINTS


def test_the_challenge_quotes_exactly_one_dollar(no_free_tier, no_network):
    r = no_free_tier.get(f"/api/v1/verify-seller?receiver={RECEIVER}")
    assert r.status_code == 402
    body = r.get_json()
    assert body["x402_amount"] == "1000000", "atomic units: 1.00 USDC is 1000000"
    accepts = body["accepts"][0]
    assert accepts["amount"] == "1000000"
    assert accepts["scheme"] == "exact"
    assert accepts["network"] == "eip155:8453"
    assert accepts["payTo"] == main.X402_RECEIVER_ADDRESS
    assert "receiver" not in no_network, "a 402 must not read the chain"


# ── the free sample ────────────────────────────────────────────────────────

def test_the_free_sample_shows_the_honesty_rules_not_just_the_shape(client):
    r = client.get("/api/v1/verify-seller/sample")
    assert r.status_code == 200
    body = r.get_json()
    assert body["paid_route"] == "/api/v1/verify-seller"
    example = body["output_example"]
    assert "coverage" in example and "complete" in example["coverage"]
    assert "payer_analysis" in example
    # A buyer must be able to see that an incomplete read is published as
    # incomplete before trusting a complete one.
    assert "partial" in body["disclaimer"]
    assert "floor" in body["disclaimer"]


# ── what it refuses, before it reads anything ──────────────────────────────

def test_a_missing_receiver_is_refused_by_name(client, no_network):
    r = client.get("/api/v1/verify-seller")
    assert r.status_code == 400
    body = r.get_json()
    assert body["error"] == "receiver_required"
    assert "free_sample" in body
    assert "receiver" not in no_network, "nothing should have been read"


@pytest.mark.parametrize("bad", [
    "not-an-address",
    "0x1234",
    "0x" + "z" * 40,
    "0x" + "1" * 41,
    "0x",
])
def test_a_malformed_address_is_refused_rather_than_read(client, no_network, bad):
    """A typo must not become a clean report about a nonexistent address."""
    r = client.get("/api/v1/verify-seller?receiver=" + bad)
    assert r.status_code == 400, bad
    assert r.get_json()["error"] == "invalid_receiver"
    assert "receiver" not in no_network, f"{bad} should not have reached the chain"


def test_an_address_without_the_0x_prefix_is_accepted_and_normalised(client, no_network):
    """Bare 40-hex is a valid address, and is normalised before use.

    Worth pinning separately from the malformed cases: it is the one input that
    LOOKS wrong and is not.
    """
    bare = RECEIVER[2:]
    r = client.get("/api/v1/verify-seller?receiver=" + bare)
    assert r.status_code == 200
    assert no_network["receiver"] == RECEIVER, "must be checksummed, not passed raw"


# ── what it reports ────────────────────────────────────────────────────────

def test_an_unreadable_chain_is_a_failure_not_a_zero(client, monkeypatch):
    """The one lie this product must never tell."""
    def dead(receiver, days=7, **kw):
        return sa.build_audit([], None, receiver=receiver, days=days,
                              failed_reason="rpc_read_failed: ConnectionError")
    monkeypatch.setattr(sa, "audit_receiver", dead)

    r = client.get(f"/api/v1/verify-seller?receiver={RECEIVER}")
    assert r.status_code == 200, "a chain problem must not be a 500 either"
    body = r.get_json()
    assert body["read"] == "failed"
    assert "rpc_read_failed" in json.dumps(body)
    assert "0 paying" not in body["verdict"].lower(), (
        "a failed read must not be worded as a clean result")
    assert body["served_from_cache"] is False


def test_a_clamped_window_is_reported_as_the_window_walked(client, no_network):
    """`days` is never trusted, and the value reaching the engine is the value
    the report will state.

    The engine cache is cleared per iteration on purpose. Two of these inputs
    clamp to the same window (`0` and `-5` both become 1), and after the first
    the second is served from cache without reaching the engine at all — which
    is correct behaviour, and would otherwise read here as a missing call.
    """
    for requested, expected in (("9999", 30), ("0", 1), ("nonsense", 7),
                                ("-5", 1), ("7", 7), ("30", 30)):
        no_network.clear()
        sa._CACHE.clear()
        main._free_tier_usage.clear()
        client.get(f"/api/v1/verify-seller?receiver={RECEIVER}&days={requested}")
        assert no_network.get("days") == expected, (requested, no_network)


def test_a_cached_report_says_it_is_cached(client, no_network):
    """A served-from-cache report must be labelled, not passed off as fresh."""
    first = client.get(f"/api/v1/verify-seller?receiver={RECEIVER}")
    assert first.status_code == 200
    assert first.get_json()["served_from_cache"] is False

    main._free_tier_usage.clear()
    second = client.get(f"/api/v1/verify-seller?receiver={RECEIVER}")
    assert second.status_code == 200
    assert second.get_json()["served_from_cache"] is True


def test_the_paid_report_carries_its_own_scope_and_buyer_note(client):
    body = client.get(f"/api/v1/verify-seller?receiver={RECEIVER}").get_json()
    assert "chain" in body["source"]
    assert "any receiver" in body["scope_note"]
    assert "endorsement" in body["buyer_note"]
    assert "coverage" in body["buyer_note"]


# ── the defect this route would otherwise have inherited ───────────────────

def test_the_scanner_is_told_which_window_to_walk():
    """fetch_incoming_transfers used to hardcode a 7-day window while its
    callers reported whatever they had been asked for, so a report headed
    "last 30 days" had in fact read 7. The window must travel with the request.
    """
    import inspect

    from scripts.competitor_recon import fetch_incoming_transfers

    sig = inspect.signature(fetch_incoming_transfers)
    assert "days" in sig.parameters, (
        "the scanner must accept the window its caller will report")
    assert sig.parameters["days"].default == 7, (
        "the default must stay 7 so existing callers are unchanged")
    assert "days" in inspect.getsource(sa.audit_receiver), (
        "audit_receiver must pass its own window through, not stop it")
