# -*- coding: utf-8 -*-
"""GET /api/v1/signal — cheap paid route returning an actual agent signal."""
import pytest


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("ADMIN_API_TOKEN", "t")
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    import main
    sample = {"generated_at": "2026-09-01T00:00:00+00:00", "signals": [
        {"token": "ETH", "action": "recommend_buy", "confidence": 0.82,
         "price_usd": 2501.2, "note": "momentum + positive funding"},
        {"token": "ONDO", "action": "monitor", "confidence": 0.41,
         "price_usd": 0.38, "note": "stale price — reduced confidence"},
    ]}
    monkeypatch.setattr(main, "_latest_signals", sample)
    return main.app.test_client()


def test_signal_route_returns_signals(client):
    r = client.get("/api/v1/signal")
    assert r.status_code == 200
    payload = r.get_json()
    assert payload["price_usdc"] == pytest.approx(0.003)
    assert len(payload["signals"]) == 2
    top = payload["signals"][0]
    assert top["token"] == "ETH" and top["action"] == "recommend_buy"


def test_signal_route_is_paid_when_free_tier_exhausted(client, monkeypatch):
    import main
    monkeypatch.setattr(main, "FREE_TIER_LIMIT", 0)
    r = client.get("/api/v1/signal")
    assert r.status_code == 402
    body = r.get_json()
    assert body["x402_accepts"] == ["tx_hash"] or body.get("accepts")


def test_signal_in_price_map_and_paid_set():
    import main
    assert main.X402_PRICE_MAP["/api/v1/signal"] == pytest.approx(0.003)
    assert "/api/v1/signal" in main.X402_PAID_ENDPOINTS
