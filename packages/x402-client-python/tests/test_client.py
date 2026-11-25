# -*- coding: utf-8 -*-
"""Tests for the zero-dependency Python x402 client.

Pure logic only: no network. The live handshake is exercised separately by
``examples/live_dry_run.py``, which spends nothing.
"""

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from kristo_x402_client import (  # noqa: E402
    PAYMENT_REQUIRED_HEADER,
    PAYMENT_SIGNATURE_HEADER,
    PROOF_HEADER,
    KristoX402Client,
    build_payment_proof,
    build_payment_signature_header,
    parse_payment_challenge,
    parse_payment_required_header,
)


def _b64url(text):
    import base64
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def _challenge(**overrides):
    accept = {
        "scheme": "exact",
        "network": "eip155:8453",
        "amount": "10000",
        "asset": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",
        "payTo": "0xB4FcF8ef52b5DC275924AeD2baE94FE6cb7fC844",
        "maxTimeoutSeconds": 300,
        "extra": {"name": "USD Coin", "version": "2"},
    }
    accept.update(overrides)
    payload = {
        "x402Version": 2,
        "resource": {"url": "https://example.test/api/v1/signal"},
        "accepts": [accept],
    }
    return _b64url(json.dumps(payload))


# ── parsing ────────────────────────────────────────────────────────────────
def test_the_v2_header_is_decoded_into_a_challenge():
    challenge = parse_payment_required_header(_challenge())
    assert challenge["rail"] == "v2"
    assert challenge["x402_version"] == 2
    assert challenge["amount_atomic"] == "10000"
    assert challenge["amount"] == 0.01
    assert challenge["recipient"] == "0xB4FcF8ef52b5DC275924AeD2baE94FE6cb7fC844"
    assert challenge["chain_id"] == 8453
    assert challenge["accepted"]["scheme"] == "exact"


def test_a_decimal_amount_is_read_as_usdc_and_a_bare_integer_as_atomic():
    # A decimal "0.005" means 0.005 USDC = 5000 atomic units.
    assert parse_payment_required_header(
        _challenge(amount="0.005"))["amount_atomic"] == "5000"
    # A bare integer "5000" is already atomic.
    assert parse_payment_required_header(
        _challenge(amount="5000"))["amount_atomic"] == "5000"


def test_an_unreadable_header_returns_none_instead_of_raising():
    assert parse_payment_required_header("not-base64!!") is None
    assert parse_payment_required_header("") is None
    assert parse_payment_required_header(None) is None


def test_a_header_without_an_accept_block_returns_none():
    assert parse_payment_required_header(
        _b64url(json.dumps({"x402Version": 2, "accepts": []}))) is None


def test_the_legacy_body_shape_still_parses():
    challenge = parse_payment_challenge({
        "error": "payment_required",
        "x402_amount": "5000",
        "x402_recipient": "0xB4FcF8ef52b5DC275924AeD2baE94FE6cb7fC844",
        "x402_chain_id": 8453,
    })
    assert challenge["rail"] == "legacy"
    assert challenge["amount"] == 0.005
    assert challenge["amount_atomic"] == "5000"


def test_a_body_that_is_not_a_payment_challenge_returns_none():
    assert parse_payment_challenge({"error": "something_else"}) is None
    assert parse_payment_challenge(None) is None


# ── header construction ────────────────────────────────────────────────────
def test_the_signature_header_echoes_the_accept_block():
    challenge = parse_payment_required_header(_challenge())
    header = build_payment_signature_header(
        "0xdeadbeef", {"nonce": "0x01"}, challenge["accepted"])
    decoded = json.loads(
        __import__("base64").urlsafe_b64decode(header + "==").decode())
    assert decoded["x402Version"] == 2
    assert decoded["accepted"]["payTo"] == challenge["recipient"]
    assert decoded["payload"]["signature"] == "0xdeadbeef"
    assert decoded["payload"]["authorization"] == {"nonce": "0x01"}


def test_the_proof_header_carries_the_lowercased_addresses():
    proof = build_payment_proof("0xABC", "0xDEF", 0.005)
    decoded = json.loads(
        __import__("base64").urlsafe_b64decode(proof + "==").decode())
    assert decoded["payer"] == "0xabc"
    assert decoded["transaction_hash"] == "0xdef"
    assert decoded["amount_usdc"] == 0.005


# ── the client's own guarantees ────────────────────────────────────────────
class _StubResponse:
    def __init__(self, status, headers, body):
        self.status = status
        self.headers = headers
        self._body = body.encode() if isinstance(body, str) else body

    def read(self):
        return self._body


def _client_with(monkeypatch, responses, signer=None):
    client = KristoX402Client(pay=signer or (lambda c: {}), auto_pay=True)
    calls = []

    def fake_fetch(url, method, headers, body_bytes):
        calls.append(dict(headers))
        status, hdrs, body = responses.pop(0)
        return status, hdrs, body.encode() if isinstance(body, str) else body

    monkeypatch.setattr(client, "_fetch", fake_fetch)
    return client, calls


def test_auto_pay_false_returns_the_challenge_and_spends_nothing(monkeypatch):
    client = KristoX402Client(auto_pay=False)
    monkeypatch.setattr(client, "_fetch", lambda *a: (
        402, {PAYMENT_REQUIRED_HEADER.lower(): _challenge()}, b"{}"))
    result = client.get("/api/v1/signal")
    assert result["ok"] is False
    assert result["status"] == 402
    assert result["payment_required"]["amount"] == 0.01


def test_a_successful_paid_call_returns_the_body(monkeypatch):
    signed = []

    def signer(challenge):
        signed.append(challenge)
        return {"signature": "0xabc", "authorization": {"nonce": "0x1"}}

    client, calls = _client_with(monkeypatch, [
        (402, {PAYMENT_REQUIRED_HEADER.lower(): _challenge()}, "{}"),
        (200, {}, '{"signal": "buy"}'),
    ], signer)
    result = client.get("/api/v1/signal")
    assert result["ok"] is True
    assert result["data"] == {"signal": "buy"}
    assert len(signed) == 1
    assert PAYMENT_SIGNATURE_HEADER in calls[1]


def test_the_client_signs_at_most_once_per_request(monkeypatch):
    signed = []

    def signer(challenge):
        signed.append(challenge)
        return {"signature": "0xabc", "authorization": {"nonce": "0x1"}}

    client, _ = _client_with(monkeypatch, [
        (402, {PAYMENT_REQUIRED_HEADER.lower(): _challenge()}, "{}"),
        (402, {PAYMENT_REQUIRED_HEADER.lower(): _challenge()}, "{}"),
    ], signer)
    result = client.get("/api/v1/signal")
    assert result["error"] == "payment_outcome_unknown"
    assert len(signed) == 1, "a second signature would be a second charge"


def test_a_425_is_retried_with_the_same_credential(monkeypatch):
    signed = []

    def signer(challenge):
        signed.append(challenge)
        return {"signature": "0xabc", "authorization": {"nonce": "0x1"}}

    client, calls = _client_with(monkeypatch, [
        (402, {PAYMENT_REQUIRED_HEADER.lower(): _challenge()}, "{}"),
        (425, {}, '{"error": "settlement_pending"}'),
        (200, {}, '{"ok": true}'),
    ], signer)
    client.in_flight_delay = 0
    result = client.get("/api/v1/signal")
    assert result["ok"] is True
    assert len(signed) == 1, "the retry must not re-sign"
    assert PAYMENT_SIGNATURE_HEADER in calls[2]


def test_the_legacy_rail_is_used_when_the_body_carries_the_terms(monkeypatch):
    signed = []

    def signer(challenge):
        signed.append(challenge)
        return {"payer": "0xabc", "txHash": "0xdef"}

    client, calls = _client_with(monkeypatch, [
        (402, {}, json.dumps({
            "error": "payment_required",
            "x402_amount": "5000",
            "x402_recipient": "0xB4FcF8ef52b5DC275924AeD2baE94FE6cb7fC844",
        })),
        (200, {}, '{"ok": true}'),
    ], signer)
    result = client.get("/api/sales")
    assert result["ok"] is True
    assert PROOF_HEADER in calls[1]


def test_a_signer_that_returns_nothing_is_a_loud_error(monkeypatch):
    client, _ = _client_with(monkeypatch, [
        (402, {PAYMENT_REQUIRED_HEADER.lower(): _challenge()}, "{}"),
    ], lambda c: None)
    with pytest.raises(TypeError):
        client.get("/api/v1/signal")
