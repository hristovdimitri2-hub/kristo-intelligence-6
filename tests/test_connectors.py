# -*- coding: utf-8 -*-
"""
Tests for the integration-connector registry, the standard x402 (EIP-3009 /
X-PAYMENT) payment rail, and the quickstart onboarding endpoint.
"""
import base64
import json
import secrets

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


# ── EIP-3009 layered verification (PayAPI review round 2) ───────────────────

def _build_signed_payload(authorization_overrides=None, tamper_from=False):
    """Real EIP-3009 payload signed with eth_account (offline)."""
    import time as _time
    from eth_account import Account
    from eth_account.messages import encode_typed_data

    usdc = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
    receiver = "0xd4cdA900839C0FED4374EE37EA0DBE8e4c6fd08f"
    acct = Account.from_key("0x" + secrets.token_hex(32))
    now = int(_time.time())
    auth = {
        "from": acct.address, "to": receiver, "value": "5000",
        "validAfter": str(now - 60), "validBefore": str(now + 600),
        "nonce": "0x" + secrets.token_hex(32),
    }
    if authorization_overrides:
        auth.update(authorization_overrides)
    domain = {"name": "USD Coin", "version": "2", "chainId": 8453,
              "verifyingContract": usdc}
    types = {"TransferWithAuthorization": [
        {"name": "from", "type": "address"}, {"name": "to", "type": "address"},
        {"name": "value", "type": "uint256"}, {"name": "validAfter", "type": "uint256"},
        {"name": "validBefore", "type": "uint256"}, {"name": "nonce", "type": "bytes32"}]}
    sm = encode_typed_data(domain_data=domain, message_types=types, message_data=auth)
    sig = Account.sign_message(sm, acct.key)["signature"].hex()
    if not sig.startswith("0x"):
        sig = "0x" + sig
    if tamper_from:
        # Tamper AFTER signing: signature no longer recovers to auth.from.
        auth["from"] = "0x000000000000000000000000000000000000dead"
    accepted = {"scheme": "exact", "network": "eip155:8453", "amount": "5000",
                "payTo": receiver, "asset": usdc, "maxTimeoutSeconds": 60,
                "extra": {"name": "USD Coin", "version": "2"}}
    payload = {"x402Version": 2, "accepted": accepted,
               "payload": {"signature": sig, "authorization": auth}}
    return acct, payload, accepted


def test_precheck_catches_structural_problems():
    from services.connectors import precheck_payment_payload
    _, payload, requirements = _build_signed_payload()
    reqs = dict(requirements)  # independent copy — precheck must compare
    # Clean payload -> no problems
    assert precheck_payment_payload(payload, reqs) == []
    # Underpayment -> caught
    payload["accepted"]["amount"] = "1"
    payload["payload"]["authorization"]["value"] = "1"
    problems = precheck_payment_payload(payload, reqs)
    assert any("amount below price" in p for p in problems)
    # Wrong receiver -> caught
    _, payload2, _ = _build_signed_payload(
        authorization_overrides={"to": "0x000000000000000000000000000000000000dead"})
    problems2 = precheck_payment_payload(payload2, reqs)
    assert any("authorization.to != payTo" in p for p in problems2)
    # Expired window -> caught
    _, payload3, _ = _build_signed_payload(
        authorization_overrides={"validBefore": "1000"})
    problems3 = precheck_payment_payload(payload3, reqs)
    assert any("expired" in p for p in problems3)


def test_local_recovery_detects_signature_from_mismatch():
    from services.connectors import _local_recover_signer
    _, payload, _ = _build_signed_payload(tamper_from=True)
    recovered, err = _local_recover_signer(payload)
    # The signature is valid but recovers to the ORIGINAL signer, not the
    # tampered authorization.from — the mismatch check must catch it.
    assert recovered is not None
    assert str(recovered).lower() != "0x000000000000000000000000000000000000dead"


def test_verify_rejects_with_precise_reason_not_generic(client, monkeypatch):
    """401 body must carry the exact rejection reason (PayAPI observability)."""
    import main
    from services import connectors
    monkeypatch.setattr(main, "FREE_TIER_LIMIT", 0)
    monkeypatch.setattr(main, "_free_tier_usage", {})
    monkeypatch.setattr(connectors, "verify_standard_payment",
                        lambda h, req: (False, "0xABC",
                                        "payai:invalid_exact_evm_signature"))
    header = base64.urlsafe_b64encode(b"garbage").decode()
    r = client.get("/api/stats", headers={"PAYMENT-SIGNATURE": header})
    assert r.status_code == 401
    body = r.get_json()
    assert body["error"] == "invalid_standard_payment"
    assert "payai:invalid_exact_evm_signature" in body["reason"]


def test_verify_standard_payment_is_local_and_canonical(monkeypatch):
    """Verification is purely local (canonical EIP-712) — no facilitator call."""
    from services import connectors
    _, payload, accepted = _build_signed_payload()
    header = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()

    def forbidden(*a, **kw):
        raise AssertionError("facilitator must NOT be needed for verification")

    monkeypatch.setattr(connectors, "_facilitator_post", forbidden)
    ok, payer, detail = connectors.verify_standard_payment(header, dict(accepted))
    assert ok is True
    assert detail == "verified_locally"
    assert payer == payload["payload"]["authorization"]["from"]


def test_settle_prefers_self_broadcast(monkeypatch):
    """Settle chain: self-broadcast first (we are the facilitator)."""
    from services import connectors
    _, payload, accepted = _build_signed_payload()
    header = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    monkeypatch.setenv("WALLET_PRIVATE_KEY", "0x" + "11" * 32)

    def fake_broadcast(p):
        assert p["payload"]["authorization"]["value"] == "5000"
        return "0x" + "ff" * 32, "settled_self_broadcast"

    monkeypatch.setattr(connectors, "_self_broadcast_settlement", fake_broadcast)

    def forbidden(*a, **kw):
        raise AssertionError("facilitator must not be tried after self-broadcast")

    monkeypatch.setattr(connectors, "_facilitator_post", forbidden)
    tx, detail = connectors.settle_standard_payment(header, dict(accepted))
    assert tx == "0x" + "ff" * 32
    assert detail == "settled_self_broadcast"


def test_settle_falls_back_to_facilitator_when_no_wallet(monkeypatch):
    """Without WALLET_PRIVATE_KEY the settle chain falls through to PayAI."""
    from services import connectors
    _, payload, accepted = _build_signed_payload()
    header = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode()
    monkeypatch.delenv("WALLET_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("CDP_API_KEY_ID", raising=False)
    monkeypatch.delenv("CDP_API_KEY_SECRET", raising=False)

    seen = []
    def fake_post(base_url, endpoint, body, token=None):
        seen.append((base_url, endpoint))
        return 200, {"success": True, "transaction": "0x" + "ab" * 32}, ""

    monkeypatch.setattr(connectors, "_facilitator_post", fake_post)
    tx, detail = connectors.settle_standard_payment(header, dict(accepted))
    assert tx == "0x" + "ab" * 32
    assert any("payai" in u for u, _ in seen) and all(
        e == "settle" for _, e in seen)


def test_split_signature_handles_y_parity():
    from services.connectors import _split_signature
    raw = "ab" * 32 + "cd" * 32 + "00"          # v = 0 (yParity)
    v, r, s = _split_signature("0x" + raw)
    assert v == 27 and r == bytes.fromhex("ab" * 32) and s == bytes.fromhex("cd" * 32)
    v2, _, _ = _split_signature("0x" + "ab" * 32 + "cd" * 32 + "1c")  # v = 28
    assert v2 == 28
    assert _split_signature("0x1234") is None   # malformed


def test_cdp_jwt_supports_pem_and_legacy_secret(monkeypatch):
    """CDP JWT must build from BOTH portal formats (PEM and legacy base64)."""
    from services.connectors import _cdp_jwt
    pytest.importorskip("cryptography")
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    import base64 as _b64

    key = ec.generate_private_key(ec.SECP256R1())
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ).decode()
    legacy_b64 = _b64.b64encode(
        key.private_numbers().private_value.to_bytes(32, "big")
    ).decode()

    kid = "organizations/3dc43ce6-05e8-4cb4-b9ad-cafcfd155082/apiKeys/53a0d0e5-c35a-4a5b-a0c5-ddb14205659c"

    monkeypatch.setenv("CDP_API_KEY_ID", kid)
    monkeypatch.setenv("CDP_API_KEY_SECRET", pem)
    token, detail = _cdp_jwt("api.cdp.coinbase.com")
    assert token and token.count(".") == 2, "PEM secret must build a JWT"
    assert detail == "ok"
    hdr = json.loads(base64.urlsafe_b64decode(token.split(".")[0] + "=="))
    assert hdr["alg"] == "ES256" and hdr["kid"] == kid

    # Render paste artifact: literal \n escapes must be normalized.
    monkeypatch.setenv("CDP_API_KEY_SECRET", pem.replace("\n", "\\n"))
    token_esc, detail_esc = _cdp_jwt("api.cdp.coinbase.com")
    assert token_esc and token_esc.count(".") == 2, \
        "PEM with literal \\n escapes must build a JWT"

    # WORST CASE (the live failure from canary 3): newlines flattened to
    # spaces -> one long line with '=' padding mid-line.
    monkeypatch.setenv("CDP_API_KEY_SECRET", pem.replace("\n", " "))
    token_flat, detail_flat = _cdp_jwt("api.cdp.coinbase.com")
    assert token_flat and token_flat.count(".") == 2, \
        f"single-line PEM must build a JWT, got: {detail_flat}"

    # Live canary-3 failure mode: trailing junk after the base64 padding.
    monkeypatch.setenv("CDP_API_KEY_SECRET",
                       pem.replace("\n", " ") + "  extraJunk12==")
    token_junk, detail_junk = _cdp_jwt("api.cdp.coinbase.com")
    assert token_junk and token_junk.count(".") == 2, \
        f"PEM with trailing junk must build a JWT, got: {detail_junk}"

    monkeypatch.setenv("CDP_API_KEY_SECRET", legacy_b64)
    token2, _ = _cdp_jwt("api.cdp.coinbase.com")
    assert token2 and token2.count(".") == 2, "legacy secret must also build"


def test_cdp_jwt_rejects_wrong_curve_and_missing(monkeypatch):
    from services.connectors import _cdp_jwt
    pytest.importorskip("cryptography")
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.hazmat.primitives import serialization

    # No credentials -> None (chain skips CDP gracefully)
    monkeypatch.delenv("CDP_API_KEY_ID", raising=False)
    monkeypatch.delenv("CDP_API_KEY_SECRET", raising=False)
    token, detail = _cdp_jwt("api.cdp.coinbase.com")
    assert token is None and "missing env" in detail

    # Wrong curve (secp256k1) -> None with clear skip
    k1 = ec.generate_private_key(ec.SECP256K1())
    pem_k1 = k1.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.TraditionalOpenSSL,
        serialization.NoEncryption(),
    ).decode()
    monkeypatch.setenv("CDP_API_KEY_ID", "organizations/x/apiKeys/y")
    monkeypatch.setenv("CDP_API_KEY_SECRET", pem_k1)
    token2, detail2 = _cdp_jwt("api.cdp.coinbase.com")
    assert token2 is None and "curve is secp256k1" in detail2


def test_l402_challenge_parser():
    from services.connectors import l402_parse_challenge, l402_ready
    ch = l402_parse_challenge(
        'L402 macaroon="AgEEbWFj", invoice="lnbc50n1pabc"'
    )
    assert ch == {"macaroon": "AgEEbWFj", "invoice": "lnbc50n1pabc"}
    assert l402_parse_challenge("Basic realm=x") is None
    assert l402_parse_challenge("") is None
    assert l402_ready() is False  # no LND credentials in test env
