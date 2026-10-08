# -*- coding: utf-8 -*-
"""
Facilitator receipt propagation tests (2026-10-07 fixes):

  (а) _facilitator_post returns response headers too
  (б) settle_standard_payment passes the extension receipt through
  (в) _emit_payment_response emits EXTENSION-RESPONSES (base64 JSON)
  (г) CDP 400 with transaction + "already" -> adopted as success
  (д) coingecko Base44 fallback logs resp.url
"""
import base64
import json
import logging
import urllib.request

import pytest


def _minimal_header() -> str:
    """Decodable PAYMENT-SIGNATURE payload (no transaction shape)."""
    payload = {"x402Version": 2,
               "accepted": {"scheme": "exact", "network": "eip155:8453",
                            "amount": "5000"},
               "payload": {"signature": "0x00",
                           "authorization": {"nonce": "0x" + "11" * 32}}}
    return base64.urlsafe_b64encode(
        json.dumps(payload).encode()).decode().rstrip("=")


# ── (а) headers се връщат ───────────────────────────────────────────────────

def test_facilitator_post_returns_response_headers(monkeypatch):
    from services import connectors

    class _FakeResp:
        status = 200
        headers = {"EXTENSION-RESPONSES": "eyJhIjoxfQ=="}

        def read(self):
            return b'{"success": true}'

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _FakeResp())
    status, parsed, raw, headers = connectors._facilitator_post(
        "https://facilitator.example", "settle", {})
    assert status == 200 and parsed == {"success": True}
    assert headers["EXTENSION-RESPONSES"] == "eyJhIjoxfQ=="


# ── (г) adopt already-settled tx ────────────────────────────────────────────

def test_adopt_already_settled_requires_transaction_and_word():
    from services.connectors import _adopt_already_settled as adopt
    body = {"success": False,
            "errorMessage": "authorization nonce already submitted; "
                            "transaction already on-chain",
            "errorReason": "invalid_payload", "transaction": "0x" + "cd" * 32}
    assert adopt(body) == "0x" + "cd" * 32
    # без "already" — не се осиновява чужд tx
    assert adopt({"success": False, "errorReason": "invalid_payload",
                  "transaction": "0xdead"}) is None
    # без transaction — не
    assert adopt({"success": False, "errorMessage": "already used"}) is None
    # успех — редовният път си го брои
    assert adopt({"success": True, "transaction": "0x1"}) is None
    assert adopt(None) is None


def test_settle_adopts_already_settled_cdp_tx(monkeypatch):
    from services import connectors
    header = _minimal_header()
    monkeypatch.delenv("WALLET_PRIVATE_KEY", raising=False)
    monkeypatch.setattr(connectors, "_self_broadcast_settlement",
                        lambda p: (None, "skip"))
    monkeypatch.setattr(connectors, "_facilitator_chain",
                        lambda: [("cdp", "https://api.cdp.coinbase.com/platform/v2/x402")])
    monkeypatch.setattr(connectors, "_cdp_jwt", lambda *a, **k: ("tok", ""))
    monkeypatch.setattr(
        connectors, "_facilitator_post",
        lambda *a, **k: (400,
                         {"success": False,
                          "errorMessage": "authorization nonce already "
                                          "submitted; transaction already "
                                          "on-chain",
                          "errorReason": "invalid_payload",
                          "transaction": "0x" + "cd" * 32}, "raw", {}))
    tx, detail, receipt = connectors.settle_standard_payment(header, {})
    assert tx == "0x" + "cd" * 32
    assert detail == "settled_already_onchain"
    assert receipt is None


def test_settle_without_already_word_still_fails(monkeypatch):
    from services import connectors
    header = _minimal_header()
    monkeypatch.delenv("WALLET_PRIVATE_KEY", raising=False)
    monkeypatch.setattr(connectors, "_self_broadcast_settlement",
                        lambda p: (None, "skip"))
    monkeypatch.setattr(connectors, "_facilitator_chain",
                        lambda: [("cdp", "https://api.cdp.coinbase.com/platform/v2/x402")])
    monkeypatch.setattr(connectors, "_cdp_jwt", lambda *a, **k: ("tok", ""))
    monkeypatch.setattr(
        connectors, "_facilitator_post",
        lambda *a, **k: (400, {"success": False, "errorReason": "invalid_payload",
                               "transaction": "0x" + "ee" * 32}, "raw", {}))
    tx, detail, receipt = connectors.settle_standard_payment(header, {})
    assert tx is None
    assert "cdp:invalid_payload" == detail


# ── (в) EXTENSION-RESPONSES в отговора ──────────────────────────────────────

@pytest.fixture()
def main_mod(monkeypatch):
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-admin-token")
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    import main
    return main


def _emit(main_mod, receipt, settlement=None):
    from flask import Response, g
    with main_mod.app.test_request_context():
        if settlement is not None:
            g.x402_settlement = settlement
        if receipt is not None:
            g.x402_extension_receipt = receipt
        resp = Response(status=200)
        return main_mod._emit_payment_response(resp)


def test_emit_encodes_dict_receipt_as_base64_json(main_mod):
    receipt = {"bazaar": {"status": "listed"}}
    resp = _emit(main_mod, receipt,
                 settlement=json.dumps({"success": True, "transaction": "0x1"}))
    header = resp.headers["EXTENSION-RESPONSES"]
    decoded = json.loads(base64.b64decode(header + "=" * (-len(header) % 4)))
    assert decoded == receipt
    assert "PAYMENT-RESPONSE" in resp.headers   # редовната разписка си остава


def test_emit_passes_through_already_encoded_receipt(main_mod):
    already = base64.b64encode(
        json.dumps({"bazaar": {"status": "processing"}}).encode()).decode()
    resp = _emit(main_mod, already)
    assert resp.headers["EXTENSION-RESPONSES"] == already


def test_emit_skips_garbage_and_absent_receipt(main_mod):
    resp = _emit(main_mod, "!!!not-json-not-base64!!!")
    assert "EXTENSION-RESPONSES" not in resp.headers
    resp2 = _emit(main_mod, None)
    assert "EXTENSION-RESPONSES" not in resp2.headers


# ── (д) Base44 fallback логва resp.url ──────────────────────────────────────

def test_base44_fallback_logs_resp_url(monkeypatch, caplog):
    from services.coingecko import CoinGeckoClient

    class _BadResp:
        ok = False
        status_code = 404
        url = "https://api.base44.com/coingecko/ping"

    client = CoinGeckoClient(api_key="k")
    monkeypatch.setattr(client._session, "get",
                        lambda *a, **k: _BadResp())
    monkeypatch.setattr(client, "_public_get_with_backoff",
                        lambda path, params, headers: {})
    # FIX #5: Base44 fallback now logs at WARNING level for operator visibility
    with caplog.at_level(logging.WARNING):
        client._get("/ping")
    assert "https://api.base44.com/coingecko/ping" in caplog.text or "Base44 proxy unavailable" in caplog.text
    assert "404" in caplog.text
    assert client._base44_available is False   # и превключва към fallback
