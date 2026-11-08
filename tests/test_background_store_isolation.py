"""Every background loop must own its Postgres link, or say why not.

THE CLASS OF DEFECT THIS PINS, and why it is a class rather than a bug.

`HistoryStore._run` serialises every caller behind ONE lock on ONE connection.
Any background job that is slow, scheduled, or network-bound and leans on that
link turns every request in the process into a waiter — and a waiter that waits
too long is REFUSED, not merely delayed.

On 08.11.2026 that produced hours of a service which answered HTTP and recorded
nothing. It was fixed FIVE times, each time for a different job, and the log named
a different holder each time it was read:

    holder=whaleflow-scan            held=45s
    holder=kristo-sentinel           held=289s
    holder=dashboard-scan            held=200s
    (plus the board build, and request-log retention)

Fixing them one at a time treats holders. This test treats the queue: it reads the
thread list out of `main.py`, looks at what each loop actually calls, and fails
when a loop does durable work on the shared store without a stated reason.

WHY AN ALLOWLIST AND NOT A BLANKET BAN. Two kinds of call are correct on the
shared link and banning them would break the design:

  * `get_meta` / `set_meta` are the LOCAL SQLite file, a different lock entirely;
  * `_organism_beat` / `_organism_journal_note` ARE the shared link's health
    signal — writing a heartbeat through an isolated link would report the wrong
    connection's health, which is worse than useless.
"""

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
MAIN_SRC = (REPO / "main.py").read_text(encoding="utf-8")
TELEGRAM_SRC = (REPO / "services" / "telegram_sales.py").read_text(
    encoding="utf-8")

#: Threads whose loops must not use the shared durable store, with the reason
#: they were isolated. A new name here must come with a real explanation.
EXPECTED_ISOLATED = {
    "dashboard-refresh": "dashboard-build",
    "dashboard-scan": "dashboard-scan",
    "whaleflow-scan": "whaleflow-scan",
}

#: Calls that are LEGITIMATELY on the shared link, each for a stated reason.
SHARED_BY_DESIGN = {
    "get_meta",                    # local SQLite, a different lock
    "set_meta",                    # local SQLite
    "_organism_beat",              # deliberately the shared link's health signal
    "_organism_journal_note",      # same
}


def _thread_targets():
    """Every `threading.Thread(target=X, name=Y)` in main.py."""
    out = []
    for m in re.finditer(
            r"threading\.Thread\(\s*target=([A-Za-z_][A-Za-z0-9_.]*)[^)]*?"
            r"name=[\"']([^\"']+)[\"']", MAIN_SRC, re.S):
        out.append((m.group(2), m.group(1)))
    return out


def _function_body(name):
    lines = MAIN_SRC.splitlines()
    start = None
    for i, line in enumerate(lines):
        if line.startswith("def %s(" % name):
            start = i
            break
    if start is None:
        return None
    body = [lines[start]]
    i = start + 1
    while i < len(lines) and (lines[i].startswith((" ", "\t"))
                              or not lines[i].strip()):
        body.append(lines[i])
        i += 1
    return "\n".join(body)


def test_the_thread_list_is_readable():
    """If this fails the extraction broke, and every assertion below is vacuous."""
    targets = _thread_targets()
    assert len(targets) >= 10, (
        "only %d threads were found; the extraction is wrong, not the code"
        % len(targets))


def test_no_unexplained_loop_uses_the_shared_durable_store():
    """THE guard. A loop doing durable work on the shared link must be isolated
    or explain itself in `SHARED_BY_DESIGN`."""
    offenders = []
    for thread_name, target in _thread_targets():
        body = _function_body(target)
        if body is None:
            continue
        calls = set(re.findall(r"dashboard_db\.([a-z_]+)", body))
        calls -= SHARED_BY_DESIGN
        if calls:
            offenders.append((thread_name, target, sorted(calls)))
    assert not offenders, (
        "these background loops still do durable work on the SHARED Postgres "
        "link, which is how a slow loop refuses every request in the process: "
        "%r" % offenders)


def test_the_known_isolated_loops_really_are_isolated():
    """Belt and braces: each must bind its own store, not merely avoid the name."""
    body = _function_body("_dashboard_scan_loop")
    assert body and '_isolated_store("dashboard-scan")' in body

    body = _function_body("_whaleflow_scan_loop")
    assert body and "_whaleflow_store()" in body

    body = _function_body("_request_log_retention")
    assert body and '_isolated_store("request-log-retention")' in body


def test_every_isolated_purpose_is_namespaced_uniquely():
    """Two jobs sharing an 'isolated' store would just be the shared link again
    under a different name.

    Note what this does NOT assert: that each purpose gets its OWN pool. It must
    not — see `test_the_pool_count_is_bounded_below_the_connection_limit`.
    """
    purposes = re.findall(r'_isolated_store\("([^"]+)"\)', MAIN_SRC)
    purposes += re.findall(r'isolated\("([^"]+)"\)', TELEGRAM_SRC)
    assert purposes, "no isolated stores found at all"
    duplicates = [p for p in set(purposes) if purposes.count(p) > 1]
    assert not duplicates, "these purposes are used twice: %r" % duplicates


def test_the_pool_count_is_bounded_below_the_connection_limit():
    """THE CEILING, and the mistake that found it.

    One Postgres connection per background job looked tidy. Every pool IS a
    connection, this database is the smallest plan (`0.1c-256mb`) with a low
    connection limit, and eight purposes across two processes is ~16 connections
    — close enough to the ceiling that opening one more blocks.

    Measured: with four pools `/api/dashboard/data` answered in 0.30s. With eight
    it hung on its FIRST step and `last_build_timings_ms` stayed EMPTY.
    """
    import main
    purposes = set(re.findall(r'_isolated_store\("([^"]+)"\)', MAIN_SRC))
    purposes |= set(re.findall(r'isolated\("([^"]+)"\)', TELEGRAM_SRC))
    pools = {main._ISOLATION_POOLS.get(p, p) for p in purposes}
    assert len(pools) <= 5, (
        "%d pools for %d purposes: each pool is a Postgres connection and the "
        "database limit is low. Share a pool deliberately instead of adding one."
        % (len(pools), len(purposes)))


def test_the_board_build_keeps_a_pool_of_its_own():
    """The read path must not queue behind a background job, whatever else is
    sharing. This is the one allocation that is not negotiable."""
    import main
    assert main._ISOLATION_POOLS.get("dashboard-build") == "dashboard-build"
    for other in ("whaleflow-scan", "dashboard-scan", "sentinel",
                  "telegram-sales", "request-log-retention", "reorg-watch"):
        assert main._ISOLATION_POOLS.get(other) != "dashboard-build", (
            "%s shares the board build's pool" % other)


def test_an_unknown_purpose_gets_its_own_pool():
    """So a new job is never SILENTLY sharing with one that is already busy —
    sharing has to be a deliberate entry in `_ISOLATION_POOLS`."""
    import main
    assert main._ISOLATION_POOLS.get("a-brand-new-job", "a-brand-new-job") == \
        "a-brand-new-job"


def test_the_telegram_loop_does_not_use_the_shared_store():
    """The fifth job. A long-poll loop that is always running is always a
    candidate to be holding the link everything else waits on."""
    assert 'isolated("telegram-sales")' in TELEGRAM_SRC
    # The only surviving reference is the documented fallback inside `_store`.
    uses = TELEGRAM_SRC.count("main_module.dashboard_db")
    assert uses <= 1, (
        "telegram_sales still reaches the shared store in %d places" % uses)


def test_retention_is_not_on_the_shared_link():
    """The heaviest single thing done to that database: a first run DELETEs over
    a million rows in batches of 5000 — the pass's own comment calls it "200+
    round trips", and every one of them used to take the request path's link."""
    body = _function_body("_request_log_retention")
    assert body is not None
    assert "dashboard_db.purge_old_requests()" not in body, (
        "retention is back on the shared link")


# ── use before binding, which isolation introduced ──────────────────────────

def test_every_isolated_store_is_bound_before_it_is_used():
    """THE BUG THIS PINS, found in the live log on 08.11:

        Dashboard retro scan failed: cannot access local variable 'scan_db'

    Redirecting a loop onto an isolated store means introducing a LOCAL NAME, and
    the binding was placed below the retro scan — which is the pass that finds
    ON-CHAIN SALES. It raised on every cycle, was caught, and was logged as
    "incremental will catch up", which it then could not do either. The money
    scan was dead while the log said it was merely behind.

    General shape, not one function: any local a loop binds must be bound before
    the line that first reads it.
    """
    import ast

    tree = ast.parse(MAIN_SRC)
    offenders = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef):
            continue
        bound = []
        for sub in ast.walk(node):
            if isinstance(sub, ast.Assign) and isinstance(sub.value, ast.Call):
                fn = sub.value.func
                name = getattr(fn, "id", None) or getattr(fn, "attr", None)
                if name in ("_isolated_store", "_whaleflow_store", "isolated"):
                    for tgt in sub.targets:
                        if isinstance(tgt, ast.Name):
                            bound.append((tgt.id, sub.lineno))
        if not bound:
            continue
        for var, bind_line in bound:
            for sub in ast.walk(node):
                if not isinstance(sub, ast.Attribute) or sub.lineno >= bind_line:
                    continue
                base = sub.value
                if isinstance(base, ast.Name) and base.id == var:
                    offenders.append(
                        "%s: `%s` read at line %d but bound at line %d"
                        % (node.name, var, sub.lineno, bind_line))
                    break
    assert not offenders, (
        "a local store is read before it is bound — it raises NameError on every "
        "cycle, and the loop's own except swallows it: %r" % offenders)


def test_no_module_level_thread_starts_before_its_names_exist():
    """THE BUG THIS PINS, measured locally on 08.11:

        Request-log retention failed (non-fatal): name '_isolated_store' is not
        defined

    `_request_log_retention` and `_detect_reorgs` were started with
    `threading.Thread(...).start()` at MODULE level. Both call `_isolated_store`,
    defined ~1,400 lines further down, so the thread could run before Python had
    created the name. Both raised NameError, both were caught by their own
    `except`, and both reported themselves as "non-fatal" — while retention is the
    fix for the 07.11 OOM and reorg detection guards recorded sales.

    A module-level thread start must therefore come AFTER every module-level
    definition it can reach. Anything that needs to run early belongs in
    `_start_background_threads()`, which runs once the module is importable.
    """
    import ast

    tree = ast.parse(MAIN_SRC)
    # Every module-level def/assignment name, with the line it is bound on.
    bound = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef,
                             ast.ClassDef)):
            bound[node.name] = node.lineno
        elif isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    bound[t.id] = node.lineno

    offenders = []
    for node in tree.body:
        # A module-level `threading.Thread(...)` statement, or a `.start()` on it
        for sub in ast.walk(node):
            if not (isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute)
                    and sub.func.attr in ("start", "Thread")):
                continue
            for name_node in ast.walk(sub):
                if not isinstance(name_node, ast.Name):
                    continue
                where = bound.get(name_node.id)
                if where is not None and where > node.lineno:
                    offenders.append(
                        ("line %d starts a thread naming `%s`, defined at line %d"
                         % (node.lineno, name_node.id, where)))
                    break
    # De-duplicate: one line can be reported by both the Thread and start walks.
    offenders = sorted(set(offenders))
    assert not offenders, (
        "a module-level thread start races the definition it needs, and the "
        "NameError lands in that thread's own except: %r" % offenders)
