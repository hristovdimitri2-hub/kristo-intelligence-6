# -*- coding: utf-8 -*-
"""Two public surfaces that published more than they were asked to.

F-26: /api/launch/health answered with the size of the sales pipeline, the
number of leads, the CRM backend in use, and whether Stripe is live or running
in mock mode - on a free, unauthenticated, crawlable URL.

F-27: /api/connectors published the gas-paying wallet's address, which links the
relayer to this service, to anyone who asked.

Both endpoints stay public and keep working, because they are genuinely useful
(they are a deploy check and public evidence that the rails are up, and the
connector list is advertised in the discovery block of /api/v1/quickstart).
Only the operational detail is withheld, and the admin credential still gets it.

Every "must not leak" assertion here is paired with proof that the request DID
reach the richer build, so the absence cannot pass because nothing happened.
"""
import re

import main

#: A 40-hex address that is unmistakably ours in a test: if it appears in a
#: public response, this exact string is what we look for.
FAKE_HOT_WALLET = "0x" + "11" * 20
FAKE_RECEIVER = "0x" + "22" * 20

OPS_KEYS = {"lead_count", "pipeline", "crm_backend", "payment_provider"}


def _health(client, headers=None):
    response = client.get("/api/launch/health", headers=headers or {})
    return response.status_code, response.get_json()


def _connectors(client, headers=None):
    response = client.get("/api/connectors", headers=headers or {})
    return response.status_code, response.get_json()


def test_the_health_check_still_answers_publicly():
    """It is a deploy check. Gating the whole thing would break Render and our
    own scripts for no gain."""
    status, body = _health(main.app.test_client())
    assert status in (200, 503)          # 503 only when the CRM is unreachable
    assert body["ok"] is True
    assert body["app"] == "kristo-intelligence-v6"
    assert body["status"] in ("live", "degraded")
    assert "timestamp" in body


def test_the_health_check_no_longer_publishes_the_business():
    status, body = _health(main.app.test_client())
    assert not (OPS_KEYS & set(body)), sorted(OPS_KEYS & set(body))
    # And it says why, so a reader does not think the fields were removed.
    assert "admin" in body.get("ops_detail", "")


def test_the_admin_still_gets_the_ops_numbers(monkeypatch):
    """The other half of the pair - without this the test above proves nothing."""
    monkeypatch.setenv("ADMIN_API_TOKEN", "unit-test-admin-token")
    status, body = _health(main.app.test_client(),
                           {"X-Admin-Token": "unit-test-admin-token"})
    assert status in (200, 503)
    assert OPS_KEYS <= set(body), sorted(OPS_KEYS - set(body))
    assert set(body["pipeline"]) >= {"new", "paid"}


def test_a_near_miss_token_gets_the_public_answer(monkeypatch):
    monkeypatch.setenv("ADMIN_API_TOKEN", "unit-test-admin-token")
    status, body = _health(main.app.test_client(),
                           {"X-Admin-Token": "unit-test-admin-toke"})
    assert not (OPS_KEYS & set(body))


def test_connectors_still_lists_the_rails_publicly():
    status, body = _connectors(main.app.test_client())
    assert status == 200
    assert body["count"] >= 6
    ids = {entry["id"] for entry in body["connectors"]}
    assert "x402-eip3009" in ids and "base-usdc-receiver" in ids


def test_connectors_no_longer_publishes_the_hot_wallet(monkeypatch):
    """The payer wallet address is the one genuinely private thing in there.

    The fee receiver is NOT private - it is the payTo in every 402 challenge -
    so this asserts about the payer wallet specifically, by setting it to a
    string this test owns.
    """
    monkeypatch.setitem(main._wallet_state, "wallet_address", FAKE_HOT_WALLET)
    monkeypatch.setitem(main._wallet_state, "fee_receiver", FAKE_RECEIVER)
    status, body = _connectors(main.app.test_client())
    assert status == 200
    raw = str(body)

    # It says a wallet is loaded - the fact that answers "is this rail working".
    payer = [e for e in body["connectors"] if e["id"] == "x402-outbound-buyer"][0]
    assert payer["status"] == "active"
    assert payer["detail"] == "payer wallet loaded"
    # And the address itself is gone.
    assert FAKE_HOT_WALLET not in raw
    assert "payer wallet=0x" not in raw
    assert not re.search(r"payer wallet=0x[0-9a-fA-F]{40}", raw)
    # The receiver is a public constant and must still be there, so this test
    # cannot pass merely by the whole section disappearing.
    assert FAKE_RECEIVER in raw


def test_the_operator_view_restores_the_wallet_address(monkeypatch):
    """Same one-click grant as the sales columns - one rule, not two."""
    monkeypatch.setitem(main._wallet_state, "wallet_address", FAKE_HOT_WALLET)
    client = main.app.test_client()
    assert FAKE_HOT_WALLET not in str(_connectors(client)[1])

    client.post("/api/dashboard/operator-view", json={"on": True})
    raw = str(_connectors(client)[1])
    assert FAKE_HOT_WALLET in raw
    assert "payer wallet=0x" in raw


def test_the_operator_view_still_does_not_open_the_off_chain_numbers():
    """The CRM/Stripe grant stays with the admin credential alone."""
    client = main.app.test_client()
    client.post("/api/dashboard/operator-view", json={"on": True})
    body = _health(client)[1]
    assert not (OPS_KEYS & set(body))
