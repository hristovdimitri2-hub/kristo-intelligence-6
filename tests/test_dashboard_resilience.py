"""The dashboard must stay operational — and must stay HONEST while it does.

The owner's requirement is that the board is always up ("искам таблото
постоянно да е оперативно").

Three fixes got here, and the difference between them matters:

  * `eafdacf` bounded the Postgres waits, so one slow read could no longer
    take the whole service down — /health came back to ~420ms from 502.
  * `a8d717e` stopped the board from blanking when a read failed.
  * the current design stops the request path from touching the database at
    all. That last one is the actual requirement: on 05.11 the endpoint still
    spent 40+ seconds INSIDE the build. Bounding a bad number is not the same
    as fixing it, and a 40-second request is a board nobody can use.

So the load-bearing assertions here are:

  * a cached variant is served WITHOUT rebuilding — measured as builder
    invocations, which is the whole point and the easiest thing to regress;
  * an ageing payload triggers a refresh BEHIND the request, so the reader
    never waits;
  * only one refresh per variant runs at a time, so a burst of visitors does
    not start one rebuild each;
  * and the honesty rules still hold: an old payload is LABELLED, nothing is
    invented, and a public caller is never served an admin variant.
"""

from __future__ import annotations

import threading
import time

import pytest


@pytest.fixture()
def main_module():
    """main.py with the networked background threads off."""
    import os

    os.environ.setdefault("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    import main

    return main


@pytest.fixture(autouse=True)
def _clean_cache(main_module):
    """Every test starts with an empty cache and leaves one behind."""
    with main_module._DASHBOARD_LAST_GOOD_LOCK:
        main_module._DASHBOARD_LAST_GOOD.clear()
        main_module._DASHBOARD_REFRESHING.clear()
    yield
    with main_module._DASHBOARD_LAST_GOOD_LOCK:
        main_module._DASHBOARD_LAST_GOOD.clear()
        main_module._DASHBOARD_REFRESHING.clear()


@pytest.fixture()
def refreshes(monkeypatch, main_module):
    """Record background refreshes instead of racing real threads.

    The scheduling decision is what most of these tests are about; running an
    actual thread would make them timing-dependent for no gain. The real
    thread is exercised separately, in the two tests that end this file.
    """
    started = []

    def fake(key, include_crm, include_sales_detail):
        started.append(key)
        return True

    monkeypatch.setattr(main_module, "_dashboard_refresh_in_background", fake)
    return started


def _fake_payload(monkeypatch, main, value=1.23, delay=0.0, gate=None):
    """Replace the real builder with a controllable stand-in."""
    calls = {"n": 0}

    def builder(include_crm=False, include_sales_detail=False):
        calls["n"] += 1
        if gate is not None:
            gate.wait(5.0)
        if delay:
            time.sleep(delay)
        return {
            "ok": True,
            "generated_at": "2026-11-05T00:00:00+00:00",
            "receiver_address": "0xd4cdA900839c0FED4374EE37EA0DBE8e4c6fd08f",
            "sections": {"onchain": {"total_usdc": value}},
            "build_no": calls["n"],
            "crm": {"leads": 7} if include_crm else None,
        }

    monkeypatch.setattr(main, "_canonical_dashboard_payload", builder)
    return calls


def _wait_for(predicate, timeout=5.0):
    """Poll until `predicate()` is true. Returns whether it became true."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


# ── 1. the happy path, and the guarantee that actually matters ─────────────
def test_a_fresh_build_is_marked_not_stale(main_module, monkeypatch):
    main = main_module
    calls = _fake_payload(monkeypatch, main)

    payload = main._dashboard_payload_resilient(False, False)

    assert payload["stale"] is False
    assert payload["sections"]["onchain"]["total_usdc"] == 1.23
    assert calls["n"] == 1


def test_a_cached_variant_is_served_without_rebuilding(main_module, monkeypatch,
                                                       refreshes):
    """THE POINT OF THE WHOLE CHANGE.

    If this regresses, every 45-second poll is back to doing the full build on
    the request path — which is what made the board take 40 seconds and the
    service fall over.
    """
    main = main_module
    calls = _fake_payload(monkeypatch, main)

    main._dashboard_payload_resilient(False, False)      # cold: builds once
    assert calls["n"] == 1

    for _ in range(5):
        payload = main._dashboard_payload_resilient(False, False)

    assert calls["n"] == 1, (
        "a served-from-cache read rebuilt the payload %d extra time(s) — the "
        "request path is doing database work again" % (calls["n"] - 1))
    assert payload["stale"] is False


def test_a_cached_read_inside_the_window_starts_no_refresh(main_module,
                                                           monkeypatch,
                                                           refreshes):
    main = main_module
    _fake_payload(monkeypatch, main)

    main._dashboard_payload_resilient(False, False)
    refreshes.clear()
    main._dashboard_payload_resilient(False, False)

    assert refreshes == [], (
        "a payload inside the revalidate window still triggered a refresh")


# ── 2. ageing triggers a refresh BEHIND the reader ─────────────────────────
def test_an_ageing_payload_starts_a_background_refresh(main_module, monkeypatch,
                                                       refreshes):
    from main import _DASHBOARD_REVALIDATE_SECONDS

    main = main_module
    _fake_payload(monkeypatch, main)
    main._dashboard_payload_resilient(False, False)

    # Backdate the cache entry past the revalidate interval.
    with main._DASHBOARD_LAST_GOOD_LOCK:
        payload, _ = main._DASHBOARD_LAST_GOOD[(False, False)]
        main._DASHBOARD_LAST_GOOD[(False, False)] = (
            payload, time.time() - (_DASHBOARD_REVALIDATE_SECONDS + 5))

    refreshes.clear()
    main._dashboard_payload_resilient(False, False)

    assert (False, False) in refreshes, (
        "an ageing payload did not schedule a refresh, so it would never "
        "become current again")


def test_the_reader_does_not_wait_for_the_refresh(main_module, monkeypatch,
                                                  refreshes):
    """The refresh is scheduled, not performed — the call returns at once."""
    from main import _DASHBOARD_REVALIDATE_SECONDS

    main = main_module
    gate = threading.Event()
    calls = _fake_payload(monkeypatch, main, gate=gate)
    main._dashboard_payload_resilient(False, False)

    with main._DASHBOARD_LAST_GOOD_LOCK:
        payload, _ = main._DASHBOARD_LAST_GOOD[(False, False)]
        main._DASHBOARD_LAST_GOOD[(False, False)] = (
            payload, time.time() - (_DASHBOARD_REVALIDATE_SECONDS + 5))

    t0 = time.time()
    out = main._dashboard_payload_resilient(False, False)
    elapsed = time.time() - t0
    gate.set()

    assert elapsed < 1.0, (
        "the read blocked for %.2fs waiting on the rebuild" % elapsed)
    assert out["ok"] is True
    assert calls["n"] == 1, "the refresh ran on the request path"


# ── 3. honesty: an old payload says so ─────────────────────────────────────
def test_a_payload_older_than_the_fresh_window_is_labelled_stale(
        main_module, monkeypatch, refreshes):
    from main import _DASHBOARD_FRESH_SECONDS

    main = main_module
    _fake_payload(monkeypatch, main)
    main._dashboard_payload_resilient(False, False)

    with main._DASHBOARD_LAST_GOOD_LOCK:
        payload, _ = main._DASHBOARD_LAST_GOOD[(False, False)]
        main._DASHBOARD_LAST_GOOD[(False, False)] = (
            payload, time.time() - (_DASHBOARD_FRESH_SECONDS + 30))

    out = main._dashboard_payload_resilient(False, False)

    assert out["stale"] is True, (
        "a payload well past the fresh window was still presented as live")
    assert out["stale_age_seconds"] >= _DASHBOARD_FRESH_SECONDS
    assert out["stale_since"]
    assert out["stale_reason"]
    # Still the real numbers, not blanks and not a zero.
    assert out["sections"]["onchain"]["total_usdc"] == 1.23


def test_the_stale_marker_reports_the_real_age(main_module, monkeypatch,
                                               refreshes):
    from main import _DASHBOARD_FRESH_SECONDS

    main = main_module
    _fake_payload(monkeypatch, main)
    main._dashboard_payload_resilient(False, False)

    age = _DASHBOARD_FRESH_SECONDS + 42
    with main._DASHBOARD_LAST_GOOD_LOCK:
        payload, _ = main._DASHBOARD_LAST_GOOD[(False, False)]
        main._DASHBOARD_LAST_GOOD[(False, False)] = (
            payload, time.time() - age)

    out = main._dashboard_payload_resilient(False, False)

    assert abs(out["stale_age_seconds"] - age) < 5, (
        "the reported age (%.0fs) is not the real one (%.0fs)"
        % (out["stale_age_seconds"], age))


# ── 4. the cold path is the only one that may raise ────────────────────────
def test_the_first_build_with_no_cache_still_raises(main_module, monkeypatch):
    """A genuinely broken service must report an error, not an empty success."""
    main = main_module

    def boom(include_crm=False, include_sales_detail=False):
        raise RuntimeError("the database is unreachable")

    monkeypatch.setattr(main, "_canonical_dashboard_payload", boom)

    with pytest.raises(RuntimeError):
        main._dashboard_payload_resilient(False, False)

    with main._DASHBOARD_LAST_GOOD_LOCK:
        assert main._DASHBOARD_LAST_GOOD == {}, (
            "a failed cold build published something to the cache")


# ── 5. the security boundary: the key is the GRANT, never the caller ───────
def test_a_public_caller_can_never_be_served_the_admin_payload(
        main_module, monkeypatch):
    """The defect this would be: serving an admin variant to an anonymous GET.

    Both variants are primed, so the only thing that can keep them apart is the
    key. A single shared slot — the obvious "optimisation" — fails here.
    """
    main = main_module
    _fake_payload(monkeypatch, main)

    main._dashboard_payload_resilient(True, True)     # admin variant primed
    main._dashboard_payload_resilient(False, False)   # public variant primed

    public = main._dashboard_payload_resilient(False, False)
    admin = main._dashboard_payload_resilient(True, True)

    assert public.get("crm") is None, (
        "an anonymous caller was served the admin payload")
    assert admin["crm"] == {"leads": 7}


def test_the_two_grants_use_separate_cache_slots(main_module, monkeypatch,
                                                 refreshes):
    main = main_module
    calls = _fake_payload(monkeypatch, main)

    main._dashboard_payload_resilient(True, False)
    main._dashboard_payload_resilient(False, True)

    assert calls["n"] == 2, (
        "the two grant pairs shared one cache slot")
    assert main._dashboard_payload_resilient(True, False)["crm"] == {"leads": 7}
    assert main._dashboard_payload_resilient(False, True).get("crm") is None


# ── 6. the REAL background thread ──────────────────────────────────────────
def test_a_failing_background_refresh_neither_raises_nor_wipes_the_cache(
        main_module, monkeypatch):
    main = main_module
    calls = _fake_payload(monkeypatch, main)
    main._dashboard_payload_resilient(False, False)

    def boom(include_crm=False, include_sales_detail=False):
        calls["n"] += 1
        raise RuntimeError("transient read failure")

    monkeypatch.setattr(main, "_canonical_dashboard_payload", boom)

    # Force a refresh through the real path; it must swallow the failure.
    main._dashboard_refresh_in_background((False, False), False, False)

    assert _wait_for(lambda: (False, False) not in main._DASHBOARD_REFRESHING), (
        "the refresh thread never cleared its in-flight marker, so this "
        "variant could never be refreshed again")

    out = main._dashboard_payload_resilient(False, False)
    assert out["sections"]["onchain"]["total_usdc"] == 1.23, (
        "a failed background refresh destroyed the good cached payload")


def test_only_one_background_refresh_per_variant_runs_at_a_time(
        main_module, monkeypatch):
    """A burst of visitors must not start one rebuild each."""
    main = main_module
    gate = threading.Event()
    calls = _fake_payload(monkeypatch, main, gate=gate)
    main._dashboard_payload_resilient(False, False)

    main._dashboard_refresh_in_background((False, False), False, False)
    assert _wait_for(lambda: (False, False) in main._DASHBOARD_REFRESHING)

    # While one is in flight, further requests must not start another.
    for _ in range(5):
        started = main._dashboard_refresh_in_background(
            (False, False), False, False)
        assert started is False, "a second refresh was started concurrently"

    gate.set()
    assert _wait_for(lambda: (False, False) not in main._DASHBOARD_REFRESHING)
    assert calls["n"] == 2, (
        "expected the cold build plus exactly one refresh, got %d builds"
        % calls["n"])


def test_the_refresh_thread_is_a_daemon(main_module, monkeypatch):
    """A non-daemon thread would hold the process open on shutdown."""
    main = main_module
    _fake_payload(monkeypatch, main)
    main._dashboard_payload_resilient(False, False)

    seen = []
    real_thread = threading.Thread

    class _Spy(real_thread):
        def __init__(self, *a, **kw):
            seen.append(kw)
            super().__init__(*a, **kw)

    monkeypatch.setattr(main.threading, "Thread", _Spy)
    main._dashboard_refresh_in_background((False, False), False, False)
    monkeypatch.undo()

    assert seen, "no thread was started"
    assert all(kw.get("daemon") is True for kw in seen)
    assert _wait_for(lambda: (False, False) not in main._DASHBOARD_REFRESHING)


# ── 7. the page must not paint LIVE over a stale payload ───────────────────
def test_the_page_checks_stale_before_it_declares_live():
    """Structural: the template must handle `d.stale` BEFORE the LIVE path.

    A fallback response is still HTTP 200, so a page that only checks `r.ok`
    prints a confident "LIVE" over numbers it was just told are old.
    """
    from pathlib import Path

    html = Path("templates/dashboard.html").read_text(encoding="utf-8")

    live_at = html.find("b.className = 'badge live'")
    assert live_at != -1, "the LIVE badge assignment moved"

    stale_at = html.find("d.stale === true")
    assert stale_at != -1, (
        "the page no longer branches on d.stale, so it will paint LIVE over a "
        "stale payload")
    assert stale_at < live_at, (
        "the stale branch comes after the LIVE badge, so a stale payload is "
        "still painted LIVE first")

    branch = html[stale_at:live_at]
    assert "return;" in branch, (
        "the stale branch does not return, so execution falls through into "
        "the LIVE path")
    assert "ЗАСТАРЕЛИ" in branch
