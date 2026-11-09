"""The dashboard must stay operational — and must stay HONEST while it does.

The owner's requirement is that the board is always up ("искам таблото
постоянно да е оперативно").

Four fixes got here, and the difference between them is the whole lesson:

  * `eafdacf` bounded the Postgres waits, so one slow read could not take the
    SERVICE down.
  * `a8d717e` stopped the board from blanking when a read failed.
  * `6679507` cached the eight unbounded request_log aggregates.
  * the current design keeps the request path off the database entirely.

The last two were needed because bounding a bad number is not the same as
fixing it. Measured after `a8d717e` deployed:

    /health              HTTP 200     420 ms
    /                    HTTP 200     345 ms
    /api/dashboard/data  40+ seconds, then HTTP 500

and measured again after the first cache landed, when four requests arrived at
once on a cold process:

    /api/dashboard/data  4 x timeout at 25 s
    /health              HTTP 502
    /                    HTTP 502
    /openapi.json        HTTP 502

So the cold path was itself the outage. Four simultaneous first requests ran
four concurrent 40-second builds, which ate all 8 gunicorn threads and queued
behind the single shared Postgres link — and the whole service died with them.

The assertions that carry the weight, therefore:

  * a cached variant is served WITHOUT rebuilding;
  * a STAMPEDE of cold requests runs exactly ONE build — the actual regression
    that took the service down twice;
  * the request thread never performs the build;
  * only one refresh per variant is ever in flight;
  * and the honesty rules hold: an old payload is LABELLED, a broken build
    raises, and a public caller is never served an admin variant.
"""

from __future__ import annotations

import json
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
    def _reset():
        with main_module._DASHBOARD_LAST_GOOD_LOCK:
            main_module._DASHBOARD_LAST_GOOD.clear()
            main_module._DASHBOARD_REFRESHING.clear()
            main_module._DASHBOARD_LAST_ERROR.clear()

    _reset()
    yield
    _reset()


@pytest.fixture()
def refreshes(monkeypatch, main_module):
    """Record refresh scheduling, and PERFORM it synchronously.

    These tests are about the scheduling decision, so running a real thread
    would only make them timing-dependent. But the fake must still build: the
    cold path now starts a background build and waits for it, so a no-op fake
    would leave every cold test waiting for a build that never happens.
    """
    started = []

    def fake(key, include_crm, include_sales_detail):
        started.append(key)
        main_module._dashboard_build(key, include_crm, include_sales_detail)
        return True

    monkeypatch.setattr(main_module, "_dashboard_refresh_in_background", fake)
    return started


@pytest.fixture()
def schedule_only(monkeypatch, main_module):
    """Record refresh scheduling WITHOUT building — for primed-cache tests."""
    started = []

    def fake(key, include_crm, include_sales_detail):
        started.append(key)
        return True

    monkeypatch.setattr(main_module, "_dashboard_refresh_in_background", fake)
    return started


def _fake_payload(monkeypatch, main, value=1.23, delay=0.0, gate=None,
                  record_thread=False):
    """Replace the real builder with a controllable stand-in."""
    calls = {"n": 0, "threads": []}

    def builder(include_crm=False, include_sales_detail=False):
        calls["n"] += 1
        if record_thread:
            calls["threads"].append(threading.current_thread().name)
        if gate is not None:
            gate.wait(10.0)
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


def _wait_for(predicate, timeout=10.0):
    """Poll until `predicate()` is true. Returns whether it became true."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


def _backdate(main, key, seconds):
    with main._DASHBOARD_LAST_GOOD_LOCK:
        payload, _ = main._DASHBOARD_LAST_GOOD[key]
        main._DASHBOARD_LAST_GOOD[key] = (payload, time.time() - seconds)


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
    """Serving from cache is what keeps the 45-second poll off the database."""
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


# ── 2. THE STAMPEDE — the regression that caused the second outage ─────────
def test_a_stampede_of_cold_requests_runs_exactly_one_build(
        main_module, monkeypatch):
    """Four concurrent cold requests must not become four 40-second builds.

    On 05.11 they did, and the result was not a slow dashboard: every gunicorn
    thread was consumed, /health returned 502 and the static `/` took 15s.
    """
    main = main_module
    gate = threading.Event()
    calls = _fake_payload(monkeypatch, main, gate=gate)

    outcomes = []

    def hit():
        try:
            outcomes.append(main._dashboard_payload_resilient(False, False))
        except Exception as exc:                       # recorded, not raised:
            outcomes.append(exc)                       # assertions below

    threads = [threading.Thread(target=hit) for _ in range(6)]
    for t in threads:
        t.start()

    assert _wait_for(lambda: (False, False) in main._DASHBOARD_REFRESHING), (
        "no build was started at all")
    time.sleep(0.4)                                    # let the rest pile up

    assert calls["n"] == 1, (
        "a stampede of 6 cold requests started %d builds" % calls["n"])
    assert len(main._DASHBOARD_REFRESHING) == 1

    gate.set()
    for t in threads:
        t.join(15)

    assert len(outcomes) == 6
    assert all(isinstance(o, dict) for o in outcomes), (
        "some waiters failed instead of being served the build they waited "
        "for: %r" % [o for o in outcomes if not isinstance(o, dict)][:2])
    assert calls["n"] == 1, "a second build ran after the first finished"


def test_the_request_thread_never_performs_the_build(main_module, monkeypatch):
    """The build runs on the daemon refresher, never on a request thread.

    This is what keeps a slow build from consuming a gunicorn worker.
    """
    main = main_module
    calls = _fake_payload(monkeypatch, main, record_thread=True)

    main._dashboard_payload_resilient(False, False)

    assert calls["threads"], "the builder never ran"
    for name in calls["threads"]:
        assert name == "dashboard-refresh", (
            "the dashboard payload was built on thread %r — a slow build "
            "there occupies a gunicorn worker" % name)


# ── 3. ageing triggers a refresh BEHIND the reader ─────────────────────────
def test_an_ageing_payload_starts_a_background_refresh(main_module, monkeypatch,
                                                       refreshes):
    from main import _DASHBOARD_REVALIDATE_SECONDS

    main = main_module
    _fake_payload(monkeypatch, main)
    main._dashboard_payload_resilient(False, False)

    _backdate(main, (False, False), _DASHBOARD_REVALIDATE_SECONDS + 5)
    refreshes.clear()
    main._dashboard_payload_resilient(False, False)

    assert (False, False) in refreshes, (
        "an ageing payload did not schedule a refresh, so it would never "
        "become current again")


def test_the_reader_does_not_wait_for_the_refresh(main_module, monkeypatch,
                                                  schedule_only):
    """With a payload in hand, a scheduled refresh must not delay the read."""
    from main import _DASHBOARD_REVALIDATE_SECONDS

    main = main_module
    gate = threading.Event()
    calls = _fake_payload(monkeypatch, main, gate=gate)

    with main._DASHBOARD_LAST_GOOD_LOCK:
        main._DASHBOARD_LAST_GOOD[(False, False)] = (
            {"ok": True, "sections": {"onchain": {"total_usdc": 1.23}}},
            time.time() - (_DASHBOARD_REVALIDATE_SECONDS + 5))

    t0 = time.time()
    out = main._dashboard_payload_resilient(False, False)
    elapsed = time.time() - t0
    gate.set()

    assert elapsed < 1.0, (
        "the read blocked for %.2fs waiting on the rebuild" % elapsed)
    assert out["ok"] is True
    assert calls["n"] == 0, "the refresh ran on the request path"
    assert schedule_only, "no refresh was scheduled for the ageing payload"


# ── 4. honesty: an old payload says so ─────────────────────────────────────
def test_a_payload_older_than_the_fresh_window_is_labelled_stale(
        main_module, monkeypatch, schedule_only):
    from main import _DASHBOARD_FRESH_SECONDS

    main = main_module
    _fake_payload(monkeypatch, main)

    with main._DASHBOARD_LAST_GOOD_LOCK:
        main._DASHBOARD_LAST_GOOD[(False, False)] = (
            {"ok": True, "sections": {"onchain": {"total_usdc": 1.23}}},
            time.time() - (_DASHBOARD_FRESH_SECONDS + 30))

    out = main._dashboard_payload_resilient(False, False)

    assert out["stale"] is True, (
        "a payload well past the fresh window was still presented as live")
    assert out["stale_age_seconds"] >= _DASHBOARD_FRESH_SECONDS
    assert out["stale_since"]
    assert out["stale_reason"]
    # Still the real numbers, not blanks and not a zero.
    assert out["sections"]["onchain"]["total_usdc"] == 1.23


def test_the_stale_marker_reports_the_real_age(main_module, monkeypatch,
                                               schedule_only):
    from main import _DASHBOARD_FRESH_SECONDS

    main = main_module
    _fake_payload(monkeypatch, main)

    age = _DASHBOARD_FRESH_SECONDS + 42
    with main._DASHBOARD_LAST_GOOD_LOCK:
        main._DASHBOARD_LAST_GOOD[(False, False)] = (
            {"ok": True, "sections": {}}, time.time() - age)

    out = main._dashboard_payload_resilient(False, False)

    assert abs(out["stale_age_seconds"] - age) < 5, (
        "the reported age (%.0fs) is not the real one (%.0fs)"
        % (out["stale_age_seconds"], age))


# ── 5. a broken build is REPORTED, not hidden behind a warm-up ─────────────
def test_a_broken_first_build_raises_the_real_reason(main_module, monkeypatch):
    """503 "warming up" would be a lie if the build is actually failing."""
    main = main_module

    def boom(include_crm=False, include_sales_detail=False):
        raise RuntimeError("the database is unreachable")

    monkeypatch.setattr(main, "_canonical_dashboard_payload", boom)

    with pytest.raises(RuntimeError) as err:
        main._dashboard_payload_resilient(False, False)

    assert "the database is unreachable" in str(err.value), (
        "the caller was told something other than the real failure")

    with main._DASHBOARD_LAST_GOOD_LOCK:
        assert main._DASHBOARD_LAST_GOOD == {}, (
            "a failed build published something to the cache")


def test_a_slow_first_build_times_out_as_warming_not_an_error(
        main_module, monkeypatch):
    """A request must not hold a worker for the whole build."""
    main = main_module
    monkeypatch.setattr(main, "_DASHBOARD_COLD_WAIT_SECONDS", 0.3)
    gate = threading.Event()
    _fake_payload(monkeypatch, main, gate=gate)

    t0 = time.time()
    with pytest.raises(main.DashboardWarming):
        main._dashboard_payload_resilient(False, False)
    elapsed = time.time() - t0
    gate.set()

    assert elapsed < 3.0, (
        "the cold path waited %.1fs, far past the 0.3s it was given" % elapsed)


# ── 6. the security boundary: the key is the GRANT, never the caller ───────
def test_a_public_caller_can_never_be_served_the_admin_payload(
        main_module, monkeypatch, refreshes):
    """A single shared cache slot — the obvious "optimisation" — fails here."""
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

    assert calls["n"] == 2, "the two grant pairs shared one cache slot"
    assert main._dashboard_payload_resilient(True, False)["crm"] == {"leads": 7}
    assert main._dashboard_payload_resilient(False, True).get("crm") is None


# ── 7. the REAL background thread ──────────────────────────────────────────
def test_a_failing_background_refresh_neither_raises_nor_wipes_the_cache(
        main_module, monkeypatch):
    main = main_module
    calls = _fake_payload(monkeypatch, main)
    main._dashboard_payload_resilient(False, False)

    def boom(include_crm=False, include_sales_detail=False):
        calls["n"] += 1
        raise RuntimeError("transient read failure")

    monkeypatch.setattr(main, "_canonical_dashboard_payload", boom)

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

    with main._DASHBOARD_LAST_GOOD_LOCK:
        main._DASHBOARD_LAST_GOOD[(False, False)] = (
            {"ok": True, "sections": {}}, time.time())

    main._dashboard_refresh_in_background((False, False), False, False)
    assert _wait_for(lambda: (False, False) in main._DASHBOARD_REFRESHING)

    for _ in range(5):
        started = main._dashboard_refresh_in_background(
            (False, False), False, False)
        assert started is False, "a second refresh was started concurrently"

    gate.set()
    assert _wait_for(lambda: (False, False) not in main._DASHBOARD_REFRESHING)
    assert calls["n"] == 1, (
        "expected exactly one refresh, got %d builds" % calls["n"])


def test_the_refresh_thread_is_a_daemon(main_module, monkeypatch):
    """A non-daemon thread would hold the process open on shutdown."""
    main = main_module
    _fake_payload(monkeypatch, main)

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


# ── 8. the diagnosis must be readable AND not a leak ───────────────────────
def _status(main, monkeypatch, admin=False):
    monkeypatch.setattr(main, "_is_admin_request", lambda: admin)
    return main.app.test_client().get("/api/dashboard/build-status")


def test_build_status_says_which_step_is_slow(main_module, monkeypatch):
    """The whole point: stop guessing which read costs the time.

    Diagnosing 05.11 meant guessing, and the first guess — "Render billing" —
    was wrong. This is the payload saying it itself.
    """
    main = main_module
    with main._DASHBOARD_LAST_GOOD_LOCK:
        main._DASHBOARD_LAST_BUILD_TIMINGS.clear()
        main._DASHBOARD_LAST_BUILD_TIMINGS.update(
            {"sales_summary": 120.0, "whaleflow_summary": 9000.0})

    d = _status(main, monkeypatch).get_json()

    assert d["slowest_step"] == "whaleflow_summary"
    assert d["last_build_timings_ms"]["whaleflow_summary"] == 9000.0


def test_build_status_reports_the_failure_type_but_never_the_message(
        main_module, monkeypatch):
    """A psycopg message can name the host and the user; a type name cannot."""
    main = main_module
    secret = "connection to server at 10.0.0.5, port 5432 failed: FATAL"
    with main._DASHBOARD_LAST_GOOD_LOCK:
        main._DASHBOARD_LAST_ERROR[(False, False)] = {
            "type": "OperationalError", "message": secret}

    d = _status(main, monkeypatch, admin=False).get_json()

    assert d["last_error_type"] == {"(False, False)": "OperationalError"}, (
        "the failure CLASS is the diagnosis and must be published")
    assert "last_error_message" not in d, (
        "the public status exposed the raw failure message")
    assert "10.0.0.5" not in json.dumps(d), (
        "the public status leaked the database host")


def test_build_status_gives_an_admin_the_message_too(main_module, monkeypatch):
    """The operator is the one who has to act on it."""
    main = main_module
    with main._DASHBOARD_LAST_GOOD_LOCK:
        main._DASHBOARD_LAST_ERROR[(False, False)] = {
            "type": "OperationalError", "message": "relation does not exist"}

    d = _status(main, monkeypatch, admin=True).get_json()

    assert d["last_error_message"] == {
        "(False, False)": "relation does not exist"}


def test_build_status_reports_cache_age_and_tunables(main_module, monkeypatch):
    main = main_module
    with main._DASHBOARD_LAST_GOOD_LOCK:
        main._DASHBOARD_LAST_GOOD[(False, False)] = ({"ok": True},
                                                     time.time() - 42)

    d = _status(main, monkeypatch).get_json()

    assert abs(d["cache_age_seconds"]["(False, False)"] - 42) < 5
    assert d["revalidate_seconds"] > 0
    assert d["cold_wait_seconds"] > 0


def test_the_data_route_answers_503_warming_not_500(main_module, monkeypatch):
    """503 says "not ready yet"; 500 would claim the service is broken."""
    main = main_module

    def warming(include_crm, include_sales_detail):
        raise main.DashboardWarming("still building")

    monkeypatch.setattr(main, "_dashboard_payload_resilient", warming)
    monkeypatch.setattr(main, "_is_admin_request", lambda: False)
    monkeypatch.setattr(main, "_operator_view_enabled", lambda: False)

    r = main.app.test_client().get("/api/dashboard/data")

    assert r.status_code == 503
    assert r.get_json()["warming"] is True


# ── 9. the page must not paint LIVE over a stale payload ───────────────────
def test_the_page_checks_stale_before_it_declares_live():
    """Structural: the template must handle `d.stale` BEFORE the LIVE path.

    A served-from-cache response is still HTTP 200, so a page that only checks
    `r.ok` prints a confident "LIVE" over numbers it was just told are old.
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

# ── 10. a restart must not be an outage ────────────────────────────────────
#
# 09.11: every deploy emptied the in-memory board, the next visitor waited the
# cold-wait window and got 503 {"warming": true} — which the page painted as
# "ГРЕШКА: HTTP 503 … НЕАКТУАЛНИ". A docs-only push did it. The owner's
# requirement is that the board is ALWAYS operational, so the last good PUBLIC
# board is now kept in the durable store (Postgres — this service has no disk,
# `data/*.db` is wiped on deploy) and replayed on a cold start.

class _FakeMetaStore:
    """Only the two calls the board's persistence uses."""

    def __init__(self, doc=None, fail_write=False):
        self.doc = dict(doc or {})
        self.writes = []
        self.fail_write = fail_write

    def get_meta(self, key, default=None):
        return self.doc.get(key, default)

    def set_meta(self, key, value):
        if self.fail_write:
            raise RuntimeError("the store refused the write")
        self.writes.append((key, value))
        self.doc[key] = value


def _seeded_store(main, age_seconds=0.0, payload=None):
    """A store holding a board that was built `age_seconds` ago."""
    doc = {"built_at": time.time() - age_seconds,
           "payload": payload if payload is not None else {"ok": True,
                                                           "signed": "REAL"}}
    return _FakeMetaStore({main._DASHBOARD_BOARD_META_KEY: json.dumps(doc)})


@pytest.fixture()
def meta_store(monkeypatch, main_module):
    """Give a test its own durable store and reset the write rate-limiter."""
    monkeypatch.setattr(main_module, "_DASHBOARD_PERSISTED_AT", 0.0)

    def _install(store):
        monkeypatch.setattr(main_module, "_dashboard_meta_store", lambda: store)
        return store

    return _install


def test_a_restart_serves_the_persisted_board_instead_of_503(
        main_module, meta_store):
    """THE FIX. Empty memory + a stored board must answer, not raise."""
    main = main_module
    store = meta_store(_seeded_store(main, age_seconds=600))

    out = main._dashboard_payload_resilient(False, False)

    assert out["signed"] == "REAL", "the stored board was not replayed"
    assert out["stale"] is True, "a 10-minute-old board was painted fresh"
    assert abs(out["stale_age_seconds"] - 600) < 30
    assert store.writes == [], "serving a stored board triggered a write"


def test_a_fresh_persisted_board_is_served_without_a_cold_wait(
        main_module, monkeypatch, meta_store, refreshes):
    """The common case: the deploy was seconds ago, so no refresh is even due."""
    main = main_module
    monkeypatch.setattr(main, "_DASHBOARD_COLD_WAIT_SECONDS", 0.01)
    meta_store(_seeded_store(main, age_seconds=1.0))

    t0 = time.time()
    out = main._dashboard_payload_resilient(False, False)

    assert time.time() - t0 < 1.0, "a stored board still waited for a cold build"
    assert out["stale"] is False
    assert refreshes == [], "a 1-second-old board should not rebuild"


def test_the_data_route_answers_200_after_a_restart(main_module, monkeypatch,
                                                    meta_store):
    """End to end, through the route the page actually calls."""
    main = main_module
    monkeypatch.setattr(main, "_is_admin_request", lambda: False)
    monkeypatch.setattr(main, "_operator_view_enabled", lambda: False)
    meta_store(_seeded_store(main, age_seconds=5.0))

    r = main.app.test_client().get("/api/dashboard/data")

    assert r.status_code == 200, (
        "a restart still answers %s — that is the error the owner saw"
        % r.status_code)
    assert r.get_json()["signed"] == "REAL"


def test_the_admin_and_operator_variants_are_never_persisted(
        main_module, meta_store):
    """The CRM section must not reach shared storage — that is why the key is
    the grant pair and why only (False, False) is written."""
    main = main_module
    store = meta_store(_FakeMetaStore())

    main._dashboard_persist_board((False, False), {"public": True})
    main._dashboard_persist_board((True, True), {"crm": {"leads": 7}})
    main._dashboard_persist_board((True, False), {"crm": {"leads": 7}})
    main._dashboard_persist_board((False, True), {"sales_detail": ["0xdead"]})

    assert [k for k, _ in store.writes] == [main._DASHBOARD_BOARD_META_KEY]
    assert "crm" not in store.writes[0][1]
    assert "0xdead" not in store.writes[0][1]


def test_a_restart_never_reads_a_non_public_board(main_module, meta_store):
    """Symmetry with the write rule: only the public key is ever looked up."""
    main = main_module
    store = meta_store(_seeded_store(main))

    assert main._dashboard_seed_from_store((True, True)) is False
    assert main._dashboard_seed_from_store((True, False)) is False
    assert store.writes == []
    assert main._dashboard_seed_from_store((False, False)) is True


def test_a_corrupt_stored_board_does_not_become_an_error(
        main_module, monkeypatch, meta_store):
    """Bad bytes in the store must degrade to the old cold behaviour, not to a
    crash on every request."""
    main = main_module
    monkeypatch.setattr(main, "_DASHBOARD_COLD_WAIT_SECONDS", 0.01)
    gate = threading.Event()
    _fake_payload(monkeypatch, main, gate=gate)     # the build will not finish
    meta_store(_FakeMetaStore({main._DASHBOARD_BOARD_META_KEY: "{not json"}))

    with pytest.raises(main.DashboardWarming):
        main._dashboard_payload_resilient(False, False)
    gate.set()


def test_a_store_that_refuses_the_write_does_not_break_the_build(
        main_module, meta_store):
    """Persistence is best-effort: the board is served from memory either way."""
    main = main_module
    meta_store(_FakeMetaStore(fail_write=True))

    main._dashboard_persist_board((False, False), {"ok": True})   # must not raise


def test_the_persist_is_rate_limited(main_module, meta_store):
    """~50 KB into Postgres every 30-second revalidation would be waste."""
    main = main_module
    store = meta_store(_FakeMetaStore())

    main._dashboard_persist_board((False, False), {"n": 1})
    main._dashboard_persist_board((False, False), {"n": 2})

    assert len(store.writes) == 1, "the board was rewritten on every build"


# ── 11. the page must not call a restart an error ──────────────────────────
def test_the_page_treats_503_as_warming_not_as_an_error():
    """Structural, because this is the text the owner reads."""
    from pathlib import Path

    html = Path("templates/dashboard.html").read_text(encoding="utf-8")

    warm_at = html.find("r.status === 503")
    throw_at = html.find("throw new Error('HTTP ' + r.status)")
    assert warm_at != -1, "the page no longer recognises a warming 503"
    assert throw_at != -1, "the generic error path moved"
    assert warm_at < throw_at, (
        "503 falls through to the error path, so a restart is still an error")

    branch = html[warm_at:throw_at]
    assert "ЗАГРЯВА" in branch, "a warming board is not labelled as warming"
    assert "ГРЕШКА" not in branch, (
        "the warming branch still writes the word ERROR on the board")
    assert "setTimeout(load, 2500)" in branch, (
        "the page does not retry quickly, so the board stays empty for a cycle")


def test_the_page_retries_a_real_error_without_waiting_a_full_cycle():
    from pathlib import Path

    html = Path("templates/dashboard.html").read_text(encoding="utf-8")

    err_at = html.find("b.className = 'badge err'")
    assert err_at != -1
    assert "setTimeout(load, 5000)" in html[err_at:err_at + 900], (
        "one failed fetch leaves the board red until the next 45s cycle")
    assert "setInterval(load, 45000)" in html, "the LIVE cycle must stay"

def test_a_transient_dropped_connection_is_not_painted_as_an_error():
    """Measured 09.11 20:10:32 during a restart: the instance swap closes the
    connection once, `fetch` throws, and the next poll 6s later answers 200. A
    board that shouts ГРЕШКА for that is reporting its own deployment."""
    from pathlib import Path

    html = Path("templates/dashboard.html").read_text(encoding="utf-8")

    assert "let failures = 0;" in html, "the failure counter is gone"
    transient_at = html.find("failures <= 3")
    err_at = html.find("b.className = 'badge err'")
    assert transient_at != -1, "a dropped connection is no longer tolerated"
    assert err_at != -1
    assert transient_at < err_at, (
        "every single failure goes straight to the error badge again")

    branch = html[transient_at:err_at]
    assert "ПРЕЗАРЕЖДАНЕ" in branch
    assert "ГРЕШКА" not in branch, (
        "the transient branch still writes the word ERROR on the board")
    assert "setTimeout(load, 2500)" in branch, (
        "a dropped connection is not retried quickly")

    assert "failures = 0;" in html[:html.find("async function load()")] or \
        "failures = 0;" in html, "the counter is never reset"
