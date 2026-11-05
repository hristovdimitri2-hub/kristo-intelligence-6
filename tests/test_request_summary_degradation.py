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


# ── 1. a failing panel degrades; it does not raise ─────────────────────────
def test_a_failing_aggregate_degrades_instead_of_raising(store, monkeypatch):
    """This is the exact failure that took the service to 502."""
    _break(monkeypatch, lambda sql: "COUNT(*) AS n FROM request_log" in sql
           and "WHERE" not in sql)

    out = store.requests_summary()          # must NOT raise

    assert out["available"] is False
    assert "total" in out["degraded"], (
        "the unreadable panel was not named, so the page cannot say what is "
        "missing")


def test_an_unreadable_number_is_none_and_never_an_invented_zero(store,
                                                                 monkeypatch):
    """A zero here is a claim about traffic. We must not invent it."""
    _break(monkeypatch, lambda sql: "COUNT(*) AS n FROM request_log" in sql
           and "WHERE" not in sql)

    out = store.requests_summary()

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

    out = store.requests_summary()

    assert out["today"] == 3, "today's real traffic was lost with the failure"
    assert out["funnel"], "the payment funnel — the revenue panel — was lost"


def test_the_section_still_has_every_key_when_degraded(store, monkeypatch):
    """The page reads these unconditionally; a missing key is a JS crash."""
    _break(monkeypatch, lambda sql: True)   # every query fails

    out = store.requests_summary()

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
    """Ten queries at 8s each is 80 seconds on a request path."""
    from integrations import dashboard_store as ds

    monkeypatch.setattr(ds, "REQUEST_SUMMARY_BUDGET_SECONDS", 0.0)
    seen = _break(monkeypatch, lambda sql: False)   # nothing fails

    out = store.requests_summary()

    assert any("out_of_budget" in name for name in out["degraded"]), (
        "a zero budget still ran queries instead of reporting them as "
        "unreached")
    assert out["degraded"], "nothing was reported as unreached"


def test_the_budget_does_not_skip_the_cheap_and_load_bearing_panels(
        store, monkeypatch):
    """Today, the funnel and the recent log come first on purpose.

    They are what the owner looks at, and they are cheap — so they must survive
    a budget that is already tight.
    """
    from integrations import dashboard_store as ds

    monkeypatch.setattr(ds, "REQUEST_SUMMARY_BUDGET_SECONDS", 6.0)

    out = store.requests_summary()

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

    out = store.requests_summary()

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
    out = store.requests_summary()          # every query runs, none fails

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
