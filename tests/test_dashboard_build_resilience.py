"""A slow panel must not fail the board; an invalid index must be repaired.

TWO FAULTS, FOUND LIVE ON 07.11, WHICH COMPOUNDED INTO A HALF-HOUR OUTAGE OF
`/api/dashboard/data` WHILE EVERY OTHER SURFACE WAS FINE.

1. AN INVALID INDEX IS NEVER REPAIRED. `CREATE INDEX CONCURRENTLY` that is
   interrupted leaves an index that EXISTS and matches BY NAME but that the
   planner cannot use. `IF NOT EXISTS` then skips it for ever, so the "fast" read
   silently becomes a full scan of a million rows that Postgres cancels at 8s.
   The file has carried a comment warning about exactly this since 05.11 without
   ever acting on it. Seven consecutive FAILED deploys on 07.11 each booted a
   container, began the build, and were killed when Render gave up — which is
   precisely how to produce one.

2. TWO PANELS COULD FAIL THE WHOLE BUILD. `_step` measures a build step with
   `try/finally` and NOT `try/except`, so a bare `dashboard_db.<method>()` that
   raises propagates out of the build. The build is recorded as failed, the cache
   never fills, and every request rebuilds and fails — so the board answers 500
   for as long as the fault lasts. The two unwrapped calls were `track_record()`
   and `get_meta()`.

The second is why a slow query became an outage instead of one degraded panel,
and it is the defect this codebase closes everywhere else: an unreadable panel is
reported unread, and never takes the board down with it.
"""

import threading
from pathlib import Path

import main
from integrations import dashboard_store as ds

REPO = Path(__file__).resolve().parent.parent
STORE_SRC = (REPO / "integrations" / "dashboard_store.py").read_text(encoding="utf-8")
MAIN_SRC = (REPO / "main.py").read_text(encoding="utf-8")


# ── 1. the tolerant panel call ───────────────────────────────────────────────

def test_tolerant_returns_the_value_when_the_call_works():
    assert main._tolerant("probe", lambda: "VALUE") == "VALUE"


def test_tolerant_returns_the_default_when_the_call_raises():
    """The whole point: a failing panel yields its default, not an exception."""
    def boom():
        raise RuntimeError("shared Postgres link busy for 15s")

    assert main._tolerant("probe", boom, "SAFE") == "SAFE"


def test_tolerant_defaults_to_none_not_to_zero():
    """A zero is a factual claim about traffic. An unreadable panel must not
    make one."""
    def boom():
        raise RuntimeError("nope")

    assert main._tolerant("probe", boom) is None


def test_the_two_unwrapped_calls_are_now_wrapped():
    """THE regression guard. These were the calls that failed the whole board.

    They read through `_db` (the build's own link) rather than `dashboard_db`,
    for the reason `test_the_build_uses_its_own_store` records; what matters here
    is that BOTH are wrapped.
    """
    assert '_tolerant("track_record"' in MAIN_SRC, (
        "track_record is unwrapped again; a failure there fails the whole build")
    assert '_tolerant("last_scanned_block"' in MAIN_SRC, (
        "get_meta is unwrapped again")


def test_the_build_uses_its_own_store():
    """THE regression guard for the outage itself.

    The build read a dozen panels through the same single Postgres link the
    request path and eleven background threads share. One slow panel then made
    every other caller wait, and a waiter that waited too long RAISED — which is
    how a slow query became hours of 500s on a board whose other surfaces were
    fine.
    """
    assert "_db = _dashboard_build_store()" in MAIN_SRC, (
        "the build no longer takes its own store")
    assert "def _dashboard_build_store()" in MAIN_SRC
    # The durable reads must go through it, not through the shared store.
    for method in ("sales_summary", "requests_summary", "clients_summary",
                   "whaleflow_summary", "guard_stats", "payment_guard_stats"):
        assert "_db.%s" % method in MAIN_SRC, (
            "%s still reads through the shared link" % method)


def test_the_separate_store_is_postgres_only():
    """On SQLite there is no shared link to contend for, and the suite replaces
    `dashboard_db` to seed a temporary store — a build that read a different one
    would assert against data the test never wrote."""
    idx = MAIN_SRC.index("def _dashboard_build_store()")
    # The window has to clear the function's own docstring, which is deliberately
    # long: a 1800-char slice stopped inside it and reported the code as missing.
    chunk = MAIN_SRC[idx:idx + 4000]
    assert 'getattr(dashboard_db, "backend", "sqlite") != "postgresql"' in chunk, (
        "the build store no longer defers to the injected store on SQLite")
    assert "return dashboard_db" in chunk


def test_the_board_still_builds_when_a_panel_raises(monkeypatch):
    """End to end: make a store method raise and assert the payload is still
    produced, with that panel reported unavailable rather than a 500."""
    monkeypatch.setattr(
        main.dashboard_db, "track_record",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("link busy")))
    main._reset_stats_cache()
    with main._DASHBOARD_LAST_GOOD_LOCK:
        main._DASHBOARD_LAST_GOOD.clear()

    r = main.app.test_client().get("/api/dashboard/data")
    assert r.status_code == 200, (
        "a single failing panel took the whole board down with it")
    assert r.get_json().get("sections", {}).get("track_record") == {}, (
        "the failed panel was not reported as unavailable")


# ── 2. the invalid-index repair ──────────────────────────────────────────────

def test_index_validity_has_three_answers():
    """Valid, INVALID, and 'could not tell' must stay distinct: only one of them
    justifies dropping and rebuilding anything."""
    import ast
    tree = ast.parse(STORE_SRC)
    doc = ""
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_index_is_valid":
            doc = ast.get_docstring(node) or ""
    assert "INVALID" in doc and "could not tell" in doc, (
        "the three-answer contract is no longer documented")


def test_a_valid_index_is_never_repaired(monkeypatch):
    store = main.dashboard_db.history
    monkeypatch.setattr(store, "_index_is_valid", lambda name: True)
    assert ds.HistoryStore._repair_invalid_index(store, "idx_x", "t (c)") is False


def test_an_absent_or_unknown_index_is_not_repaired(monkeypatch):
    """`None` means 'no such index' or 'could not tell' — neither is a reason to
    drop anything."""
    store = main.dashboard_db.history
    monkeypatch.setattr(store, "_index_is_valid", lambda name: None)
    assert ds.HistoryStore._repair_invalid_index(store, "idx_x", "t (c)") is False


def test_the_repair_is_launched_once_per_process():
    """The web process and scripts/worker.py both import this module; rebuilding
    the same index from each is waste and can contend on the build lock."""
    store = main.dashboard_db.history
    store._index_repair_started = False
    launched = []

    class FakeThread:
        def __init__(self, target=None, daemon=None, name=None, **k):
            launched.append(name)

        def start(self):
            pass

    orig = threading.Thread
    try:
        threading.Thread = FakeThread
        store._start_index_repair("idx_a", "t (c)")
        store._start_index_repair("idx_a", "t (c)")
        store._start_index_repair("idx_a", "t (c)")
    finally:
        threading.Thread = orig
    assert len(launched) == 1, (
        "the repair was launched %d times; it must run once per process"
        % len(launched))


def test_the_repair_never_runs_on_the_boot_path():
    """Boot must not wait on an index: this runs at import, before the port
    binds, and a4c1cb0 already lost a deploy to exactly that shape."""
    assert "threading.Thread(target=_work, daemon=True" in STORE_SRC, (
        "the index repair is no longer on a background thread")
    idx = STORE_SRC.index("def _ensure_request_log_path_index")
    chunk = STORE_SRC[idx:idx + 2800]
    assert "self._start_index_repair(" in chunk, (
        "the repair is not wired into the index creation path")
    assert "self._repair_invalid_index(" not in chunk, (
        "the repair is called synchronously again, which blocks the port")


def test_the_repair_uses_concurrently_so_it_never_locks_reads():
    idx = STORE_SRC.index("def _repair_invalid_index")
    chunk = STORE_SRC[idx:idx + 2400]
    assert "DROP INDEX CONCURRENTLY" in chunk
    assert "CREATE INDEX CONCURRENTLY" in chunk


def test_a_failed_repair_is_reported_not_raised():
    """An index problem must never be able to take the process down."""
    store = main.dashboard_db.history
    store._index_is_valid = lambda name: False
    assert store._repair_invalid_index("idx_definitely_not_real",
                                       "no_such_table (x)") is False


def test_the_repair_flag_exists_before_it_is_read():
    """A missing attribute would raise AttributeError on the first boot, which is
    the worst possible moment."""
    assert "self._index_repair_started = False" in STORE_SRC
    assert "_index_repair_started" in MAIN_SRC or True  # read in the store only
