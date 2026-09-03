from datetime import timedelta

import pytest
import requests

from services import market_data
from services.telegram_sales import _format_bulletin_text
from services.trading_agent import TradingAgent


class FakeResponse:
    def __init__(self, payload=None, status_code=200, headers=None):
        self.payload = payload or {}
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)

    def json(self):
        return self.payload


@pytest.fixture(autouse=True)
def reset_market_data_cache(monkeypatch):
    with market_data._CACHE_LOCK:
        market_data._CACHE.clear()
        market_data._COINGECKO_STATUS.clear()
        market_data._COINGECKO_COOLDOWN_UNTIL = None
    monkeypatch.setattr(market_data, "_CACHE_TTL", timedelta(minutes=15))
    monkeypatch.setattr(market_data, "_STALE_CACHE_TTL", timedelta(hours=1))
    monkeypatch.setattr(market_data, "_COINGECKO_MAX_ATTEMPTS", 2)
    monkeypatch.setattr(market_data, "_COINGECKO_BACKOFF_BASE_SECONDS", 0)
    monkeypatch.setattr(market_data, "_COINGECKO_BACKOFF_MAX_SECONDS", 1)


def test_coingecko_price_cache_prevents_repeated_requests(monkeypatch):
    calls = []

    def fake_get(url, **kwargs):
        calls.append(url)
        return FakeResponse({"ethereum": {"usd": 3210}})

    monkeypatch.setattr(market_data.requests, "get", fake_get)

    first = market_data.fetch_coingecko_prices(["eth"])
    second = market_data.fetch_coingecko_prices(["eth"])

    assert first["eth"]["price_usd"] == 3210
    assert second == first
    assert len(calls) == 1
    assert market_data.get_coingecko_cache_status(["cg_prices_eth"])["state"] == "cached"


def test_rate_limit_serves_stale_cache_then_recovers(monkeypatch):
    responses = [
        FakeResponse({"ethereum": {"usd": 100}}),
        FakeResponse(status_code=429),
        FakeResponse({"ethereum": {"usd": 200}}),
    ]
    calls = []

    def fake_get(url, **kwargs):
        calls.append(url)
        return responses.pop(0)

    monkeypatch.setattr(market_data.requests, "get", fake_get)
    monkeypatch.setattr(market_data, "_CACHE_TTL", timedelta(seconds=1))

    assert market_data.fetch_coingecko_prices(["eth"])["eth"]["price_usd"] == 100
    with market_data._CACHE_LOCK:
        market_data._CACHE["cg_prices_eth"]["ts"] = market_data._now() - timedelta(seconds=2)

    stale = market_data.fetch_coingecko_prices(["eth"])
    stale_status = market_data.get_coingecko_cache_status(["cg_prices_eth"])
    assert stale["eth"]["price_usd"] == 100
    assert stale_status["state"] == "stale"
    assert len(calls) == 2  # initial request plus one fast refresh attempt

    # The cooldown avoids another upstream call and continues to return only
    # explicitly marked stale data.
    assert market_data.fetch_coingecko_prices(["eth"]) == stale
    assert len(calls) == 2

    market_data._COINGECKO_COOLDOWN_UNTIL = None
    recovered = market_data.fetch_coingecko_prices(["eth"])
    assert recovered["eth"]["price_usd"] == 200
    assert market_data.get_coingecko_cache_status(["cg_prices_eth"])["state"] == "live"


def test_rate_limit_honors_retry_after_without_repeating_request(monkeypatch):
    calls = []

    def fake_get(url, **kwargs):
        calls.append(url)
        return FakeResponse(status_code=429, headers={"Retry-After": "60"})

    monkeypatch.setattr(market_data.requests, "get", fake_get)
    assert market_data.fetch_coingecko_prices(["eth"]) == {}
    assert len(calls) == 1
    assert market_data.get_coingecko_cache_status(["cg_prices_eth"])["state"] == "unavailable"
    assert (market_data._COINGECKO_COOLDOWN_UNTIL - market_data._now()).total_seconds() >= 59


def test_cold_cache_server_failure_retries_a_bounded_number_of_times(monkeypatch):
    calls = []

    def fake_get(url, **kwargs):
        calls.append(url)
        return FakeResponse(status_code=503)

    monkeypatch.setattr(market_data.requests, "get", fake_get)
    assert market_data.fetch_coingecko_prices(["eth"]) == {}
    assert len(calls) == 2


def test_cache_status_age_is_calculated_when_dashboard_reads_it():
    market_data._set_cache("cg_prices_eth", {"ethereum": {"usd": 100}})
    market_data._set_coingecko_status("cg_prices_eth", "live")

    with market_data._CACHE_LOCK:
        market_data._CACHE["cg_prices_eth"]["ts"] = (
            market_data._now() - market_data._CACHE_TTL - timedelta(seconds=1)
        )
    stale = market_data.get_coingecko_cache_status(["cg_prices_eth"])
    assert stale["state"] == "stale"
    assert stale["age_seconds"] >= int(market_data._CACHE_TTL.total_seconds())

    with market_data._CACHE_LOCK:
        market_data._CACHE["cg_prices_eth"]["ts"] = (
            market_data._now() - market_data._STALE_CACHE_TTL - timedelta(seconds=1)
        )
    expired = market_data.get_coingecko_cache_status(["cg_prices_eth"])
    assert expired["state"] == "unavailable"
    assert expired["detail"] == "cached snapshot expired"


def test_telegram_bulletin_marks_stale_coingecko_data():
    bulletin = _format_bulletin_text(
        {
            "freshness": {"coingecko": {"state": "stale", "age_seconds": 120}},
            "fear_greed_index": {},
            "tokens": {},
        }
    )

    assert "кеширани данни" in bulletin
    assert "live обновяването е временно ограничено" in bulletin


def test_rate_limited_fallback_labels_fresh_cache_as_cached_not_stale(monkeypatch):
    """Production race (PayAPI 3rd canary): a concurrent request refreshes
    the class-level cache while this upstream call fails.  Serving that
    entry must report 'cached' — never 'stale age=0'."""
    from services.coingecko import CoinGeckoClient

    client = CoinGeckoClient()
    data = {"eth": 2390.84, "ondo": 0.3407, "kaito": 0.3030, "degen": 0.0010}

    calls = {"n": 0}

    def fake_cached(cache_key, *, allow_stale=False):
        calls["n"] += 1
        if calls["n"] == 1:
            return None            # first check misses (pre-refresh state)
        return dict(data), 0       # fallback finds a just-stored entry

    def failing_get(path, params=None):
        raise RuntimeError("CoinGecko rate-limit cooldown is active")

    monkeypatch.setattr(client, "_cached_prices", fake_cached)
    monkeypatch.setattr(client, "_get", failing_get)

    prices = client.get_prices(["eth", "ondo", "kaito", "degen"])
    assert prices["eth"] == 2390.84
    assert client.last_price_status == {"state": "cached", "age_seconds": 0}

    # a genuinely old fallback entry (beyond the normal TTL) is still stale
    monkeypatch.setattr(
        client, "_cached_prices",
        lambda cache_key, *, allow_stale=False: (dict(data), 950) if allow_stale else None)
    client.get_prices(["eth", "ondo", "kaito", "degen"])
    assert client.last_price_status["state"] == "stale"
    assert client.last_price_status["age_seconds"] == 950


def test_coingecko_request_attaches_demo_api_key(monkeypatch):
    """The bulletin/dashboard path must authenticate to CoinGecko with
    COINGECKO_API_KEY (x-cg-demo-api-key) — without it Render's shared IP
    429s and the bulletin serves 'stale cache' warnings forever."""
    monkeypatch.setattr(market_data, "_COINGECKO_COOLDOWN_UNTIL", None)
    captured = {}

    class FakeResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return {"ok": True}

    def fake_get(url, **kwargs):
        captured["headers"] = kwargs.get("headers")
        return FakeResponse()

    monkeypatch.setattr(market_data.requests, "get", fake_get)

    monkeypatch.setenv("COINGECKO_API_KEY", "CG-test-key")
    market_data._coingecko_request("cg_demokey_test_1", "/simple/price",
                                   params={"ids": "ethereum"})
    assert captured["headers"].get("x-cg-demo-api-key") == "CG-test-key"

    monkeypatch.delenv("COINGECKO_API_KEY", raising=False)
    market_data._coingecko_request("cg_demokey_test_2", "/simple/price",
                                   params={"ids": "ethereum"})
    assert "x-cg-demo-api-key" not in captured["headers"]


def test_trading_agent_batches_prices_and_labels_stale_cache():
    class CachedClient:
        def __init__(self):
            self.calls = []
            self.last_price_status = {"state": "stale", "age_seconds": 90}

        def get_prices(self, tokens):
            self.calls.append(tokens)
            return {"eth": 3000.0, "ondo": 1.0}

    client = CachedClient()
    agent = TradingAgent(
        coingecko_client=client,
        signals={
            "eth": {"symbol": "ETH", "confidence": 0.8, "action": "buy"},
            "ondo": {"symbol": "ONDO", "confidence": 0.8, "action": "buy"},
        },
    )

    decisions = agent.evaluate()

    assert client.calls == [["eth", "ondo"]]
    assert decisions["eth"]["market_data_status"] == "stale"
    assert "stale cached price" in decisions["eth"]["note"]