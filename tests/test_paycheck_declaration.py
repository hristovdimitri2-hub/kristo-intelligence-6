# -*- coding: utf-8 -*-
"""GET /.well-known/paycheck.json — the declared payout wallet.

Lumière PayCheck watches the payTo of every endpoint it lists. When that
address moves it cross-checks the seller's own declaration, the seller's
earlier wallets and direct transfers between the old and the new wallet on
Base; a change it cannot confirm is `avoid` for 24 hours and then `caution`.
This file is the declaration it checks against, so a deliberate rotation is
recognised as one instead of reading as a hijack.

Their documented shape is exactly `{"payTo": ["0x…"]}`. The tests below pin
that shape AND the invariant that matters more than the shape: the address in
this file can never disagree with the address in the 402 quote.
"""
import pytest


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-admin-token")
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    import main
    main._free_tier_usage.clear()
    yield main.app.test_client(), main
    main._free_tier_usage.clear()


def test_the_declaration_is_the_documented_shape(client):
    c, _main = client
    r = c.get("/.well-known/paycheck.json")
    assert r.status_code == 200
    body = r.get_json()
    assert set(body) == {"payTo"}, (
        "Lumiere documents `{\"payTo\": [...]}` and nothing else; extra keys "
        "would be guessing at a parser we cannot see. Got %r" % sorted(body))
    assert isinstance(body["payTo"], list)
    assert len(body["payTo"]) == 1


def test_the_declared_wallet_is_the_one_the_402_quotes(client):
    """A declaration that can disagree with the quote it describes is worse
    than no declaration — and this is the whole point of the file."""
    c, main = client
    declared = c.get("/.well-known/paycheck.json").get_json()["payTo"][0]
    assert declared == main.X402_RECEIVER_ADDRESS

    main._free_tier_usage["127.0.0.1"] = 999
    try:
        challenge = c.get("/api/stats")
        assert challenge.status_code == 402
        quoted = challenge.get_json()["accepts"][0]["payTo"]
    finally:
        main._free_tier_usage.pop("127.0.0.1", None)
    assert declared == quoted, (
        "the payout declaration and the live 402 quote must be the same fact")


def test_the_declaration_stays_free_with_the_tier_exhausted(client):
    """A wallet rotation must be recognisable exactly when traffic is heaviest."""
    c, main = client
    main._free_tier_usage["127.0.0.1"] = 999
    try:
        r = c.get("/.well-known/paycheck.json")
        assert r.status_code == 200
        assert r.get_json()["payTo"]
    finally:
        main._free_tier_usage.pop("127.0.0.1", None)


def test_the_address_is_checksummed(client):
    """EIP-55, because every other surface we publish uses it."""
    c, _main = client
    address = c.get("/.well-known/paycheck.json").get_json()["payTo"][0]
    assert address.startswith("0x") and len(address) == 42
    assert address != address.lower(), "expected an EIP-55 checksummed address"
