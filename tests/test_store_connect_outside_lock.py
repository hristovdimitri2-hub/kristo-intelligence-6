"""Opening a Postgres link must never happen while holding the statement lock.

THE OUTAGE THIS PINS, measured on 08.11.2026.

The service answered HTTP, `/health` said `ok`, and the paid routes returned
correct 402s — while it did NO WORK AT ALL. `last_scanned_block` was frozen,
`request_log` stopped growing, and all six organism blocks read `not_reached`
for ever.

The cause was one line of ordering. `_run` called `_pg_connection()` INSIDE the
`_pg_lock` critical section, and `_pg_connection` may open a connection. libpq's
`connect_timeout` bounds the TCP connect but NOT DNS resolution, so a slow
resolver hangs that call indefinitely. Held under the statement lock, a single
hang is permanent and total: every later caller waits out the lock timeout and is
refused.

It was invisible for two reasons, and both are worth keeping in mind:

  * the writes that failed are swallowed on purpose — a heartbeat and a request
    log are telemetry, and telemetry must not be able to fail the thing it
    describes — so nothing but a `debug` line recorded it;
  * `/health` reads the freshest evidence from process MEMORY when the store
    cannot answer, so the surface used to judge health was the one surface that
    could not see the fault.

The pattern gave itself away: writes flowed for a few minutes after each boot and
then stopped for ever, because the connection only needs OPENING after something
invalidates the existing one.
"""

from pathlib import Path

import main

REPO = Path(__file__).resolve().parent.parent
STORE_SRC = (REPO / "integrations" / "dashboard_store.py").read_text(encoding="utf-8")
MAIN_SRC = (REPO / "main.py").read_text(encoding="utf-8")


def _run_body() -> str:
    idx = STORE_SRC.index("    def _run(self, sql: str")
    end = STORE_SRC.index("\n    def _ensure_schema", idx)
    return STORE_SRC[idx:end]


def test_the_connection_is_opened_before_the_statement_lock_is_taken():
    """THE regression guard. If this inverts, one hang is permanent again."""
    body = _run_body()
    connect_at = body.index("conn = self._pg_connection()")
    lock_at = body.index("self._pg_lock.acquire(")
    assert connect_at < lock_at, (
        "the connection is opened INSIDE the statement lock again: a hanging "
        "connect would wedge every caller for ever, which is the 08.11 outage")


def test_the_connection_is_no_longer_opened_inside_the_critical_section():
    """Belt and braces: the old call site must be gone from the inner try."""
    body = _run_body()
    inner = body[body.index("self._pg_lock.acquire("):]
    assert "conn = self._pg_connection()" not in inner, (
        "a second call to _pg_connection() sits inside the critical section")


def test_connection_creation_has_its_own_lock():
    """Opening a link must not serialise behind the statement lock."""
    idx = STORE_SRC.index("    def _pg_connection(self)")
    end = STORE_SRC.index("    def _pg_open(self", idx)
    chunk = STORE_SRC[idx:end]
    assert "with self._pg_conn_lock:" in chunk, (
        "connection creation is not guarded by its own lock")
    # Only CODE matters: the docstring legitimately DISCUSSES `_pg_lock` while
    # explaining why this ordering is required.
    code = "\n".join(
        line for line in chunk.splitlines()
        if not line.strip().startswith("#"))
    for pattern in ("self._pg_lock.acquire", "with self._pg_lock",
                    "self._pg_lock.release"):
        assert pattern not in code, (
            "connection creation touches the statement lock: %s" % pattern)


def test_the_two_locks_are_different_objects():
    store = main.dashboard_db.history
    assert store._pg_conn_lock is not store._pg_lock


def test_a_failed_statement_closes_our_own_connection_not_the_shared_field():
    """Since the link is opened outside the lock, another thread may already have
    replaced the field by the time we fail; closing theirs would break a
    connection somebody is about to use."""
    body = _run_body()
    assert "dead = conn" in body, (
        "the failure path no longer captures the connection it actually used")
    assert "if self._pg_conn is conn:" in body, (
        "the shared field is cleared unconditionally, which can discard another "
        "thread's working connection")


def test_the_broken_connection_is_closed_AFTER_the_lock_is_released():
    """THE wedge, and why its fix is an ordering.

    On a socket that died without a FIN — `SSL error: unexpected eof while
    reading`, measured 08.11 — `close()` itself can block. Called from inside the
    critical section it holds the one link every other caller is waiting on, so
    the service kept answering HTTP while recording nothing, and every write
    failed with `busy for 2s`.
    """
    body = _run_body()
    release_at = body.index("self._pg_lock.release()")
    close_at = body.index("dead.close()")
    assert close_at > release_at, (
        "the broken connection is closed BEFORE the lock is released again, "
        "which lets a blocking close wedge every caller")


def test_the_lock_timeout_names_the_holder():
    """A bare "busy" told us nothing for hours; the holder and how long it has
    held must be in the message."""
    body = _run_body()
    assert "_pg_lock_owner" in body
    assert "holder=%s" in body


def test_a_heartbeat_round_trips():
    """The organism's write path must work end to end, because it is the first
    thing that breaks when the shared link cannot be written."""
    from services import organism as org
    store = main.dashboard_db
    assert org.beat(store, "delivery", "ok", "round-trip probe") is True
    v = org.last_verdict(store, "delivery")
    assert v.get("verdict") == "ok"
    assert v.get("at") is not None


# ── 3. an isolated store must not repeat the schema DDL ─────────────────────

def test_an_isolated_store_skips_the_schema_pass():
    """A store opened only to own a connection must not run the DDL.

    THE DEFECT THIS PINS, measured 08.11. `_isolated_store` created a
    `DashboardStore`, whose `HistoryStore.__init__` runs the full schema pass.
    That pass is not free on this database — the plan is `0.1c-256mb`, and
    `CREATE TABLE IF NOT EXISTS` takes an ACCESS EXCLUSIVE lock even when the
    table already exists. With the board build AND the whale scan each opening an
    isolated store at boot, three schema passes contended on those locks, and the
    board's FIRST build step then waited behind them and never completed:

        /api/dashboard/data  ->  503, and `last_build_timings_ms` stayed EMPTY

    Empty timings is the tell: not one step had finished.
    """
    idx = MAIN_SRC.index('store = DashboardStore(DASHBOARD_DB_FILE')
    chunk = MAIN_SRC[idx - 900:idx + 200]
    assert "ensure_schema=False" in chunk, (
        "the isolated store runs the schema pass again, which stalls the board")
    assert "ensure_schema: bool = True" in STORE_SRC, (
        "HistoryStore no longer accepts the flag")
    assert "if ensure_schema:" in STORE_SRC, (
        "HistoryStore ignores the flag and always runs the DDL")
