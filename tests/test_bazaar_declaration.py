# -*- coding: utf-8 -*-
"""
Bazaar discovery-readiness tests (local only — nothing is listed/published).

Validates the 4 items of the Bazaar pathway (docs/BAZAAR_RESEARCH.md):
  1. 402 body declares listing metadata: resource.{serviceName,tags,iconUrl}
  2. extensions.bazaar schema shape matches the x402 v2 wire contract
     (no `jsonschema` dependency in this repo — structural validation in the
     style of tests/test_x402scan_compliance.py)
  3. the demo client echoes `extensions` into the PAYMENT-SIGNATURE payload
     (scripts/demo_sponsored_pay.py:echo_extensions)
  4. PAYMENT-SAFETY: a payload carrying the echoed `extensions` key still
     passes precheck_payment_payload + _local_recover_signer — the echo must
     never break payment verification (connectors reads only accepted/payload)
  5. EXTENSION-RESPONSES decoding + the iconUrl asset is served, not paywalled
"""
import base64
import json
import secrets
import sys
import time
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import demo_sponsored_pay as client_mod  # noqa: E402  (scripts/ is not a package)


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-admin-token")
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    import main
    main._free_tier_usage.clear()
    return main.app.test_client()


def _challenge_body(client):
    """A 402 challenge for a paid endpoint (free tier exhausted)."""
    import main
    main._free_tier_usage["127.0.0.1"] = 999
    r = client.get("/api/stats")
    assert r.status_code == 402
    return r.get_json()


# ── 1. listing metadata on the 402 resource ──────────────────────────────────

def test_402_resource_carries_bazaar_listing_metadata(client):
    d = _challenge_body(client)
    res = d["resource"]
    assert isinstance(res.get("serviceName"), str) and res["serviceName"].strip(), \
        "resource.serviceName must be a non-empty string"
    assert isinstance(res.get("tags"), list) and res["tags"], \
        "resource.tags must be a non-empty list"
    assert all(isinstance(t, str) and t.strip() for t in res["tags"]), \
        "resource.tags entries must be non-empty strings"
    icon = res.get("iconUrl")
    assert isinstance(icon, str) and icon.startswith(("http://", "https://")), \
        f"resource.iconUrl must be an absolute URL, got {icon!r}"


# ── 2. extensions.bazaar wire-contract shape ─────────────────────────────────

def _validate_bazaar_declaration(d: dict):
    """Structural schema check mirroring the @x402/extensions wire contract
    (BAZAAR_RESEARCH.md; PayAI/agentcash expectations). Returns list of
    problems — empty means the declaration is well-formed."""
    problems = []
    ext = d.get("extensions")
    if not isinstance(ext, dict) or "bazaar" not in ext:
        return ["extensions.bazaar missing"]
    bz = ext["bazaar"]

    info = bz.get("info")
    if not isinstance(info, dict):
        problems.append("extensions.bazaar.info missing")
    else:
        inp = info.get("input")
        if not isinstance(inp, dict):
            problems.append("extensions.bazaar.info.input missing")
        else:
            if inp.get("type") != "http":
                problems.append(f"info.input.type={inp.get('type')!r} != 'http'")
            if inp.get("method") not in ("GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"):
                problems.append(f"info.input.method={inp.get('method')!r} invalid")

    schema = bz.get("schema")
    if not isinstance(schema, dict):
        problems.append("extensions.bazaar.schema missing")
        return problems
    if not str(schema.get("$schema", "")).startswith("https://json-schema.org/"):
        problems.append(f"schema.$schema={schema.get('$schema')!r} not a JSON-Schema dialect URI")
    if schema.get("type") != "object":
        problems.append(f"schema.type={schema.get('type')!r} != 'object'")
    props = schema.get("properties")
    if not isinstance(props, dict):
        problems.append("schema.properties missing")
        return problems
    in_props = (props.get("input") or {}).get("properties") or {}
    if not isinstance(in_props.get("queryParams"), dict) and not isinstance(in_props.get("body"), dict):
        problems.append("input schema must expose queryParams OR body")
    out_props = (props.get("output") or {}).get("properties") or {}
    if not isinstance(out_props.get("example"), dict):
        problems.append("output schema must expose an example property")
    return problems


def test_402_bazaar_declaration_matches_wire_contract(client):
    d = _challenge_body(client)
    problems = _validate_bazaar_declaration(d)
    assert not problems, "bazaar declaration malformed: " + "; ".join(problems)


# ── 3. client echoes extensions into the payment payload ─────────────────────

def test_client_echoes_extensions_into_payment_payload():
    challenge = {"x402Version": 2,
                 "extensions": {"bazaar": {"info": {"input": {"type": "http", "method": "GET"}}}}}
    payload = {"x402Version": 2, "accepted": {}, "payload": {"signature": "0x", "authorization": {}}}
    out = client_mod.echo_extensions(payload, challenge)
    assert out["extensions"] == challenge["extensions"], \
        "client MUST copy the 402's extensions verbatim into the payment payload"
    # original untouched (pure function — no surprise mutation)
    assert "extensions" not in payload


def test_client_echo_tolerates_missing_extensions():
    payload = {"x402Version": 2, "accepted": {}, "payload": {}}
    out = client_mod.echo_extensions(payload, {"x402Version": 2})
    assert "extensions" not in out
    out2 = client_mod.echo_extensions(payload, {"extensions": {}})
    assert "extensions" not in out2


# ── 4. PAYMENT-SAFETY: echoed extensions never break verification ────────────

def _build_signed_payload():
    """Real EIP-3009 payload signed offline (pattern from test_connectors)."""
    from eth_account import Account
    from eth_account.messages import encode_typed_data

    usdc = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
    receiver = "0xd4cdA900839C0FED4374EE37EA0DBE8e4c6fd08f"
    acct = Account.from_key("0x" + secrets.token_hex(32))
    now = int(time.time())
    auth = {"from": acct.address, "to": receiver, "value": "5000",
            "validAfter": str(now - 60), "validBefore": str(now + 600),
            "nonce": "0x" + secrets.token_hex(32)}
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
    accepted = {"scheme": "exact", "network": "eip155:8453", "amount": "5000",
                "payTo": receiver, "asset": usdc, "maxTimeoutSeconds": 60,
                "extra": {"name": "USD Coin", "version": "2"}}
    return {"x402Version": 2, "accepted": accepted,
            "payload": {"signature": sig, "authorization": auth}}, dict(accepted)


def test_payment_payload_with_echoed_extensions_still_verifies():
    """The echoed extensions key MUST NOT break precheck or EIP-712 recovery —
    payment verification reads only accepted/payload (connectors.py)."""
    from services.connectors import precheck_payment_payload, _local_recover_signer

    payload, reqs = _build_signed_payload()
    # sanity: clean payload verifies
    assert precheck_payment_payload(payload, reqs) == []
    recovered, err = _local_recover_signer(payload)
    assert err is None and recovered

    # now simulate the client echo (what demo_sponsored_pay sends with --send)
    echoed = client_mod.echo_extensions(
        payload, {"extensions": {"bazaar": {"schema": {"type": "object"}}}})
    assert echoed["extensions"]["bazaar"]["schema"]["type"] == "object"

    problems = precheck_payment_payload(echoed, reqs)
    assert problems == [], f"echoed extensions broke precheck: {problems}"
    recovered2, err2 = _local_recover_signer(echoed)
    assert err2 is None and recovered2 == recovered, \
        "echoed extensions changed the recovered signer"

    # verify_standard_payment end-to-end still accepts it
    from services.connectors import verify_standard_payment
    header = base64.urlsafe_b64encode(
        json.dumps(echoed, separators=(",", ":")).encode()).decode()
    ok, payer, detail = verify_standard_payment(header, reqs)
    assert ok, f"verify_standard_payment rejected echoed payload: {detail}"
    assert payer and payer.lower() == recovered.lower()


# ── 5. EXTENSION-RESPONSES decoding + icon asset ────────────────────────────

def test_read_extension_responses_decodes_bazaar_status(capsys):
    receipt = {"bazaar": {"status": "listed", "tx": "0xdead"}}
    hdr_val = base64.b64encode(json.dumps(receipt).encode()).decode().rstrip("=")
    client_mod.read_extension_responses({"EXTENSION-RESPONSES": hdr_val})
    err = capsys.readouterr().err
    assert "bazaar status: listed" in err and "0xdead" in err


def test_read_extension_responses_tolerates_absent_or_garbage(capsys):
    client_mod.read_extension_responses({})  # absent — logged, no crash
    client_mod.read_extension_responses({"extension-responses": "!!!not-base64!!!"})
    err = capsys.readouterr().err
    assert "absent" in err
    assert "undecodable" in err


def test_icon_url_asset_serves_svg(client):
    d = _challenge_body(client)
    icon = d["resource"]["iconUrl"]
    # strip the scheme+host the test client uses — request the path directly
    path = "/" + icon.split("/", 3)[-1]
    r = client.get(path)
    assert r.status_code == 200, f"iconUrl asset {path} must be served, got {r.status_code}"
    assert b"<svg" in r.data
