"""
TTL cache for /api/dashboard-stats (option A, double-door approved 11.10).

The public payload aggregates request_log (~783K rows, ~22 seq scans) and
measured ~41s live — above the Sentinel weekly report's own 30s timeout,
which rendered "API stats unavailable". These tests prove:
  (a) the first call builds through the store exactly once,
  (b) a second call inside the TTL is served from cache (no new build),
  (c) after the TTL expires the next call rebuilds (the cache never freezes),
  (d) the paid /api/stats route (include_recent_requests=True) never shares
      this cache.
"""
import pytest


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("ADMIN_API_TOKEN", "test-admin-token")
    monkeypatch.setenv("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    import main
    main._free_tier_usage.clear()
    main._reset_stats_cache()
    yield main.app.test_client()
    main._reset_stats_cache()


def _spy_payload(monkeypatch):
    """Record (include_recent_requests, …) for every real payload build."""
    import main
    calls = []
    real = main._statistics_payload

    def spy(include_recent_requests: bool):
        calls.append(include_recent_requests)
        return real(include_recent_requests)

    monkeypatch.setattr(main, "_statistics_payload", spy)
    return calls


def test_dashboard_stats_first_call_builds_then_serves_cache(client, monkeypatch):
    """(a)+(b): first call builds once; a second call inside the TTL
    returns the cached payload without touching the store again."""
    calls = _spy_payload(monkeypatch)

    r1 = client.get("/api/dashboard-stats")
    assert r1.status_code == 200
    body1 = r1.get_json()
    assert body1 is not None, "Response must be JSON"
    assert calls == [False], f"first call must build exactly once, got {calls}"

    r2 = client.get("/api/dashboard-stats")
    assert r2.status_code == 200
    assert r2.get_json() == body1, "cached response must be identical"
    assert calls == [False], f"TTL hit must NOT rebuild, got {calls}"


def test_dashboard_stats_cache_expires_and_rebuilds(client, monkeypatch):
    """(c): once the TTL has expired the next call rebuilds fresh —
    the cache never freezes forever."""
    calls = _spy_payload(monkeypatch)

    assert client.get("/api/dashboard-stats").status_code == 200
    assert len(calls) == 1

    # Force expiry without sleeping 60s in the suite: TTL 0 = always stale.
    import main
    monkeypatch.setattr(main, "STATS_CACHE_TTL_SECONDS", 0)

    assert client.get("/api/dashboard-stats").status_code == 200
    assert len(calls) == 2, "expired cache must rebuild from the store"


def test_paid_api_stats_route_does_not_share_the_cache(client, monkeypatch):
    """(d): /api/stats (paid route, include_recent_requests=True) must build
    on every call — the cache serves ONLY /api/dashboard-stats."""
    calls = _spy_payload(monkeypatch)
    import main
    # Both calls are free-tier-eligible (the guard exempts the test IP).
    monkeypatch.setattr(main, "FREE_TIER_LIMIT", 99)

    assert client.get("/api/dashboard-stats").status_code == 200
    assert client.get("/api/stats").status_code == 200
    assert client.get("/api/stats").status_code == 200
    # dashboard-stats built once (then cached); /api/stats built every time.
    assert calls == [False, True, True], f"cache isolation broken: {calls}"
