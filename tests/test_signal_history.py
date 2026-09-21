"""Guards for the SIX FROZEN RULES of /public/signals/history (18.09).

These tests exist so the rules cannot drift after data arrives: the thresholds,
the window, the source order, "n is always shown" and the review schedule are all
pinned here. If someone moves a rule to make a number look better, this file
fails — that is its entire job.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    # Production semantics: no free tier. This also keeps THIS file from eating
    # the shared free-call budget and turning other tests' 200s into 402s.
    monkeypatch.setenv("KRISTO_FREE_TIER_LIMIT", "0")
    import main
    from integrations.dashboard_store import DashboardStore

    monkeypatch.setattr(main, "FREE_TIER_LIMIT", 0, raising=False)
    monkeypatch.setattr(main, "_free_tier_usage", {}, raising=False)
    monkeypatch.setattr(main, "dashboard_db",
                        DashboardStore(tmp_path / "dashboard_state.db"))
    return main.app.test_client(), main


def _iso(hours_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(hours=hours_ago)).isoformat()


# ── rule 1: free, ≥24h old only, the fresh signal stays paid ─────────────────

def test_the_feed_is_free_and_serves_only_signals_older_than_24h(client):
    _test_client, main = client
    fresh_id = "eth:" + datetime.now(timezone.utc).strftime("%Y-%m-%d")
    assert main.dashboard_db.record_signal_issue(fresh_id, "eth", "buy", 0.9,
                                                 _iso(1), 2500.0, 0.05)
    assert main.dashboard_db.record_signal_issue("eth:old", "eth", "buy", 0.9,
                                                 _iso(30), 2500.0, 0.05)

    response = _test_client.get("/public/signals/history")
    assert response.status_code == 200            # free: no 402, no key
    body = response.get_json()
    ids = [r["id"] for r in body["records"]]
    assert "eth:old" in ids
    assert fresh_id not in ids, "a fresh signal must stay paid"
    assert body["framing"].startswith("Thresholds, review schedule")
    assert body["frozen_on"] == "2026-09-18"
    assert "≥24h" in body["paid_note"]


def test_the_paid_route_still_charges(client):
    """Protection: the feed is free, the signal is not."""
    _test_client, main = client
    response = _test_client.get("/api/v1/signal")
    assert response.status_code in (402, 200)
    if response.status_code == 402:
        payload = response.get_json()
        assert payload["accepts"][0]["payTo"] == main.X402_RECEIVER_ADDRESS
        assert payload["accepts"][0]["amount"] == "3000"   # 0.003, untouched


# ── rule 2: volatility at issue, immutable; hit/miss/flat boundaries ─────────

def test_volatility_is_computed_at_issue_and_never_recomputed(client):
    _test_client, main = client
    from services import signal_track_record as track

    closes = [100, 101, 100.5, 102, 101.5, 103, 102.5, 104, 103.5, 105,
              104.5, 106, 105.5, 107, 106.5, 108, 107.5, 109, 108.5, 110,
              109.5, 111, 110.5, 112, 111.5]
    vol = track.realized_volatility_24h(closes)
    assert vol and vol > 0
    assert main.dashboard_db.record_signal_issue(
        "eth:day1", "eth", "buy", 0.9, _iso(30), 100.0, vol) is True
    # A second write for the same id is a no-op — the threshold cannot move.
    assert main.dashboard_db.record_signal_issue(
        "eth:day1", "eth", "sell", 0.1, _iso(30), 100.0, 0.99) is False
    row = main.dashboard_db.signal_history_rows(_iso(24))[0]
    assert row["action"] == "buy" and row["vol_threshold"] == vol


def test_hit_miss_flat_follow_the_signed_threshold():
    from services import signal_track_record as track

    # 100 -> 110 is +10%; a 5% threshold => hit for a buy, miss for a sell.
    assert track.classify(100, 110, 0.05, "buy") == ("hit", 10.0)
    assert track.classify(100, 110, 0.05, "sell") == ("miss", 10.0)
    # +3% is inside the 5% band => flat, in either direction.
    assert track.classify(100, 103, 0.05, "buy")[0] == "flat"
    assert track.classify(100, 97, 0.05, "sell")[0] == "flat"
    # Non-directional calls are never scored into a verdict.
    assert track.classify(100, 130, 0.05, "monitor") == ("unresolved", None)
    # Missing numbers are unresolved, never guessed.
    assert track.classify(None, 110, 0.05, "buy") == ("unresolved", None)
    assert track.classify(100, 110, None, "buy") == ("unresolved", None)


# ── rule 3: the frozen fallback order, window-only ──────────────────────────

def test_resolution_uses_coingecko_first_then_dexscreener(client, monkeypatch):
    _test_client, main = client
    from services import signal_track_record as track

    main.dashboard_db.record_signal_issue("eth:day", "eth", "buy", 0.9,
                                          _iso(25), 100.0, 0.05)
    calls = []

    def _cg(asset, ts, **kw):
        calls.append("coingecko")
        return 110.0, "coingecko"

    def _dex(asset, ref, **kw):
        calls.append("dexscreener")
        return 111.0, "dexscreener"

    monkeypatch.setattr(track, "fetch_price_at", _cg)
    monkeypatch.setattr(track, "fetch_dexscreener_implied", _dex)
    assert main._resolve_track_record() == 1
    assert calls == ["coingecko"], "the fallback must not be tried first"
    row = main.dashboard_db.signal_history_rows(_iso(24))[0]
    assert row["outcome"] == "hit" and row["resolution_source"] == "coingecko"


def test_both_sources_failing_means_unresolved_not_a_guess(client, monkeypatch):
    _test_client, main = client
    from services import signal_track_record as track

    main.dashboard_db.record_signal_issue("kaito:day", "kaito", "buy", 0.7,
                                          _iso(25), 1.0, 0.05)
    monkeypatch.setattr(track, "fetch_price_at", lambda a, t, **kw: (None, ""))
    monkeypatch.setattr(track, "fetch_dexscreener_implied",
                        lambda a, r, **kw: (None, ""))
    assert main._resolve_track_record() == 1
    row = main.dashboard_db.signal_history_rows(_iso(24))[0]
    assert row["outcome"] == "unresolved"
    assert row["price_at_24h"] is None and row["move_pct"] is None


def test_the_dexscreener_fallback_is_refused_outside_the_window(client, monkeypatch):
    """The fallback implies '24h ago from NOW' — outside the ±2h window that is
    not the signal's 24th hour, so it must never resolve anything."""
    _test_client, main = client
    from services import signal_track_record as track

    main.dashboard_db.record_signal_issue("degen:day", "degen", "buy", 0.6,
                                          _iso(100), 1.0, 0.05)
    monkeypatch.setattr(track, "fetch_price_at", lambda a, t, **kw: (None, ""))
    used = []

    def _dex(asset, ref, **kw):
        used.append(asset)
        return 1.2, "dexscreener"

    monkeypatch.setattr(track, "fetch_dexscreener_implied", _dex)
    main._resolve_track_record()
    assert used == [], "the fallback ran outside the window"
    assert main.dashboard_db.signal_history_rows(
        _iso(24))[0]["outcome"] == "unresolved"


def test_dexscreener_implied_price_ignores_symbol_collisions(monkeypatch):
    """A fake 'ETH' at $0.01 on Base must not resolve a $2,500 ETH signal."""
    from services import signal_track_record as track

    class _Response:
        status_code = 200

        @staticmethod
        def json():
            return {"pairs": [
                {"baseToken": {"symbol": "ETH"}, "chainId": "base",
                 "priceUsd": "0.01", "priceChange": {"h24": 0.0},
                 "liquidity": {"usd": 900000}},
                {"baseToken": {"symbol": "ETH"}, "chainId": "base",
                 "priceUsd": "2500", "priceChange": {"h24": 2.0},
                 "liquidity": {"usd": 500000}},
            ]}

    monkeypatch.setattr(track.requests, "get", lambda *a, **kw: _Response())
    price, source = track.fetch_dexscreener_implied("eth", 2500.0)
    assert source == "dexscreener"
    assert abs(price - 2500 / 1.02) < 1e-6      # the 10× guard skipped the fake


# ── rule 5: n always shown, percentages only at n≥50, unresolved visible ────

def test_percentages_appear_only_at_n_50_and_n_is_always_shown():
    from services import signal_track_record as track

    def row(outcome, asset="ETH", confidence=0.9):
        return {"id": "x", "asset": asset, "outcome": outcome,
                "confidence": confidence, "move_pct": 1.0}

    small = track.build_feed([row("hit"), row("miss")])
    eth = small["by_asset"][0]
    assert eth["n"] == 2 and eth["hits"] == 1
    assert eth["hit_rate_pct"] is None, "a percentage appeared below n=50"
    assert small["totals"]["hit_rate_pct"] is None      # also gated (rule 6)

    big = [row("hit") for _ in range(40)] + [row("miss") for _ in range(10)]
    cell = track.build_feed(big)["by_asset"][0]
    assert cell["n"] == 50 and cell["hit_rate_pct"] == 80.0


def test_unresolved_is_visible_per_asset_and_explained():
    from services import signal_track_record as track

    rows = ([{"id": "1", "asset": "ETH", "outcome": "hit", "confidence": 0.9,
              "move_pct": 1.0}] * 8 +
            [{"id": "2", "asset": "DEGEN", "outcome": "unresolved",
              "confidence": 0.6, "move_pct": None}] * 4 +
            [{"id": "3", "asset": "DEGEN", "outcome": "hit", "confidence": 0.6,
              "move_pct": 2.0}])
    feed = track.build_feed(rows)
    assert feed["unresolved_by_asset"] == {"DEGEN": 4}
    degen = [c for c in feed["by_asset"] if c["asset"] == "DEGEN"][0]
    assert degen["n"] == 1 and degen["unresolved"] == 4
    assert degen["total_issued"] == 5
    assert "unresolved concentrates in thinner markets" in feed["unresolved_note"]


def test_confidence_bands_are_pre_declared():
    from services import signal_track_record as track

    rows = [{"id": "1", "asset": "ETH", "outcome": "hit", "confidence": 0.9,
             "move_pct": 1.0},
            {"id": "2", "asset": "ETH", "outcome": "miss", "confidence": 0.5,
             "move_pct": -1.0},
            {"id": "3", "asset": "ETH", "outcome": "hit", "confidence": None,
             "move_pct": 1.0}]
    bands = {c["band"]: c for c in track.build_feed(rows)["by_confidence"]}
    assert bands["0.8-1.0"]["n"] == 1 and bands["0.8-1.0"]["hits"] == 1
    assert bands["0.4-0.6"]["n"] == 1 and bands["0.4-0.6"]["hits"] == 0
    assert bands["unknown"]["n"] == 1
    assert all(c["hit_rate_pct"] is None for c in bands.values())


# ── rule 6: the review schedule is a guard, not a promise ───────────────────

def test_hit_rate_is_withheld_before_the_first_checkpoint():
    from services import signal_track_record as track

    rows = [{"id": str(i), "asset": "ETH", "outcome": "hit", "confidence": 0.9,
             "move_pct": 1.0} for i in range(29)]
    feed = track.build_feed(rows)
    assert feed["totals"]["scored_n"] == 29
    assert feed["totals"]["hit_rate_pct"] is None
    assert feed["totals"]["gate_open"] is False
    assert feed["schedule"]["next_checkpoint"] == 30

    rows.append({"id": "30", "asset": "ETH", "outcome": "hit",
                 "confidence": 0.9, "move_pct": 1.0})
    feed = track.build_feed(rows)
    assert feed["totals"]["hit_rate_pct"] == 100.0
    assert feed["schedule"]["next_checkpoint"] == 100


def test_the_real_agent_vocabulary_is_mapped_exactly():
    """The first version guessed "buy"/"long" and the LIVE run showed the agent's
    real strings — every one of them landed in `not_scored`, so the feed would
    have stayed empty forever while looking perfectly healthy. These are the
    exact values observed in production on 18.09."""
    from services import signal_track_record as track

    assert track.direction_of("recommend_accumulate_on_dips") == 1
    assert track.direction_of("recommend_small_allocation_only") == 1
    assert track.direction_of("recommend_buy") == 1
    assert track.direction_of("sell") == -1
    assert track.direction_of("avoid") == -1
    # Ambiguous or neutral: counted, never scored.
    assert track.direction_of("recommend_hold_or_add") == 0
    assert track.direction_of("monitor") == 0
    assert track.direction_of("hold") == 0
    assert track.direction_of("wait") == 0
    # Unknown strings are never guessed into a direction.
    assert track.direction_of("launch_moon") == 0
    assert track.direction_of("") == 0


def test_the_volatility_fetch_is_skipped_for_a_day_already_recorded(client, monkeypatch):
    """18.09 live finding: the volatility was fetched BEFORE the idempotency check,
    so every 5-minute agent cycle spent 4 heavy CoinGecko history calls on rows
    that already existed → HTTP 429 → vol_threshold None → records that could
    never be scored. An existing asset+day must cost ZERO network calls."""
    _test_client, main = client
    from services import signal_track_record as track

    assert main.dashboard_db.record_signal_issue(
        "eth:" + datetime.now(timezone.utc).strftime("%Y-%m-%d"), "eth",
        "recommend_accumulate_on_dips", 0.8, _iso(1), 2600.0, 0.05)
    calls = []
    monkeypatch.setattr(track, "fetch_hourly_closes",
                        lambda asset, **kw: calls.append(asset) or [100.0] * 30)

    main._record_track_record([{"token": "eth", "action":
                                "recommend_accumulate_on_dips",
                                "confidence": 0.8, "price_usd": 2600.0}])
    assert calls == [], "an existing day still triggered a CoinGecko fetch"


def test_no_volatility_means_the_record_is_deferred_not_frozen(client, monkeypatch):
    """A record without a threshold can never be scored (hit/miss/flat are all
    defined against it), so it must NOT be frozen: skip and retry next cycle."""
    _test_client, main = client
    from services import signal_track_record as track

    monkeypatch.setattr(track, "fetch_hourly_closes", lambda asset, **kw: [])
    day = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    main._record_track_record([{"token": "eth", "action":
                                "recommend_accumulate_on_dips",
                                "confidence": 0.8, "price_usd": 2600.0}])
    assert not main.dashboard_db.signal_history_exists("eth:" + day), \
        "an unscorable record was frozen anyway"

    # And once the series IS available, the record lands with its threshold.
    closes = [100 + i for i in range(30)]
    monkeypatch.setattr(track, "fetch_hourly_closes", lambda asset, **kw: closes)
    main._record_track_record([{"token": "eth", "action":
                                "recommend_accumulate_on_dips",
                                "confidence": 0.8, "price_usd": 2600.0}])
    assert main.dashboard_db.signal_history_exists("eth:" + day)
    # A future cutoff selects everything (the public feed's ≥24h filter is what
    # keeps this fresh row out of /public/signals/history — by design).
    due = main.dashboard_db.signal_history_due(_iso(-1))
    assert due and due[0]["vol_threshold"] and due[0]["outcome"] == "pending"


def test_the_frozen_rules_are_pinned():
    """The six rules, as constants. Changing one is a product decision that must
    not happen silently — the feed's credibility rests on them."""
    from services import signal_track_record as track

    assert track.FROZEN_ON == "2026-09-18"
    assert track.CHECKPOINTS == (30, 100, 200)
    assert track.MIN_PERCENT_N == 50
    assert track.PRICE_WINDOW_HOURS == 2
    assert track.VOL_LOOKBACK_DAYS == 14
    assert track.RESOLVE_AFTER_HOURS == 24
    assert track.ASSET_IDS == {"eth": "ethereum", "ondo": "ondo-finance",
                               "kaito": "kaito", "degen": "degen-base"}


def test_checkpoints_are_recorded_once_in_the_durable_store(client):
    _test_client, main = client
    rows = [{"id": str(i), "asset": "ETH", "outcome": "hit", "confidence": 0.9,
             "move_pct": 1.0} for i in range(30)]
    first = main._track_record_checkpoints(rows)
    assert [c["n"] for c in first] == [30]
    assert first[0]["hit_rate_pct"] == 100.0
    # A second call must not rewrite history.
    worse = [dict(r, outcome="miss") for r in rows]
    again = main._track_record_checkpoints(worse)
    assert again[0]["hit_rate_pct"] == 100.0, "the checkpoint was rewritten"


def test_a_final_checkpoint_below_50_is_recorded_as_a_failure(client):
    """The schedule's last clause: if the FINAL checkpoint (n=200) comes in under
    50%, that is recorded as a failure in the same durable row the number lives in
    — shown, not explained away."""
    _test_client, main = client
    rows = ([{"id": str(i), "asset": "ETH", "outcome": "hit", "confidence": 0.9,
              "move_pct": 1.0} for i in range(98)] +
            [{"id": "m%d" % i, "asset": "ETH", "outcome": "miss",
              "confidence": 0.9, "move_pct": -1.0} for i in range(102)])
    saved = main._track_record_checkpoints(rows)
    assert [c["n"] for c in saved] == [30, 100, 200]
    final = saved[-1]
    assert final["hit_rate_pct"] == 49.0
    assert final["verdict"] == "below_50_at_final_checkpoint"
    assert "recorded here as a failure" in final["note"]
    # The earlier checkpoints are plain records — no verdict, no spin.
    assert "verdict" not in saved[0] and "verdict" not in saved[1]


def test_non_directional_issues_are_counted_but_never_scored(client):
    """A `monitor` cannot hit or miss, so it must not pad the sample — but the
    fact that it was issued stays visible."""
    _test_client, main = client
    assert main.dashboard_db.record_signal_issue(
        "eth:flat", "eth", "monitor", 0.5, _iso(30), 2500.0, None,
        outcome="not_scored")
    body = _test_client.get("/public/signals/history").get_json()
    assert body["records"] == []
    assert body["totals"]["not_scored_non_directional"] == 1
    assert body["totals"]["scored_n"] == 0
    assert body["totals"]["issued"] == 1