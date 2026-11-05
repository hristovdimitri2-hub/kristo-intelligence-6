"""One slow panel must never take the whole board down.

THE OUTAGE THIS EXISTS FOR. `requests_summary` issues ten queries over
`request_log` (~783K rows, no retention anywhere). Several are full scans:
`COUNT(*)` with no WHERE cannot use an index on any Postgres, and every GROUP BY
reads the whole table. Measured LIVE on 05.11, after four earlier fixes had
already shipped:

    /api/dashboard/build-status
      last_error_type        = QueryCanceled          <- psycopg's statement_timeout
      slowest_step           = requests_summary
      requests_summary       = 21501 ms / 10457 ms / 10153 ms / 11198 ms
      sales_summary          = 172 ms / 7 ms / 8 ms   <- the rest was FINE
      guard_endpoint_map     = 95 ms / 1 ms

The first query to hit the 8-second statement timeout raised QueryCanceled,
which failed the ENTIRE build. A failed build never filled the cache, so every
request built again, so every request timed out again — and the service went to
502 while the dashboard-warmer kept retrying on a 30-second loop.

Note what the numbers say about the earlier four fixes: they were all correct and
none of them was the cause. The whale index, the lock budgets, the 60s cache and
the single-flight cold path were each real and each necessary; the board was
still down because ONE of ten queries could not be read and that was treated as
a fatal error for the other nine.

The assertions that matter:

  * a failing query DEGRADES the section; it does not raise;
  * the numbers that could not be read become None — never an invented 0,
    because a zero here is a factual claim about traffic;
  * the numbers that WERE read stay real and are still shown;
  * the exhausted budget stops issuing queries instead of overrunning; and
  * the page renders "—" for a missing number and SAYS which panels are missing,
    rather than showing an empty table that reads as "no traffic".
"""

from __future__ import annotations

import pathlib
from pathlib import Path

import pytest


@pytest.fixture()
def store(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from integrations.dashboard_store import DashboardStore

    d = DashboardStore(tmp_path / "traffic.db")
    for _ in range(3):
        d.record_request("GET", "/api/v1/signal", "ai_agent", 200, "UA", "")
    return d


def _break(monkeypatch, predicate, exc=None):
    """Make HistoryStore._run raise for matching SQL, and count the calls."""
    from integrations import dashboard_store as ds

    real = ds.HistoryStore._run
    seen = []

    def flaky(self, sql, params=(), fetch=""):
        seen.append(sql)
        if predicate(sql):
            raise exc or RuntimeError("canceling statement due to statement timeout")
        return real(self, sql, params, fetch)

    monkeypatch.setattr(ds.HistoryStore, "_run", flaky)
    return seen


def _compute(store, **kw):
    """The layer that ISSUES the queries — what the background pass runs.

    These tests used to call `store.requests_summary()`. That is no longer the
    same thing, and deliberately so: the request path is forbidden from reading
    the unbounded aggregates at all (they exceed postgres's statement timeout
    and one of them used to fail the whole build). So the invariants about a
    FAILING panel belong on `_requests_summary_compute`, which is exactly what
    the snapshot pass calls. The serve layer's own honesty rule — an unread
    panel is named, never zeroed — is tested separately below.
    """
    target = getattr(store, "history", store)
    return target._requests_summary_compute(**kw)


# ── 1. a failing panel degrades; it does not raise ─────────────────────────
def test_a_failing_aggregate_degrades_instead_of_raising(store, monkeypatch):
    """This is the exact failure that took the service to 502."""
    _break(monkeypatch, lambda sql: "COUNT(*) AS n FROM request_log" in sql
           and "WHERE" not in sql)

    out = _compute(store)                   # must NOT raise

    assert out["available"] is False
    assert "total" in out["degraded"], (
        "the unreadable panel was not named, so the page cannot say what is "
        "missing")


def test_an_unreadable_number_is_none_and_never_an_invented_zero(store,
                                                                 monkeypatch):
    """A zero here is a claim about traffic. We must not invent it."""
    _break(monkeypatch, lambda sql: "COUNT(*) AS n FROM request_log" in sql
           and "WHERE" not in sql)

    out = _compute(store)

    assert out["total"] is None, (
        "an unreadable total was reported as a NUMBER — that is a fabricated "
        "traffic figure, not a missing one")
    assert out["total_clean"] is None, (
        "total_clean was derived from a value we could not read")
    assert out["total"] != 0, "fell back to an invented zero"


def test_the_panels_that_were_read_stay_real(store, monkeypatch):
    """Degrading one panel must not blank the rest of the board."""
    _break(monkeypatch, lambda sql: "COUNT(*) AS n FROM request_log" in sql
           and "WHERE" not in sql)

    out = _compute(store)

    assert out["today"] == 3, "today's real traffic was lost with the failure"
    assert out["funnel"], "the payment funnel — the revenue panel — was lost"


def test_the_section_still_has_every_key_when_degraded(store, monkeypatch):
    """The page reads these unconditionally; a missing key is a JS crash."""
    _break(monkeypatch, lambda sql: True)   # every query fails

    out = _compute(store)

    for key in ("today", "total", "today_clean", "total_clean", "by_source",
                "by_channel", "top_paths", "top_user_agents", "hourly",
                "funnel", "recent", "degraded", "available", "internal_noise"):
        assert key in out, "degraded output dropped the %r key" % key
    assert out["available"] is False
    assert len(out["degraded"]) >= 8, (
        "only %d panels were named as degraded, but every query failed"
        % len(out["degraded"]))


# ── 2. the budget stops the read instead of overrunning ────────────────────
def test_an_exhausted_budget_stops_issuing_queries(store, monkeypatch):
    """Ten queries at 8s each is 80 seconds on a request path.

    Driven by a FAKE clock rather than real elapsed time. The first version of
    this test set the budget to 0.0 and asserted everything degraded — and it
    passed on a machine whose monotonic clock is fine-grained, then failed here,
    where `time.monotonic()` only advances about every 15 ms: the first few
    queries ran inside the same clock tick and were therefore "within budget".
    The assertion was measuring clock granularity, not the budget.

    A clock that advances a fixed amount per query tests the rule itself.
    """
    from integrations import dashboard_store as ds

    ticks = {"t": 1000.0}
    monkeypatch.setattr(ds.time, "monotonic", lambda: ticks["t"])
    monkeypatch.setattr(ds, "REQUEST_SUMMARY_BUDGET_SECONDS", 5.0)

    real = ds.HistoryStore._run
    issued = []

    def slow(self, sql, params=(), fetch=""):
        issued.append(sql)
        ticks["t"] += 3.0            # each query costs 3 of the 5 seconds
        return real(self, sql, params, fetch)

    monkeypatch.setattr(ds.HistoryStore, "_run", slow)

    out = _compute(store)

    assert out["degraded"], "the budget never fired at all"
    assert all("out_of_budget" in name for name in out["degraded"]), (
        "a panel was reported as FAILED when it was merely not reached: %r"
        % out["degraded"])
    assert len(issued) <= 3, (
        "the budget did not stop the read — %d queries were still issued"
        % len(issued))


def test_the_budget_does_not_skip_the_cheap_and_load_bearing_panels(
        store, monkeypatch):
    """Today, the funnel and the recent log come first on purpose.

    They are what the owner looks at, and they are cheap — so a budget that is
    merely tight must still reach them.
    """
    from integrations import dashboard_store as ds

    ticks = {"t": 1000.0}
    monkeypatch.setattr(ds.time, "monotonic", lambda: ticks["t"])
    monkeypatch.setattr(ds, "REQUEST_SUMMARY_BUDGET_SECONDS", 6.0)

    real = ds.HistoryStore._run

    def cheap(self, sql, params=(), fetch=""):
        ticks["t"] += 0.1            # every query is fast
        return real(self, sql, params, fetch)

    monkeypatch.setattr(ds.HistoryStore, "_run", cheap)

    out = _compute(store)

    assert out["today"] == 3
    assert "today" not in out["degraded"]
    assert "recent" not in out["degraded"]


# ── 3. the page must not present a missing number as a real one ────────────
def test_the_page_renders_a_missing_number_as_a_dash():
    """`card(null)` used to print the literal string "null"."""
    html = Path("templates/dashboard.html").read_text(encoding="utf-8")

    start = html.find("function card(")
    assert start != -1
    body = html[start:start + 400]

    assert "num(v)" in body, (
        "card() renders its value without the missing-value guard, so an "
        "unreadable number prints as `null` or blank")
    assert "DASH" in html, "there is no placeholder for a missing number"


def test_the_page_says_which_panels_could_not_be_read():
    """An empty table reads as "no traffic". It has to say "not read"."""
    html = Path("templates/dashboard.html").read_text(encoding="utf-8")

    assert "r.degraded" in html, (
        "the page ignores the degraded list, so a panel that could not be read "
        "is indistinguishable from a panel with no traffic")
    render = html[html.find("function renderRequests("):][:1400]
    assert "degraded" in render


# ── 4. the revenue panel must not claim zero when it was not read ──────────
def test_an_unread_funnel_route_is_none_not_zero(store, monkeypatch):
    """"0 → 0 (0%)" on a paid route is a revenue claim, not a blank.

    This is worse than a missing number: the funnel is the panel that shows
    whether the x402 handshake converts, and printing zeros there says nobody
    has ever paid.
    """
    _break(monkeypatch, lambda sql: "SUM(CASE WHEN status_code = 402" in sql)

    out = _compute(store)

    assert "funnel" in out["degraded"], "the unread funnel was not named"
    for path, row in out["funnel"].items():
        assert row["challenges_total"] is None, (
            "%s reported challenges_total=%r for a query that never ran"
            % (path, row["challenges_total"]))
        assert row["paid_total"] is None, (
            "%s claimed paid_total=%r without reading the database"
            % (path, row["paid_total"]))


def test_a_funnel_route_with_no_traffic_is_still_a_real_zero(store,
                                                             monkeypatch):
    """An answered query with no rows for a route genuinely means zero.

    Without this, "not read" and "no traffic" would collapse into one state and
    the honest fix would just be a different lie.
    """
    out = _compute(store)          # every query runs, none fails

    assert out["funnel"], "no funnel routes at all"
    for path, row in out["funnel"].items():
        assert row["challenges_total"] == 0, (
            "an ANSWERED funnel query must be able to report a real zero")


def test_the_page_does_not_print_a_dashless_zero_for_an_unread_funnel():
    """`f.challenges_today || 0` turns "not read" into "nobody paid"."""
    html = Path("templates/dashboard.html").read_text(encoding="utf-8")
    fn = html[html.find("function renderFunnel("):][:1200]

    assert "null" in fn or "undefined" in fn, (
        "renderFunnel does not check for a missing reading, so an unread route "
        "still renders as a confident 0 → 0 (0%)")
    assert "DASH" in fn, "renderFunnel has no placeholder for a missing reading"


# ── 5. the honest markers must survive the payload whitelist ───────────────
def test_the_degraded_list_survives_into_the_served_payload(monkeypatch):
    """`sections.requests` is an explicit whitelist, and it silently dropped it.

    The store marked missing panels honestly and the page knew how to print
    them — but `main.py` rebuilt the section key by key and never copied
    `degraded` across, so the page could not tell "not read" from "no traffic".
    A marker that is computed and then discarded is not a safeguard.
    """
    import os

    os.environ.setdefault("KRISTO_DISABLE_BACKGROUND_THREADS", "true")
    import main

    body = main.app.test_client().get("/api/dashboard/data").get_json()
    rq = body["sections"]["requests"]

    assert "degraded" in rq, (
        "the served payload drops the degraded list, so an unread panel is "
        "presented as an empty one")
    assert "available" in rq, "the served payload drops the available flag"
    assert isinstance(rq["degraded"], list), (
        "degraded must always be a list — the page iterates it unconditionally")


# ── 6. the request path must never touch the unbounded aggregates ──────────
def test_the_request_path_never_reads_a_heavy_panel(store, monkeypatch):
    """THE regression guard for the 05.11 outage.

    Eight of these ten aggregates are full scans that postgres was cancelling
    at its 8s statement timeout. Running any of them per request is what made
    the board hang past 90s and then took the whole service to 502 with it, and
    the page polls every 45 seconds.

    So this asserts on the SQL the REQUEST path actually asked for: if someone
    later deletes a panel from `REQUEST_SUMMARY_FAST_PANELS`, or calls the
    compute without restricting it, this fails.
    """
    seen = _break(monkeypatch, lambda sql: False)   # nothing fails; record only

    store.requests_summary()

    for sql in seen:
        # Unbounded groupings: these have no predicate that can serve them.
        for marker in ("GROUP BY source", "GROUP BY funnel", "GROUP BY user_agent"):
            assert marker not in sql, (
                "the request path issued a full-table aggregate (%r). That is "
                "the read that took the service down on 05.11 — it belongs in "
                "the background snapshot." % marker)
        # The funnel also groups by path, and that one IS allowed, because it
        # restricts itself with `path IN (...)` and `idx_request_log_path`
        # serves it. The all-time `GROUP BY path` restricts nothing.
        if "GROUP BY path" in sql:
            assert "path IN" in sql, (
                "the request path ran the all-time GROUP BY path, which scans "
                "every row: %r" % " ".join(sql.split())[:120])
        # Every COUNT(*) over the log must be bounded by the indexed day window.
        # `total` and `noise_total` have no such bound and cannot be served.
        if "COUNT(*) AS n FROM request_log" in sql:
            assert "ts >= ? AND ts < ?" in sql, (
                "the request path ran an unbounded COUNT(*) over the whole "
                "table: %r" % " ".join(sql.split())[:120])
    assert seen, "no queries ran at all — this test would pass vacuously"


def test_a_panel_awaiting_the_snapshot_is_named_and_never_zeroed(store):
    """No snapshot yet is UNREADABLE, not zero, and not silent.

    Three distinct states have to stay distinguishable on the board: a real
    zero (we asked, nobody came), a failure (we asked, it broke), and not-read
    (we never asked). Collapsing the last into a zero would claim nobody has
    ever visited the site — a traffic statement we did not measure.
    """
    out = store.requests_summary()

    assert out["total"] is None, "an unread total was reported as a number"
    assert out["total"] != 0, "an unread total was reported as zero"
    named = [d.split(":")[0] for d in out["degraded"]]
    assert "total" in named, (
        "the board cannot say which all-time panel is missing: %r"
        % out["degraded"])
    assert any("awaiting_snapshot" in d for d in out["degraded"]), (
        "a panel that was never attempted was reported as a FAILURE — the two "
        "are different and the page shows them differently")


def test_the_snapshot_supplies_the_heavy_panels_to_the_request_path(
        store, monkeypatch):
    """The whole point: real all-time numbers, read out of band."""
    target = getattr(store, "history", store)
    monkeypatch.setattr(
        target, "snapshot_state",
        lambda: {"value": {"total": 999, "total_clean": 900,
                           "internal_noise": {"today": 0, "total": 99,
                                              "label": "x"},
                           "by_source": [{"source": "direct", "n": 5}],
                           "by_channel": [], "by_source_clean": [],
                           "top_paths": [], "top_user_agents": []},
                 "computed_at": 1000.0, "degraded": []})

    out = store.requests_summary()

    assert out["total"] == 999, "the snapshot's total never reached the board"
    assert out["by_source"] == [{"source": "direct", "n": 5}]
    assert out["today_clean"] == out["today"], (
        "today_clean must be recomputed from the LIVE today and the parked "
        "noise count, not copied from a stale difference")
    assert "awaiting_snapshot" not in " ".join(out["degraded"])


def _fake_psycopg(monkeypatch, on_connect=None, statements=None):
    """A stand-in for psycopg that is a PACKAGE.

    `_pg_open` does `from psycopg.rows import dict_row`, so the fake must be
    importable AS a package: a bare module object raises `ModuleNotFoundError:
    No module named 'psycopg.rows'; 'psycopg' is not a package`. One shared fake
    also means these tests cannot disagree about what a connection looks like.
    """
    import sys
    import types

    class _Cursor:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute(self, sql, params=None):
            if statements is not None:
                statements.append((sql, params))
        def fetchall(self): return []
        def fetchone(self): return None
        @property
        def rowcount(self): return 0

    class _Conn:
        def cursor(self): return _Cursor()
        def commit(self): pass
        def close(self): pass

    rows = types.ModuleType("psycopg.rows")
    rows.dict_row = object()
    pkg = types.ModuleType("psycopg")
    pkg.__path__ = []                      # makes `psycopg.rows` importable
    pkg.rows = rows

    def _connect(dsn, **kw):
        if on_connect is not None:
            on_connect(dsn, kw)
        return _Conn()

    pkg.connect = _connect
    monkeypatch.setitem(sys.modules, "psycopg", pkg)
    monkeypatch.setitem(sys.modules, "psycopg.rows", rows)
    return pkg


def test_the_snapshot_runs_on_its_own_connection_with_a_longer_timeout(
        store, monkeypatch):
    """Both halves of the fix, asserted on the SQL actually sent.

    The shared connection carries an 8s statement timeout — that is what was
    cancelling these reads, so no retry or budget could ever have read them.
    And `_run` holds the shared link's lock for the whole statement, so a
    20-second read through it would queue every fast panel behind it.
    """
    from integrations import dashboard_store as ds

    opened = []
    _fake_psycopg(monkeypatch, on_connect=lambda dsn, kw: opened.append(dsn))
    target = getattr(store, "history", store)
    monkeypatch.setattr(target, "backend", "postgresql")
    monkeypatch.setattr(target, "database_url", "postgres://x/y")

    with target._private_runner() as runner:
        assert runner is not None

    assert opened == ["postgres://x/y"], (
        "the snapshot did not open its own connection — it would contend for "
        "the shared lock and re-create the outage")
    assert ds.REQUEST_SNAPSHOT_STATEMENT_TIMEOUT_MS > ds.PG_STATEMENT_TIMEOUT_MS, (
        "the snapshot's statement timeout is not longer than the shared one, "
        "so postgres will cancel the very reads it exists to perform")


def test_the_statement_timeout_is_set_with_set_config_not_set(store, monkeypatch):
    """A dialect rule that a fake cursor CANNOT catch, so assert on the statement.

    PostgreSQL does not accept a bind parameter on the right of `SET`. psycopg
    sends `$1`, the server answers 42601 syntax error at or near "$1", and the
    pass died there — BEFORE reading a single row. The board then said "awaiting
    the snapshot" for ever, which is exactly what it looked like: waiting.

    Every unit test above passed while this was broken, because a fake connection
    does not have PostgreSQL's grammar. The assertion therefore has to be about
    the SQL we send, and the correct idiom is `set_config`, which is what the
    shared connection twenty lines up already used.
    """
    from integrations import dashboard_store as ds

    seen = []
    _fake_psycopg(monkeypatch, statements=seen)
    target = getattr(store, "history", store)
    monkeypatch.setattr(target, "backend", "postgresql")
    monkeypatch.setattr(target, "database_url", "postgres://x/y")

    with target._private_runner():
        pass

    timeouts = [(sql, params) for sql, params in seen
                if "statement_timeout" in sql]
    assert timeouts, "the private connection never set its own statement timeout"

    for sql, params in timeouts:
        assert not sql.lstrip().upper().startswith("SET "), (
            "`SET statement_timeout = %%s` is a syntax error in PostgreSQL: it "
            "takes no bind parameter, and this is the statement that silently "
            "stopped the snapshot pass from ever running. Sent: %r" % sql)
        assert "set_config" in sql, (
            "the timeout must be set with set_config(...), the parameterisable "
            "form. Sent: %r" % sql)
        assert str(ds.REQUEST_SNAPSHOT_STATEMENT_TIMEOUT_MS) in str(params), (
            "the private connection's timeout is not the snapshot's own: %r"
            % (params,))


def test_the_private_connection_hands_back_rows_by_name(store, monkeypatch):
    """The SECOND dialect rule a fake cursor cannot catch, and it bit next.

    Panel readers index rows by column name — `row["n"]` — because `sqlite3.Row`
    allows it and this module serves both backends. psycopg's default factory
    returns plain tuples, so the private connection raised

        TypeError: tuple indices must be integers or slices, not str

    on the first aggregate it read. Measured live after the `set_config` fix
    landed: `snapshot_error='TypeError'`, and the board still showed dashes.
    A fake connection has no row factory to get wrong, so this asserts on the
    arguments passed to `connect()`.
    """
    import sys
    import types

    sentinel = object()
    calls = []

    class FakeCursor:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def execute(self, sql, params=None): pass
        def fetchall(self): return []
        def fetchone(self): return None
        @property
        def rowcount(self): return 0

    class FakeConn:
        def cursor(self): return FakeCursor()
        def commit(self): pass
        def close(self): pass

    rows_module = types.ModuleType("psycopg.rows")
    rows_module.dict_row = sentinel
    fake = types.ModuleType("psycopg")
    fake.rows = rows_module
    fake.connect = lambda dsn, **kw: (calls.append(kw), FakeConn())[1]
    monkeypatch.setitem(sys.modules, "psycopg", fake)
    monkeypatch.setitem(sys.modules, "psycopg.rows", rows_module)

    target = getattr(store, "history", store)
    monkeypatch.setattr(target, "backend", "postgresql")
    monkeypatch.setattr(target, "database_url", "postgres://x/y")

    with target._private_runner():
        pass

    assert calls, "the private connection was never opened"
    for kwargs in calls:
        assert "row_factory" in kwargs, (
            "the private Postgres connection was opened without a row factory, "
            "so every panel that indexes a row by name will raise TypeError "
            "and the snapshot pass will die before it reads anything. "
            "Arguments: %r" % (kwargs,))
        assert kwargs["row_factory"] is sentinel, (
            "the private connection does not use the same row factory as the "
            "shared one, so the two disagree about what a row IS: %r"
            % (kwargs["row_factory"],))


def test_both_postgres_links_are_made_in_one_place(store, monkeypatch):
    """If two connections must agree, they must not be built in two places.

    They were, and they drifted on BOTH dialect rules — first the statement
    timeout, then the row factory — each costing a deploy to find, because each
    failure was silent. Asserting the FACTORY rather than the arguments is what
    makes that drift impossible to reintroduce without deleting this test.
    """
    from integrations import dashboard_store as ds

    target = getattr(store, "history", store)
    monkeypatch.setattr(target, "backend", "postgresql")
    monkeypatch.setattr(target, "database_url", "postgres://x/y")

    opened = []

    def fake_open(statement_timeout_ms):
        opened.append(statement_timeout_ms)
        raise RuntimeError("reached _pg_open, which is the assertion")

    monkeypatch.setattr(target, "_pg_open", fake_open)

    target._pg_conn = None
    with pytest.raises(RuntimeError, match="reached _pg_open"):
        target._run("SELECT 1")
    with pytest.raises(RuntimeError, match="reached _pg_open"):
        with target._private_runner():
            pass

    assert opened == [ds.PG_STATEMENT_TIMEOUT_MS,
                      ds.REQUEST_SNAPSHOT_STATEMENT_TIMEOUT_MS], (
        "the shared and private Postgres links are not both made through "
        "_pg_open, so they can drift apart again: %r" % (opened,))


def test_a_snapshot_pass_that_fails_keeps_the_previous_numbers(
        store, monkeypatch):
    """A failed pass must not blank the board it was meant to fill."""
    target = getattr(store, "history", store)
    previous = {"value": {"total": 42}, "computed_at": 1.0}
    monkeypatch.setattr(target, "snapshot_state", lambda: previous)

    def boom():
        raise RuntimeError("private connection refused")
    monkeypatch.setattr(target, "_private_runner", boom)

    assert target.refresh_requests_snapshot() == previous, (
        "a failed snapshot pass discarded the numbers we already had")


def test_the_snapshot_round_trip_serves_real_all_time_numbers(tmp_path):
    """End to end on the real path: record traffic, run the pass, serve it.

    The tests above mock the snapshot. This one does not: it records rows, runs
    the very `refresh_requests_snapshot` the warmer runs — through the store's
    ordinary runner, so no socket is needed — and then asserts the request path
    serves the numbers it parked, with no "unreadable" marker left behind.

    That ordering matters. Before the snapshot exists the same call must report
    the panels as UNREAD rather than as zero, so this asserts both halves: the
    honest gap, then the real number.
    """
    from integrations.dashboard_store import DashboardStore

    store = DashboardStore(tmp_path / "round_trip.db")
    for _ in range(3):
        store.record_request("GET", "/api/v1/signal", "api", 200,
                             user_agent="x402-agent/1.0")

    assert store.requests_summary()["total"] is None, (
        "an all-time count was reported as a number before anything read it")

    target = getattr(store, "history", store)
    target.refresh_requests_snapshot(runner=target._run)
    out = store.requests_summary()

    assert out["total"] == 3, "the parked snapshot never reached the board"
    assert out["available"] is True, out["degraded"]
    assert not out["degraded"], out["degraded"]


def test_a_panel_the_snapshot_failed_is_reported_as_a_failure(
        store, monkeypatch):
    """The THIRD state: the background pass tried and could not read it.

    Three states must stay distinguishable on the board — a real zero (asked,
    nobody came), a failure (asked, it broke), and not-read (never asked) — and
    the tests above cover two of them. This is the one a mutation survived on:
    with the failure branch removed, a panel named in the snapshot's own
    `degraded` list was silently dropped from the board's, so a broken read
    looked exactly like a healthy one.
    """
    target = getattr(store, "history", store)
    monkeypatch.setattr(
        target, "snapshot_state",
        lambda: {"value": {"total": None, "internal_noise": {}},
                 "degraded": ["total:QueryCanceled"],
                 "skipped": [],
                 "computed_at": 1000.0})

    out = store.requests_summary()

    named = [d.split(":")[0] for d in out["degraded"]]
    assert "total" in named, (
        "a panel the snapshot failed was dropped from the board entirely, so "
        "a broken read looks like a healthy one: %r" % out["degraded"])
    assert "total:awaiting_snapshot" not in out["degraded"], (
        "a FAILED read was reported as a pending one — the page would sit "
        "waiting for a pass that has already run and already failed")
    assert out["total"] is None, "a failed read was reported as a number"


# ── 7. a live panel that fails falls back to the parked one ────────────────
def _snapshot_with(store, monkeypatch, value, degraded=(), skipped=()):
    target = getattr(store, "history", store)
    monkeypatch.setattr(
        target, "snapshot_state",
        lambda: {"value": value, "degraded": list(degraded),
                 "skipped": list(skipped), "computed_at": 1000.0})
    return target


def test_a_live_funnel_that_fails_falls_back_to_the_parked_one(
        store, monkeypatch):
    """Measured live on 05.11: the funnel was in `degraded` while the other four
    fast panels answered, because `idx_request_log_path` was not serving it and
    the grouped scan fell to the 8s ceiling.

    There were two real numbers available and the board showed neither. A dash
    next to a value we actually hold is its own kind of lie, so the parked one
    is served — and the failure marker goes with it, because the panel is no
    longer unreadable.
    """
    parked_funnel = {"/api/v1/signal": {"challenges_today": 7, "paid_today": 2}}
    _snapshot_with(store, monkeypatch,
                   {"funnel": parked_funnel, "total": 99})
    _break(monkeypatch, lambda sql: "path IN" in sql)

    out = store.requests_summary()

    assert out["funnel"] == parked_funnel, (
        "a failing live funnel was shown as unreadable while a real reading sat "
        "parked: %r" % (out["funnel"],))
    assert "funnel" not in [d.split(":")[0] for d in out["degraded"]], (
        "the panel is reported as unreadable even though a value is being "
        "served for it: %r" % out["degraded"])
    assert "funnel" in (out.get("served_from_snapshot") or []), (
        "the payload does not say that this number is the parked one, so its "
        "age cannot be told")


def test_the_live_funnel_wins_when_it_answers(store, monkeypatch):
    """Fresh beats old. The parked copy is a fallback, not the source."""
    _snapshot_with(store, monkeypatch,
                   {"funnel": {"/stale": {"challenges_today": 1}}, "total": 99})

    out = store.requests_summary()

    assert "/stale" not in (out.get("funnel") or {}), (
        "the parked funnel overrode a live reading, so the board shows an older "
        "number than the one it just read")
    assert "funnel" not in (out.get("served_from_snapshot") or [])


def test_the_parked_funnel_is_never_used_to_invent_zero(store, monkeypatch):
    """With no parked copy either, the four values stay None — never 0.

    The funnel is a MAP of routes, so an unreadable one is a dict whose values
    are all None rather than a bare None. That distinction is the reason the
    fallback above had to test the degraded marker instead of `is None`: the
    naive test never fired and a real parked reading stayed invisible.
    """
    _snapshot_with(store, monkeypatch, {"total": 99})
    _break(monkeypatch, lambda sql: "path IN" in sql)

    out = store.requests_summary()
    assert isinstance(out["funnel"], dict) and out["funnel"], (
        "the funnel must still name its routes, so the page can render the "
        "panel and say it is unread: %r" % (out["funnel"],))
    for route, counts in out["funnel"].items():
        for field, value in counts.items():
            assert value is None, (
                "%s.%s is %r — an unread number was reported as a reading"
                % (route, field, value))
    assert "funnel" in [d.split(":")[0] for d in out["degraded"]], (
        "the board does not say the funnel could not be read")


def test_a_parked_absence_never_overwrites_a_live_reading(store, monkeypatch):
    """The other half of the merge, and the worst shape of wrong.

    `internal_noise.today` is read LIVE, from the indexed day window; the
    snapshot does not read that half at all, so its `today` is None. A plain
    `dict.update()` copied that absence over the live count — and measured on the
    live board that produced `today` a real 22277, `today_clean` a dash, and
    `degraded` EMPTY, because the panel had in fact been read. Two numbers about
    the same traffic, one right and one missing, with nothing to say which.
    """
    _snapshot_with(store, monkeypatch,
                   {"internal_noise": {"today": None, "total": 1075724}})

    out = store.requests_summary()

    assert out["today"] is not None, "the live day count went missing"
    assert out["internal_noise"]["today"] is not None, (
        "the snapshot's absence for the day half overwrote the live reading")
    assert out["internal_noise"]["total"] == 1075724, (
        "the snapshot's real all-time count was not used")
    assert out["today_clean"] == max(0, out["today"]
                                     - out["internal_noise"]["today"]), (
        "today_clean is not the difference of the two numbers shown beside it: "
        "%r vs today=%r noise_today=%r"
        % (out["today_clean"], out["today"], out["internal_noise"]["today"]))


# ── 8. a pass that keeps failing must say so ───────────────────────────────
def test_a_failing_snapshot_pass_is_reported_by_class(store, monkeypatch):
    """'Still coming' and 'has been failing' both look like a dash.

    Only one of them is worth waiting for, so the CLASS of the last failure is
    published. The message is not: a driver error can carry the DSN, which is
    why the payload carries `QueryCanceled` and not the connection string.
    """
    target = getattr(store, "history", store)
    monkeypatch.setattr(target, "_private_runner", lambda: (_ for _ in ()).throw(
        RuntimeError("postgres://user:secret@host/db refused")))

    assert target.refresh_requests_snapshot() == {}
    assert target._snapshot_last_error == "RuntimeError"

    out = store.requests_summary()
    assert out["snapshot_error"] == "RuntimeError", (
        "the board cannot say that the snapshot pass is failing")
    assert "secret" not in str(out), (
        "the driver's message reached the payload, so the DSN can leak")


def test_a_pass_that_succeeds_clears_the_previous_failure(store, monkeypatch):
    """A stale failure is its own lie once the thing works again."""
    target = getattr(store, "history", store)
    target._snapshot_last_error = "QueryCanceled"

    target.refresh_requests_snapshot(runner=target._run)

    assert target._snapshot_last_error is None
    assert store.requests_summary()["snapshot_error"] is None

