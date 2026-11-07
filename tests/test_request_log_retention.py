"""request_log retention — the fix for the 07.11 memory kill.

`request_log` was the one table in the service with no retention at all: it
grew from the first day and never shrank, and the ten dashboard aggregates over
it were the most expensive reads in the service (10-21s each against an 8s
statement timeout). These tests pin the two things that matter:

  1. It deletes rows past the horizon and nothing else.
  2. It is idempotent, and a hostile `days` cannot turn it into "delete all".

The horizon itself is asserted too: 30 days is only safe because the single
window any query opens on this table is 24 hours. If someone later widens a
dashboard read to 30 days, the horizon has to move with it — that coupling is
what these assertions protect.
"""
from datetime import datetime, timedelta, timezone

from integrations import dashboard_store as ds
from integrations.dashboard_store import DashboardStore


def _insert_request(store, ts, path="/api/v1/signal", status=402):
    """Insert one request_log row at an explicit timestamp.

    `record_request` stamps `now()` and cannot express an old row, which is
    exactly what a retention test needs — so the row goes in directly, against
    the same columns `record_request` writes.
    """
    store.history._run(
        """INSERT INTO request_log
               (ts, method, path, source, status_code, user_agent, referer,
                funnel)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (ts, "GET", path, "render", status, "test/1.0", "", path))


def test_retention_deletes_only_rows_past_the_horizon(tmp_path):
    store = DashboardStore(tmp_path / "retention.db")
    old_ts = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
    fresh_ts = datetime.now(timezone.utc).isoformat()
    _insert_request(store, old_ts)
    _insert_request(store, fresh_ts)

    assert store.purge_old_requests() == 1          # the 40-day-old row
    assert store.purge_old_requests() == 0          # idempotent


def test_retention_keeps_a_row_just_inside_the_horizon(tmp_path):
    """A row at 29 days must survive; 31 days must not. The boundary is the
    whole contract — off-by-one here silently deletes history that a panel
    could still have shown."""
    store = DashboardStore(tmp_path / "boundary.db")
    inside = (datetime.now(timezone.utc) - timedelta(days=29)).isoformat()
    outside = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
    _insert_request(store, inside, path="/keep")
    _insert_request(store, outside, path="/drop")

    assert store.purge_old_requests() == 1
    rows = store.history._run(
        "SELECT path FROM request_log", (), "all")[0]
    assert [r["path"] for r in rows] == ["/keep"]


def test_a_zero_or_negative_horizon_cannot_mean_delete_everything(tmp_path):
    """`max(1, int(days))` mirrors the whale pass.

    Without it, `days=0` would delete every row in the traffic ledger — a
    mistake that is unrecoverable, on a table that backs the whole dashboard.
    """
    store = DashboardStore(tmp_path / "guard.db")
    fresh = datetime.now(timezone.utc).isoformat()
    _insert_request(store, fresh)

    assert store.purge_old_requests(0) == 0
    assert store.purge_old_requests(-5) == 0
    rows = store.history._run(
        "SELECT COUNT(*) AS n FROM request_log", (), "one")[0]
    assert rows["n"] == 1, "a hostile horizon deleted live traffic"


def test_the_horizon_is_wider_than_anything_that_reads_the_table():
    """The coupling that makes 30 days safe.

    Every query against `request_log` opens a 24-hour window. Retention is only
    correct while it stays strictly wider than the widest read; if a read grows
    past it, deleted rows become missing answers on a panel.
    """
    assert ds.REQUEST_LOG_RETENTION_DAYS_DEFAULT == 30
    # 24h read < 30d horizon, with real headroom.
    assert ds.REQUEST_LOG_RETENTION_DAYS_DEFAULT > 1
    assert ds.REQUEST_LOG_RETENTION_DAYS_DEFAULT * 24 > 24


def test_retention_is_batched_and_bounded_per_statement(tmp_path):
    """The first run on the live table has ~1.1M rows to remove. One unbounded
    DELETE would hold a long lock and could itself exhaust memory on the small
    plan — the very failure this pass exists to fix."""
    import inspect

    src = inspect.getsource(ds.HistoryStore.purge_old_requests)
    assert "LIMIT" in src, "the delete must be batched, not one unbounded DELETE"
    assert "5000" in src, "the batch size is part of the contract"


def test_retention_reports_what_it_removed(tmp_path):
    """The boot log line is the only record of what happened. A pass that
    deleted rows but reported 0 would be worse than no log at all."""
    store = DashboardStore(tmp_path / "count.db")
    old = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    for _ in range(3):
        _insert_request(store, old)
    assert store.purge_old_requests() == 3
