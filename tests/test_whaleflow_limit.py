# -*- coding: utf-8 -*-
"""`?limit=` on the whale feed: the caller's bill, clamped.

The owner's task was "?limit= on whaleflow". The parameter exists and is clamped
in the handler, but NOTHING tested it — and the reason it matters is money: the
50-row default is ~16.9 KB / ~4.2k tokens, which costs the BUYER 4x the $0.003
we charge on a mid model and 20x on a frontier one. A caller that cannot ask for
fewer rows is being billed for tokens it did not want.

These tests pin the whole contract:
  * the caller's value is used (not the env default);
  * it is clamped to 1..200 — a request may LOWER the response, never raise it;
  * a non-numeric value falls back instead of failing a PAID call;
  * `hours` is clamped the same way, to 1..168.
"""

import pytest


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    import main
    main._free_tier_usage.clear()
    # Generous on purpose: several requests run from one IP in a single test and
    # the subject here is the parameter, not the challenge. The paywall has its
    # own tests.
    monkeypatch.setattr(main, "FREE_TIER_LIMIT", 999)
    yield main
    main._free_tier_usage.clear()


def _stub(main, monkeypatch, seen):
    def fake_summary(window_hours=None, limit=None):
        seen.append({"limit": limit, "hours": window_hours})
        return {
            "whales": [], "count": 0, "window_hours": window_hours,
            "threshold_usdc": 5_000_000, "scanned_until_block": 1,
        }
    monkeypatch.setattr(main.dashboard_db, "whaleflow_summary", fake_summary)


def _call(main, query=""):
    return main.app.test_client().get("/api/v1/whaleflow" + query)


def test_the_callers_limit_is_used_not_the_env_default(client, monkeypatch):
    seen = []
    _stub(client, monkeypatch, seen)
    r = _call(client, "?limit=5")
    assert r.status_code == 200, r.get_data(as_text=True)
    assert seen and seen[0]["limit"] == 5, seen


def test_the_limit_is_clamped_to_two_hundred(client, monkeypatch):
    """A caller may lower the response, never raise it past the ceiling."""
    seen = []
    _stub(client, monkeypatch, seen)
    r = _call(client, "?limit=1000")
    assert r.status_code == 200
    assert seen[0]["limit"] == 200, seen


def test_a_zero_or_negative_limit_still_returns_something(client, monkeypatch):
    seen = []
    _stub(client, monkeypatch, seen)
    for query in ("?limit=0", "?limit=-5"):
        r = _call(client, query)
        assert r.status_code == 200, (query, r.get_data(as_text=True))
    assert [s["limit"] for s in seen] == [1, 1], seen


def test_a_non_numeric_limit_does_not_fail_a_paid_call(client, monkeypatch):
    """`?limit=abc` must fall back, not 500 — the caller already paid."""
    seen = []
    _stub(client, monkeypatch, seen)
    r = _call(client, "?limit=abc")
    assert r.status_code == 200, r.get_data(as_text=True)
    assert seen[0]["limit"] == 50, seen


def test_the_hours_window_is_clamped_the_same_way(client, monkeypatch):
    seen = []
    _stub(client, monkeypatch, seen)
    assert _call(client, "?hours=9999").status_code == 200
    assert _call(client, "?hours=0").status_code == 200
    assert [s["hours"] for s in seen] == [168, 1], seen
