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
    under a different name."""
    purposes = re.findall(r'_isolated_store\("([^"]+)"\)', MAIN_SRC)
    purposes += re.findall(r'isolated\("([^"]+)"\)', TELEGRAM_SRC)
    assert purposes, "no isolated stores found at all"
    duplicates = [p for p in set(purposes) if purposes.count(p) > 1]
    assert not duplicates, "these purposes are used twice: %r" % duplicates


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
