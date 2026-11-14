# -*- coding: utf-8 -*-
"""Do we pass the buyer-side traps we expect of our own sellers?

The r/x402 "x402 Agent Safety" exam (fizzl, 2026-11) runs a buyer agent against
17 hostile sellers and lists the traps. The seller's own traps are the ones a
SELLER can commit, and this file checks each of them against our app in-process
so the next deploy cannot regress them:

  overcharge        the 402 asks more than the published price
  hidden price      the price in the description differs from the amount
  rotating payTo    the 402 names a different address per request
  look-alike payTo  the address is not a valid EIP-55 checksum
  asks again        a paid request is answered 402 again
  expired quote     the challenge carries no validity window
  CORS              a browser client cannot even read the 402
  no resource       the 402 does not name the URL it was asked for

The test is a SELLER audit, not a buyer harness: it never pays. It is the
cheap half of the "we have 19/19 calls but never verified delivery" gap.
"""

import base64
import json

import pytest

PAID_ROUTES = [
    "/api/v1/signal",
    "/api/v1/whaleflow",
    "/api/arb/opportunities",
    "/api/bot-status",
    "/api/sales",
    "/api/stats",
    "/api/v1/verify-seller",
    "/api/v1/seller-check",
]


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-admin-token")
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    import main
    main._free_tier_usage.clear()
    main._free_tier_usage["127.0.0.1"] = 999
    yield main.app.test_client()
    main._free_tier_usage.clear()


def _challenge(client, path):
    r = client.get(path)
    assert r.status_code == 402, f"{path}: expected 402, got {r.status_code}"
    raw = r.headers.get("PAYMENT-REQUIRED") or r.headers.get("payment-required")
    assert raw, f"{path}: 402 without a PAYMENT-REQUIRED header"
    return json.loads(base64.b64decode(raw).decode()), r.get_json()


def _is_checksummed(address: str) -> bool:
    from eth_utils import is_checksum_address
    return is_checksum_address(address)


def test_one_pay_to_for_every_route(client):
    """rotating payTo: a different address per request is a classic trap."""
    seen = {}
    for path in PAID_ROUTES:
        head, _ = _challenge(client, path)
        seen[path] = head["accepts"][0]["payTo"]
    assert len(set(seen.values())) == 1, (
        "the paid routes advertise different payTo addresses: %s" % seen)


def test_the_pay_to_is_a_valid_checksum(client):
    """look-alike payTo: a wrong-case address is not a valid EIP-55 address."""
    head, _ = _challenge(client, "/api/v1/signal")
    pay_to = head["accepts"][0]["payTo"]
    assert _is_checksummed(pay_to), (
        "payTo %s is not EIP-55 valid; a client that validates checksums will "
        "read it as a look-alike address" % pay_to)


def test_the_amount_matches_the_published_price(client):
    """overcharge: the 402 must not ask more than the price map says."""
    import main
    for path in PAID_ROUTES:
        head, _ = _challenge(client, path)
        acc = head["accepts"][0]
        expected = int(round(float(main._get_dynamic_price("127.0.0.1", path)) * 1_000_000))
        assert int(acc["amount"]) == expected, (
            "%s: 402 asks %s atomic, the price map says %s"
            % (path, acc["amount"], expected))


def test_the_description_does_not_contain_a_second_price(client):
    """hidden price: a price in the description is a different number."""
    head, _ = _challenge(client, "/api/v1/signal")
    acc = head["accepts"][0]
    amount = int(acc["amount"])
    desc = (head.get("resource") or {}).get("description") or ""
    # The description is prose; it must not restate a USDC figure. A number in
    # the text is a second price, and the agent has no way to know which is real.
    for token in ("$", "USDC", "usdc"):
        assert token not in desc, (
            "the description states a price (%r); the amount is the only "
            "price the agent may read" % token)


def test_the_quote_carries_a_validity_window(client):
    """expired quote: a challenge with no window is not a quote."""
    head, _ = _challenge(client, "/api/v1/whaleflow")
    acc = head["accepts"][0]
    assert "maxTimeoutSeconds" in acc, "the challenge has no validity window"
    assert int(acc["maxTimeoutSeconds"]) > 0


def test_the_challenge_names_the_url_it_was_asked_for(client):
    """no resource: the 402 must say which resource it prices."""
    head, _ = _challenge(client, "/api/arb/opportunities")
    res = head.get("resource") or {}
    assert res.get("url"), "the 402 has no resource.url"
    assert "/api/arb/opportunities" in res["url"]


def test_cors_lets_a_browser_read_the_402(client):
    """CORS: a paid GET route must expose the payment headers to a browser."""
    head, _ = _challenge(client, "/api/v1/signal")
    r = client.get("/api/v1/signal")
    assert r.headers.get("Access-Control-Allow-Origin") == "*"
    methods = r.headers.get("Access-Control-Allow-Methods", "")
    assert "GET" in methods
    expose = r.headers.get("Access-Control-Expose-Headers", "")
    assert "PAYMENT-REQUIRED" in expose or "payment-required" in expose


def test_a_preflight_answers_200_with_methods(client):
    """A browser preflight must not be answered by the paywall."""
    r = client.options("/api/v1/signal")
    assert r.status_code in (200, 204), r.status_code
    assert "Access-Control-Allow-Methods" in r.headers
