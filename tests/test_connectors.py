# -*- coding: utf-8 -*-
"""
Tests for the integration-connector registry, the standard x402 (EIP-3009 /
X-PAYMENT) payment rail, and the quickstart onboarding endpoint.
"""
import base64
import json

import pytest


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-admin-token")
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    import main
    main._free_tier_usage.clear()
    return main.app.test_client()


def test_connectors_endpoint_is_free_and_structured(client):
    r = client.get("/api/connectors")
    assert r.status_code == 200
    data = r.get_json()
    assert data["count"] >= 6
    assert data["active"] >= 3
    ids = [c["id"] for c in data["connectors"]]
    assert len(ids) == len(set(ids)), "connector ids must be unique"
    required = {
        "base-usdc-receiver", "x402-challenge-v2", "x402-eip3009",
        "x402-outbound-buyer", "l402-lightning", "mcp-sse",
        "marketplace-x402scan", "marketplace-payapi", "marketplace-nohumans",
    }
    assert required.issubset(set(ids))
    for c in data["connectors"]:
        assert c["status"] in ("active", "inactive", "degraded")
        assert c["direction"] in ("inbound", "outbound")
        assert c["last_activity"]


def test_base_usdc_receiver_connector_advertises_bound_receiver(client):
    from config import BOUND_BASE_FEE_RECEIVER
    data = client.get("/api/connectors").get_json()
    recv = next(c for c in data["connectors"] if c["id"] == "base-usdc-receiver")
    assert recv["status"] == "active"
    assert BOUND_BASE_FEE_RECEIVER in recv["detail"]


def test_l402_connector_honest_about_lightning(client):
    data = client.get("/api/connectors").get_json()
    l402 = next(c for c in data["connectors"] if c["id"] == "l402-lightning")
    # Without LND credentials the connector must report inactive, not pretend.
    assert l402["status"] == "inactive"
    assert "L402_LND_ADDRESS" in l402["detail"]


def test_quickstart_is_free_and_complete(client):
    r = client.get("/api/v1/quickstart")
    assert r.status_code == 200
    d = r.get_json()
    assert d["protocol"] == "x402 v2"
    assert d["network"] == "base"
    assert d["cheapest_call"]["amount_usdc"] <= 0.005
    assert "X-Payment-Proof" in d["steps"][-1]
    for key in ("curl", "python", "node"):
        assert "/api/stats" in d[key], f"{key} snippet must target a paid route"


def test_quickstart_is_excluded_from_paywall(client, monkeypatch):
    import main
    monkeypatch.setattr(main, "FREE_TIER_LIMIT", 0)
    monkeypatch.setattr(main, "_free_tier_usage", {})
    assert client.get("/api/v1/quickstart").status_code == 200
    assert client.get("/api/connectors").status_code == 200


def test_standard_xpay_rail_unlocks_paid_call(client, monkeypatch):
    """A standard x402 client (X-PAYMENT / EIP-3009) pays -> 200 + sale recorded."""
    import main
    from services import connectors
    monkeypatch.setattr(main, "FREE_TIER_LIMIT", 0)
    monkeypatch.setattr(main, "_free_tier_usage", {})

    def fake_verify(header, requirements):
        assert requirements["scheme"] == "exact"
        assert requirements["network"] == "eip155:8453"
        assert requirements["amount"] == "5000"
        return True, "0xABCDEF1234567890abcdef1234567890abcdef12", "verified"

    tx = "0x" + "ab" * 32
    def fake_settle(header, requirements):
        return tx, "settled"

    monkeypatch.setattr(connectors, "verify_standard_payment", fake_verify)
    monkeypatch.setattr(connectors, "settle_standard_payment", fake_settle)
    # Keep the global sales ledger clean — the test only asserts the unlock.
    recorded = []
    monkeypatch.setattr(main, "_record_real_sale",
                        lambda **kw: recorded.append(kw))

    header = base64.urlsafe_b64encode(json.dumps({"x402Version": 2}).encode()).decode()
    r = client.get("/api/stats", headers={"X-PAYMENT": header})
    assert r.status_code == 200, f"standard payment must unlock the call: {r.status_code}"

    # The settlement must be recorded as a REAL sale exactly once.
    assert len(recorded) == 1
    assert recorded[0]["tx_hash"] == tx
    assert recorded[0]["amount_usd"] == pytest.approx(0.005)


def test_standard_xpay_invalid_payload_rejected_with_401(client, monkeypatch):
    import main
    from services import connectors
    monkeypatch.setattr(main, "FREE_TIER_LIMIT", 0)
    monkeypatch.setattr(main, "_free_tier_usage", {})
    monkeypatch.setattr(connectors, "verify_standard_payment",
                        lambda h, req: (False, None, "invalid_signature"))

    header = base64.urlsafe_b64encode(b"garbage").decode()
    r = client.get("/api/stats", headers={"X-PAYMENT": header})
    assert r.status_code == 401
    assert r.get_json()["error"] == "invalid_standard_payment"


def test_payment_signature_header_v2_unlocks_paid_call(client, monkeypatch):
    """x402 v2 spec clients send PAYMENT-SIGNATURE (not X-PAYMENT) — accepted."""
    import main
    from services import connectors
    monkeypatch.setattr(main, "FREE_TIER_LIMIT", 0)
    monkeypatch.setattr(main, "_free_tier_usage", {})

    def fake_verify(header, requirements):
        assert requirements["scheme"] == "exact"
        assert requirements["network"] == "eip155:8453"
        assert requirements["amount"] == "5000"
        return True, "0xABCDEF1234567890abcdef1234567890abcdef12", "verified"

    tx = "0x" + "cd" * 32
    monkeypatch.setattr(connectors, "verify_standard_payment", fake_verify)
    monkeypatch.setattr(connectors, "settle_standard_payment",
                        lambda h, req: (tx, "settled"))
    recorded = []
    monkeypatch.setattr(main, "_record_real_sale",
                        lambda **kw: recorded.append(kw))

    header = base64.urlsafe_b64encode(json.dumps({"x402Version": 2}).encode()).decode()
    r = client.get("/api/stats", headers={"PAYMENT-SIGNATURE": header})
    assert r.status_code == 200, \
        f"PAYMENT-SIGNATURE must unlock the call: {r.status_code}"
    assert len(recorded) == 1 and recorded[0]["tx_hash"] == tx
    # Spec-compliant settlement receipt header.
    assert "PAYMENT-RESPONSE" in r.headers
    settlement = json.loads(r.headers["PAYMENT-RESPONSE"])
    assert settlement["success"] is True
    assert settlement["transaction"] == tx


def test_payment_signature_takes_priority_over_x_payment(client, monkeypatch):
    """When both headers are present the v2 PAYMENT-SIGNATURE wins."""
    import main
    from services import connectors
    monkeypatch.setattr(main, "FREE_TIER_LIMIT", 0)
    monkeypatch.setattr(main, "_free_tier_usage", {})
    seen = []
    monkeypatch.setattr(connectors, "verify_standard_payment",
                        lambda h, req: (seen.append(h) or (True, None, "verified")))
    monkeypatch.setattr(connectors, "settle_standard_payment",
                        lambda h, req: ("0x" + "ee" * 32, "settled"))
    monkeypatch.setattr(main, "_record_real_sale", lambda **kw: None)

    v2 = base64.urlsafe_b64encode(b"v2-payload").decode()
    v1 = base64.urlsafe_b64encode(b"v1-payload").decode()
    r = client.get("/api/stats", headers={
        "PAYMENT-SIGNATURE": v2, "X-PAYMENT": v1,
    })
    assert r.status_code == 200
    assert seen and seen[0] == v2


def test_402_advertises_payment_required_header(client, monkeypatch):
    """402 must carry the spec PAYMENT-REQUIRED header (base64url challenge)."""
    import main
    monkeypatch.setattr(main, "FREE_TIER_LIMIT", 0)
    monkeypatch.setattr(main, "_free_tier_usage", {})
    r = client.get("/api/stats")
    assert r.status_code == 402
    raw = r.headers["PAYMENT-REQUIRED"]
    payload = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
    assert payload["x402Version"] == 2
    assert payload["accepts"][0]["network"] == "eip155:8453"
    assert payload["accepts"][0]["payTo"] == main.X402_RECEIVER_ADDRESS


def test_api_sales_price_is_flat_0_005(client, monkeypatch):
    """PayAPI review: /api/sales must challenge at $0.005 (5000 atomic)."""
    import main
    monkeypatch.setattr(main, "FREE_TIER_LIMIT", 0)
    monkeypatch.setattr(main, "_free_tier_usage", {})
    r = client.get("/api/sales")
    assert r.status_code == 402
    body = r.get_json()
    assert body["accepts"][0]["amount"] == "5000"
    assert float(body["x402_amount"]) == pytest.approx(0.005)
    assert float(body["payment"]["amount_usdc"]) == pytest.approx(0.005)


def test_l402_challenge_parser():
    from services.connectors import l402_parse_challenge, l402_ready
    ch = l402_parse_challenge(
        'L402 macaroon="AgEEbWFj", invoice="lnbc50n1pabc"'
    )
    assert ch == {"macaroon": "AgEEbWFj", "invoice": "lnbc50n1pabc"}
    assert l402_parse_challenge("Basic realm=x") is None
    assert l402_parse_challenge("") is None
    assert l402_ready() is False  # no LND credentials in test env
