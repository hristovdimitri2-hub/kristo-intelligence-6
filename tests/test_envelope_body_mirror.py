# -*- coding: utf-8 -*-
"""envelope-body-mirror (x402 Doctor, 21.10) — точната логика на чека.

Fizzl13/x402-doctor lib/diagnose.js:
    JSON.stringify(bodyJson.accepts) === JSON.stringify(decoded.accepts)
— STRICT key-order string compare. jsonify() сортира ключовете
алфавитно (app.json.sort_keys=True, Flask 3.x), а PAYMENT-REQUIRED
header payload-ът е json.dumps в insertion order → еднакви по стойност
accepts[] се сравняваха НЕравни → warn и на 6-те рута.

Тези тестове закачат точно това сравнение (не „на око").
"""
import base64
import json

import pytest

ROUTES = ("/api/v1/signal", "/api/v1/whaleflow", "/api/stats",
          "/api/bot-status", "/api/sales", "/api/arb/opportunities")


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-admin-token")
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    import main
    main._free_tier_usage.clear()
    # Exhaust free tier → every paid route answers 402 (the challenge).
    main._free_tier_usage["127.0.0.1"] = 999
    yield main.app.test_client()
    main._free_tier_usage.clear()


def _js_stringify(obj):
    """JS JSON.stringify: compact separators; key order = order in text."""
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=True)


def _decode_header(response):
    hdr = response.headers.get("PAYMENT-REQUIRED")
    assert hdr, "PAYMENT-REQUIRED header missing"
    padded = hdr + "=" * (-len(hdr) % 4)
    return json.loads(base64.b64decode(padded).decode())


@pytest.mark.parametrize("route", ROUTES)
def test_body_accepts_stringify_equals_header(client, route):
    """THE exact Doctor envelope-body-mirror comparison, on all 6 routes."""
    r = client.get(route)
    assert r.status_code == 402
    dec = _decode_header(r)
    body = r.get_json()
    # get_json() returns dicts in TEXT order — same as JS JSON.parse.
    assert _js_stringify(body["accepts"]) == _js_stringify(dec["accepts"]), (
        "body accepts[] must stringify identically to the header challenge "
        "(key order included) — otherwise x402 Doctor warns "
        "envelope-body-mirror")
    # body carries two mirror aliases of accepts — they must agree too
    assert _js_stringify(body["accepts[]"]) == _js_stringify(dec["accepts"])
    assert _js_stringify(body["x402_accepts"]) == _js_stringify(
        dec["accepts"])


@pytest.mark.parametrize("route", ROUTES)
def test_values_unchanged_by_unsorted_body(client, route):
    """Key ORDER was the fix — values must stay byte-equal to the header."""
    r = client.get(route)
    assert r.status_code == 402
    dec = _decode_header(r)
    body = r.get_json()
    assert body["accepts"] == dec["accepts"]
    assert body["resource"]["url"] == dec["resource"]["url"]
    # prices / payTo untouched (guards from the task boundaries)
    assert body["accepts"][0]["payTo"] == dec["accepts"][0]["payTo"]
    assert body["accepts"][0]["amount"] == dec["accepts"][0]["amount"]


@pytest.mark.parametrize("route", ROUTES)
def test_plain_text_body_is_valid_json(client, route):
    """Ръчният Response трябва да остане валиден JSON (без сортиране)."""
    r = client.get(route)
    raw = r.get_data(as_text=True)
    parsed = json.loads(raw)
    assert parsed["x402Version"] == 2
    assert parsed["error"] == "payment_required"