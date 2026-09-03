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
         "price_usd": 2501.2, "reasoning": "Core L1 / gas asset on Base",
         "note": "price=$2501.2000"},
        {"token": "ONDO", "action": "monitor", "confidence": 0.41,
         "price_usd": 0.38, "reasoning": "stale price — reduced confidence",
         "note": "stale price — reduced confidence"},
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


def test_signal_route_price_usd_is_number_and_reasoning_present(client, monkeypatch):
    """PayAPI reviewer (2nd verified route): price_usd must be a real number
    (not null, not embedded in note) and every signal needs a one-line
    reasoning naming the main driver."""
    import main
    # other tests in this module consume the shared per-IP free-tier counter
    monkeypatch.setattr(main, "FREE_TIER_LIMIT", 1000)
    r = client.get("/api/v1/signal")
    assert r.status_code == 200
    for sig in r.get_json()["signals"]:
        assert isinstance(sig["price_usd"], (int, float))
        assert sig["price_usd"] > 0
        assert isinstance(sig["reasoning"], str) and sig["reasoning"].strip()
        assert "price=" not in sig["reasoning"]


def test_publish_agent_signals_maps_price_and_reasoning(monkeypatch):
    """Raw TradingAgent decisions (key `price_usd`) must land in the
    published schema with a numeric price and non-empty reasoning — this
    was the null-price_usd bug PayAPI's reviewer found."""
    import main
    monkeypatch.setattr(
        main, "_latest_signals", {"generated_at": None, "signals": []})
    decisions = {
        "eth": {
            "symbol": "ETH", "price_usd": 2387.78, "bias": "BULLISH",
            "confidence": 0.78, "action": "recommend_buy", "approved": True,
            "risk_score": 40, "risk_flags": [], "suggested_position_usd": 780.0,
            "narrative": "Core L1 / gas asset on Base; staking yield.",
            "reasoning": "Core L1 / gas asset on Base; staking yield.",
            "note": "price=$2387.7800", "market_data_status": "live",
            "source": "baseline",
        },
        "degen": {
            "symbol": "DEGEN", "price_usd": None, "bias": "SPECULATIVE",
            "confidence": 0.36, "action": "monitor", "approved": True,
            "risk_score": 55, "risk_flags": [], "suggested_position_usd": 0.0,
            "narrative": "Base-native social token.",
            "reasoning": "Base-native social token.; live price "
                         "unavailable — confidence reduced",
            "note": "no live price — reduced confidence",
            "market_data_status": "unavailable", "source": "baseline",
        },
    }
    main._publish_agent_signals(decisions)
    with main._lock:
        published = {s["token"]: s for s in main._latest_signals["signals"]}
    eth = published["eth"]
    assert eth["price_usd"] == pytest.approx(2387.78)
    assert "Core L1" in eth["reasoning"]
    # no-price signals keep a null price but still carry a reason
    degen = published["degen"]
    assert degen["price_usd"] is None
    assert degen["reasoning"].strip()
    # sorted by confidence, highest first
    order = [s["token"] for s in main._latest_signals["signals"]]
    assert order == ["eth", "degen"]


def test_trading_agent_age_zero_is_never_stale():
    """PayAPI reviewer (3rd canary): a cache that is 0 seconds old is NOT
    stale.  The old check taxed every confidence by exactly 10% and told
    buyers to verify prices that already matched CoinGecko."""
    from services.trading_agent import TradingAgent

    class FreshButMislabelled:
        last_price_status = {"state": "stale", "age_seconds": 0}

        def get_prices(self, tokens):
            return {t: 2390.84 for t in tokens}

    signals = {"eth": {"symbol": "ETH", "bias": "BULLISH", "confidence": 0.78,
                       "narrative": "Core L1 / gas asset on Base",
                       "action": "monitor"}}
    d = TradingAgent(coingecko_client=FreshButMislabelled(),
                     signals=signals).evaluate()["eth"]
    assert d["confidence"] == pytest.approx(0.78)      # no 10% tax
    assert d["note"] == "price=$2390.8400"             # honest note
    assert "stale" not in d["note"].lower()
    assert "stale" not in d["reasoning"].lower()


def test_trading_agent_emits_reasoning_and_numeric_price():
    """TradingAgent itself must emit reasoning + numeric price_usd for live,
    stale, and missing price states."""
    from services.trading_agent import TradingAgent

    class LiveClient:
        last_price_status = {"state": "live", "age_seconds": 0}

        def get_prices(self, tokens):
            return {t: 2387.78 for t in tokens}

    class StaleClient(LiveClient):
        last_price_status = {"state": "stale", "age_seconds": 420}

    class DeadClient:
        last_price_status = {"state": "unavailable", "age_seconds": None}

        def get_prices(self, tokens):
            return {t: None for t in tokens}

    signals = {"eth": {"symbol": "ETH", "bias": "BULLISH", "confidence": 0.78,
                       "narrative": "Core L1 / gas asset on Base",
                       "action": "monitor"}}

    live = TradingAgent(coingecko_client=LiveClient(), signals=signals).evaluate()["eth"]
    assert live["price_usd"] == pytest.approx(2387.78)
    assert live["reasoning"].startswith("Core L1 / gas asset on Base")
    assert "price=" not in live["reasoning"]

    stale = TradingAgent(coingecko_client=StaleClient(), signals=signals).evaluate()["eth"]
    assert stale["reasoning"].startswith("Core L1 / gas asset on Base")
    assert "stale" in stale["reasoning"].lower()

    dead = TradingAgent(coingecko_client=DeadClient(), signals=signals).evaluate()["eth"]
    assert dead["price_usd"] is None
    assert dead["reasoning"].startswith("Core L1 / gas asset on Base")
    assert "confidence reduced" in dead["reasoning"]


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
