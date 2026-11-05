"""The request-log summary is computed once per TTL, not once per poll.

`requests_summary` issues EIGHT unbounded aggregates over `request_log`:
`COUNT(*)` with no WHERE (which cannot use an index), plus `GROUP BY source /
funnel / path / user_agent` over the whole table. `request_log` has no
retention — nothing ever deletes from it — and the same module already records
a fix for two full scans when it held "~783K rows".

On 05.11 those scans ran on every 45-second poll, behind the single shared
Postgres link. /api/dashboard/data hung past 90s and took /health down with it.

The fix replays a computed summary for `REQUEST_SUMMARY_TTL_SECONDS`. These
tests pin the two properties that make it a fix rather than a bug:

  * it actually removes the database work (measured as `_run` calls, not as a
    claim in a docstring), and
  * it changes NO displayed value — the cached answer must equal the freshly
    computed one, field for field.
"""

from __future__ import annotations

import time

import pytest


@pytest.fixture()
def store(tmp_path, monkeypatch):
    """A real DashboardStore over a temp SQLite file (DATABASE_URL off)."""
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from integrations.dashboard_store import DashboardStore

    return DashboardStore(tmp_path / "ttl.db")


def _count_runs(monkeypatch, target):
    """Wrap `_run` and count how many statements actually reach the database.

    `DashboardStore.requests_summary` delegates to `self.history`, and it is
    the HistoryStore's `_run` that issues the SQL — so the counter has to sit
    there. Counting on the facade would count nothing and the test would pass
    for a reason that has nothing to do with the cache.
    """
    target = getattr(target, "history", target)
    counter = {"n": 0}
    original = target._run

    def counted(sql, params=(), fetch=""):
        counter["n"] += 1
        return original(sql, params, fetch)

    monkeypatch.setattr(target, "_run", counted)
    return counter


# ── 1. THE POINT: repeated polls must not repeat the scans ─────────────────
def test_a_second_call_within_the_ttl_runs_no_more_queries(
        store, monkeypatch):
    """The defect: eight full scans of request_log on every 45s poll."""
    store.requests_summary()                     # warm the cache first
    counter = _count_runs(monkeypatch, store)

    store.requests_summary()
    store.requests_summary()
    store.requests_summary()

    assert counter["n"] == 0, (
        "a cached poll still issued %d statement(s) against request_log — "
        "the TTL is not preventing the full scans" % counter["n"])


def test_the_first_call_does_the_work_and_later_ones_do_not(
        store, monkeypatch):
    counter = _count_runs(monkeypatch, store)

    store.requests_summary()
    first = counter["n"]

    assert first > 1, (
        "precondition: the summary used to be several statements, got %d" % first)

    store.requests_summary()
    assert counter["n"] == first, (
        "the second call issued new statements instead of replaying")


# ── 2. the cache must expire ───────────────────────────────────────────────
def test_the_cache_expires_once_the_ttl_passes(store, monkeypatch):
    from integrations import dashboard_store as ds

    monkeypatch.setattr(ds, "REQUEST_SUMMARY_TTL_SECONDS", 0.05)
    store.requests_summary()

    counter = _count_runs(monkeypatch, store)
    time.sleep(0.12)
    store.requests_summary()

    assert counter["n"] > 0, (
        "the summary never expired — the board would show hours-old numbers "
        "forever")


def test_a_different_recent_limit_is_not_served_from_the_cache(
        store, monkeypatch):
    """The cache is keyed on the limit; a 5-row tail must not answer a 25-row one."""
    store.requests_summary(recent_limit=25)
    counter = _count_runs(monkeypatch, store)

    store.requests_summary(recent_limit=5)

    assert counter["n"] > 0, (
        "a different recent_limit was answered from another limit's cache")


# ── 3. NO DISPLAYED NUMBER MAY CHANGE ──────────────────────────────────────
def test_the_cached_answer_is_identical_to_a_fresh_one(store, monkeypatch):
    """Caching must be invisible in the payload, not merely fast.

    This is the acceptance criterion: the owner sees the same numbers, and the
    database does a fraction of the work.
    """
    from integrations import dashboard_store as ds

    fresh = store.requests_summary()

    # Force a recompute by expiring the cache, then compare.
    monkeypatch.setattr(ds, "REQUEST_SUMMARY_TTL_SECONDS", 0.0)
    store.requests_summary()
    time.sleep(0.02)
    recomputed = store.requests_summary()

    assert recomputed == fresh, (
        "the cached summary and a freshly computed one disagree")


def test_the_summary_still_carries_every_documented_key(store):
    s = store.requests_summary()
    for key in ("today_date", "today", "total", "today_clean", "total_clean",
                "internal_noise", "by_source", "by_source_clean", "by_channel",
                "top_paths", "top_user_agents", "hourly", "funnel", "recent"):
        assert key in s, "the cached summary dropped the %r key" % key


# ── 4. a caller must not be able to corrupt the cache ──────────────────────
def test_mutating_the_returned_value_does_not_corrupt_the_cache(store):
    """The wrapper hands back a deep copy, so downstream edits stay downstream.

    THE MUTATION HAS TO LAND ON A CACHE HIT. The first call is always a miss,
    and a miss returns a freshly built object under either implementation —
    so mutating THAT proves nothing about the copy. The value that can leak is
    the one served from the cache, which is what this mutates.
    """
    store.requests_summary()                  # prime

    hit = store.requests_summary()            # served FROM the cache
    hit["total"] = -999
    hit.setdefault("by_source", []).append({"source": "INJECTED", "n": 1})
    hit["internal_noise"]["today"] = -1

    second = store.requests_summary()         # another cache hit

    assert second["total"] != -999, (
        "a caller's edit to a cache-served dict reached the cache")
    assert not any(r.get("source") == "INJECTED"
                   for r in second.get("by_source", [])), (
        "a caller's edit to a nested list reached the cache")
    assert second["internal_noise"]["today"] != -1, (
        "a caller's edit to a NESTED dict reached the cache — a shallow copy "
        "shares the inner objects")


# ── 5. the TTL must actually beat the page's refresh interval ──────────────
def test_the_default_ttl_covers_the_pages_own_refresh_interval():
    """If the TTL were shorter than the refresh, every poll would recompute.

    The two numbers live in different files — the interval in the template,
    the TTL in the store — so this reads the interval out of the page rather
    than restating it. A TTL below the refresh silently restores the exact
    behaviour the cache exists to remove, and nothing else would notice.
    """
    import re
    from pathlib import Path

    from integrations import dashboard_store as ds

    html = Path("templates/dashboard.html").read_text(encoding="utf-8")
    m = re.search(r"setInterval\(load,\s*(\d+)\)", html)
    assert m, (
        "the dashboard's refresh interval moved; this test can no longer "
        "check the TTL against it")
    refresh_s = int(m.group(1)) / 1000.0

    assert ds.REQUEST_SUMMARY_TTL_SECONDS >= refresh_s, (
        "REQUEST_SUMMARY_TTL_SECONDS (%.0fs) is shorter than the page's "
        "refresh (%.0fs), so the dashboard recomputes the eight full scans on "
        "every single poll" % (ds.REQUEST_SUMMARY_TTL_SECONDS, refresh_s))
    # And it must not be so long that `today` visibly drifts.
    assert ds.REQUEST_SUMMARY_TTL_SECONDS <= 300
