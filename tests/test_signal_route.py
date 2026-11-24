# -*- coding: utf-8 -*-
"""GET /api/v1/signal — cheap paid route returning an actual agent signal."""
import pytest


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("ADMIN_API_TOKEN", "t")
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    import main
    # The default is now 0 (strict x402); this test is about the signal
    # payload, not the paywall, so grant one free call explicitly.
    monkeypatch.setattr(main, "FREE_TIER_LIMIT", 1)
    # Other modules leave 127.0.0.1 in the shared counter (some set it to 999
    # to exhaust the tier), so the budget has to be reset here as well —
    # otherwise one free call is already "used" before this test starts.
    monkeypatch.setattr(main, "_free_tier_usage", {})
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
    import main
    assert payload["price_usdc"] == pytest.approx(
        main.KRISTO_SIGNAL_PRICE)
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
    assert main.X402_PRICE_MAP["/api/v1/signal"] == pytest.approx(
        main.KRISTO_SIGNAL_PRICE)
    assert "/api/v1/signal" in main.X402_PAID_ENDPOINTS


# ── the route must never take money for an empty answer ─────────────────────

def test_no_payment_is_taken_when_the_engine_has_no_signal(client, monkeypatch):
    """A paid route with nothing to deliver must not settle a payment.

    Measured from the outside by Ernest (Earnordie.ai) on 16.11.2026: a real
    $0.003 call settled and came back HTTP 200 with `signal_count: 0` and
    `generated_at: null`, because `_latest_signals` is an in-process snapshot
    that starts EMPTY on every deploy and is only refilled by the background
    agent. A 402 promises a price and a receiver, never that the route has
    something to sell, so the refusal has to happen before a facilitator is
    asked to settle — which is what `_x402_unready_payload` does.
    """
    import main
    monkeypatch.setattr(main, "_latest_signals",
                        {"generated_at": None, "signals": []})
    # Exhaust the free tier so the request reaches the credential path, and
    # present a credential so the guard is reached before any settlement.
    monkeypatch.setattr(main, "FREE_TIER_LIMIT", 0)
    monkeypatch.setattr(main, "_free_tier_usage", {"127.0.0.1": 1})

    r = client.get("/api/v1/signal",
                   headers={"X-Payment-Proof": "deliberately-not-a-proof"})
    assert r.status_code == 503, r.status_code
    body = r.get_json()
    assert body["error"] == "no_signal_to_deliver"
    assert body["payment_taken"] is False, "the whole point is that it is not"
    assert "No payment was taken" in body["message"]
    assert r.headers.get("Retry-After") == "60", (
        "a temporary emptiness has to say when to come back")


def test_the_guard_starts_a_producer_that_never_ran_in_this_process(monkeypatch):
    """A refusal must be temporary: the process has to start its own producer.

    Measured 24.11.2026: the process serving payments answered
    `arb_scan_count: 0` and `signal_generated_at: None` on every attempt for
    minutes, while the scanner ran elsewhere in the same service. Without this
    kick the route is not late, it is unsellable — and the guard, which is
    right to refuse, would be the thing keeping it that way.
    """
    import time
    import main

    started = []
    monkeypatch.setattr(main, "_unready_kick_attempted", set())
    monkeypatch.setattr(main, "_background_agent_loop", lambda: started.append(1))

    main._kick_unready_producer("/api/v1/signal")
    for _ in range(100):
        if started:
            break
        time.sleep(0.02)
    assert started, "the signal engine was never started in this process"

    # Once per process, not once per refused request.
    main._kick_unready_producer("/api/v1/signal")
    time.sleep(0.05)
    assert len(started) == 1, "a second copy of the producer was started"


def test_the_guard_starts_the_arbitrage_scanner_too(monkeypatch):
    """Same rule on the other guarded route, through its own entry point."""
    import main
    import services.arb_radar as arb_radar

    calls = []
    monkeypatch.setattr(main, "_unready_kick_attempted", set())
    monkeypatch.setattr(arb_radar, "start_arb_radar_thread",
                        lambda: calls.append(1))

    main._kick_unready_producer("/api/arb/opportunities")
    assert calls == [1], "the arbitrage scanner was not started"


def test_the_rest_are_not_guarded_and_have_nothing_to_kick(client, monkeypatch):
    """Only producers that begin empty on a deploy are guarded and kicked."""
    import main
    monkeypatch.setattr(main, "_unready_kick_attempted", set())
    for path in ("/api/v1/whaleflow", "/api/stats", "/api/sales",
                 "/api/bot-status", "/api/v1/verify-seller"):
        assert main._x402_unready_payload(path) is None, path
    assert main._unready_kick_attempted == set(), (
        "a route that is not guarded must not start anything")


def test_the_guard_stands_down_as_soon_as_a_signal_exists(client):
    """An empty snapshot is the only trigger; a populated one must pass."""
    import main
    assert main._x402_unready_payload("/api/v1/signal") is None


def test_the_guard_is_scoped_to_the_routes_that_start_empty(client, monkeypatch):
    """Only producers that begin empty on a deploy are guarded.

    /api/v1/signal and /api/arb/opportunities both read an in-process cache that
    nothing fills until a background loop completes its first pass. A route that
    reads durable storage is deliberately NOT guarded: a restart does not empty
    it, and "no whale over the threshold in 24h" is a real answer.

    Driven through the client rather than by calling the guard directly, because
    the refusal body carries a `free_sample` URL built from `request`.
    """
    import main
    monkeypatch.setattr(main, "_latest_signals",
                        {"generated_at": None, "signals": []})
    monkeypatch.setattr(main, "FREE_TIER_LIMIT", 0)
    monkeypatch.setattr(main, "_free_tier_usage", {"127.0.0.1": 1})

    for path, error in (("/api/v1/signal", "no_signal_to_deliver"),
                        ("/api/arb/opportunities",
                         "no_opportunities_to_deliver")):
        r = client.get(path, headers={"X-Payment-Proof": "not-a-proof"})
        assert r.status_code == 503, (path, r.status_code)
        assert r.get_json()["error"] == error, path

    # The rest are not guarded, and the guard must not invent a refusal for one.
    for path in ("/api/v1/whaleflow", "/api/stats", "/api/sales",
                 "/api/bot-status", "/api/v1/verify-seller"):
        assert main._x402_unready_payload(path) is None, path


def test_a_producer_that_ran_and_found_nothing_is_a_real_answer(
        client, monkeypatch):
    """The rule is "has the producer run", not "is the list empty".

    An engine that completed a pass and published zero signals has answered the
    question — "no signal right now" IS the product. Refusing that would be its
    own kind of lie, and it would make the route unbuyable during a genuinely
    quiet market. Only a snapshot that was never filled is a non-answer.
    """
    import main
    monkeypatch.setattr(main, "_latest_signals",
                        {"generated_at": "2026-01-01T00:00:00+00:00",
                         "signals": []})
    assert main._x402_unready_payload("/api/v1/signal") is None, (
        "an engine that ran and produced zero signals has still answered")
