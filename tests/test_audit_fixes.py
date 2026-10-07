# -*- coding: utf-8 -*-
"""
Одит фиксове (07.10.2026), всеки с тест:

  а5 — преди доставка receipt.status == 1, иначе fail-closed (без доставка);
  г1 — EXTENSION-RESPONSES санитизация (CR/LF strip + таван 8KB + try/around);
  б2 — precheck: valid_before <= now + 60s (горна граница на прозореца).
"""
import base64
import json
import sys
import time
import types

import pytest

USDC = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"
PAYTO = "0xd4cdA900839C0FED4374EE37EA0DBE8e4c6fd08f"
TX = "0x" + "cd" * 32
PAYER = "0x" + "aa" * 20


def _payment_header(nonce="0x" + "11" * 32) -> str:
    now = int(time.time())
    auth = {"from": PAYER, "to": PAYTO, "value": 5000,
            "validAfter": 0, "validBefore": now + 55, "nonce": nonce}
    payload = {"payload": {"authorization": auth},
               "signature": "0x" + "ab" * 65}
    return base64.urlsafe_b64encode(
        json.dumps(payload).encode()).decode().rstrip("=")


def _install_web3(monkeypatch, receipt=None, raise_missing=False, head=10 ** 9):
    """Fake web3 module за стандартния rail (nonce-търсене + receipt + C2)."""
    fake = types.ModuleType("web3")

    class _Eth:
        block_number = head

        def get_transaction_receipt(self, tx):
            if raise_missing:
                raise ValueError(f"receipt not found: {tx}")
            return receipt

        def get_logs(self, spec):
            return []

    class _W3:
        HTTPProvider = staticmethod(
            lambda url, request_kwargs=None: ("fake", url))

        def __init__(self, provider=None, *args, **kwargs):
            self.eth = _Eth()

        @staticmethod
        def to_checksum_address(addr):
            return addr

    fake.Web3 = _W3
    monkeypatch.setitem(sys.modules, "web3", fake)


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("ADMIN_API_TOKEN", "t")
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    import main
    from services import connectors
    monkeypatch.setattr(main, "FREE_TIER_LIMIT", 0)
    main._free_tier_usage.clear()
    monkeypatch.setattr(connectors, "verify_standard_payment",
                        lambda h, req: (True, PAYER, "verified"))
    monkeypatch.setattr(connectors, "settle_standard_payment",
                        lambda h, req: (TX, "settled", None))
    # изолация на durable store-а: тестовете не пишат редове в реалната база
    monkeypatch.setattr(main.dashboard_db, "claim_payment_tx",
                        lambda *a, **kw: True)
    monkeypatch.setattr(main.dashboard_db, "mark_payment_delivered",
                        lambda *a, **kw: True)
    monkeypatch.setattr(main.dashboard_db, "release_payment_retry_slot",
                        lambda *a, **kw: True)
    monkeypatch.setattr(main.dashboard_db, "record_sale", lambda *a, **kw: None)
    # ... нито в RAM sales/daily stats (иначе тестове за „нулева база"
    # след този модул виждат фалшива продажба)
    monkeypatch.setattr(main, "_record_real_sale", lambda **kw: None)
    return main.app.test_client()


# ── а5: receipt.status == 1 или нищо не се доставя ─────────────────────────

def test_a5_reverted_receipt_fails_closed_without_delivery(client, monkeypatch):
    import main
    events = []
    monkeypatch.setattr(main.dashboard_db, "record_guard_event",
                        lambda kind, **kw: events.append(kind))
    _install_web3(monkeypatch, receipt={"status": 0, "blockNumber": 100,
                                        "blockHash": "0x" + "cd" * 32})
    r = client.get("/api/stats", headers={"PAYMENT-SIGNATURE": _payment_header()})
    assert r.status_code == 401
    body = r.get_json()
    assert "settlement_not_confirmed" in body.get("reason", "")
    assert "PAYMENT-RESPONSE" not in r.headers      # никаква разписка/доставка
    assert "c2_receipt_status_refused" in events    # fail-closed е логнат


def test_a5_successful_receipt_still_delivers(client, monkeypatch):
    _install_web3(monkeypatch, receipt={"status": 1, "blockNumber": 100,
                                        "blockHash": "0x" + "cd" * 32})
    r = client.get("/api/stats", headers={"PAYMENT-SIGNATURE": _payment_header()})
    assert r.status_code == 200
    assert "PAYMENT-RESPONSE" in r.headers



# ── г1: EXTENSION-RESPONSES санитизация ─────────────────────────────────────

@pytest.fixture()
def main_mod(monkeypatch):
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-admin-token")
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    import main
    return main


def _emit(main_mod, receipt):
    from flask import Response, g
    with main_mod.app.test_request_context():
        g.x402_settlement = json.dumps(
            {"success": True, "transaction": TX, "network": "eip155:8453",
             "payer": PAYER})
        g.x402_extension_receipt = receipt
        resp = Response(status=200)
        return main_mod._emit_payment_response(resp)


def test_g1_strips_crlf_from_passthrough_receipt(main_mod):
    """Фасилитатор може да вмъкне CR/LF дори във валиден base64(JSON) поток —
    b64decode ги игнорира, но raw стойността ги съдържа → header injection."""
    clean = base64.b64encode(json.dumps({"a": 1}).encode()).decode()
    dirty = clean[:4] + "\r\n" + clean[4:]
    resp = _emit(main_mod, dirty)
    value = resp.headers["EXTENSION-RESPONSES"]
    assert "\r" not in value and "\n" not in value
    decoded = json.loads(base64.b64decode(value + "=" * (-len(value) % 4)))
    assert decoded == {"a": 1}                          # съдържанието е цяло


def test_g1_garbage_injection_cannot_survive_sanitizer(main_mod):
    clean = base64.b64encode(json.dumps({"a": 1}).encode()).decode()
    dirty = clean[:4] + "\r\nInjected: evil" + clean[4:]
    resp = _emit(main_mod, dirty)
    value = resp.headers.get("EXTENSION-RESPONSES", "")
    assert "\r" not in value and "\n" not in value
    assert "Injected" not in value                      # никакъв header injection
    assert resp.status_code == 200                      # отговорът е жив


def test_g1_caps_oversized_receipt_at_8kb(main_mod):
    huge = base64.b64encode(
        json.dumps({"pad": "x" * 20000}).encode()).decode()
    resp = _emit(main_mod, huge)
    value = resp.headers["EXTENSION-RESPONSES"]
    assert len(value) == 8192                           # таванът държи


def test_g1_broken_receipt_never_breaks_the_response(main_mod):
    resp = _emit(main_mod, {"bad": object()})           # json.dumps ще хвърли
    assert resp.status_code == 200                      # отговорът е жив
    assert "EXTENSION-RESPONSES" not in resp.headers    # и без счупен header
    assert "PAYMENT-RESPONSE" in resp.headers           # основната разписка си е там


# ── б2: горна граница на авторизационния прозорец ──────────────────────────

def _precheck_payload(valid_before: int) -> dict:
    now = int(time.time())
    auth = {"from": PAYER, "to": PAYTO, "value": "5000",
            "validAfter": str(now - 10), "validBefore": str(valid_before),
            "nonce": "0x" + "33" * 32}
    return {
        "accepted": {"scheme": "exact", "network": "eip155:8453",
                     "amount": "5000", "asset": USDC, "payTo": PAYTO,
                     "extra": {"name": "USD Coin", "version": "2"}},
        "payload": {"signature": "0x" + "44" * 65, "authorization": auth},
    }


def _reqs() -> dict:
    return {"amount": "5000", "asset": USDC, "payTo": PAYTO}


def test_b2_rejects_window_longer_than_60s():
    from services.connectors import precheck_payment_payload
    now = int(time.time())
    problems = precheck_payment_payload(_precheck_payload(now + 600), _reqs())
    assert any("window too long" in p for p in problems)


def test_b2_accepts_window_up_to_60s():
    from services.connectors import precheck_payment_payload
    now = int(time.time())
    for valid_before in (now + 55, now + 60):
        problems = precheck_payment_payload(
            _precheck_payload(valid_before), _reqs())
        assert not any("window too long" in p for p in problems), \
            f"validBefore=now+{valid_before - now}s трябваше да мине"
    # и чист прозорец — никакви проблеми изобщо
    assert precheck_payment_payload(_precheck_payload(now + 55), _reqs()) == []


def test_b2_window_fix_matches_demo_client():
    """Клиентът подписва с прозорец ≤60s — иначе сам себе си отхвърля."""
    import re
    src = open("scripts/demo_sponsored_pay.py", encoding="utf-8").read()
    assert re.search(r"time\.time\(\)\)\s*\+\s*(5[0-9]|60)\b", src), \
        "demo клиентът трябва да подписва с validBefore ≤ now+60"

def test_a5_missing_receipt_fails_closed(client, monkeypatch):
    import main
    monkeypatch.setattr(main.dashboard_db, "record_guard_event",
                        lambda kind, **kw: None)
    _install_web3(monkeypatch, raise_missing=True)
    r = client.get("/api/stats", headers={"PAYMENT-SIGNATURE": _payment_header()})
    assert r.status_code == 401
    assert "settlement_not_confirmed" in r.get_json().get("reason", "")
