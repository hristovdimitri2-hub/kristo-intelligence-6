"""
402 challenge response headers — Cache-Control + CORS (double gate 13.10).

x402-doctor (revecs-hq) + live curl found: no Cache-Control (a cached
challenge fails at settlement) and zero Access-Control-* (browser clients
cannot read PAYMENT-REQUIRED/payment-required — x402-foundation/x402#3722).
These tests pin the fix on the three paid routes, keep the pre-existing 402
headers/body as a regression guard, and prove the CORS layer stays scoped
to 402 responses (a 200 public route must not gain CORS).
"""
import base64
import json

import pytest

# path -> exact X-Payment-Amount-USDC the 402 must advertise (regression).
ROUTES = {
    "/api/v1/signal": "0.003",
    "/api/v1/whaleflow": "0.003",
    "/api/bot-status": "0.005",
}
REQUIRED_EXPOSE = [
    "PAYMENT-REQUIRED",
    "payment-required",
    "x-payment-address",
    "x-payment-amount-usdc",
    "x-payment-chain",
    "x-payment-required",
    "x-payment-token-contract",
]


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-admin-token")
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    import main
    main._free_tier_usage.clear()
    # Exhaust the free tier for this test IP → the paywall answers 402.
    main._free_tier_usage["127.0.0.1"] = 999
    yield main.app.test_client()
    main._free_tier_usage.clear()


def _get_402(client, path):
    r = client.get(path)
    assert r.status_code == 402, f"{path}: expected 402, got {r.status_code}"
    return r


def test_payment_required_header_matches_body_field_by_field(client):
    """Header/body parity (ContextIQ x402 Inspector, 18.10): the authoritative
    PAYMENT-REQUIRED header and the body must carry the same payment details —
    same payTo bytes, same atomic units, canonical CAIP-2 network, no
    base/base-mainnet variants in the mirrors."""
    r = _get_402(client, "/api/v1/whaleflow")
    header = json.loads(
        base64.b64decode(r.headers["PAYMENT-REQUIRED"]).decode())
    b = r.get_json()
    h_acc = header["accepts"]

    # the three accepts mirrors are byte-for-byte the header's accepts
    assert b["accepts"] == h_acc
    assert b["accepts[]"] == h_acc
    assert b["x402_accepts"] == h_acc

    # canonical EIP-55 payTo everywhere (checksum fix, 19.10 — bytes are
    # identical, only the register changed; wallet untouched)
    CANON = "0xd4cdA900839c0feD4374EE37EA0dbe8E4C6fd08f"
    acc0 = h_acc[0]
    assert acc0["payTo"] == CANON
    assert b["x402_recipient"] == CANON
    assert b["payment"]["receiver_address"] == CANON
    assert b["x402_network"] == acc0["network"] == "eip155:8453"
    assert b["payment"]["network"] == acc0["network"]
    assert b["payment"]["chain"] == acc0["network"]
    assert b["x402_recipient"] == acc0["payTo"]
    assert b["payment"]["receiver_address"] == acc0["payTo"]
    assert b["x402_amount"] == acc0["amount"]           # atomic, not decimal
    assert b["payment"]["amount_usdc"] == int(acc0["amount"])
    assert b["x402_token_contract"] == acc0["asset"]
    assert b["payment"]["token_contract"] == acc0["asset"]
    assert b["x402_chain_id"] == 8453
    # legacy string variants must be gone from the mirrors
    body_dump = json.dumps(b)
    assert '"base-mainnet"' not in body_dump
    assert b["payment"].get("chain") != "base"
    assert b["payment"].get("network") != "base"


def test_402_carries_no_store_on_every_paid_route(client):
    """(а) Cache-Control: no-store — a cached challenge breaks settlement."""
    for path in ROUTES:
        r = _get_402(client, path)
        assert r.headers.get("Cache-Control") == "no-store", (
            path, r.headers.get("Cache-Control"))


def test_402_cors_exposes_payment_headers(client):
    """(б) ACAO + Expose-Headers with the exact names from the live curl."""
    r = _get_402(client, "/api/v1/signal")
    assert r.headers.get("Access-Control-Allow-Origin") == "*"
    expose = r.headers.get("Access-Control-Expose-Headers", "")
    have = {h.strip().lower() for h in expose.split(",") if h.strip()}
    for name in REQUIRED_EXPOSE:
        assert name.lower() in have, f"missing {name} in {expose!r}"
    # …and the same on the other two paid routes (еднакво на всичките три).
    for path in ("/api/v1/whaleflow", "/api/bot-status"):
        r = _get_402(client, path)
        assert r.headers.get("Access-Control-Allow-Origin") == "*", path
        assert r.headers.get("Cache-Control") == "no-store", path


def test_402_keeps_existing_headers_body_and_amounts(client):
    """(в) Регресия: старите 402 header-и, тялото и сумите са непроменени."""
    for path, amount in ROUTES.items():
        r = _get_402(client, path)
        # pre-existing payment headers (werkzeug headers are case-insensitive)
        assert r.headers.get("X-Payment-Required") == "x402"
        assert r.headers.get("X-Payment-Address")
        assert r.headers.get("X-Payment-Amount-USDC") == amount
        assert r.headers.get("X-Payment-Chain") == "base"
        assert r.headers.get("X-Payment-Token-Contract")
        assert r.headers.get("WWW-Authenticate", "").startswith(
            'x402 realm="kristo-intelligence"')
        # canonical v2 challenge header + body
        pr = r.headers.get("PAYMENT-REQUIRED")
        assert pr, "PAYMENT-REQUIRED header missing"
        decoded = json.loads(base64.b64decode(pr))
        assert decoded["x402Version"] == 2
        body = r.get_json()
        assert body["x402Version"] == 2
        assert body["accepts"][0]["amount"]
        assert body["accepts"][0]["payTo"].lower().startswith("0xd4cd")


def test_cors_stays_scoped_to_402(client):
    """Обхват: публичният 200 НЕ получава CORS (and no no-store)."""
    r = client.get("/health")
    assert r.status_code == 200
    assert "Access-Control-Allow-Origin" not in r.headers
    assert r.headers.get("Cache-Control") != "no-store"