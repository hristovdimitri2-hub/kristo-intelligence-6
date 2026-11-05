"""Bounds on the ONE shared Postgres link — the 05.11 outage.

HistoryStore keeps a single Postgres connection behind a single lock
(`self._pg_lock`, since it is documented as "one shared, serialised link").
That design is fine while every statement is fast. It stops being fine the
moment one of them is not: the holder keeps the lock, every caller queues
behind it, and because the process runs `--workers 1 --threads 8`, eight
queued callers are every worker there is.

That is exactly what happened. Measured against the live service on 05.11:

    /api/dashboard/data  hung past 90s, no response at all
    /api/v1/whaleflow    402 in 10.6s
    /health              502 (once the threads were gone)
    Render              answered 502 with x-render-routing: dynamic-paid-error

The 402 is the tell: a 402 challenge is a STATIC response that reads no
history table. It took 10.6s only because request logging goes through the
same lock. Nothing about that route was slow; it was waiting.

These tests pin the three bounds that stop a slow link from becoming a dead
service. They are deliberately about SHAPE, not about milliseconds: they
assert that waiting is finite, that the lock is always given back, and that
the reconnect is bounded and detectable. A future edit that removes any of
those must fail here rather than in production.
"""

from __future__ import annotations

import threading

import pytest


# ── helpers ────────────────────────────────────────────────────────────────
class _FakeCursor:
    def __init__(self, log):
        self._log = log

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, sql, params=()):
        self._log.append((sql, params))

    def fetchall(self):
        return []

    def fetchone(self):
        return None

    @property
    def rowcount(self):
        return 0


class _FakeConn:
    def __init__(self, log):
        self._log = log
        self.closed = False
        self.broken = False
        self.commits = 0

    def cursor(self):
        return _FakeCursor(self._log)

    def commit(self):
        self.commits += 1

    def close(self):
        self.closed = True


def _history_store():
    """A HistoryStore carrying only the fields `_run`/`_pg_connection` touch.

    Built with `__new__` deliberately. `__init__` runs the entire schema DDL,
    which needs a real database and is unrelated to the bounds under test —
    and a `:memory:` SQLite connector cannot serve it anyway, because every
    call would open a fresh, empty database.
    """
    from integrations.dashboard_store import HistoryStore

    store = HistoryStore.__new__(HistoryStore)
    store.backend = "postgresql"
    store.database_url = "postgresql://fake/db"
    store._ph = "%s"
    store._pg_conn = None
    store._pg_lock = threading.Lock()
    store._lock = threading.Lock()
    return store


# ── 1. a held lock must not block a caller forever ─────────────────────────
def test_a_held_lock_refuses_instead_of_queueing_forever(monkeypatch):
    """The defect: waiting on `_pg_lock` without a bound.

    A caller that waits forever behind a stalled holder is how one slow
    statement became a 90-second hang and then a 502 for the whole service.
    With the bound in place the caller gives up and RAISES — a fast, honest
    error — rather than consuming a worker indefinitely.
    """
    from integrations import dashboard_store as ds

    store = _history_store()
    store.backend = "postgresql"
    store.database_url = "postgresql://fake/db"
    store._pg_connection = lambda: _FakeConn([])

    # The whole point: keep the wait small enough to test, not to hide it.
    monkeypatch.setattr(ds, "PG_LOCK_WAIT_SECONDS", 0.25)

    # Simulate the stalled holder: take the lock and do not give it back.
    assert store._pg_lock.acquire(blocking=False)
    try:
        started = threading.Event()
        finished = threading.Event()
        raised = []

        def caller():
            started.set()
            try:
                store._run("SELECT 1", fetch="all")
            except BaseException as exc:  # noqa: BLE001 - we assert on the type
                raised.append(exc)
            finally:
                finished.set()

        t = threading.Thread(target=caller, daemon=True)
        t.start()
        started.wait(2)
        # If the wait were unbounded this would never be set.
        assert finished.wait(10), "_run() did not return while the lock was held"
        t.join(5)

        assert raised, "a held lock must surface as an error, not a silent wait"
        assert isinstance(raised[0], TimeoutError), (
            "expected TimeoutError, got %r" % (raised[0],))
        assert "busy" in str(raised[0]).lower()
    finally:
        store._pg_lock.release()


# ── 2. the lock is ALWAYS given back ───────────────────────────────────────
def test_the_lock_is_released_after_a_successful_statement():
    store = _history_store()
    store.backend = "postgresql"
    store._pg_connection = lambda: _FakeConn([])

    store._run("SELECT 1", fetch="all")

    assert store._pg_lock.acquire(blocking=False), (
        "the shared link lock was not released after a normal call")
    store._pg_lock.release()


def test_the_lock_is_released_even_when_the_statement_raises():
    """A lock leaked on the error path poisons EVERY later caller.

    This is the failure mode a `with` block would have hidden and a bare
    `try/finally` written in the wrong order would still leak: the first
    broken statement must not leave the shared link permanently unusable.
    """
    store = _history_store()

    class _Exploding:
        closed = False
        broken = False

        def cursor(self):
            raise RuntimeError("connection reset")

        def close(self):
            pass

    store._pg_connection = lambda: _Exploding()

    with pytest.raises(RuntimeError):
        store._run("SELECT 1", fetch="all")

    assert store._pg_lock.acquire(blocking=False), (
        "the shared link lock leaked on the error path")
    store._pg_lock.release()


# ── 3. the reconnect is bounded, and a dead link is detected ───────────────
def test_connect_is_bounded_and_sets_a_statement_timeout(monkeypatch):
    """`psycopg.connect` must never be called without `connect_timeout`.

    The sibling Postgres connection in this module already passed
    `connect_timeout=5`; the one on the dashboard's hot path did not, so a
    slow or unreachable database could pin the caller — and the lock — for as
    long as the OS was willing to wait for a TCP handshake.

    The session `statement_timeout` is the second half: it makes the SERVER
    cancel a runaway statement, so the lock comes back without the client
    having to notice.
    """
    import psycopg
    from integrations import dashboard_store as ds

    calls = {}

    def fake_connect(url, **kwargs):
        calls["url"] = url
        calls["kwargs"] = kwargs
        return _FakeConn(calls.setdefault("log", []))

    monkeypatch.setattr(psycopg, "connect", fake_connect)
    monkeypatch.setattr(ds, "PG_CONNECT_TIMEOUT_SECONDS", 5)
    monkeypatch.setattr(ds, "PG_STATEMENT_TIMEOUT_MS", 8000)

    store = _history_store()
    store.backend = "postgresql"
    store.database_url = "postgresql://fake/db"
    store._pg_conn = None

    conn = store._pg_connection()

    assert calls["url"] == "postgresql://fake/db"
    assert calls["kwargs"].get("connect_timeout") == 5, (
        "connect_timeout is missing — an unreachable database can pin the lock")
    assert conn.commits == 1, "the statement_timeout was never committed"
    sql = " ".join(s for s, _ in calls["log"])
    assert "statement_timeout" in sql, (
        "no session statement_timeout — a runaway statement holds the lock")
    assert "8000" in str(calls["log"]), "the configured timeout was not applied"


def test_a_broken_but_not_closed_connection_is_rebuilt(monkeypatch):
    """`closed` alone is not a liveness check.

    A connection the server reaped, or one on a socket that died without a
    FIN, reports `closed == False` and then blocks on the next statement. It
    must be treated as unusable so the link is rebuilt instead.
    """
    from integrations import dashboard_store as ds

    zombie = _FakeConn([])
    zombie.closed = False
    zombie.broken = True          # the state `closed` cannot see
    fresh = _FakeConn([])
    made = []

    store = _history_store()
    store.backend = "postgresql"
    store.database_url = "postgresql://fake/db"
    store._pg_conn = zombie

    def fake_connect(url, **kwargs):
        made.append(url)
        return fresh

    import psycopg
    monkeypatch.setattr(psycopg, "connect", fake_connect)

    assert store._pg_connection() is fresh, (
        "a broken link was reused instead of replaced")
    assert made, "no reconnect was attempted for a broken link"


# ── 4. the defaults themselves must stay safe ──────────────────────────────
def test_the_default_bounds_are_finite_and_below_the_server_timeout():
    """The bounds only help if they are smaller than the layers above them.

    gunicorn is configured `--timeout 120` (Procfile and Dockerfile). A bound
    at or above that would still let the worker be killed before the caller
    ever gives up, which is the 502 this work exists to prevent.
    """
    from integrations import dashboard_store as ds

    assert 0 < ds.PG_CONNECT_TIMEOUT_SECONDS <= 30
    assert 0 < ds.PG_STATEMENT_TIMEOUT_MS <= 60_000
    assert 0 < ds.PG_LOCK_WAIT_SECONDS <= 60

    # Worst case for one statement: reconnect, then the statement itself, then
    # the wait for the lock. It must leave room inside gunicorn's 120s.
    worst = (ds.PG_CONNECT_TIMEOUT_SECONDS
             + ds.PG_STATEMENT_TIMEOUT_MS / 1000.0
             + ds.PG_LOCK_WAIT_SECONDS)
    assert worst < 120, (
        "worst-case single statement (%.1fs) can outlive gunicorn's 120s "
        "timeout, so the worker can still be killed" % worst)
